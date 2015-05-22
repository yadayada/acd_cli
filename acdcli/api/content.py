import http.client as http
import os
import json
import io
import mimetypes
from collections import OrderedDict
import logging
from urllib.parse import quote_plus

try:
    from requests_toolbelt import MultipartEncoder
except ImportError:
    from acdcli.bundled.encoder import MultipartEncoder

from .common import *

FS_RW_CHUNK_SZ = 1024 * 64

PARTIAL_SUFFIX = '.__incomplete'
CHUNK_SIZE = 500 * 1024 ** 2  # basically arbitrary
CHUNK_MAX_RETRY = 5
CONSECUTIVE_DL_LIMIT = CHUNK_SIZE

logger = logging.getLogger(__name__)


def tee_open(path: str, **kwargs):
    f = open(path, 'rb')
    return TeeBufferedReader(f, **kwargs)


class TeeBufferedReader(object):
    """Creates proxy buffered reader object that allows callbacks on read operations."""
    def __init__(self, file: io.BufferedReader, callbacks: list=None):
        self._file = file
        self._callbacks = callbacks

    def __getattr__(self, item):
        try:
            return object.__getattr__(item)
        except AttributeError:
            return getattr(self._file, item)

    def read(self, ln=-1):
        ln = ln if ln in (0, -1) else FS_RW_CHUNK_SZ
        chunk = self._file.read(ln)
        if self._callbacks:
            for callback in self._callbacks:
                callback(chunk)
        return chunk


def create_folder(name: str, parent=None) -> dict:
    # params = {'localId' : ''}
    body = {'kind': 'FOLDER', 'name': name}
    if parent:
        body['parents'] = [parent]
    body_str = json.dumps(body)

    acc_codes = [http.CREATED]

    r = BackOffRequest.post(get_metadata_url() + 'nodes', acc_codes=acc_codes, data=body_str)

    if r.status_code not in acc_codes:
        raise RequestError(r.status_code, r.text)

    return r.json()


def _get_mimetype(file_name: str) -> str:
    mt = mimetypes.guess_type(file_name)[0]
    return mt if mt else 'application/octet-stream'


def upload_file(file_name: str, parent: str=None, read_callbacks=None, deduplication=False) -> dict:
    params = {} if deduplication else {'suppress': 'deduplication'}

    basename = os.path.basename(file_name)
    metadata = {'kind': 'FILE', 'name': basename}
    if parent:
        metadata['parents'] = [parent]
    mime_type = _get_mimetype(basename)
    f = tee_open(file_name, callbacks=read_callbacks)

    # basename is ignored
    m = MultipartEncoder(fields=OrderedDict([('metadata', json.dumps(metadata)),
                                             ('content', (quote_plus(basename), f, mime_type))]))

    ok_codes = [http.CREATED]
    r = BackOffRequest.post(get_content_url() + 'nodes', params=params, data=m,
                            acc_codes=ok_codes, stream=True, headers={'Content-Type': m.content_type})

    if r.status_code not in ok_codes:
        raise RequestError(r.status_code, r.text)
    return r.json()


def overwrite_file(node_id: str, file_name: str, read_callbacks=None, deduplication=False) -> dict:
    params = {} if deduplication else {'suppress': 'deduplication'}

    basename = os.path.basename(file_name)
    mime_type = _get_mimetype(basename)
    f = tee_open(file_name, callbacks=read_callbacks)

    # basename is ignored
    m = MultipartEncoder(fields={('content', (quote_plus(basename), f, mime_type))})

    r = BackOffRequest.put(get_content_url() + 'nodes/' + node_id + '/content', params=params, data=m,
                           stream=True, headers={'Content-Type': m.content_type})

    if r.status_code not in OK_CODES:
        raise RequestError(r.status_code, r.text)

    return r.json()


# local name be valid (must be checked prior to call)
def download_file(node_id: str, basename: str, dirname: str=None, **kwargs):
    """kwargs:
    write_callbacks (list[function])
    resume (bool=True): whether to resume if partial file exists
    """
    dl_path = basename
    if dirname:
        dl_path = os.path.join(dirname, basename)
    part_path = dl_path + PARTIAL_SUFFIX
    offset = 0

    resume = kwargs.get('resume', True)
    if resume and os.path.isfile(part_path):
        with open(part_path, 'ab') as f:
            trunc_pos = os.path.getsize(part_path) - 1 - FS_RW_CHUNK_SZ
            f.truncate(trunc_pos if trunc_pos >= 0 else 0)

        write_callbacks = kwargs.get('write_callbacks')
        if write_callbacks:
            with open(part_path, 'rb') as f:
                for chunk in iter(lambda: f.read(FS_RW_CHUNK_SZ), b''):
                    for rcb in write_callbacks:
                        rcb(chunk)

        f = open(part_path, 'ab')
    else:
        f = open(part_path, 'wb')
    offset = f.tell()

    chunked_download(node_id, f, offset=offset, **kwargs)

    f.close()
    if os.path.isfile(dl_path):
        logger.info('Deleting existing file "%s".' % dl_path)
        os.remove(dl_path)
    os.rename(part_path, dl_path)


@catch_conn_exception
def chunked_download(node_id: str, file: io.BufferedWriter, **kwargs):
    """Keyword args:
    offset (int): byte offset -- start byte for ranged request
    length (int): total length, equal to end - 1
    write_callbacks (list[function])
    """
    ok_codes = [http.PARTIAL_CONTENT]

    write_callbacks = kwargs.get('write_callbacks', [])

    length = kwargs.get('length', 100 * 1024 ** 4)

    chunk_start = kwargs.get('offset', 0)
    retries = 0
    while chunk_start < length:
        chunk_end = chunk_start + CHUNK_SIZE - 1
        if chunk_end >= length:
            chunk_end = length - 1

        if retries >= CHUNK_MAX_RETRY:
            raise RequestError(RequestError.CODE.FAILED_SUBREQUEST,
                               '[acd_cli] Downloading chunk failed multiple times.')
        r = BackOffRequest.get(get_content_url() + 'nodes/' + node_id + '/content', stream=True,
                               acc_codes=ok_codes,
                               headers={'Range': 'bytes=%d-%d' % (chunk_start, chunk_end)})

        logger.debug('Range %d-%d' % (chunk_start, chunk_end))
        # this should only happen at the end of unknown-length downloads
        if r.status_code == http.REQUESTED_RANGE_NOT_SATISFIABLE:
            logger.debug('Invalid byte range requested %d-%d' % (chunk_start, chunk_end))
            break
        if r.status_code not in ok_codes:
            r.close()
            retries += 1
            logging.debug('Chunk [%d-%d], retry %d.' % (chunk_start, chunk_end, retries))
            continue

        curr_ln = 0
        # connection exceptions occur here
        for chunk in r.iter_content(chunk_size=FS_RW_CHUNK_SZ):
            if chunk:  # filter out keep-alive new chunks
                file.write(chunk)
                file.flush()
                for wcb in write_callbacks:
                    wcb(chunk)
                curr_ln += len(chunk)
        chunk_start += CHUNK_SIZE
        retries = 0
        r.close()

    return

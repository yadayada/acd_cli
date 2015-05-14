import http.client as http
import sys
import os
import json
import io
import mimetypes
from collections import OrderedDict
import logging

try:
    from requests_toolbelt import MultipartEncoder
except ImportError:
    from acdcli.bundled.encoder import MultipartEncoder

from . import oauth
from .common import *
from ..utils import progress

FS_RW_CHUNK_SZ = 1024 * 64

PARTIAL_SUFFIX = '.__incomplete'
CHUNK_SIZE = 50 * 1024 ** 2  # basically arbitrary
CHUNK_MAX_RETRY = 5
CONSECUTIVE_DL_LIMIT = CHUNK_SIZE

logger = logging.getLogger(__name__)


def tee_open(path: str, **kwargs):
    f = open(path, 'rb')
    return TeeBufferedReader(f, **kwargs)


class TeeBufferedReader(object):
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


def upload_file(file_name: str, parent: str=None, read_callback=None, deduplication=False) -> dict:
    params = {} if deduplication else {'suppress': 'deduplication'}

    metadata = {'kind': 'FILE', 'name': os.path.basename(file_name)}
    if parent:
        metadata['parents'] = [parent]

    pgo = progress.Progress(os.path.getsize(file_name))
    mime_type = _get_mimetype(file_name)
    callbacks = [pgo.new_chunk]
    if read_callback:
        callbacks.append(read_callback)

    f = tee_open(file_name, callbacks=callbacks)
    m = MultipartEncoder(fields=OrderedDict([('metadata', json.dumps(metadata)),
                                             ('content', (file_name, f, mime_type))]))

    ok_codes = [http.CREATED]
    r = BackOffRequest.post(get_content_url() + 'nodes', params=params, data=m,
                            acc_codes=ok_codes, stream=True, headers={'Content-Type': m.content_type})

    if r.status_code not in ok_codes:
        raise RequestError(r.status_code, r.text)
    return r.json()


def overwrite_file(node_id: str, file_name: str, read_callback=None, deduplication=False) -> dict:
    params = {} if deduplication else {'suppress': 'deduplication'}

    pgo = progress.Progress(os.path.getsize(file_name))

    callbacks = [pgo.new_chunk]
    if read_callback:
        callbacks.append(read_callback)

    mime_type = _get_mimetype(file_name)
    f = tee_open(file_name, callbacks=callbacks)
    m = MultipartEncoder(fields={('content', ('name=' + file_name, f, 'Content-Type=' + mime_type))})

    r = BackOffRequest.put(get_content_url() + 'nodes/' + node_id + '/content', params=params, data=m,
                           stream=True, headers={'Content-Type': m.content_type})

    if r.status_code not in OK_CODES:
        raise RequestError(r.status_code, r.text)

    return r.json()


# local name be valid (must be checked prior to call)
def download_file(node_id: str, basename: str, dirname: str=None, **kwargs):
    """kwargs: write_callback, resume: bool=True"""
    dl_path = basename
    if dirname:
        dl_path = os.path.join(dirname, basename)
    part_path = dl_path + PARTIAL_SUFFIX
    offset = 0

    if ('resume' not in kwargs or kwargs['resume']) \
            and os.path.isfile(part_path):
        with open(part_path, 'wb') as f:
            trunc_pos = os.path.getsize(part_path) - 1 - FS_RW_CHUNK_SZ
            f.truncate(trunc_pos if trunc_pos >= 0 else 0)

        write_callback = kwargs.get('write_callback')
        if write_callback:
            with open(part_path, 'rb') as f:
                while True:
                    chunk = f.read(FS_RW_CHUNK_SZ)
                    if not chunk:
                        break
                    write_callback(chunk)

        f = open(part_path, 'ab')
    else:
        f = open(part_path, 'wb')
    offset = f.tell()

    chunked_download(node_id, f, offset=offset, **kwargs)

    if os.path.isfile(dl_path):
        logger.info('Deleting existing file "%s".' % dl_path)
        os.remove(dl_path)
    os.rename(part_path, dl_path)


@catch_conn_exception
def chunked_download(node_id: str, file: io.BufferedWriter, **kwargs):
    """Keyword args:
    offset: byte offset
    length: total length, equal to end - 1
    write_callback
    """
    ok_codes = [http.PARTIAL_CONTENT]

    write_callback = kwargs.get('write_callback', None)

    length = kwargs.get('length', 100 * 1024 ** 4)

    pgo = progress.Progress()
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
                if write_callback:
                    write_callback(chunk)
                curr_ln += len(chunk)
                pgo.print_progress(length, curr_ln + chunk_start)
        chunk_start += CHUNK_SIZE
        retries = 0
        r.close()

    return
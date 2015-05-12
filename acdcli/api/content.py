import http.client as http
import sys
import os
import json
import pycurl
import io
from io import BytesIO
import logging
from requests.exceptions import ConnectionError

try:
    from requests.packages.urllib3.exceptions import ReadTimeoutError
except ImportError:
    class ReadTimeoutError(Exception):
        pass

from . import oauth
from .common import *
from ..utils import progress

FS_RW_CHUNK_SZ = 8192

PARTIAL_SUFFIX = '.__incomplete'
CHUNK_SIZE = 50 * 1024 ** 2  # basically arbitrary
CHUNK_MAX_RETRY = 5
CONSECUTIVE_DL_LIMIT = CHUNK_SIZE

logger = logging.getLogger(__name__)


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


# file must be valid, readable
def upload_file(file_name: str, parent: str=None, read_callback=None, deduplication=False) -> dict:
    params = ''
    if not deduplication:
        params = '?suppress=deduplication'  # suppresses 409 response

    metadata = {'kind': 'FILE', 'name': os.path.basename(file_name)}
    if parent:
        metadata['parents'] = [parent]

    buffer = BytesIO()
    c = pycurl.Curl()
    c.setopt(c.URL, get_content_url() + 'nodes' + params)
    c.setopt(c.HTTPHEADER, oauth.get_auth_header_curl())
    c.setopt(c.WRITEDATA, buffer)
    c.setopt(c.HTTPPOST, [('metadata', json.dumps(metadata)),
                          ('content', (c.FORM_FILE, file_name.encode(sys.getfilesystemencoding())))])
    pgo = progress.Progress()
    c.setopt(c.NOPROGRESS, 0)
    c.setopt(c.PROGRESSFUNCTION, pgo.curl_ul_progress)

    ok_codes = [http.CREATED]
    try:
        BackOffRequest.perform(c, acc_codes=ok_codes)
    except pycurl.error as e:
        raise RequestError(e.args[0], e.args[1])

    status = c.getinfo(pycurl.HTTP_CODE)
    # c.close()
    print()  # break progress line

    body = buffer.getvalue().decode('utf-8')

    if status not in ok_codes:
        # print('Uploading "%s" failed.' % file_name)
        raise RequestError(status, body)

    return json.loads(body)


def overwrite_file(node_id: str, file_name: str, read_callback=None, deduplication=False) -> dict:
    params = ''
    if not deduplication:
        params = '?suppress=deduplication'  # suppresses 409 response

    buffer = BytesIO()
    c = pycurl.Curl()
    c.setopt(c.URL, get_content_url() + 'nodes/' + node_id + '/content' + params)
    c.setopt(c.WRITEDATA, buffer)
    c.setopt(c.HTTPPOST, [('content', (c.FORM_FILE, file_name.encode(sys.getfilesystemencoding())))])
    c.setopt(c.CUSTOMREQUEST, 'PUT')
    pgo = progress.Progress()
    c.setopt(c.NOPROGRESS, 0)
    c.setopt(c.PROGRESSFUNCTION, pgo.curl_ul_progress)

    try:
        BackOffRequest.perform(c)
    except pycurl.error as e:
        raise RequestError(e.args[0], e.args[1])

    status = c.getinfo(pycurl.HTTP_CODE)
    # c.close()
    print()  # break progress line

    body = buffer.getvalue().decode('utf-8')

    if status not in OK_CODES:
        # print('Overwriting "%s" failed.' % file_name)
        raise RequestError(status, body)

    return json.loads(body)


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

    total_ln = kwargs.get('length', -1)

    if 0 <= total_ln < CONSECUTIVE_DL_LIMIT and offset == 0:
        consecutive_download(node_id, f, **kwargs)
    else:
        chunked_download(node_id, f, offset=offset, **kwargs)

    if os.path.isfile(dl_path):
        os.remove(dl_path)
    os.rename(part_path, dl_path)


# to be deprecated later
def consecutive_download(node_id: str, file: io.BufferedWriter, **kwargs):
    """Keyword args: write_callback"""
    r = BackOffRequest.get(get_content_url() + 'nodes/' + node_id + '/content', stream=True)
    if r.status_code not in OK_CODES:
        raise RequestError(r.status_code, r.text)

    write_callback = kwargs.get('write_callback', None)

    total_ln = int(r.headers.get('content-length'))
    length = kwargs.get('length', None)
    if length and total_ln != length:
        logging.info('Length mismatch: argument %d, content %d' % (length, total_ln))

    pgo = progress.Progress()
    curr_ln = 0
    try:
        for chunk in r.iter_content(chunk_size=FS_RW_CHUNK_SZ):
            if chunk:  # filter out keep-alive new chunks
                file.write(chunk)
                file.flush()
                if write_callback:
                    write_callback(chunk)
                curr_ln += len(chunk)
                pgo.print_progress(total_ln, curr_ln)
    except (ConnectionError, ReadTimeoutError) as e:
        raise RequestError(RequestError.CODE.READ_TIMEOUT, '[acd_cli] Timeout. ' + e.__str__())
    print()  # break progress line
    r.close()
    return


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

        try:
            curr_ln = 0
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
        except (ConnectionError, ReadTimeoutError) as e:
            file.close()
            raise RequestError(RequestError.CODE.READ_TIMEOUT, '[acd_cli] Timeout. ' + e.__str__())

    print()  # break progress line
    return
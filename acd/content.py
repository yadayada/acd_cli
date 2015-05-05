import http.client as http
import sys
import os
import time
import json
import pycurl
from io import BytesIO
import logging
from requests.exceptions import ConnectionError
try:
    from requests.packages.urllib3.exceptions import ReadTimeoutError
except ImportError:
    pass

from acd.common import *
from acd import oauth
import utils

logger = logging.getLogger(__name__)


class Progress:
    """line progress indicator"""
    start = None

    # noinspection PyUnusedLocal
    def curl_ul_progress(self, total_dl_sz, downloaded, total_ul_sz, uploaded):
        self.print_progress(total_ul_sz, uploaded)

    def print_progress(self, total_sz, current):
        if not self.start:
            self.start = time.time()

        if total_sz:
            duration = time.time() - self.start
            if duration:
                speed = current / duration
            else:
                speed = 0
            if total_sz:
                rate = float(current) / total_sz
            else:
                rate = 1
            percentage = round(rate * 100, ndigits=2)
            completed = "#" * int(percentage / 3)
            spaces = " " * (33 - len(completed))
            sys.stdout.write('\r[%s%s] %s%% of %s, %s'
                             % (completed, spaces, ('%4.1f' % percentage).rjust(5),
                                (utils.file_size_str(total_sz)).rjust(9), (utils.speed_str(speed)).rjust(10)))
            sys.stdout.flush()


def create_folder(name, parent=None):
    # params = {'localId' : ''}
    body = {'kind': 'FOLDER', 'name': name}
    if parent:
        body['parents'] = [parent]
    body_str = json.dumps(body)

    acc_codes = [http.CREATED]

    r = BackOffRequest.post(get_metadata_url() + 'nodes', acc_codes=acc_codes, data=body_str)

    if r.status_code not in acc_codes:
        # print('Error creating folder "%s"' % name)
        raise RequestError(r.status_code, r.text)

    return r.json()


# file must be valid, readable
def upload_file(file_name: str, parent=None):
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
                          ('content', (c.FORM_FILE, file_name.encode('UTF-8')))])
    pgo = Progress()
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


def overwrite_file(node_id, file_name):
    params = '?suppress=deduplication'  # suppresses 409 response

    buffer = BytesIO()
    c = pycurl.Curl()
    c.setopt(c.URL, get_content_url() + 'nodes/' + node_id + '/content' + params)
    c.setopt(c.WRITEDATA, buffer)
    c.setopt(c.HTTPPOST, [('content', (c.FORM_FILE, file_name.encode('UTF-8')))])
    c.setopt(c.CUSTOMREQUEST, 'PUT')
    pgo = Progress()
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
# existing file will be overwritten
def download_file(node_id, local_name, local_path=None, write_callback=None):
    r = BackOffRequest.get(get_content_url() + 'nodes/' + node_id, stream=True)
    if r.status_code not in OK_CODES:
        # print('Downloading %s failed.' % node_id)
        raise RequestError(r.status_code, r.text)

    dl_path = local_name
    if local_path:
        dl_path = os.path.join(local_path, local_name)
    pgo = Progress()
    with open(dl_path, 'wb') as f:
        total_ln = int(r.headers.get('content-length'))
        curr_ln = 0
        try:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:  # filter out keep-alive new chunks
                    f.write(chunk)
                    f.flush()
                    if write_callback:
                        write_callback(chunk)
                    curr_ln += len(chunk)
                    pgo.print_progress(total_ln, curr_ln)
        except (ConnectionError, ReadTimeoutError) as e:
            raise RequestError(RequestError.CODE.READ_TIMEOUT, '[acd_cli] Timeout. ' + e.__str__())
    print()  # break progress line
    r.close()
    return  # no response text?

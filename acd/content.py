from http import client as http
import http.client as http
import requests
import json
import sys
import os
import pycurl
from io import BytesIO

from acd import oauth
from acd.common import RequestError
import utils


def progress(total_to_download, total_downloaded, total_to_upload, total_uploaded):
    if total_to_upload:
        rate = float(total_uploaded) / total_to_upload
        percentage = round(rate * 100, ndigits=2)
        completed = "#" * int(percentage / 2)
        spaces = " " * (50 - len(completed))
        sys.stdout.write('[%s%s] %05.2f%% of %s\r'
                         % (completed, spaces, percentage, utils.file_size_str(total_to_upload)))
        sys.stdout.flush()


def create_folder(name, parent=None):
    # params = {'localId' : ''}
    body = {'kind': 'FOLDER', 'name': name}
    if parent:
        body['parents'] = [parent]
    body_str = json.dumps(body)

    r = requests.post(oauth.get_metadata_url() + 'nodes', headers=oauth.get_auth_header(), data=body_str)

    if r.status_code != http.CREATED:
        print('Error creating folder "%s"' % name)
        raise RequestError(r.status_code, r.text)

    return r.json()


# file must be valid, readable
def upload_file(file_name, parent=None):
    params = '?suppress=deduplication'  # suppresses 409 response

    metadata = {'kind': 'FILE', 'name': os.path.split(file_name)[1]}
    if parent:
        metadata['parents'] = [parent]

    buffer = BytesIO()
    c = pycurl.Curl()
    c.setopt(c.URL, oauth.get_content_url() + 'nodes' + params)
    c.setopt(c.HTTPHEADER, ['Authorization: ' + oauth.get_auth_token()])
    c.setopt(c.WRITEDATA, buffer)
    c.setopt(c.HTTPPOST, [('metadata', json.dumps(metadata)),
                          ('content', (c.FORM_FILE, file_name))])
    c.setopt(c.NOPROGRESS, 0)
    c.setopt(c.PROGRESSFUNCTION, progress)
    # c.setopt(c.VERBOSE, 1)
    c.perform()

    status = c.getinfo(pycurl.HTTP_CODE)
    c.close()
    print()  # break progress line

    body = buffer.getvalue().decode('utf-8')

    if status != http.CREATED:
        print('Uploading "%s" failed.' % file_name)
        raise RequestError(status, body)

    return json.loads(body)


# TODO
def overwrite_file(file_name, node_id):
    pass


# local name must checked prior to call
# existing file will be overwritten
def download_file(id, local_name):
    r = requests.get(oauth.get_content_url() + 'nodes/' + id, headers=oauth.get_auth_header(), stream=True)
    if r.status_code != http.OK:
        print('Downloading %s failed.' % id)
    with open(local_name, 'wb') as f:
        total_ln = int(r.headers.get('content-length'))
        curr_ln = 0
        for chunk in r.iter_content(chunk_size=8192):
            if chunk:  # filter out keep-alive new chunks
                f.write(chunk)
                f.flush()
                curr_ln += len(chunk)
                progress(0, 0, total_ln, curr_ln)
    print()  # break progress line
    return  # no response text?
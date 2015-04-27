import os
import json
import requests
import urllib
import time
import logging
import webbrowser

logger = logging.getLogger(__name__)

settings_path = ''
OAUTH_DATA_FILE = 'oauth_data'
ENDPOINT_DATA_FILE = 'endpoint_data'

# json key names
EXP_IN_KEY = 'expires_in'
ACC_TOKEN_KEY = 'access_token'
REFR_TOKEN_KEY = 'refresh_token'

# custom key added by appspot app
EXP_TIME_KEY = 'exp_time'

oauth_data_path = lambda: os.path.join(settings_path, OAUTH_DATA_FILE)
endpoint_data_path = lambda: os.path.join(settings_path, ENDPOINT_DATA_FILE)

oauth_data = {}
endpoint_data = {}

get_metadata_url = lambda: endpoint_data['metadataUrl']
get_content_url = lambda: endpoint_data['contentUrl']

# remote request URLs
APPSPOT_URL = 'https://tensile-runway-92512.appspot.com/'

AMZ_ENDPOINT_REQ_URL = 'https://drive.amazonaws.com/drive/v1/account/endpoint'
ENDPOINT_VAL_TIME = 259200


def oauth_data_changed():
    with open(oauth_data_path(), 'w') as oa:
        json.dump(oauth_data, oa, indent=4, sort_keys=True)


def endpoint_data_changed():
    with open(endpoint_data_path(), 'w') as ep:
        json.dump(endpoint_data, ep, indent=4, sort_keys=True)


def init(path=''):
    global settings_path
    settings_path = path

    try:
        get_data()
        return True
    except:
        raise


def get_data():
    global oauth_data
    global endpoint_data

    curr_time = time.time()

    if not os.path.isfile(oauth_data_path()):
        webbrowser.open_new_tab(APPSPOT_URL)
        input('A browser tab will been opened. Please follow the link, accept the request '
              'and save the plaintext response data into a file called "%s" in the application directory. '
              'Then, press a key to continue.\n' % OAUTH_DATA_FILE)

        if not os.path.isfile(oauth_data_path()):
            raise Exception

    with open(oauth_data_path()) as oa:
        oauth_data = json.load(oa)
        if EXP_TIME_KEY not in oauth_data:
            treat_auth_token(oauth_data, curr_time)
            oauth_data_changed()

    if not os.path.isfile(endpoint_data_path()):
        get_endpoints()
    else:
        with open(endpoint_data_path()) as ep:
            endpoint_data = json.load(ep)
        if time.time() > endpoint_data[EXP_TIME_KEY]:
            get_endpoints()


def get_auth_token():
    if time.time() > oauth_data[EXP_TIME_KEY]:
        refresh_auth_token()
    return "Bearer " + oauth_data[ACC_TOKEN_KEY]


def get_auth_header():
    return {'Authorization': get_auth_token()}


def get_endpoints():
    global endpoint_data

    r = requests.get(AMZ_ENDPOINT_REQ_URL, headers=get_auth_header())
    try:
        e = r.json()
        e[EXP_TIME_KEY] = time.time() + ENDPOINT_VAL_TIME
        endpoint_data = e
        endpoint_data_changed()
    except ValueError as e:
        print('Invalid JSON.')
        raise e


def treat_auth_token(token, curr_time):
    """Adds expiration time to Amazon OAUTH dict"""
    if not token:
        return
    try:
        token[EXP_TIME_KEY] = curr_time + token[EXP_IN_KEY] - 120
    except KeyError as e:
        print('Fatal error: Token key not found.')
        raise e


def refresh_auth_token():
    global oauth_data

    print('Refreshing authentication token.')

    ref = {REFR_TOKEN_KEY: oauth_data[REFR_TOKEN_KEY]}
    t = time.time()

    response = requests.post(APPSPOT_URL, data=ref)
    try:
        r = response.json()
    except ValueError as e:
        print('Refresh error: Invalid JSON.')
        raise e

    treat_auth_token(r, t)
    oauth_data = r
    oauth_data_changed()

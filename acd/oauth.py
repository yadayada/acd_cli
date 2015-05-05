import os
import json
import requests
import time
import logging
import webbrowser

__all__ = ['init', 'get_auth_header', 'get_auth_header_curl']

logger = logging.getLogger(__name__)

cache_path = ''
OAUTH_DATA_FILE = 'oauth_data'

# json key names
EXP_IN_KEY = 'expires_in'
ACC_TOKEN_KEY = 'access_token'
REFR_TOKEN_KEY = 'refresh_token'

EXP_TIME_KEY = 'exp_time'

oauth_data_path = lambda: os.path.join(cache_path, OAUTH_DATA_FILE)
oauth_data = {}

# remote request URLs
APPSPOT_URL = 'https://tensile-runway-92512.appspot.com/'


def _oauth_data_changed():
    with open(oauth_data_path(), 'w') as oa:
        json.dump(oauth_data, oa, indent=4, sort_keys=True)


def init(path) -> bool:
    global cache_path
    cache_path = path

    try:
        _get_data()
        return True
    except:
        raise


def _get_data():
    global oauth_data

    curr_time = time.time()

    if not os.path.isfile(oauth_data_path()):
        webbrowser.open_new_tab(APPSPOT_URL)
        input('A browser tab will have/be opened at %s.\nPlease accept the request ' % APPSPOT_URL +
              'and save the plaintext response data into a file called "%s"' % OAUTH_DATA_FILE +
              ' in the directory "%s".\nThen, press a key to continue.\n' % cache_path)

        if not os.path.isfile(oauth_data_path()):
            logger.error('File "%s" not found.' % OAUTH_DATA_FILE)
            raise Exception

    with open(oauth_data_path()) as oa:
        oauth_data = json.load(oa)
        if EXP_TIME_KEY not in oauth_data:
            _treat_auth_token(oauth_data, curr_time)
            _oauth_data_changed()


def _get_auth_token() -> str:
    if time.time() > oauth_data[EXP_TIME_KEY]:
        _refresh_auth_token()
    return "Bearer " + oauth_data[ACC_TOKEN_KEY]


def get_auth_header() -> dict:
    return {'Authorization': _get_auth_token()}


def get_auth_header_curl() -> list:
    return ['Authorization: ' + _get_auth_token()]


def _treat_auth_token(token, curr_time):
    """Adds expiration time to Amazon OAuth dict"""
    if not token:
        return
    try:
        token[EXP_TIME_KEY] = curr_time + token[EXP_IN_KEY] - 120
        logger.info('Auth token expiration ')
    except KeyError as e:
        logger.critical('Fatal error: Token key "%s" not found.' % EXP_IN_KEY)
        raise e


def _refresh_auth_token():
    global oauth_data

    logger.info('Refreshing authentication token.')

    ref = {REFR_TOKEN_KEY: oauth_data[REFR_TOKEN_KEY]}
    t = time.time()

    response = requests.post(APPSPOT_URL, data=ref)
    try:
        r = response.json()
    except ValueError as e:
        logger.critical('Refresh error: Invalid JSON.')
        raise e

    _treat_auth_token(r, t)
    oauth_data = r
    _oauth_data_changed()

import os
import json
import requests
import time
import logging
import webbrowser
import datetime

__all__ = ('init', 'get_auth_header')

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


def init(path: str) -> bool:
    global cache_path
    cache_path = path

    _load_data()
    return True


def _load_data():
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
        o = oa.read()
    oauth_data = _validate(o)
    if EXP_TIME_KEY not in oauth_data:
        _treat_auth_token(oauth_data, curr_time)
        _write_oauth_data()
    else:
        _get_auth_token(reload=False)


def _get_auth_token(reload=True) -> str:
    global oauth_data
    if time.time() > oauth_data[EXP_TIME_KEY]:
        logger.info('Token expired at %s.' % datetime.datetime.fromtimestamp(oauth_data[EXP_TIME_KEY]).isoformat(' '))

        # if multiple instances are running, check for updated file
        if reload:
            with open(oauth_data_path()) as oa:
                o = oa.read()
            oauth_data = _validate(o)

        if time.time() > oauth_data[EXP_TIME_KEY]:
            _refresh_auth_token()
        else:
            logger.info('Externally updated token found in oauth file.')
    return "Bearer " + oauth_data[ACC_TOKEN_KEY]


def get_auth_header() -> dict:
    return {'Authorization': _get_auth_token()}


def _treat_auth_token(token: str, curr_time: float):
    """Adds expiration time to OAuth dict"""
    if not token:
        return
    try:
        token[EXP_TIME_KEY] = curr_time + token[EXP_IN_KEY] - 120
        logger.info('New token expires at %s.' % datetime.datetime.fromtimestamp(token[EXP_TIME_KEY]).isoformat(' '))
    except KeyError as e:
        logger.critical('Fatal error: Token key "%s" not found.' % EXP_IN_KEY)
        raise e


def _refresh_auth_token():
    """:raises RequestError"""
    global oauth_data

    logger.info('Refreshing authentication token.')

    ref = {REFR_TOKEN_KEY: oauth_data[REFR_TOKEN_KEY]}
    t = time.time()

    from .common import RequestError

    try:
        response = requests.post(APPSPOT_URL, data=ref)
    except ConnectionError as e:
        logger.critical('Error refreshing authentication token.')
        raise RequestError(RequestError.CODE.CONN_EXCEPTION, e.__str__())

    if response.status_code != requests.codes.ok:
        raise RequestError(RequestError.CODE.REFRESH_FAILED,
                           'Error refreshing authentication token: %s' % requests.text)

    r = _validate(response.text)

    _treat_auth_token(r, t)
    oauth_data = r
    _write_oauth_data()


def _validate(oauth: str):
    """:throws: RequestError"""
    from .common import RequestError
    try:
        o = json.loads(oauth)
        o[ACC_TOKEN_KEY]
        o[EXP_IN_KEY]
        o[REFR_TOKEN_KEY]
        return o
    except (ValueError, KeyError) as e:
        logger.critical('Invalid authentication token: Invalid JSON or missing key.')
        raise RequestError(RequestError.CODE.REFRESH_FAILED, e.__str__())


def _write_oauth_data():
    """Called to dump (treated) OAuth dict to file as JSON."""

    with open(oauth_data_path(), 'w') as oa:
        json.dump(oauth_data, oa, indent=4, sort_keys=True)
import os
import time
import json
import http.client as http
import random
from time import sleep
import logging
import requests
from threading import Lock, local
import re

from requests.exceptions import ConnectionError

try:
    from requests.exceptions import ReadTimeout as ReadTimeoutError
except ImportError:
    try:
        from requests.packages.urllib3.exceptions import ReadTimeoutError
    except ImportError:
        class ReadTimeoutError(Exception):
            pass

from . import oauth

__all__ = ('RequestError', 'BackOffRequest',
           'OK_CODES', 'init', 'catch_conn_exception', 'get_metadata_url', 'get_content_url')

logger = logging.getLogger(__name__)

# status codes that indicate request success
OK_CODES = [http.OK]

cache_path = ''
ENDPOINT_DATA_FILE = 'endpoint_data'
endpoint_data_path = lambda: os.path.join(cache_path, ENDPOINT_DATA_FILE)

# json key names
ACC_TOKEN_KEY = 'access_token'
REFR_TOKEN_KEY = 'refresh_token'

EXP_TIME_KEY = 'exp_time'

endpoint_data = {}
get_metadata_url = lambda: endpoint_data['metadataUrl']
get_content_url = lambda: endpoint_data['contentUrl']

AMZ_ENDPOINT_REQ_URL = 'https://drive.amazonaws.com/drive/v1/account/endpoint'
ENDPOINT_VAL_TIME = 259200

CONN_TIMEOUT = 30
IDLE_TIMEOUT = 60
REQUESTS_TIMEOUT = (CONN_TIMEOUT, IDLE_TIMEOUT) if requests.__version__ >= '2.4.0' else IDLE_TIMEOUT


def init(path='') -> bool:
    """Initializes OAuth and endpoints."""
    logger.info('Initializing ACD with path "%s".' % path)

    global cache_path
    cache_path = path

    return oauth.init(path) and _load_endpoints()


def _load_endpoints() -> bool:
    global endpoint_data

    if not os.path.isfile(endpoint_data_path()):
        endpoint_data = _get_endpoints()
    else:
        with open(endpoint_data_path()) as ep:
            endpoint_data = json.load(ep)
        if time.time() > endpoint_data[EXP_TIME_KEY]:
            logger.info('Endpoint data expired.')
            endpoint_data = _get_endpoints()

    return True


def _get_endpoints() -> dict:
    global endpoint_data
    r = requests.get(AMZ_ENDPOINT_REQ_URL, headers=oauth.get_auth_header())
    if r.status_code not in OK_CODES:
        logger.critical('Error getting endpoint data. Response: %s' % r.text)
        raise Exception

    try:
        e = r.json()
    except ValueError as e:
        logger.critical('Invalid JSON: "%s"' % r.text)
        raise e

    e[EXP_TIME_KEY] = time.time() + ENDPOINT_VAL_TIME
    endpoint_data = e

    try:
        get_metadata_url()
        get_content_url()
    except KeyError as e:
        logger.critical('Received invalid endpoint data.')
        raise e

    _save_endpoint_data()

    return e


def _save_endpoint_data():
    f = open(endpoint_data_path(), 'w')
    json.dump(endpoint_data, f, indent=4, sort_keys=True)
    f.flush()
    os.fsync(f.fileno())
    f.close()


class RequestError(Exception):
    class CODE(object):
        CONN_EXCEPTION = 1000
        FAILED_SUBREQUEST = 1002
        INCOMPLETE_RESULT = 1003
        REFRESH_FAILED = 1004
        INVALID_TOKEN = 1005

    def __init__(self, status_code: int, msg: str):
        self.status_code = status_code
        if msg:
            self.msg = msg
        else:
            self.msg = '[acd_cli] no body received.'

    def __str__(self):
        return 'RequestError: ' + str(self.status_code) + ', ' + self.msg


def catch_conn_exception(func):
    """Request connection exception decorator
    :raises RequestError"""

    def decorated(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (ConnectionError, ReadTimeoutError) as e:
            raise RequestError(RequestError.CODE.CONN_EXCEPTION, e.__str__())

    return decorated


class BackOffRequest(object):
    """Wrapper for requests that implements timed back-off algorithm
    https://developer.amazon.com/public/apis/experience/cloud-drive/content/best-practices
    Caution: this catches all connection errors and may stall for a long time.
    It is necessary to init this module before use.
    """

    __session = None
    __thr_local = local()
    __lock = Lock()
    __retries = 0
    __next_req = time.time()

    random.seed()

    @classmethod
    def _succeeded(cls):
        with cls.__lock:
            cls.__retries = 0
        cls.__calc_next()

    @classmethod
    def _failed(cls):
        with cls.__lock:
            cls.__retries += 1
        cls.__calc_next()

    @classmethod
    def __calc_next(cls):
        """Calculates minimal acceptable time for next request.
        Back-off time is in a range of seconds, depending on number of failed previous tries (r):
        [0,2^r], maximum interval [0,256]"""
        with cls.__lock:
            duration = random.random() * 2 ** min(cls.__retries, 8)
            cls.__next_req = time.time() + duration

    @classmethod
    def _wait(cls):
        with cls.__lock:
            duration = cls.__next_req - time.time()
        if duration > 5:
            logger.warning('Waiting %fs because of error(s).' % duration)
        logger.debug('Retry %i, waiting %fs' % (cls.__retries, duration))
        if duration > 0:
            sleep(duration)

    @classmethod
    @catch_conn_exception
    def _request(cls, type_, url: str, acc_codes: list, **kwargs) -> requests.Response:
        if not cls.__session:
            cls.__session = requests.session()
        cls._wait()

        with cls.__lock:
            headers = oauth.get_auth_header()
        if 'headers' in kwargs:
            headers = dict(headers, **(kwargs['headers']))
            del kwargs['headers']

        last_url = getattr(cls.__thr_local, 'last_req_url', None)
        if url == last_url:
            logger.debug('%s "%s"' % (type_, url))
        else:
            logger.info('%s "%s"' % (type_, url))
        if 'data' in kwargs.keys():
            logger.debug(kwargs['data'])

        cls.__thr_local.last_req_url = url

        if 'timeout' in kwargs:
            timeout = kwargs['timeout']
            del kwargs['timeout']
        else:
            timeout = REQUESTS_TIMEOUT

        try:
            r = cls.__session.request(type_, url, headers=headers, timeout=timeout, **kwargs)
        except:
            cls._failed()
            raise

        cls._succeeded() if r.status_code in acc_codes else cls._failed()
        return r

    # HTTP verbs

    @classmethod
    def get(cls, url, acc_codes=OK_CODES, **kwargs) -> requests.Response:
        return cls._request('GET', url, acc_codes, **kwargs)

    @classmethod
    def post(cls, url, acc_codes=OK_CODES, **kwargs) -> requests.Response:
        return cls._request('POST', url, acc_codes, **kwargs)

    @classmethod
    def patch(cls, url, acc_codes=OK_CODES, **kwargs) -> requests.Response:
        return cls._request('PATCH', url, acc_codes, **kwargs)

    @classmethod
    def put(cls, url, acc_codes=OK_CODES, **kwargs) -> requests.Response:
        return cls._request('PUT', url, acc_codes, **kwargs)

    @classmethod
    def delete(cls, url, acc_codes=OK_CODES, **kwargs) -> requests.Response:
        return cls._request('DELETE', url, acc_codes, **kwargs)

    @classmethod
    def paginated_get(cls, url: str, params: dict=None) -> list:
        """Gets node list in segments of 200."""
        if params is None:
            params = {}
        node_list = []

        while True:
            r = cls.get(url, params=params)
            if r.status_code not in OK_CODES:
                logger.error("Error getting node list.")
                raise RequestError(r.status_code, r.text)
            ret = r.json()
            node_list.extend(ret['data'])
            if 'nextToken' in ret.keys():
                params['startToken'] = ret['nextToken']
            else:
                if ret['count'] != len(node_list):
                    logger.warning(
                        'Expected %i items in page, received %i.' % (ret['count'], len(node_list)))
                break

        return node_list


def is_valid_id(id: str) -> bool:
    return bool(id) and len(id) == 22 and re.match('^[a-zA-Z0-9_-]*$', id)

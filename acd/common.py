import os
import time
import json
import http.client as http
import requests
from requests.exceptions import ConnectionError
import random
from time import sleep
import logging

from acd import oauth

__all__ = ('RequestError', 'BackOffRequest',
           'OK_CODES', 'init', 'get_metadata_url', 'get_content_url', 'paginated_get_request')

logger = logging.getLogger(__name__)

# status codes that indicate request success
OK_CODES = [http.OK]

settings_path = ''
ENDPOINT_DATA_FILE = 'endpoint_data'
endpoint_data_path = lambda: os.path.join(settings_path, ENDPOINT_DATA_FILE)

# json key names
EXP_IN_KEY = 'expires_in'
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


def init(path=''):
    global settings_path
    settings_path = path

    return oauth.init(path) and _load_endpoints()


def _load_endpoints():
    global endpoint_data

    if not os.path.isfile(endpoint_data_path()):
        endpoint_data = _get_endpoints()
    else:
        with open(endpoint_data_path()) as ep:
            endpoint_data = json.load(ep)
        if time.time() > endpoint_data[EXP_TIME_KEY]:
            endpoint_data = _get_endpoints()

    return True


def _get_endpoints():
    global endpoint_data
    r = requests.get(AMZ_ENDPOINT_REQ_URL, headers=oauth.get_auth_header())
    try:
        e = r.json()
        e[EXP_TIME_KEY] = time.time() + ENDPOINT_VAL_TIME
        endpoint_data = e
        _save_endpoint_data()
    except ValueError as e:
        logger.critical('Invalid JSON.')
        raise e

    return e


def _save_endpoint_data():
    with open(endpoint_data_path(), 'w') as ep:
        json.dump(endpoint_data, ep, indent=4, sort_keys=True)


class RequestError(Exception):
    def __init__(self, status_code, msg):
        self.status_code = status_code
        if msg:
            self.msg = msg
        else:
            self.msg = '{"message": "[acd_cli] no body received."}'

    def __str__(self):
        return 'RequestError: ' + str(self.status_code) + ', ' + self.msg


class BackOffRequest(object):
    """Wrapper for Requests/pycurl that implements timed back-off algorithm"""
    __session = None
    __retries = 0
    random.seed()

    @classmethod
    def _success(cls):
        cls.__retries = 0

    @classmethod
    def _failed(cls):
        cls.__retries += 1

    @classmethod
    def _wait(cls):
        duration = random.random() * 2 ** min(cls.__retries, 8)
        if duration > 5:
            logger.info('Waiting %f s because of error/s.' % duration)
        logger.info('Retry %i, waiting %f secs' % (cls.__retries, duration))
        sleep(duration)

    @classmethod
    def _request(cls, type_, url, acc_codes, **kwargs):
        if not cls.__session:
            cls.__session = requests.session()
        headers = oauth.get_auth_header()
        cls._wait()
        try:
            r = cls.__session.request(type_, url, headers=headers, timeout=(CONN_TIMEOUT, IDLE_TIMEOUT), **kwargs)
        except requests.exceptions.ConnectionError as e:
            raise RequestError(e.args[0].args[0], e.args[0].args[1])
        if r.status_code in acc_codes:
            cls._success()
        else:
            cls._failed()
        return r

    @classmethod
    def get(cls, url, acc_codes=OK_CODES, **kwargs):
        return cls._request('GET', url, acc_codes, **kwargs)

    @classmethod
    def post(cls, url, acc_codes=OK_CODES, **kwargs):
        return cls._request('POST', url, acc_codes, **kwargs)

    @classmethod
    def patch(cls, url, acc_codes=OK_CODES, **kwargs):
        return cls._request('PATCH', url, acc_codes, **kwargs)

    @classmethod
    def put(cls, url, acc_codes=OK_CODES, **kwargs):
        return cls._request('PUT', url, acc_codes, **kwargs)

    @classmethod
    def delete(cls, url, acc_codes=OK_CODES, **kwargs):
        return cls._request('DELETE', url, acc_codes, **kwargs)

    @classmethod
    def perform(cls, curl_obj, acc_codes=OK_CODES):
        cls._wait()
        if logger.getEffectiveLevel() == logging.DEBUG:
            curl_obj.setopt(curl_obj.VERBOSE, 1)
        curl_obj.setopt(curl_obj.HTTPHEADER, oauth.get_auth_header_curl())
        curl_obj.setopt(curl_obj.CONNECTTIMEOUT, CONN_TIMEOUT)
        curl_obj.setopt(curl_obj.LOW_SPEED_LIMIT, 1)
        curl_obj.setopt(curl_obj.LOW_SPEED_TIME, IDLE_TIMEOUT)
        curl_obj.perform()
        if curl_obj.getinfo(curl_obj.HTTP_CODE) in acc_codes:
            cls._success()
        else:
            cls._failed()


def paginated_get_request(url, params=None):
    if params is None:
        params = {}
    node_list = []

    while True:
        r = BackOffRequest.get(url, params=params)
        if r.status_code not in OK_CODES:
            logger.error("Error getting node list.")
            raise RequestError(r.status_code, r.text)
        ret = r.json()
        node_list.extend(ret['data'])
        if 'nextToken' in ret.keys():
            params['startToken'] = ret['nextToken']
        else:
            if ret['count'] != len(node_list):
                logger.warning('Expected {} items, received {}.'.format(ret['count'], len(node_list)))
            break

    return node_list
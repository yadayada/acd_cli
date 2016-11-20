import configparser
import logging
import os
import json
import requests
import time

from acdcli.utils.conf import get_conf

from . import oauth
from .backoff_req import BackOffRequest
from .common import *
from .account import AccountMixin
from .content import ContentMixin
from .metadata import MetadataMixin
from .trash import TrashMixin

logger = logging.getLogger(__name__)

_EXP_TIME_KEY = 'exp_time'
_AMZ_ENDPOINT_REQ_URL = 'https://drive.amazonaws.com/drive/v1/account/endpoint'

_SETTINGS_FILENAME = 'acd_client.ini'

_def_conf = configparser.ConfigParser()
_def_conf['endpoints'] = dict(filename='endpoint_data', validity_duration=259200)
_def_conf['transfer'] = dict(fs_chunk_size=128 * 1024, dl_chunk_size=500 * 1024 ** 2,
                             chunk_retries=1, connection_timeout=30, idle_timeout=60)
_def_conf['proxies'] = dict()


class ACDClient(AccountMixin, ContentMixin, MetadataMixin, TrashMixin):
    """Provides a client to the Amazon Cloud Drive RESTful interface."""

    def __init__(self, cache_path='', settings_path=''):
        """Initializes OAuth and endpoints."""

        self._conf = get_conf(settings_path, _SETTINGS_FILENAME, _def_conf)

        self.cache_path = cache_path
        logger.info('Initializing ACD with path "%s".' % cache_path)

        self.handler = oauth.create_handler(cache_path)

        self._endpoint_data = {}
        self._load_endpoints()

        requests_timeout = (self._conf.getint('transfer', 'connection_timeout'),
                            self._conf.getint('transfer', 'idle_timeout'))
        proxies = dict(self._conf['proxies'])

        self.BOReq = BackOffRequest(self.handler, requests_timeout, proxies)

    @property
    def _endpoint_data_path(self):
        return os.path.join(self.cache_path, self._conf['endpoints']['filename'])

    def _load_endpoints(self):
        """Tries to load endpoints from file and calls
        :meth:`_get_endpoints` on failure or if they are outdated."""

        if not os.path.isfile(self._endpoint_data_path):
            self._endpoint_data = self._get_endpoints()
        else:
            with open(self._endpoint_data_path) as ep:
                self._endpoint_data = json.load(ep)
            if time.time() > self._endpoint_data[_EXP_TIME_KEY]:
                logger.info('Endpoint data expired.')
                self._endpoint_data = self._get_endpoints()

    def _get_endpoints(self) -> dict:
        """Retrieves Amazon endpoints and saves them on success.

        :raises: ValueError if requests returned invalid JSON
        :raises: KeyError if endpoint data does not include expected keys"""

        r = requests.get(_AMZ_ENDPOINT_REQ_URL, auth=self.handler)
        if r.status_code not in OK_CODES:
            logger.critical('Error getting endpoint data. Response: %s' % r.text)
            raise Exception

        try:
            e = r.json()
        except ValueError as e:
            logger.critical('Invalid JSON: "%s"' % r.text)
            raise e

        e[_EXP_TIME_KEY] = time.time() + self._conf.getint('endpoints', 'validity_duration')
        self._endpoint_data = e

        try:
            self.metadata_url
            self.content_url
        except KeyError as e:
            logger.critical('Received invalid endpoint data.')
            raise e

        self._save_endpoint_data()

        return e

    def _save_endpoint_data(self):
        f = open(self._endpoint_data_path, 'w')
        json.dump(self._endpoint_data, f, indent=4, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
        f.close()

    @property
    def metadata_url(self):
        return self._endpoint_data['metadataUrl']

    @property
    def content_url(self):
        return self._endpoint_data['contentUrl']

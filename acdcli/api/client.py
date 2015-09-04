import os
import time
import json
import requests
import logging

from . import oauth
from .backoff_req import BackOffRequest
from .common import *
from .account import AccountMixin
from .content import ContentMixin
from .metadata import MetadataMixin
from .trash import TrashMixin

logger = logging.getLogger(__name__)

EXP_TIME_KEY = 'exp_time'

AMZ_ENDPOINT_REQ_URL = 'https://drive.amazonaws.com/drive/v1/account/endpoint'
ENDPOINT_VAL_TIME = 259200


class ACDClient(AccountMixin, ContentMixin, MetadataMixin, TrashMixin):
    _ENDPOINT_DATA_FILE = 'endpoint_data'

    def __init__(self, path=''):
        """Initializes OAuth and endpoints."""
        self.cache_path = path
        logger.info('Initializing ACD with path "%s".' % path)

        self.handler = oauth.create_handler(path)

        self._endpoint_data = {}
        self._load_endpoints()

        self.BOReq = BackOffRequest(self.handler.get_auth_header)

    @property
    def _endpoint_data_path(self):
        return os.path.join(self.cache_path, ACDClient._ENDPOINT_DATA_FILE)

    def _load_endpoints(self) -> bool:
        if not os.path.isfile(self._endpoint_data_path):
            self._endpoint_data = self._get_endpoints()
        else:
            with open(self._endpoint_data_path) as ep:
                self._endpoint_data = json.load(ep)
            if time.time() > self._endpoint_data[EXP_TIME_KEY]:
                logger.info('Endpoint data expired.')
                self._endpoint_data = self._get_endpoints()

        return True

    def _get_endpoints(self) -> dict:
        r = requests.get(AMZ_ENDPOINT_REQ_URL, headers=self.handler.get_auth_header())
        if r.status_code not in OK_CODES:
            logger.critical('Error getting endpoint data. Response: %s' % r.text)
            raise Exception

        try:
            e = r.json()
        except ValueError as e:
            logger.critical('Invalid JSON: "%s"' % r.text)
            raise e

        e[EXP_TIME_KEY] = time.time() + ENDPOINT_VAL_TIME
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

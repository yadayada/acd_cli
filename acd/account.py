import http.client as http
import requests
import logging

from acd import oauth
from acd.common import RequestError
import utils

logger = logging.getLogger(__name__)


class Usage(object):
    _dict = {}

    def __init__(self, _dict):
        self._dict = _dict

    @staticmethod
    def format_line(type, count, size):
        return '{0:10} {1:4}, {2:>6} {3:3}\n'.format(type + ':', count, *size)

    def __str__(self):
        _str = ''
        try:
            sum_count = 0
            sum_bytes = 0
            for key in self._dict.keys():
                if not isinstance(self._dict[key], dict):
                    continue
                sum_count += self._dict[key]['total']['count']
                sum_bytes += self._dict[key]['total']['bytes']
            _str = Usage.format_line('Documents', self._dict['doc']['total']['count'],
                                     utils.file_size_pair(self._dict['doc']['total']['bytes'])) + \
                   Usage.format_line('Other', self._dict['other']['total']['count'],
                                     utils.file_size_pair(self._dict['other']['total']['bytes'])) + \
                   Usage.format_line('Photos', self._dict['photo']['total']['count'],
                                     utils.file_size_pair(self._dict['photo']['total']['bytes'])) + \
                   Usage.format_line('Videos', self._dict['video']['total']['count'],
                                     utils.file_size_pair(self._dict['video']['total']['bytes'])) + \
                   Usage.format_line('Total', sum_count, utils.file_size_pair(sum_bytes))
        except KeyError:
            logger.warning('Invalid usage JSON string.')
        return _str


def get_account_usage():
    r = requests.get(oauth.get_metadata_url() + 'account/usage', headers=oauth.get_auth_header())
    if r.status_code != http.OK:
        raise RequestError(r.status_code, r.text)
    return Usage(r.json())


def get_quota():
    r = requests.get(oauth.get_metadata_url() + 'account/quota', headers=oauth.get_auth_header())
    if r.status_code != http.OK:
        raise RequestError(r.status_code, r.text)
    return r.json()

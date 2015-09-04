"""ACD account information"""

import logging
import collections
from .common import *

logger = logging.getLogger(__name__)


class _Usage(object):
    dict_ = {}

    def __init__(self, dict_):
        self.dict_ = dict_

    @staticmethod
    def format_line(type_, count, size):
        return '{0:10} {1:7}, {2:>6} {3:3}\n'.format(type_ + ':', count, *size)

    def __str__(self):
        str_ = ''
        try:
            sum_count = 0
            sum_bytes = 0
            for key in self.dict_.keys():
                if not isinstance(self.dict_[key], dict):
                    continue
                sum_count += self.dict_[key]['total']['count']
                sum_bytes += self.dict_[key]['total']['bytes']
            types = collections.OrderedDict([('Documents', 'doc'),
                                             ('Other', 'other'),
                                             ('Photos', 'photo'),
                                             ('Videos', 'video')])
            total_count = 0
            total_bytes = 0
            for desc in types:
                t = types[desc]
                type_usage = self.dict_[t]['total']
                type_count = type_usage['count']
                type_bytes = type_usage['bytes']
                total_count += type_count
                total_bytes += type_bytes
                str_ += _Usage.format_line(desc, type_count, _Usage.file_size_pair(type_bytes))
            str_ += _Usage.format_line('Total', total_count, _Usage.file_size_pair(total_bytes))
        except KeyError:
            logger.warning('Invalid usage JSON string.')
        return str_

    @staticmethod
    def file_size_pair(num: int, suffix='B') -> str:
        for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
            if abs(num) < 1024.0:
                return '%3.1f' % num, '%s%s' % (unit, suffix)
            num /= 1024.0
        return '%.1f' % num, '%s%s' % ('Yi', suffix)


class AccountMixin(object):
    def get_account_info(self) -> dict:
        """Gets account status [ACTIVE, ...?] and terms of use version."""
        r = self.BOReq.get(self.metadata_url + 'account/info')
        return r.json()

    def get_account_usage(self) -> str:
        r = self.BOReq.get(self.metadata_url + 'account/usage')
        if r.status_code not in OK_CODES:
            raise RequestError(r.status_code, r.text)
        return _Usage(r.json())

    def get_quota(self) -> dict:
        r = self.BOReq.get(self.metadata_url + 'account/quota')
        if r.status_code not in OK_CODES:
            raise RequestError(r.status_code, r.text)
        return r.json()

    def fs_sizes(self) -> tuple:
        """:returns tuple: total and free space"""
        q = self.get_quota()
        return q.get('quota', 0), q.get('available', 0)

import logging

from .common import *

logger = logging.getLogger(__name__)


class _Usage(object):
    dict_ = {}

    def __init__(self, dict_):
        self.dict_ = dict_

    @staticmethod
    def format_line(type_, count, size):
        return '{0:10} {1:4}, {2:>6} {3:3}\n'.format(type_ + ':', count, *size)

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
            str_ = _Usage.format_line('Documents', self.dict_['doc']['total']['count'],
                                     self.file_size_pair(self.dict_['doc']['total']['bytes'])) + \
                   _Usage.format_line('Other', self.dict_['other']['total']['count'],
                                     self.file_size_pair(self.dict_['other']['total']['bytes'])) + \
                   _Usage.format_line('Photos', self.dict_['photo']['total']['count'],
                                     self.file_size_pair(self.dict_['photo']['total']['bytes'])) + \
                   _Usage.format_line('Videos', self.dict_['video']['total']['count'],
                                     self.file_size_pair(self.dict_['video']['total']['bytes'])) + \
                   _Usage.format_line('Total', sum_count, self.file_size_pair(sum_bytes))
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


def get_account_info() -> dict:
    r = BackOffRequest.get(get_metadata_url() + 'account/info')
    return r.json()


def get_account_usage() -> str:
    r = BackOffRequest.get(get_metadata_url() + 'account/usage')
    if r.status_code not in OK_CODES:
        raise RequestError(r.status_code, r.text)
    return _Usage(r.json())


def get_quota() -> dict:
    r = BackOffRequest.get(get_metadata_url() + 'account/quota')
    if r.status_code not in OK_CODES:
        raise RequestError(r.status_code, r.text)
    return r.json()

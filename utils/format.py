import logging

logger = logging.getLogger(__name__)


# shamelessly copied from
# http://stackoverflow.com/questions/1094841/reusable-library-to-get-human-readable-version-of-file-size
def file_size_str(num: int, suffix='B') -> str:
    for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Yi', suffix)


def file_size_pair(num: int, suffix='B') -> str:
    for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
        if abs(num) < 1024.0:
            return '%3.1f' % num, '%s%s' % (unit, suffix)
        num /= 1024.0
    return '%.1f' % num, '%s%s' % ('Yi', suffix)


def speed_str(num: int, suffix='B', time_unit='s') -> str:
    for unit in ['', 'K', 'M', 'G', 'T', 'P', 'E', 'Z']:
        if abs(num) < 1000.0:
            return "%3.1f%s%s/%s" % (num, unit, suffix, time_unit)
        num /= 1000.0
    return "%.1f%s%s/%s" % (num, 'Y', suffix, time_unit)
import os
import hashlib
import threading
import logging

logger = logging.getLogger('utils')


class Hasher(object):
    """MD5 hash generator. Performs background hashing if file size threshold is exceeded."""

    BG_HASHING_THR = 500 * 1024 ** 2

    def __init__(self, file_name):
        self.file_name = file_name
        self.short_name = os.path.basename(file_name)
        self.md5 = None
        self.thr = None
        self.halt = False
        self.start_hashing()

    def stop(self):
        if self.thr:
            logger.info('Stopping hashing thread for "%s".' % self.short_name)
            self.halt = True
            self.thr.join()
            logger.info('Thread stopped.')

    def start_hashing(self):
        if os.path.getsize(self.file_name) > Hasher.BG_HASHING_THR:
            self.thr = threading.Thread(target=self.generate_md5_hash)
            logger.info('Starting background hashing of "%s"' % self.short_name)
            self.thr.start()
        else:
            self.generate_md5_hash()

    def get_result(self):
        if self.thr:
            self.thr.join()

        return self.md5

    def generate_md5_hash(self):
        hasher = hashlib.md5()
        with open(self.file_name, 'rb') as f:
            while True and not self.halt:
                chunk = f.read(1024 ** 2)
                if not chunk:
                    break
                hasher.update(chunk)

        if not self.halt:
            logger.info('MD5 of "%s" is %s' % (self.short_name, hasher.hexdigest()))
            self.md5 = hasher.hexdigest()


class IncrementalHasher():
    def __init__(self):
        self.hasher = hashlib.md5()

    def update(self, chunk):
        self.hasher.update(chunk)

    def get_result(self):
        return self.hasher.hexdigest()


# shamelessly copied from
# http://stackoverflow.com/questions/1094841/reusable-library-to-get-human-readable-version-of-file-size
def file_size_str(num, suffix='B'):
    for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Yi', suffix)


def file_size_pair(num, suffix='B'):
    for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
        if abs(num) < 1024.0:
            return '%3.1f' % num, '%s%s' % (unit, suffix)
        num /= 1024.0
    return '%.1f' % num, '%s%s' % ('Yi', suffix)


def speed_str(num, suffix='B', time_unit='s'):
    for unit in ['', 'K', 'M', 'G', 'T', 'P', 'E', 'Z']:
        if abs(num) < 1000.0:
            return "%3.1f%s%s/%s" % (num, unit, suffix, time_unit)
        num /= 1000.0
    return "%.1f%s%s/%s" % (num, 'Y', suffix, time_unit)
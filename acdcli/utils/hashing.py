import hashlib
import logging
import os
import threading

logger = logging.getLogger(__name__)


class Hasher(object):
    """MD5 hash generator. Performs background hashing starting with initialization if file size threshold is exceeded.
    Smaller file will be hashed synchronously if MD5 is requested by invoking get_result()."""

    BG_HASHING_THR = 500 * 1024 ** 2

    def __init__(self, file_name: str):
        self.file_name = file_name
        self.short_name = os.path.basename(file_name)
        self.md5 = None
        self.thr = None
        self.halt = False
        self._start_hashing()

    def stop(self):
        if self.thr:
            logger.info('Stopping hashing thread for "%s".' % self.short_name)
            self.halt = True
            self.thr.join()
            logger.info('Thread stopped.')

    def _start_hashing(self):
        if os.path.getsize(self.file_name) > Hasher.BG_HASHING_THR:
            self.thr = threading.Thread(target=self.generate_md5_hash)
            logger.info('Starting background hashing of "%s"' % self.short_name)
            self.thr.start()

    def get_result(self) -> str:
        if self.thr:
            self.thr.join()
        else:
            self.generate_md5_hash()

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

    def get_result(self) -> str:
        return self.hasher.hexdigest()


def hash_file(file_name: str) -> str:
    hasher = Hasher(file_name)
    return hasher.get_result()
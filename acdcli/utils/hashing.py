import hashlib
import logging
import os

logger = logging.getLogger(__name__)


class IncrementalHasher(object):
    def __init__(self):
        self.hasher = hashlib.md5()

    def update(self, chunk):
        self.hasher.update(chunk)

    def get_result(self) -> str:
        return self.hasher.hexdigest()


def hash_file(file_name: str) -> str:
    hasher = hashlib.md5()
    with open(file_name, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 ** 2), b''):
            hasher.update(chunk)
    logger.debug('MD5 of "%s" is %s' % (os.path.basename(file_name), hasher.hexdigest()))
    return hasher.hexdigest()
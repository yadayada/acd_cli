import hashlib
import logging
import os

logger = logging.getLogger(__name__)


class IncrementalHasher(object):
    __slots__ = ('hasher',)

    def __init__(self):
        self.hasher = hashlib.md5()

    def update(self, chunk):
        self.hasher.update(chunk)

    def get_result(self) -> str:
        return self.hasher.hexdigest()

def hash_bytes(bytes_) -> str:
    hasher = hashlib.md5()
    bytes_.seek(0)
    for chunk in iter(lambda: bytes_.read(1024 ** 2), b''):
        hasher.update(chunk)
    return hasher.hexdigest()

def hash_file(file_name: str) -> str:
    with open(file_name, 'rb') as f:
        md5 = hash_bytes(f)
    logger.debug('MD5 of "%s" is %s' % (os.path.basename(file_name), md5))
    return md5
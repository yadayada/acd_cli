import re
import os
from multiprocessing.pool import ThreadPool

BG_HASHING_THR = 500 * 1024 ** 2


class Hasher():
    def __init__(self, file_name):
        self.file_name = file_name
        self.md5 = None
        self.async_result = None
        self.pool = None
        self.start_hashing()

    def __stop__(self):
        if self.pool:
            self.pool.terminate()

    def start_hashing(self):
        if os.path.getsize(self.file_name) > BG_HASHING_THR:
            self.pool = ThreadPool(processes=1)
            self.async_result = self.pool.apply_async(generate_md5_hash, (self.file_name,))
        else:
            self.md5 = generate_md5_hash(self.file_name)

    def get_result(self):
        if self.async_result:
            self.md5 = self.async_result.get()
        return self.md5


def generate_md5_hash(file_name):
    import hashlib
    hasher = hashlib.md5()
    with open(file_name, 'rb') as f:
        while True:
            chunk = f.read(1024 ** 2)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def is_uploadable(file_name):
    return os.path.isfile(file_name) and os.access(file_name, os.R_OK)


# shamelessly copied from
# http://stackoverflow.com/questions/1094841/reusable-library-to-get-human-readable-version-of-file-size
def file_size_str(num, suffix='B'):
    for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Yi', suffix)
"""Experimental fusepy read support"""

import os
import io
import sys
import stat
import errno
import logging
from acdcli.bundled.fuse import FUSE, FuseOSError, Operations
from time import time
from datetime import datetime, timedelta
from collections import deque

from acdcli.utils import hashing
from acdcli.cache import query, sync
from acdcli.api import account, content, metadata, trash
from acdcli.api.common import RequestError

logger = logging.getLogger(__name__)


class ChunkCache(object):
    FUSE_BS = 128 * 1024
    CHUNK_SZ = 16 * FUSE_BS
    chunks = deque(maxlen=50)

    class Chunk(object):
        def __init__(self, id, offset, length):
            self.id = id
            self.offset = offset
            self.length = length
            self.end = offset + length - 1
            self.buf = io.BytesIO()
            content.download_chunk(id, self.buf, offset=offset, length=length)

    @classmethod
    def get(cls, id, offset, length):
        end = offset + length - 1
        for chunk in cls.chunks:
            if id != chunk.id:
                continue
            if offset >= chunk.offset and end <= chunk.end:
                chunk.buf.seek(offset - chunk.offset)
                b = io.BytesIO()
                b.write(chunk.buf.read(length))
                return b

        if length > cls.CHUNK_SZ:
            logger.warning('Requested chunk size exceeds FUSE block size.')
        c = cls.Chunk(id, offset, cls.CHUNK_SZ)
        cls.chunks.append(c)
        b = io.BytesIO()
        b.write(c.buf.read(length))
        return b


class ACDFuse(Operations):
    def __init__(self):
        self.total, self.free = account.fs_sizes()

    def readdir(self, path, fh):
        id = query.resolve_path(path, trash=False)

        return [_ for _ in ['.', '..'] + [b.node.name for b in query.list_children(id)]]

    def getattr(self, path, fh=None):
        id = query.resolve_path(path, trash=False)
        node = query.get_node(id)
        if not node:
            raise FuseOSError(errno.ENOENT)

        times = dict(st_atime=time(),
                     st_mtime=(node.modified - datetime(1970, 1, 1)) / timedelta(seconds=1),
                     st_ctime=(node.created - datetime(1970, 1, 1)) / timedelta(seconds=1))

        if node.is_folder():
            return dict(st_mode=stat.S_IFDIR | 0o7777, **times)
        if node.is_file():
            return dict(st_mode=stat.S_IFREG | 0o6667, st_size=node.size, **times)

    def listxattr(self, path):
        return []

    def read(self, path, length, offset, fh):
        logger.debug("%s l %d o %d fh %d" % (path, length, offset, fh))
        id = query.resolve_path(path, trash=False)
        b = io.BytesIO()
        # content.chunked_download(id, b, offset=offset, length=offset + length)
        content.download_chunk(id, b, offset=offset, length=length)
        return b.getvalue()

    # def read(self, path, length, offset, fh):
    #     logger.debug("%s, ln: %d of: %d fh %d" % (os.path.basename(path), length, offset, fh))
    #     id = query.resolve_path(path, trash=False)
    #
    #     b2 = ChunkCache.get(id, offset, length)
    #     bv2 = b2.getvalue()
    #
    #     b = io.BytesIO()
    #     content.chunked_download(id, b, offset=offset, length=offset + length)
    #     bv = b.getvalue()
    #     h1 = hashing.IncrementalHasher()
    #     h1.update(bv)
    #     h2 = hashing.IncrementalHasher()
    #     h2.update(bv2)
    #
    #     if h1.get_result() != h2.get_result():
    #         logger.error('Chunk mismatch %s, %d, %d, l1: %d, l2:%d'
    #                      % (id, offset, length, len(bv), len(bv)))
    #
    #     return bv2

    def statfs(self, path):
        bs = 512 * 1024
        logger.info('bs %s' % bs)

        return dict(f_bsize=bs,
                    f_frsize=bs,
                    f_blocks=int(self.total / bs),  # total no of blocks
                    f_bfree=int(self.free / bs),  # free blocks
                    f_bavail=int(self.free / bs),
                    f_namemax=256
                    )

    def rmdir(self, path):
        n = query.resolve_path(path)
        if not n:
            raise FuseOSError(errno.ENOENT)
        try:
            r = trash.move_to_trash(n)
            sync.insert_node(r)
        except RequestError as e:
            if e.status_code == e.CODE.CONN_EXCEPTION:
                raise FuseOSError(errno.ECOMM)
            else:
                raise FuseOSError(errno.EREMOTEIO)

    def unlink(self, path):
        self.rmdir(path)

    def create(self, path, mode):
        name = os.path.basename(path)

        ppath = os.path.dirname(path)
        pid = query.resolve_path(ppath)
        if not pid:
            raise FuseOSError(errno.ENOTDIR)

        try:
            r = content.create_file(name, pid)
            sync.insert_node(r)
        except RequestError as e:
            if e.status_code == e.CODE.CONN_EXCEPTION:
                raise FuseOSError(errno.ECOMM)
            elif e.status_code == 409:
                raise FuseOSError(errno.EEXIST)
            else:
                raise FuseOSError(errno.EREMOTEIO)

        return 0

    def rename(self, old, new):
        id = query.resolve_path(old)
        new = os.path.basename(new)
        try:
            r = metadata.rename_node(id, new)
            sync.insert_node(r)
        except RequestError as e:
            if e.status_code == e.CODE.CONN_EXCEPTION:
                raise FuseOSError(errno.ECOMM)
            elif e.status_code == 409:
                raise FuseOSError(errno.EEXIST)
            else:
                raise FuseOSError(errno.EREMOTEIO)


def mount(path: str):
    FUSE(ACDFuse(), path, foreground=True, nothreads=True)
"""Experimental fusepy read support"""

import os
import stat
import errno
import logging
from time import time
from datetime import datetime, timedelta
from collections import deque, defaultdict

from acdcli.bundled.fuse import FUSE, FuseOSError as FuseError, Operations
from acdcli.cache import query, sync
from acdcli.api import account, content, metadata, trash
from acdcli.api.common import RequestError

logger = logging.getLogger(__name__)

FUSE_BS = 128 * 1024
CHUNK_SZ = content.CHUNK_SIZE


class FuseOSError(FuseError):
    def __init__(self, err_no):
        logger.debug('FUSE error %i, %s.' % (err_no, errno.errorcode[err_no]))
        super().__init__(err_no)


class StreamedResponseCache(object):
    """Stream response cache intended for consecutive access."""

    class StreamChunk(object):
        __slots__ = ('offset', 'r', 'end')

        def __init__(self, id, offset, length, **kwargs):
            self.offset = offset
            self.r = content.response_chunk(id, offset, length, **kwargs)
            self.end = offset + int(self.r.headers['content-length']) - 1

        def has_byte_range(self, offset, length):
            """chunk begins at offset and has at least length bytes remaining"""
            logger.debug('s: %d-%d; r: %d-%d'
                         % (self.offset, self.end, offset, offset + length - 1))
            if offset == self.offset and offset + length - 1 <= self.end:
                return True

        def get(self, length):
            b = next(self.r.iter_content(length))
            logger.debug('streamed %ib' % len(b))
            self.offset += len(b)

            if len(b) < length and self.offset <= self.end:
                logger.warning('Chunk ended unexpectedly.')
                raise Exception
            return b

        def close(self):
            self.r.close()

    class File(object):
        __slots__ = ('chunks', 'access')

        def __init__(self):
            self.chunks = deque(maxlen=15)
            self.access = time()

        def get(self, id, offset, length, total):
            self.access = time()

            i = self.chunks.__len__() - 1
            while i >= 0:
                c = self.chunks[i]
                if c.has_byte_range(offset, length):
                    try:
                        bytes_ = c.get(length)
                    except:
                        self.chunks.remove(c)
                    else:
                        return bytes_
                i -= 1

            try:
                chunk = StreamedResponseCache.StreamChunk(id, offset, CHUNK_SZ, timeout=5)
            except RequestError as e:
                logger.error('Creating chunk failed. Code: %i, msg: %s' % (e.status_code, e.msg))
                raise FuseOSError(errno.ECOMM)
            else:
                self.chunks.append(chunk)
                return chunk.get(length)

        def clear(self):
            for chunk in self.chunks:
                try:
                    chunk.close()
                except:
                    pass
            self.chunks.clear()

    files = defaultdict(File)

    @classmethod
    def get(cls, id, offset, length, total):
        return cls.files[id].get(id, offset, length, total)

    @classmethod
    def invalidate(cls):
        pass

    @classmethod
    def release(cls, id):
        cls.files[id].clear()


class ACDFuse(Operations):
    def __init__(self):
        self.total, _ = account.fs_sizes()
        self.free = self.total - query.calculate_usage()
        self.fh = 1

    def readdir(self, path, fh):
        logger.debug('readdir %s' % path)

        node, _ = query.resolve(path, trash=False)
        if not node:
            raise FuseOSError(errno.ENOENT)

        return [_ for _ in ['.', '..'] + [c.name for c in node.available_children()]]

    def getattr(self, path, fh=None):
        logger.debug('getattr %s' % path)

        id = query.resolve_path(path, trash=False)
        node = query.get_node(id)
        if not node:
            raise FuseOSError(errno.ENOENT)

        times = dict(st_atime=time(),
                     st_mtime=(node.modified - datetime(1970, 1, 1)) / timedelta(seconds=1),
                     st_ctime=(node.created - datetime(1970, 1, 1)) / timedelta(seconds=1))

        if node.is_folder():
            return dict(st_mode=stat.S_IFDIR | 0o0777, st_nlink=node.size, **times)
        if node.is_file():
            return dict(st_mode=stat.S_IFREG | 0o0666,
                        st_nlink=len(node.parents), st_size=node.size, **times)

    def read(self, path, length, offset, fh):
        logger.debug("read %s, ln: %d of: %d fh %d" % (os.path.basename(path), length, offset, fh))
        node, _ = query.resolve(path, trash=False)
        if node.size == 0:
            return b''

        return StreamedResponseCache.get(node.id, offset, length, node.size)

    def statfs(self, path):
        bs = 512 * 1024
        return dict(f_bsize=bs,
                    f_frsize=bs,
                    f_blocks=self.total // bs,  # total no of blocks
                    f_bfree=self.free // bs,  # free blocks
                    f_bavail=self.free // bs,
                    f_namemax=256
                    )

    def mkdir(self, path, mode):
        logger.debug('+mkdir %s' % path)

        name = os.path.basename(path)
        ppath = os.path.dirname(path)
        pid = query.resolve_path(ppath)
        if not pid:
            raise FuseOSError(errno.ENOTDIR)

        try:
            r = content.create_folder(name, pid)
        except RequestError as e:
            if e.status_code == e.CODE.CONN_EXCEPTION:
                raise FuseOSError(errno.ECOMM)
            elif e.status_code == 409:
                raise FuseOSError(errno.EEXIST)
            else:
                raise FuseOSError(errno.EREMOTEIO)
        else:
            sync.insert_node(r)

    @staticmethod
    def _trash(path):
        logger.debug('trash %s' % path)
        node, parent = query.resolve(path)

        if not node:  # or not parent:
            raise FuseOSError(errno.ENOENT)

        logger.debug('%s %s' % (node, parent))

        try:
            # if len(node.parents) > 1:
            #     r = metadata.remove_child(parent.id, node.id)
            # else:
            r = trash.move_to_trash(node.id)
        except RequestError as e:
            if e.status_code == e.CODE.CONN_EXCEPTION:
                raise FuseOSError(errno.ECOMM)
            else:
                raise FuseOSError(errno.EREMOTEIO)
        else:
            sync.insert_node(r)

    def rmdir(self, path):
        logger.debug('-rmdir %s' % path)
        self._trash(path)

    def unlink(self, path):
        logger.debug('-unlink %s' % path)
        self._trash(path)

    def create(self, path, mode):
        logger.debug('+create %s' % path)

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

        self.fh += 1
        return self.fh

    def rename(self, old, new):
        if old == new:
            return

        logger.debug('rename %s %s' % (old, new))

        id = query.resolve_path(old)
        if not id:
            raise FuseOSError(errno.ENOENT)

        new_bn, old_bn = os.path.basename(new), os.path.basename(old)
        new_dn, old_dn = os.path.dirname(new), os.path.dirname(old)

        existing_id = query.resolve_path(new)
        if existing_id:
            en = query.get_node(existing_id)
            if en and en.is_file() and en.size == 0:
                trash.move_to_trash(existing_id)
            else:
                raise FuseOSError(errno.EEXIST)

        if new_bn != old_bn:
            self._rename(id, new_bn)

        if new_dn != old_dn:
            odir_id = query.resolve_path(old_dn)
            ndir_id = query.resolve_path(new_dn)
            if not odir_id or not ndir_id:
                raise FuseOSError(errno.ENOTDIR)
            self._move(id, odir_id, ndir_id)

    @staticmethod
    def _rename(id, name):
        try:
            r = metadata.rename_node(id, name)
        except RequestError as e:
            logger.debug(e)
            if e.status_code == e.CODE.CONN_EXCEPTION:
                raise FuseOSError(errno.ECOMM)
            elif e.status_code == 409:
                raise FuseOSError(errno.EEXIST)
            else:
                raise FuseOSError(errno.EREMOTEIO)
        else:
            sync.insert_node(r)

    @staticmethod
    def _move(id, old_folder, new_folder):
        try:
            r = metadata.move_node_from(id, old_folder, new_folder)
        except RequestError as e:
            if e.status_code == e.CODE.CONN_EXCEPTION:
                raise FuseOSError(errno.ECOMM)
            raise FuseOSError(errno.EREMOTEIO)
        else:
            sync.insert_node(r)

    def open(self, path, flags):
        logger.debug('open %s' % path)
        self.fh += 1
        return self.fh

    # def write(self, path, data, offset, fh):
    #     logger.debug('write %s , l: %d, o: %d, fh: %d' % (path, 0, offset, fh))
    #     # with open(os.devnull, 'wb') as dn:
    #     return len(data)

    # def truncate(self, path, length, fh=None):
    #     logger.debug('truncate %s path, %d' % (path, length))
    #     pass

    def release(self, path, fh):
        logger.debug('release %s, %d' % (path, fh))

        node, _ = query.resolve(path, trash=False)
        StreamedResponseCache.release(node.id)

    def utimens(self, path, times=None):
        logger.debug('utimens %s' % path)

    def chmod(self, path, mode):
        logger.debug('chmod %s %s' % (path, oct(mode)))

    def chown(self, path, uid, gid):
        logger.debug('chmod %s %d %d' % (path, uid, gid))


def mount(path: str, **kwargs):
    if not query.get_root_node():
        logger.critical('Root node not found. Aborting.')
        return 1
    if not os.path.isdir(path):
        logger.critical('Mount directory does not exist.')
        return 1

    FUSE(ACDFuse(), path, entry_timeout=60, auto_cache=True,
         nothreads=True,  # threading will break the caching
         uid=os.getuid(), gid=os.getgid(),
         subtype=ACDFuse.__name__,
         **kwargs
         )


def unmount(path=None, lazy=False):
    """Unmounts a specific mountpoint if path given or all of the user's ACDFuse mounts."""
    import re
    import subprocess
    from itertools import chain

    options = ['-u']
    if lazy:
        options.append('-z')

    fuse_st = ACDFuse.__name__

    if path:
        paths = [path]
    else:
        paths = []
        try:
            mounts = subprocess.check_output(['mount', '-l', '-t', 'fuse.' + fuse_st])
            mounts = mounts.decode('UTF-8').splitlines()
        except:
            logger.critical('Getting mountpoints failed.')
            return 1

        for mount in mounts:
            if 'user_id=%i' % os.getuid() in mount:
                paths.append(re.search(fuse_st + ' on (.*) type fuse.', mount).group(1))

    ret = 0
    for path in paths:
        command = list(chain.from_iterable([['fusermount'], options, [path]]))
        try:
            subprocess.check_call(command)
        except subprocess.CalledProcessError:
            # logger.error('Unmounting %s failed.' % path)
            ret |= 1

    return ret

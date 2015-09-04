"""fusepy filesystem"""

import sys
import os
import stat
import errno
import logging
from time import time, sleep
from datetime import datetime, timedelta
from collections import deque, defaultdict
from multiprocessing import Process
from threading import Thread, Lock
from queue import Queue, Full as QueueFull

from acdcli.bundled.fuse import FUSE, FuseOSError as FuseError, Operations
from acdcli.api.common import RequestError
from acdcli.api.content import CHUNK_SIZE as CHUNK_SZ

logger = logging.getLogger(__name__)

FUSE_BS = 128 * 1024
MAX_CHUNKS_PER_FILE = 15
CHUNK_TIMEOUT = 5

WRITE_TIMEOUT = 60
WRITE_BUFFER_SZ = 2 ** 10

MIN_AUTOSYNC_INTERVAL = 60


def _autosync(interval: int):
    if not interval:
        return

    import acd_cli

    interval = max(MIN_AUTOSYNC_INTERVAL, interval)
    while True:
        try:
            acd_cli.sync_node_list(full=False)
        except:
            pass
        sleep(interval)


class FuseOSError(FuseError):
    def __init__(self, err_no: int):
        # logger.debug('FUSE error %i, %s.' % (err_no, errno.errorcode[err_no]))
        super().__init__(err_no)

    @staticmethod
    def convert(e: RequestError):
        """:raises FUSEOSError"""

        try:
            caller = sys._getframe().f_back.f_code.co_name + ': '
        except AttributeError:
            caller = ''
        logger.error(caller + e.__str__())

        if e.status_code == e.CODE.CONN_EXCEPTION:
            raise FuseOSError(errno.ECOMM)
        elif e.status_code == e.codes.CONFLICT:
            raise FuseOSError(errno.EEXIST)
        elif e.status_code == e.codes.REQUESTED_RANGE_NOT_SATISFIABLE:
            raise FuseOSError(errno.EFAULT)
        else:
            raise FuseOSError(errno.EREMOTEIO)


class ReadProxy(object):
    """Dict of stream chunks for consecutive read access of files."""

    def __init__(self, acd_client):
        self.acd_client = acd_client
        self.files = defaultdict(ReadProxy.File)

    class StreamChunk(object):
        __slots__ = ('offset', 'r', 'end')

        def __init__(self, acd_client, id_, offset, length, **kwargs):
            self.offset = offset
            self.r = acd_client.response_chunk(id_, offset, length, **kwargs)
            self.end = offset + int(self.r.headers['content-length']) - 1

        def has_byte_range(self, offset, length):
            """chunk begins at offset and has at least length bytes remaining"""
            logger.debug('s: %d-%d; r: %d-%d'
                         % (self.offset, self.end, offset, offset + length - 1))
            if offset == self.offset and offset + length - 1 <= self.end:
                return True

        def get(self, length):
            b = next(self.r.iter_content(length))
            self.offset += len(b)

            if len(b) < length and self.offset <= self.end:
                logger.warning('Chunk ended unexpectedly.')
                raise Exception
            return b

        def close(self):
            self.r.close()

    class File(object):
        __slots__ = ('chunks', 'access', 'lock')

        def __init__(self):
            self.chunks = deque(maxlen=MAX_CHUNKS_PER_FILE)
            self.access = time()
            self.lock = Lock()

        def get(self, acd_client, id_, offset, length, total):
            self.access = time()

            with self.lock:
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
                with self.lock:
                    chunk = ReadProxy.StreamChunk(acd_client, id_, offset,
                                                  CHUNK_SZ, timeout=CHUNK_TIMEOUT)
                    self.chunks.append(chunk)
                    return chunk.get(length)
            except RequestError as e:
                FuseOSError.convert(e)

        def clear(self):
            with self.lock:
                for chunk in self.chunks:
                    try:
                        chunk.close()
                    except:
                        pass
                self.chunks.clear()

    def get(self, id_, offset, length, total):
        return self.files[id_].get(self.acd_client, id_, offset, length, total)

    def invalidate(self):
        pass

    def release(self, id_):
        self.files[id_].clear()


class WriteProxy(object):
    """Dict of WriteStreams for consecutive write operations."""

    def __init__(self, acd_client, cache):
        self.acd_client = acd_client
        self.cache = cache
        self.files = defaultdict(WriteProxy.WriteStream)

    class WriteStream(object):
        __slots__ = ('q', 'offset', 'error', 'closed')

        def __init__(self):
            self.q = Queue(maxsize=WRITE_BUFFER_SZ)
            self.offset = 0
            self.error = False
            self.closed = False

        def write(self, data):
            try:
                self.q.put(data, timeout=WRITE_TIMEOUT)
            except QueueFull:
                logger.error('Write timeout.')
                raise FuseOSError(errno.ETIMEDOUT)
            self.offset += len(data)

        def read(self, ln=0):
            if self.error:
                raise FuseOSError(errno.EREMOTEIO)

            if self.closed and self.q.empty():
                return b''

            b = [self.q.get()]
            self.q.task_done()
            while not self.q.empty():
                b.append(self.q.get())
                self.q.task_done()

            return b''.join(b)

        def close(self):
            self.closed = True
            if self.error:
                pass

    def write_n_sync(self, stream: WriteStream, node_id: str):
        try:
            r = self.acd_client.overwrite_stream(stream, node_id)
        except RequestError as e:
            stream.error = True
            logger.error('Error writing file. Code: %i, msg: %s' % (e.status_code, e.msg))
        else:
            self.cache.insert_node(r)

    def write(self, node_id, fh, offset, bytes_):
        f = self.files[fh]

        if f.offset == offset:
            f.write(bytes_)
        else:
            logger.error('Wrong offset for writing to fh %s.' % fh)
            raise FuseOSError(errno.EFAULT)

        if offset == 0:
            t = Thread(target=self.write_n_sync, args=(f, node_id))
            t.daemon = True
            t.start()

    def release(self, fh):
        f = self.files.get(fh)
        if f:
            f.close()


class LoggingMixIn(object):
    """Modified pyfuse LoggingMixIn that does not log read or written bytes."""
    log = logging.getLogger('fuse.log')

    def __call__(self, op, path, *args):
        self.log.debug('-> %s %s %s', op, path,
                       repr(args) if op != 'write' else repr((len(args[0]),) + args[1:]))

        ret = '[Unhandled Exception]'
        try:
            ret = getattr(self, op)(path, *args)
            return ret
        except OSError as e:
            ret = str(e)
            raise
        finally:
            self.log.debug('<- %s %s', op, repr(ret) if op != 'read' else '')


class ACDFuse(LoggingMixIn, Operations):
    class XATTRS(object):
        ID = 'acd.id'
        DESCR = 'acd.description'

        @classmethod
        def vars(cls):
            return [getattr(cls, x) for x in set(dir(cls)) - set(dir(type('', (object,), {})))
                    if not callable(getattr(cls, x))]

    class FXATTRS(XATTRS):
        MD5 = 'acd.md5'

    def __init__(self, **kwargs):
        self.cache = kwargs['cache']
        self.acd_client = kwargs['acd_client']

        self.rp = ReadProxy(self.acd_client)
        self.wp = WriteProxy(self.acd_client, self.cache)
        # self.pc = PathCache(self.cache)

        self.total, _ = self.acd_client.fs_sizes()
        self.free = self.total - self.cache.calculate_usage()
        self.fh = 1
        self.nlinks = kwargs.get('nlinks', False)

        sync_interval = kwargs.get('interval', 0)
        p = Process(target=_autosync, args=(sync_interval,))
        p.start()

    def readdir(self, path, fh):
        node, _ = self.cache.resolve(path, trash=False)
        if not node:
            raise FuseOSError(errno.ENOENT)

        return [_ for _ in ['.', '..'] + [c.name for c in node.available_children()]]

    def getattr(self, path, fh=None):
        node, _ = self.cache.resolve(path, trash=False)
        if not node:
            raise FuseOSError(errno.ENOENT)

        times = dict(st_atime=time(),
                     st_mtime=(node.modified - datetime(1970, 1, 1)) / timedelta(seconds=1),
                     st_ctime=(node.created - datetime(1970, 1, 1)) / timedelta(seconds=1))

        if node.is_folder():
            return dict(st_mode=stat.S_IFDIR | 0o0777,
                        st_nlink=node.nlinks if self.nlinks else 1, **times)
        if node.is_file():
            return dict(st_mode=stat.S_IFREG | 0o0666,
                        st_nlink=node.nlinks if self.nlinks else 1,
                        st_size=node.size, **times)

    def listxattr(self, path):
        node, _ = self.cache.resolve(path, trash=False)
        if node.is_file():
            return self.FXATTRS.vars()
        elif node.is_folder():
            return self.XATTRS.vars()

    def getxattr(self, path, name, position=0):
        node, _ = self.cache.resolve(path, trash=False)

        if name == self.XATTRS.ID:
            return bytes(node.id, encoding='utf-8')
        elif name == self.XATTRS.DESCR:
            return bytes(node.description if node.description else '', encoding='utf-8')
        elif name == self.FXATTRS.MD5:
            return bytes(node.md5, encoding='utf-8')

        raise FuseOSError(errno.ENODATA)

    def read(self, path, length, offset, fh):
        node, _ = self.cache.resolve(path, trash=False)

        if not node:
            raise FuseOSError(errno.ENOENT)

        if node.size == 0 or node.size == offset:
            return b''

        return self.rp.get(node.id, offset, length, node.size)

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
        name = os.path.basename(path)
        ppath = os.path.dirname(path)
        pid = self.cache.resolve_path(ppath)
        if not pid:
            raise FuseOSError(errno.ENOTDIR)

        try:
            r = self.acd_client.create_folder(name, pid)
        except RequestError as e:
            FuseOSError.convert(e)
        else:
            self.cache.insert_node(r)

    def _trash(self, path):
        logger.debug('trash %s' % path)
        node, parent = self.cache.resolve(path, False)

        if not node:  # or not parent:
            raise FuseOSError(errno.ENOENT)

        logger.debug('%s %s' % (node, parent))

        try:
            # if len(node.parents) > 1:
            #     r = metadata.remove_child(parent.id, node.id)
            # else:
            r = self.cache.move_to_trash(node.id)
        except RequestError as e:
            FuseOSError.convert(e)
        else:
            self.cache.insert_node(r)

    def rmdir(self, path):
        self._trash(path)

    def unlink(self, path):
        self._trash(path)

    def create(self, path, mode):
        name = os.path.basename(path)
        ppath = os.path.dirname(path)
        pid = self.cache.resolve_path(ppath, False)
        if not pid:
            raise FuseOSError(errno.ENOTDIR)

        try:
            r = self.acd_client.create_file(name, pid)
            self.cache.insert_node(r)
        except RequestError as e:
            FuseOSError.convert(e)

        self.fh += 1
        return self.fh

    def rename(self, old, new):
        if old == new:
            return

        id = self.cache.resolve_path(old, False)
        if not id:
            raise FuseOSError(errno.ENOENT)

        new_bn, old_bn = os.path.basename(new), os.path.basename(old)
        new_dn, old_dn = os.path.dirname(new), os.path.dirname(old)

        existing_id = self.cache.resolve_path(new, False)
        if existing_id:
            en = self.cache.get_node(existing_id)
            if en and en.is_file():
                self.acd_client.move_to_trash(existing_id)
            else:
                raise FuseOSError(errno.EEXIST)

        if new_bn != old_bn:
            self._rename(id, new_bn)

        if new_dn != old_dn:
            odir_id = self.cache.resolve_path(old_dn, False)
            ndir_id = self.cache.resolve_path(new_dn, False)
            if not odir_id or not ndir_id:
                raise FuseOSError(errno.ENOTDIR)
            self._move(id, odir_id, ndir_id)

    def _rename(self, id, name):
        try:
            r = self.acd_client.rename_node(id, name)
        except RequestError as e:
            FuseOSError.convert(e)
        else:
            self.cache.insert_node(r)

    def _move(self, id, old_folder, new_folder):
        try:
            r = self.acd_client.move_node(id, new_folder)
        except RequestError as e:
            FuseOSError.convert(e)
        else:
            self.cache.insert_node(r)

    def open(self, path, flags):
        logger.debug('open %s %x' % (path, flags))
        self.fh += 1
        return self.fh

    def write(self, path, data, offset, fh):
        if offset == 0:
            n, p = self.cache.resolve(path, False)
            node_id = n.id
        else:
            node_id = ''
        self.wp.write(node_id, fh, offset, data)
        return len(data)

    def truncate(self, path, length, fh=None):
        """Actually truncating to a length of 0 would result in errors.
        Truncating to >0 is not supported by the ACD API.
        """
        if length > 0:
            n, _ = self.cache.resolve(path)
            if n.size != length:
                raise FuseOSError(errno.ENOSYS)

    def release(self, path, fh):
        node, _ = self.cache.resolve(path, trash=False)
        if node:
            self.rp.release(node.id)
            self.wp.release(fh)

    def utimens(self, path, times=None):
        """:param times: """
        if times:
            mtime = times[1]
            # TODO: update time

    def chmod(self, path, mode):
        logger.debug('chmod %s %s' % (path, oct(mode)))

    def chown(self, path, uid, gid):
        pass


class LoggingMixIn:
    """Modified pyfuse LoggingMixIn that does not log read and written bytes"""
    log = logging.getLogger('acd_fuse')

    def __call__(self, op, path, *args):
        self.log.debug('-> %s %s %s', op, path,
                       repr(args) if op != 'write' else repr((len(args[0]),) + args[1:]))

        ret = '[Unhandled Exception]'
        try:
            ret = getattr(self, op)(path, *args)
            return ret
        except OSError as e:
            ret = str(e)
            raise
        finally:
            self.log.debug('<- %s %s', op, repr(ret) if op != 'read' else '')


def mount(path: str, args: dict, **kwargs):
    if not args['cache'].get_root_node():
        logger.critical('Root node not found. Aborting.')
        return 1
    if not os.path.isdir(path):
        logger.critical('Mountpoint does not exist or already used.')
        return 1

    FUSE(ACDFuse(**args), path, entry_timeout=60, attr_timeout=60, auto_cache=True,
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

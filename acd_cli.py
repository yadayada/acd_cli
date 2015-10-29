#!/usr/bin/env python3
import sys
import os
import json
import argparse
import logging
import logging.handlers
import signal
import time
import re
import appdirs
from functools import partial
from collections import namedtuple
from datetime import datetime, timedelta
from multiprocessing import Event

from pkgutil import walk_packages
from pkg_resources import iter_entry_points

import acdcli
from acdcli.api import client
from acdcli.api.common import RequestError, is_valid_id
from acdcli.cache import db, format
from acdcli.utils import hashing, progress
from acdcli.utils.threading import QueuedLoader

# load local plugin modules (default ones, for developers)
from acdcli import plugins

for importer, modname, ispkg in walk_packages(path=plugins.__path__, prefix=plugins.__name__ + '.',
                                              onerror=lambda x: None):
    if not ispkg:
        __import__(modname)

# load additional plugins from entry point
for plug_mod in iter_entry_points(group='acdcli.plugins', name=None):
    __import__(plug_mod.module_name)

_app_name = 'acd_cli'

logger = logging.getLogger(_app_name)

# path settings

cp = os.environ.get('ACD_CLI_CACHE_PATH')
sp = os.environ.get('ACD_CLI_SETTINGS_PATH')

CACHE_PATH = cp if cp else appdirs.user_cache_dir(_app_name)
SETTINGS_PATH = sp if sp else appdirs.user_config_dir(_app_name)

if not os.path.isdir(CACHE_PATH):
    try:
        os.makedirs(CACHE_PATH, mode=0o0700)  # private data
    except OSError:
        logger.critical('Error creating cache directory "%s"' % CACHE_PATH)
        sys.exit(1)

# consts

MIN_AUTOSYNC_INTERVAL = 60
MAX_LOG_SIZE = 10 * 2 ** 20
MAX_LOG_FILES = 5

# return values

ERROR_RETVAL = 1
INVALID_ARG_RETVAL = 2  # doubles as flag
INIT_FAILED_RETVAL = 3
KEYB_INTERR_RETVAL = 4

# additional retval flags
UL_DL_FAILED = 8
UL_TIMEOUT = 16
HASH_MISMATCH = 32
ERR_CR_FOLDER = 64
SIZE_MISMATCH = 128
CACHE_ASYNC = 256
DUPLICATE = 512
DUPLICATE_DIR = 1024
NAME_COLLISION = 2048


def signal_handler(signal_, frame):
    sys.exit(KEYB_INTERR_RETVAL)


signal.signal(signal.SIGINT, signal_handler)
if hasattr(signal, 'SIGPIPE'):
    signal.signal(signal.SIGPIPE, signal_handler)


def pprint(d: dict):
    print(json.dumps(d, indent=4, sort_keys=True))


acd_client = None
cache = None

#
# Glue functions (API, cache)
#


class CacheConsts(object):
    CHECKPOINT_KEY = 'checkpoint'
    LAST_SYNC_KEY = 'last_sync'
    MAX_AGE = 30


def sync_node_list(full=False) -> 'Union[int, None]':
    global cache
    cp_ = cache.KeyValueStorage.get(CacheConsts.CHECKPOINT_KEY) if not full else None

    if full:
        cache.drop_all()
        cache = db.NodeCache(CACHE_PATH)

    try:
        for changeset in acd_client.get_changes(checkpoint=cp_, include_purged=bool(cp_)):
            if changeset.reset and not full:
                cache.drop_all()
                cache = db.NodeCache(CACHE_PATH)
                full = True
            else:
                cache.remove_purged(changeset.purged_nodes)

            if len(changeset.nodes) > 0:
                cache.insert_nodes(changeset.nodes, partial=not full)
            cache.KeyValueStorage.update({CacheConsts.LAST_SYNC_KEY: time.time()})

            if len(changeset.nodes) > 0 or len(changeset.purged_nodes) > 0:
                cache.KeyValueStorage.update({CacheConsts.CHECKPOINT_KEY: changeset.checkpoint})

    except RequestError as e:
        print(e)
        if e.CODE == RequestError.CODE.INCOMPLETE_RESULT:
            logger.warning('Sync incomplete.')
        else:
            logger.critical('Sync failed.')
        return ERROR_RETVAL


def old_sync() -> 'Union[int, None]':
    global cache
    cache.drop_all()
    cache = db.NodeCache(CACHE_PATH)
    try:
        folders = acd_client.get_folder_list()
        folders.extend(acd_client.get_trashed_folders())
        files = acd_client.get_file_list()
        files.extend(acd_client.get_trashed_files())
    except RequestError as e:
        logger.critical('Sync failed.')
        print(e)
        return ERROR_RETVAL

    cache.insert_nodes(files + folders, partial=False)
    cache.KeyValueStorage['sync_date'] = time.time()


def autosync(interval: int, stop: Event=None):
    """Periodically syncs the node cache each *interval* seconds.
    The *stop* Event may be triggered to end syncing."""

    if not interval:
        return

    interval = max(MIN_AUTOSYNC_INTERVAL, interval)
    while True:
        if stop.is_set():
            break
        try:
            sync_node_list(full=False)
        except:
            import traceback
            logger.error(traceback.format_exc())
        time.sleep(interval)

#
# File transfer
#

RetryRetVal = namedtuple('RetryRetVal', ['ret_val', 'retry'])
STD_RETRY_RETVALS = [UL_DL_FAILED]


def retry_on(ret_vals: 'List[int]'):
    """Retry decorator that sets the wrapped function's progress handler argument according to its
    return value and wraps the return value in RetryRetVal object.

    :param ret_vals: list of retry values on which execution should be repeated"""

    def wrap(f: 'Callable'):
        def wrapped(*args, **kwargs) -> RetryRetVal:
            ret_val = ERROR_RETVAL
            try:
                ret_val = f(*args, **kwargs)
            except:
                import traceback
                logger.error(traceback.format_exc())
            h = kwargs.get('pg_handler')
            h.status = ret_val
            retry = ret_val in ret_vals
            if retry:
                h.reset()
            return RetryRetVal(ret_val, ret_val in ret_vals)

        return wrapped

    return wrap


def compare_hashes(hash1: str, hash2: str, file_name: str) -> int:
    """:returns: 0 on success, HASH_MISMATCH on failure"""
    if hash1 != hash2:
        logger.error('Hash mismatch between local and remote file for "%s".' % file_name)
        return HASH_MISMATCH

    logger.debug('Local and remote hashes match for "%s".' % file_name)
    return 0


def create_upload_jobs(dirs: list, path: str, parent_id: str, overwr: bool, force: bool,
                       dedup: bool, exclude: list, exclude_paths: list, jobs: list) -> int:
    """Creates upload job if passed path is a file, delegates directory traversal otherwise.
    Detects soft links that link to an already queued directory.

    :param dirs: list of directories' inodes traversed so far
    :param exclude: list of file exclusion patterns
    :param exclude_paths: list of paths for file or directory exclusion"""

    if os.path.realpath(path) in [os.path.realpath(p) for p in exclude_paths]:
        logger.info('Skipping upload of path "%s".' % path)
        return 0

    if not os.access(path, os.R_OK):
        logger.error('Path "%s" is not accessible.' % path)
        return INVALID_ARG_RETVAL

    if os.path.isdir(path):
        ino = os.stat(path).st_ino
        if ino in dirs:
            logger.warning('Duplicate directory detected: "%s".' % path)
            return DUPLICATE_DIR
        dirs.append(ino)
        return traverse_ul_dir(dirs, path, parent_id, overwr, force, dedup,
                               exclude, exclude_paths, jobs)
    elif os.path.isfile(path):
        short_nm = os.path.basename(path)
        for reg in exclude:
            if re.match(reg, short_nm):
                logger.info('Skipping upload of "%s" because of exclusion pattern.' % short_nm)
                return 0

        prog = progress.FileProgress(os.path.getsize(path))
        fo = partial(upload_file, path, parent_id, overwr, force, dedup, pg_handler=prog)
        jobs.append(fo)
        return 0


def traverse_ul_dir(dirs: list, directory: str, parent_id: str, overwr: bool, force: bool,
                    dedup: bool, exclude: list, exclude_paths: list, jobs: list) -> int:
    """Duplicates local directory structure."""

    if parent_id is None:
        parent_id = cache.get_root_id()
    parent = cache.get_node(parent_id)

    real_path = os.path.realpath(directory)
    short_nm = os.path.basename(real_path)

    curr_node = parent.get_child(short_nm)
    if not curr_node or not curr_node.is_available() or not parent.is_available():
        try:
            r = acd_client.create_folder(short_nm, parent_id)
            logger.info('Created folder "%s"' % (parent.full_path() + short_nm))
            cache.insert_node(r)
            curr_node = cache.get_node(r['id'])
        except RequestError as e:
            if e.status_code == 409:
                logger.error('Folder "%s" already exists. Please sync.' % short_nm)
            else:
                logger.error('Error creating remote folder "%s": %s.' % (short_nm, e))
            return ERR_CR_FOLDER
    elif curr_node.is_file():
        logger.error('Cannot create remote folder "%s", '
                     'because a file of the same name already exists.' % short_nm)
        return ERR_CR_FOLDER

    try:
        entries = sorted(os.listdir(directory))
    except OSError as e:
        logger.error('Skipping directory %s because of an error.' % directory)
        logger.info(e)
        return ERROR_RETVAL

    ret_val = 0
    for entry in entries:
        full_path = os.path.join(real_path, entry)
        ret_val |= create_upload_jobs(dirs, full_path, curr_node.id,
                                      overwr, force, dedup, exclude, exclude_paths, jobs)

    return ret_val


@retry_on(STD_RETRY_RETVALS)
def upload_file(path: str, parent_id: str, overwr: bool, force: bool, dedup: bool,
                pg_handler: progress.FileProgress = None) -> RetryRetVal:
    short_nm = os.path.basename(path)

    if dedup and cache.file_size_exists(os.path.getsize(path)):
        nodes = cache.find_md5(hashing.hash_file(path))
        nodes = [n for n in format.PathFormatter(nodes)]
        if len(nodes) > 0:
            # print('Skipping upload of duplicate file "%s".' % short_nm)
            logger.info('Location of duplicates: %s' % nodes)
            pg_handler.done()
            return DUPLICATE

    conflicting_node = cache.conflicting_node(short_nm, parent_id)
    file_id = None
    if conflicting_node:
        if conflicting_node.is_folder():
            logger.error('Name collision with existing folder '
                         'in the same location: "%s".' % short_nm)
            return NAME_COLLISION

        file_id = conflicting_node.id

    if not file_id:
        logger.info('Uploading %s' % path)
        hasher = hashing.IncrementalHasher()
        try:
            r = acd_client.upload_file(path, parent_id,
                                       read_callbacks=[hasher.update, pg_handler.update],
                                       deduplication=dedup)
        except RequestError as e:
            if e.status_code == 409:  # might happen if cache is outdated
                if not dedup:
                    logger.error('Uploading "%s" failed. Name collision with non-cached file. '
                                 'If you want to overwrite, please sync and try again.' % short_nm)
                else:
                    logger.error(
                        'Uploading "%s" failed. '
                        'Name or hash collision with non-cached file.' % short_nm)
                    logger.info(e)
                # colliding node ID is returned in error message -> could be used to continue
                return CACHE_ASYNC
            elif e.status_code == 504 or e.status_code == 408:  # proxy timeout / request timeout
                logger.warning('Timeout while uploading "%s".' % short_nm)
                # TODO: wait; request parent folder's children
                return UL_TIMEOUT
            else:
                logger.error(
                    'Uploading "%s" failed. %s.' % (short_nm, str(e)))
                return UL_DL_FAILED
        else:
            cache.insert_node(r)
            file_id = r['id']
            md5 = cache.get_node(file_id).md5
            return compare_hashes(hasher.get_result(), md5, short_nm)

    # else: file exists
    if not overwr and not force:
        logger.info('Skipping upload of existing file "%s".' % short_nm)
        pg_handler.done()
        return 0

    rmod = (conflicting_node.modified - datetime(1970, 1, 1)) / timedelta(seconds=1)
    rmod = datetime.utcfromtimestamp(rmod)
    lmod = datetime.utcfromtimestamp(os.path.getmtime(path))
    lcre = datetime.utcfromtimestamp(os.path.getctime(path))

    logger.debug('Remote mtime: %s, local mtime: %s, local ctime: %s' % (rmod, lmod, lcre))

    # ctime is checked because files can be overwritten by files with older mtime
    if rmod < lmod or (rmod < lcre and conflicting_node.size != os.path.getsize(path)) \
            or force:
        return overwrite(file_id, path, dedup=dedup, pg_handler=pg_handler).ret_val
    elif not force:
        logger.info('Skipping upload of "%s" because of mtime or ctime and size.' % short_nm)
        pg_handler.done()
        return 0


@retry_on(STD_RETRY_RETVALS)
def overwrite(node_id, local_file, dedup=False,
              pg_handler: progress.FileProgress = None) -> RetryRetVal:
    hasher = hashing.IncrementalHasher()
    try:
        r = acd_client.overwrite_file(node_id, local_file,
                                      read_callbacks=[hasher.update, pg_handler.update],
                                      deduplication=dedup)
        cache.insert_node(r)
        node = cache.get_node(r['id'])
        md5 = node.md5

        return compare_hashes(md5, hasher.get_result(), local_file)
    except RequestError as e:
        logger.error('Error overwriting file. %s' % str(e))
        return UL_DL_FAILED


@retry_on([])
def upload_stream(stream, file_name, parent_id, dedup=False,
                  pg_handler: progress.FileProgress = None) -> RetryRetVal:
    hasher = hashing.IncrementalHasher()
    try:
        r = acd_client.upload_stream(stream, file_name, parent_id,
                                     read_callbacks=[hasher.update, pg_handler.update],
                                     deduplication=dedup)
        cache.insert_node(r)
        node = cache.get_node(r['id'])
        return compare_hashes(node.md5, hasher.get_result(), 'stream')
    except RequestError as e:
        logger.error('Error uploading stream. %s' % str(e))
        return UL_DL_FAILED


def create_dl_jobs(node_id: str, local_path: str,
                   exclude: 'List[re._pattern_type]', jobs: list) -> int:
    """Populates passed jobs list with download partials."""

    local_path = local_path if local_path else ''

    node = cache.get_node(node_id)
    if not node.is_available():
        return 0

    if node.is_folder():
        return traverse_dl_folder(node_id, local_path, exclude, jobs)

    loc_name = node.name

    for reg in exclude:
        if re.match(reg, loc_name):
            logger.info('Skipping download of "%s" because of exclusion pattern.' % loc_name)
            return 0

    flp = os.path.join(local_path, loc_name)
    if os.path.isfile(flp):
        logger.info('Skipping download of existing file "%s"' % loc_name)
        if os.path.getsize(flp) != node.size:
            logger.info('Skipped file "%s" has different size than local file.' % loc_name)
            return SIZE_MISMATCH
        return 0

    prog = progress.FileProgress(node.size)
    fo = partial(download_file, node_id, local_path, pg_handler=prog)
    jobs.append(fo)

    return 0


def traverse_dl_folder(node_id: str, local_path: str,
                       exclude: 'List[re._pattern_type', jobs: list) -> int:
    """Duplicates remote folder structure."""

    if not local_path:
        local_path = os.getcwd()

    node = cache.get_node(node_id)

    if node.name is None:
        curr_path = os.path.join(local_path, 'acd')
    else:
        curr_path = os.path.join(local_path, node.name)

    try:
        os.makedirs(curr_path, exist_ok=True)
    except OSError:
        logger.error('Error creating directory "%s".' % curr_path)
        return ERR_CR_FOLDER

    ret_val = 0
    children = sorted(node.children)
    for child in children:
        ret_val |= create_dl_jobs(child.id, curr_path, exclude, jobs)
    return ret_val


@retry_on(STD_RETRY_RETVALS)
def download_file(node_id: str, local_path: str,
                  pg_handler: progress.FileProgress = None) -> RetryRetVal:
    node = cache.get_node(node_id)
    name, md5, size = node.name, node.md5, node.size
    # db.Session.remove()  # otherwise, sqlalchemy will complain if thread crashes

    logger.info('Downloading "%s"' % name)

    hasher = hashing.IncrementalHasher()
    try:
        acd_client.download_file(node_id, name, local_path, length=size,
                                 write_callbacks=[hasher.update, pg_handler.update])
    except RequestError as e:
        logger.error('Downloading "%s" failed. %s' % (name, str(e)))
        return UL_DL_FAILED
    else:
        return compare_hashes(hasher.get_result(), md5, name)


#
# Subparser actions. Return value Union[None, int] will be used as sys exit status.
#

# decorators

nocache_actions = []
offline_actions = []
no_autores_trash_actions = []


def nocache_action(func):
    """Decorator for actions that do not need to read from cache or autoresolve."""
    nocache_actions.append(func)
    return func


def offline_action(func):
    """Decorator for actions that can be performed without API calls."""
    offline_actions.append(func)
    return func


def no_autores_trash_action(func):
    """Decorator for actions that should not have trash paths auto-resolved."""
    no_autores_trash_actions.append(func)
    return func


# actual actions

def sync_action(args: argparse.Namespace):
    print('Syncing...')
    r = sync_node_list(full=args.full)
    if not r:
        print('Done.')
    return r


def old_sync_action(args: argparse.Namespace):
    print('Syncing...')
    r = old_sync()
    if not r:
        print('Done.')
    return r


@nocache_action
@offline_action
def delete_everything_action(args: argparse.Namespace):
    from distutils.util import strtobool
    from shutil import rmtree

    a = input('Do you really want to delete %s? [y/n] ' % CACHE_PATH)
    try:
        if strtobool(a):
            rmtree(CACHE_PATH)
    except ValueError:
        pass
    except OSError as e:
        print(e)
        print('Deleting directory failed.')


@nocache_action
@offline_action
def clear_action(args: argparse.Namespace):
    if not db.remove_db_file(CACHE_PATH):
        return ERROR_RETVAL


@nocache_action
@offline_action
def print_version_action(args: argparse.Namespace):
    print('%s %s, api %s ' % (_app_name, acdcli.__version__, acdcli.api.__version__))


@offline_action
def tree_action(args: argparse.Namespace):
    tree = cache.tree(args.node, args.include_trash)
    if tree is None:
        logger.critical('Invalid folder.')
        return INVALID_ARG_RETVAL

    tree = format.TreeFormatter(tree)
    for node in tree:
        print(node)


@nocache_action
def usage_action(args: argparse.Namespace):
    r = acd_client.get_account_usage()
    print(r, end='')


@nocache_action
def quota_action(args: argparse.Namespace):
    r = acd_client.get_quota()
    pprint(r)


def regex_helper(args: argparse.Namespace) -> 'List[re._pattern_type]':
    """Pre-compiles regexes from strings in args namespace."""
    excl_re = []
    for re_ in args.exclude_re:
        try:
            excl_re.append(re.compile(re_, flags=re.IGNORECASE))
        except re.error as e:
            logger.critical('Invalid regular expression: %s. %s' % (re_, e))
            sys.exit(INVALID_ARG_RETVAL)

    for ending in args.exclude_fe:
        excl_re.append(re.compile('^.*\.' + re.escape(ending) + '$', flags=re.IGNORECASE))

    return excl_re


@no_autores_trash_action
def upload_action(args: argparse.Namespace) -> int:
    if not cache.get_node(args.parent):
        logger.critical('Invalid upload folder.')
        return INVALID_ARG_RETVAL

    excl_re = regex_helper(args)

    jobs = []
    ret_val = 0
    for path in args.path:
        if not os.path.exists(path):
            logger.error('Path "%s" does not exist.' % path)
            ret_val |= INVALID_ARG_RETVAL
            continue

        ret_val |= create_upload_jobs([], path, args.parent, args.overwrite, args.force,
                                      args.deduplicate, excl_re, args.exclude_path, jobs)

    ql = QueuedLoader(args.max_connections, max_retries=args.max_retries)
    ql.add_jobs(jobs)

    return ret_val | ql.start()


@no_autores_trash_action
def upload_stream_action(args: argparse.Namespace) -> int:
    if not cache.get_node(args.parent):
        logger.critical('Invalid upload folder')
        return INVALID_ARG_RETVAL

    prog = progress.FileProgress(0)
    ql = QueuedLoader(max_retries=0)
    job = partial(upload_stream,
                  sys.stdin.buffer, args.name, args.parent, args.deduplicate, pg_handler=prog)
    ql.add_jobs([job])

    return ql.start()


def overwrite_action(args: argparse.Namespace) -> int:
    if not os.path.isfile(args.file):
        logger.error('Invalid file.')
        return INVALID_ARG_RETVAL

    prog = progress.FileProgress(os.path.getsize(args.file))
    ql = QueuedLoader(max_retries=args.max_retries)
    job = partial(overwrite, args.node, args.file, pg_handler=prog)
    ql.add_jobs([job])

    return ql.start()


def download_action(args: argparse.Namespace) -> int:
    excl_re = regex_helper(args)

    jobs = []
    ret_val = 0
    ret_val |= create_dl_jobs(args.node, args.path, excl_re, jobs)

    ql = QueuedLoader(args.max_connections, max_retries=args.max_retries)
    ql.add_jobs(jobs)

    return ret_val | ql.start()


def cat_action(args: argparse.Namespace) -> int:
    n = cache.get_node(args.node)
    if not n or not n.is_file():
        return INVALID_ARG_RETVAL

    try:
        acd_client.chunked_download(args.node, sys.stdout.buffer)
    except RequestError as e:
        logger.error('Downloading failed. %s' % str(e))
        return UL_DL_FAILED

    return 0


def mkdir(parent, name: str) -> bool:
    """Creates a folder and inserts it into cache upon success."""
    if parent.is_file():
        logger.error('Cannot create directory "%s". Parent is not a folder.' % name)
        return False

    c = parent.get_child(name)
    if c:
        if c.is_file():
            logger.error('Cannot create directory "%s". File exists.' % name)
            return False
        else:
            logger.warning('Folder "%s" already exists.' % name)
            return True

    parent_id = parent.id

    try:
        r = acd_client.create_folder(name, parent_id)
    except RequestError as e:
        if e.status_code == 409:
            logger.warning('Node "%s" already exists. %s' % (name, str(e)))
            return False
        else:
            logger.error('Error creating folder "%s". %s' % (name, str(e)))
            return False
    else:
        cache.insert_node(r)
        return True


def create_action(args: argparse.Namespace) -> int:
    segments = [seg for seg in args.new_folder.split('/') if seg] # non-empty path segments

    if not segments:
        return

    cur_path = '/'
    parent = cache.get_root_node()

    for s in segments[:-1]:
        cur_path += s + '/'
        child = parent.get_child(s)

        if child:
            parent = child
            continue

        if not args.parents:
            logger.error('Path "%s" does not exist.' % cur_path)
            return ERR_CR_FOLDER

        if not mkdir(parent, s):
            return ERR_CR_FOLDER

        parent = parent.get_child(s)

    if not mkdir(parent, segments[-1]):
        return ERR_CR_FOLDER


@no_autores_trash_action
@offline_action
def list_trash_action(args: argparse.Namespace):
    t_list = cache.list_trash(args.recursive)
    for node in format.ListFormatter(t_list, recursive=args.recursive):
        print(node)


def trash_action(args: argparse.Namespace) -> int:
    try:
        r = acd_client.move_to_trash(args.node)
        cache.insert_node(r)
    except RequestError as e:
        print(e)
        return ERROR_RETVAL


def restore_action(args: argparse.Namespace) -> int:
    try:
        r = acd_client.restore(args.node)
    except RequestError as e:
        logger.error('Error restoring "%s": %s' % (args.node, e))
        return ERROR_RETVAL
    cache.insert_node(r)


@offline_action
def resolve_action(args: argparse.Namespace) -> int:
    node = cache.resolve_path(args.path)
    if node:
        print(node)
    else:
        return INVALID_ARG_RETVAL


@offline_action
def find_action(args: argparse.Namespace):
    r = cache.find(args.name)
    r = format.LongIDFormatter(r)
    for node in r:
        print(node)
    if not r:
        return INVALID_ARG_RETVAL


@offline_action
def find_md5_action(args: argparse.Namespace) -> int:
    if len(args.md5) != 32:
        logger.critical('Invalid MD5 specified')
        return INVALID_ARG_RETVAL
    nodes = cache.find_md5(args.md5)
    for node in format.LongIDFormatter(nodes):
        print(node)


@offline_action
def find_regex_action(args: argparse.Namespace) -> int:
    try:
        re.compile(args.regex)
    except re.error as e:
        logger.critical('Invalid regular expression specified')
        return INVALID_ARG_RETVAL
    r = cache.find_regex(args.regex)
    r = format.LongIDFormatter(r)
    for node in r:
        print(node)
    return 0


@offline_action
def children_action(args: argparse.Namespace) -> int:
    nodes = cache.list_children(args.node, args.recursive, args.include_trash)
    for entry in format.ListFormatter(nodes, recursive=args.recursive, long=args.long):
        print(entry)


def move_action(args: argparse.Namespace) -> int:
    node = cache.get_node(args.child)
    if not node:
        return INVALID_ARG_RETVAL
    if len(node.parents) > 1:
        logger.error('Cannot move node with multiple parents.')
        return ERROR_RETVAL

    try:
        r = acd_client.move_node(args.child, args.parent)
        cache.insert_node(r)
    except RequestError as e:
        print(e)
        return ERROR_RETVAL


def rename_action(args: argparse.Namespace) -> int:
    try:
        r = acd_client.rename_node(args.node, args.name)
        cache.insert_node(r)
    except RequestError as e:
        print(e)
        return ERROR_RETVAL


def add_child_action(args: argparse.Namespace) -> int:
    try:
        r = acd_client.add_child(args.parent, args.child)
        cache.insert_node(r)
    except RequestError as e:
        print(e)
        return ERROR_RETVAL


def remove_child_action(args: argparse.Namespace) -> int:
    try:
        r = acd_client.remove_child(args.parent, args.child)
        cache.insert_node(r)
    except RequestError as e:
        print(e)
        return ERROR_RETVAL


def metadata_action(args: argparse.Namespace) -> int:
    try:
        r = acd_client.get_metadata(args.node, args.assets)
        pprint(r)
    except RequestError as e:
        print(e)
        return INVALID_ARG_RETVAL


@offline_action
def dump_sql_action(args: argparse.Namespace):
    cache.dump_table_sql()


def mount_action(args: argparse.Namespace):
    asp = partial(autosync, args.interval, stop=Event())

    import acdcli.acd_fuse
    acdcli.acd_fuse.mount(args.path, dict(acd_client=acd_client, cache=cache,
                                          nlinks=args.nlinks, autosync=asp),
                          ro=args.ro, foreground=args.foreground, nothreads=args.single_threaded,
                          nonempty=args.nonempty, modules=args.modules,
                          allow_root=args.allow_root, allow_other=args.allow_other)


@offline_action
@nocache_action
def unmount_action(args: argparse.Namespace):
    import acdcli.acd_fuse
    return acdcli.acd_fuse.unmount(args.path, args.lazy)


#
# helper methods
#


def resolve_remote_path_args(args: argparse.Namespace, attrs: list, incl_trash: bool = True):
    """In-place replaces certain attributes in Namespace by resolved node ID.
    :param attrs: list of attributes that may be given in absolute path form
    :param incl_trash: whether to resolve trashed files
    """
    for id_attr in attrs:
        if hasattr(args, id_attr):
            val = getattr(args, id_attr)
            if not val:
                continue
            if '/' in val:
                v = cache.resolve_path(val, trash=incl_trash)
                if not v:
                    logger.critical('Could not resolve path "%s".' % val)
                    sys.exit(INVALID_ARG_RETVAL)
                logger.info('Resolved "%s" to "%s"' % (val, v))
                setattr(args, id_attr, v)
                setattr(args, id_attr + '_path', val)
            elif not is_valid_id(val):
                logger.critical('Invalid ID format: "%s".' % val)
                sys.exit(INVALID_ARG_RETVAL)


def set_log_level(args: argparse.Namespace):
    fmt = '%(asctime)s.%(msecs).03d [%(levelname)s] [%(name)s] - %(message)s'
    ansi_fmt = fmt + '\x1b[K'  # clear right
    time_fmt = '%y-%m-%d %H:%M:%S'

    dumbfmtter = logging.Formatter(fmt=fmt, datefmt=time_fmt)
    ansifmtter = logging.Formatter(fmt=ansi_fmt, datefmt=time_fmt)

    # stderr handler
    sh = logging.StreamHandler()
    tty = hasattr(sys.__stderr__, 'isatty') and sys.__stderr__.isatty()
    sh.setFormatter(ansifmtter if tty else dumbfmtter)

    # debug log files in cache path
    rfh = logging.handlers.RotatingFileHandler(os.path.join(CACHE_PATH, _app_name + '.log'),
                                               maxBytes=MAX_LOG_SIZE, backupCount=MAX_LOG_FILES)
    rfh.setFormatter(dumbfmtter)
    rfh.setLevel(logging.DEBUG)

    verbose = False
    lvl = logging.WARNING

    if args.verbose:
        lvl = logging.INFO
        if args.verbose > 1:
            verbose = True
    elif args.debug:
        lvl = logging.DEBUG
        if args.debug > 1:
            verbose = True

    sh.setLevel(lvl)

    if verbose:
        logging.getLogger('sqlalchemy.engine').setLevel(lvl)
        logging.getLogger('sqlalchemy.orm').setLevel(lvl)
    if args.debug:
        import http.client
        http.client.HTTPConnection.debuglevel = 1

        # monkey patch for suppressing overlong http.client's HTTPConnection send debug prints
        # TODO: use logger instead of print
        def ellipses_print(*args, **kwargs):
            for a in args:
                if len(a) > 2000:
                    print('[...]', file=sys.stderr, **kwargs)
                    return

            print(*args, file=sys.stderr, **kwargs)

        http.client.print = ellipses_print

    root_logger = logging.getLogger()
    root_logger.addHandler(sh)
    if args.log:
        root_logger.addHandler(rfh)
        root_logger.setLevel(logging.DEBUG)
    else:
        root_logger.setLevel(lvl)


def set_encoding(force_utf: bool = False):
    """Sets the default encoding to UTF-8 if none is set.
    :param force_utf: force UTF-8 output
    """
    enc = str.lower(sys.stdout.encoding)
    utf_flag = False

    if not enc or force_utf:
        import io

        sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.detach(), encoding='utf-8')
        utf_flag = True

    return utf_flag


def check_cache() -> bool:
    """Checks for existence of root node and logs cache age.

    :returns: whether a root node was found"""

    if not cache.get_root_node():
        logger.critical('Root node not found. Please sync.')
        return False

    last_sync = cache.KeyValueStorage.get(CacheConsts.LAST_SYNC_KEY)
    if not last_sync:
        return True
    last_sync = datetime.utcfromtimestamp(float(last_sync))
    age = (datetime.utcnow() - last_sync) / timedelta(days=1)
    if age > CacheConsts.MAX_AGE:
        logger.warning('Cache data may be outdated. Please sync.')
    else:
        logger.info('Last sync at %s.' % last_sync)
    return True


def check_py_version():
    if sys.version_info[:3] in [(3, 2, 3), (3, 3, 0), (3, 3, 1)]:
        logger.warning('Your Python version is known to cause issues. Uploading might not work.')


# noinspection PyProtectedMember
class Argument(object):
    """Simple argparse argument container"""

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def attach(self, subparser: argparse._ActionsContainer):
        subparser.add_argument(*self.args, **self.kwargs)


def get_parser() -> tuple:
    max_ret = Argument('--max-retries', '-r', action='store', type=int, default=0,
                       help='set the maximum number of retries '
                            '[default: 0, maximum: %i]' % QueuedLoader.MAX_RETRIES)

    opt_parser = argparse.ArgumentParser(
        prog=_app_name, formatter_class=argparse.RawTextHelpFormatter,
        epilog='Hints: \n'
               '  * Remote locations may be specified as path in most cases, '
               'e.g. "/folder/file", or via ID \n'
               '  * If you need to enter a node ID that contains a leading dash (minus) sign, '
               'precede it by two dashes and a space, e.g. \'-- -xfH...\'\n'
               '  * actions marked with [+] have optional arguments')
    log_group = opt_parser.add_mutually_exclusive_group()
    log_group.add_argument('-v', '--verbose', action='count',
                           help='prints some info messages to stderr; '
                                'use "-vv" to also get sqlalchemy info')
    log_group.add_argument('-d', '--debug', action='count',
                           help='prints info and debug to stderr; '
                                'use "-dd" to also get sqlalchemy debug messages')
    opt_parser.add_argument('-nl', '--no-log', action='store_false', dest='log',
                            help='do not save a log of debug messages')
    opt_parser.add_argument('-c', '--color', default=format.ColorMode['never'],
                            choices=format.ColorMode.keys(),
                            help='"never" [default] turns coloring off, '
                                 '"always" turns coloring on '
                                 'and "auto" colors listings when stdout is a tty '
                                 '[uses the Linux-style LS_COLORS environment variable]')
    opt_parser.add_argument('-i', '--check', default=db.NodeCache.IntegrityCheckType['full'],
                            choices=db.NodeCache.IntegrityCheckType.keys(),
                            help='select database integrity check type [default: full]')
    opt_parser.add_argument('-u', '--utf', action='store_true',
                            help='force utf output')
    opt_parser.add_argument('-nw', '--no-wait', action='store_true', help=argparse.SUPPRESS)

    subparsers = opt_parser.add_subparsers(title='action', dest='action')
    subparsers.required = True

    vers_sp = subparsers.add_parser('version', aliases=['v'], help='print version and exit\n')
    vers_sp.set_defaults(func=print_version_action)

    sync_sp = subparsers.add_parser('sync', aliases=['s'],
                                    help='[+] refresh node list cache; fetches complete node list'
                                         'if cache is empty or incremental changes '
                                         'if cache is non-empty')
    sync_sp.add_argument('--full', '-f', action='store_true',
                         help='perform a full sync even if the node list is not empty')
    sync_sp.set_defaults(func=sync_action)

    old_sync_sp = subparsers.add_parser('old-sync', add_help=False)
    old_sync_sp.set_defaults(func=old_sync_action)

    clear_sp = subparsers.add_parser('clear-cache', aliases=['cc'],
                                     help='delete node cache file [offline operation]\n\n')
    clear_sp.set_defaults(func=clear_action)

    tree_sp = subparsers.add_parser('tree', aliases=['t'],
                                    help='[+] print directory tree [offline operation]')
    tree_sp.add_argument('--include-trash', '-t', action='store_true')
    tree_sp.add_argument('node', nargs='?', default=None, help='root folder for the tree')
    tree_sp.set_defaults(func=tree_action)

    list_c_sp = subparsers.add_parser('children', aliases=['ls', 'dir'],
                                      help='[+] list folder\'s children [offline operation]\n\n')
    list_c_sp.add_argument('--long', '-l', action='store_true', help='long listing format')
    list_c_sp.add_argument('--include-trash', '-t', action='store_true')
    list_c_sp.add_argument('--recursive', '-r', action='store_true')
    list_c_sp.add_argument('node', nargs='?', default='/',
                           help='folder to display contents of [optional]')
    list_c_sp.set_defaults(func=children_action)

    find_sp = subparsers.add_parser('find', aliases=['f'], help=
    'find nodes by name [offline operation] [case insensitive]')
    find_sp.add_argument('name')
    find_sp.set_defaults(func=find_action)

    find_hash_sp = subparsers.add_parser('find-md5', aliases=['fh'],
                                         help='find files by MD5 hash [offline operation]')
    find_hash_sp.add_argument('md5')
    find_hash_sp.set_defaults(func=find_md5_action)

    find_regex_sp = subparsers.add_parser('find-regex', aliases=['fr'],
                                          help='find nodes by regular expression '
                                               '[offline operation] [case insensitive]\n\n')
    find_regex_sp.add_argument('regex')
    find_regex_sp.set_defaults(func=find_regex_action)

    dummy_p = argparse.ArgumentParser().add_subparsers()
    re_dummy_sp = dummy_p.add_parser('', add_help=False)
    re_dummy_sp.add_argument('--max-connections', '-x', action='store', type=int, default=1,
                             help='set the maximum concurrent connections [default: 1, '
                                  'maximum: %i' % QueuedLoader.MAX_NUM_WORKERS + ']')
    max_ret.attach(re_dummy_sp)
    re_dummy_sp.add_argument('--exclude-ending', '-xe', action='append', dest='exclude_fe',
                             default=[], help='exclude files whose endings match the given string,'
                                              ' e.g. "bak" [case insensitive]')
    re_dummy_sp.add_argument('--exclude-regex', '-xr', action='append', dest='exclude_re',
                             default=[],
                             help='exclude files whose names match the given regular expression,'
                                  ' e.g. "^thumbs\.db$" [case insensitive]')

    upload_sp = subparsers.add_parser('upload', aliases=['ul'], parents=[re_dummy_sp],
                                      help='[+] file and directory upload to a remote destination')
    upload_sp.add_argument('--exclude-path', '-xp', action='append', dest='exclude_path',
                           default=[], help='exclude file or directory '
                                            'that match the given string')
    upload_sp.add_argument('--overwrite', '-o', action='store_true',
                           help='overwrite if local modification time is higher '
                                'or local ctime is higher than remote modification time '
                                'and local/remote file sizes do not match.')
    upload_sp.add_argument('--force', '-f', action='store_true', help='force overwrite')
    upload_sp.add_argument('--deduplicate', '-d', action='store_true',
                           help='exclude duplicate files from upload')
    upload_sp.add_argument('path', nargs='+', help='a path to a local file or directory')
    upload_sp.add_argument('parent', help='remote parent folder')
    upload_sp.set_defaults(func=upload_action)

    overwrite_sp = subparsers.add_parser('overwrite', aliases=['ov'], help=
    'overwrite file A [remote] with content of file B [local]')
    max_ret.attach(overwrite_sp)
    overwrite_sp.add_argument('node')
    overwrite_sp.add_argument('file')
    overwrite_sp.set_defaults(func=overwrite_action)

    stream_sp = subparsers.add_parser('stream', aliases=['st'],
                                      help='[+] upload the standard input stream to a file')
    stream_sp.add_argument('--deduplicate', '-d', action='store_true',
                           help='prevent duplicates from getting stored after upload')
    stream_sp.add_argument('name', help='the remote file name')
    stream_sp.add_argument('parent', help='remote parent folder')
    stream_sp.set_defaults(func=upload_stream_action)

    download_sp = subparsers.add_parser('download', aliases=['dl'], parents=[re_dummy_sp],
                                        help='download a remote folder or file; '
                                             'will skip existing local files')
    download_sp.add_argument('node')
    download_sp.add_argument('path', nargs='?', default=None, help='local download path [optional]')
    download_sp.set_defaults(func=download_action)

    cat_sp = subparsers.add_parser('cat', help='output a file to the standard output stream\n\n')
    cat_sp.add_argument('node')
    cat_sp.set_defaults(func=cat_action)

    cr_fo_sp = subparsers.add_parser('create', aliases=['c', 'mkdir'],
                                     help='create folder using an absolute path\n\n')
    cr_fo_sp.add_argument('--parents', '-p', action='store_true',
                          help='create parent folders as needed')
    cr_fo_sp.add_argument('new_folder', help='an absolute folder path, '
                                             'e.g. "/my/dir/"; trailing slash is optional')
    cr_fo_sp.set_defaults(func=create_action)

    trash_sp = subparsers.add_parser('list-trash', aliases=['lt'],
                                     help='[+] list trashed nodes [offline operation]')
    trash_sp.add_argument('--recursive', '-r', action='store_true')
    trash_sp.set_defaults(func=list_trash_action)

    m_trash_sp = subparsers.add_parser('trash', aliases=['rm'], help='move node to trash')
    m_trash_sp.add_argument('node')
    m_trash_sp.set_defaults(func=trash_action)

    rest_sp = subparsers.add_parser('restore', aliases=['re'], help='restore node from trash\n\n')
    rest_sp.add_argument('node', help='ID of the node')
    rest_sp.set_defaults(func=restore_action)

    move_sp = subparsers.add_parser('move', aliases=['mv'], help='move node A into folder B')
    move_sp.add_argument('child')
    move_sp.add_argument('parent')
    move_sp.set_defaults(func=move_action)

    rename_sp = subparsers.add_parser('rename', aliases=['rn'], help='rename a node\n\n')
    rename_sp.add_argument('node')
    rename_sp.add_argument('name')
    rename_sp.set_defaults(func=rename_action)

    res_sp = subparsers.add_parser('resolve', aliases=['rs'],
                                   help='resolve a path to a node ID [offline operation]\n\n')
    res_sp.add_argument('path')
    res_sp.set_defaults(func=resolve_action)

    # maybe the child operations should not be exposed
    # they can be used for creating hardlinks
    add_c_sp = subparsers.add_parser('add-child', aliases=['ac'],
                                     help='add a node to a parent folder')
    add_c_sp.add_argument('parent')
    add_c_sp.add_argument('child')
    add_c_sp.set_defaults(func=add_child_action)

    rem_c_sp = subparsers.add_parser('remove-child', aliases=['rc'],
                                     help='remove a node from a parent folder\n\n')
    rem_c_sp.add_argument('parent')
    rem_c_sp.add_argument('child')
    rem_c_sp.set_defaults(func=remove_child_action)

    usage_sp = subparsers.add_parser('usage', aliases=['u'], help='show drive usage data')
    usage_sp.set_defaults(func=usage_action)

    quota_sp = subparsers.add_parser('quota', aliases=['q'], help='show drive quota [raw JSON]')
    quota_sp.set_defaults(func=quota_action)

    meta_sp = subparsers.add_parser('metadata', aliases=['m'],
                                    help='print a node\'s metadata [raw JSON]\n\n')
    meta_sp.add_argument('--assets', '-a', action='store_true')
    meta_sp.add_argument('node')
    meta_sp.set_defaults(func=metadata_action)

    fuse_sp = subparsers.add_parser('mount', help='[+] mount the cloud drive at a local directory')
    fuse_sp.add_argument('--ro', '-ro', action='store_true', help='mount read-only')
    fuse_sp.add_argument('--foreground', '-fg', action='store_true', help='do not detach')
    fuse_sp.add_argument('--single-threaded', '-st', action='store_true')
    # fuse_sp.add_argument('--multi-threaded', '-mt', action='store_false', dest='single_threaded')
    fuse_sp.add_argument('--nonempty', '-ne', action='store_true',
                         help='allow mounting over a non-empty directory')
    fuse_sp.add_argument('--allow-root', '-ar', action='store_true',
                         help='allow access to root user')
    fuse_sp.add_argument('--allow-other', '-ao', action='store_true',
                         help='allow access to other users')
    fuse_sp.add_argument('--modules', action='store', default='',
                         help='add iconv or subdir modules')
    fuse_sp.add_argument('--nlinks', '-n', action='store_true', help='calculate nlinks')
    fuse_sp.add_argument('--interval', '-i', type=int, default=60,
                         help='sync every x seconds [default: 60, off: 0]')
    fuse_sp.add_argument('path')
    fuse_sp.set_defaults(func=mount_action)

    umount_sp = subparsers.add_parser('umount', help='[+] unmount cloud drive(s)')
    umount_sp.add_argument('--lazy', '-l', '-z', action='store_true')
    umount_sp.add_argument('path', nargs='?', default=None, help='local path to unmount [optional]')
    umount_sp.set_defaults(func=unmount_action)

    # undocumented actions

    de_sp = subparsers.add_parser('delete-everything', add_help=False)
    de_sp.set_defaults(func=delete_everything_action)

    # useful for interactive mode
    dn_sp = subparsers.add_parser('init', aliases=['i'], add_help=False)
    dn_sp.set_defaults(func=None)

    # dump sql database creation sequence to stdout
    dmp_sp = subparsers.add_parser('dumpsql', add_help=False)
    dmp_sp.set_defaults(func=dump_sql_action)

    return opt_parser, subparsers


def main():
    opt_parser, subparsers = get_parser()
    opt_parser.set_defaults(acd_client=lambda: acd_client, cache=lambda: cache)

    # plugins

    plugin_log = [str(plugins.Plugin)]
    for plugin in plugins.Plugin:
        if plugin.check_version(acdcli.__version__):
            log = []
            plugin.attach(subparsers, log)
            plugin_log.extend(log)
        else:
            plugin_log.append('Script version is not compatible with "%s".' % plugin)

    args = opt_parser.parse_args()

    set_log_level(args)
    if set_encoding(force_utf=args.utf):
        logger.info('Stdout/stderr encoding changed to UTF-8. ANSI escape codes may not work.')
    else:
        import colorama
        colorama.init()

    check_py_version()

    for msg in plugin_log:
        logger.info(msg)

    global acd_client
    global cache

    if args.func not in offline_actions:
        try:
            acd_client = client.ACDClient(CACHE_PATH)
        except:
            raise
            sys.exit(INIT_FAILED_RETVAL)

    if args.func not in nocache_actions:
        try:
            cache = db.NodeCache(CACHE_PATH, args.check)
        except:
            raise
            sys.exit(INIT_FAILED_RETVAL)
        if args.func not in [sync_action, old_sync_action, dump_sql_action]:
            if not check_cache():
                sys.exit(INIT_FAILED_RETVAL)

    format.init(args.color)

    if args.no_wait:
        from acdcli.api.backoff_req import BackOffRequest
        BackOffRequest._wait = lambda x: None

    autoresolve_attrs = ['child', 'parent', 'node']
    resolve_remote_path_args(args, autoresolve_attrs,
                             incl_trash=args.action not in no_autores_trash_actions)

    # call appropriate sub-parser action
    if args.func:
        logger.debug(args)
        sys.exit(args.func(args))


if __name__ == "__main__":
    if sys.argv[-1] == 'init':
        try:
            from importlib import reload
        except ImportError:
            from imp import reload
    main()

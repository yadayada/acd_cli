#!/usr/bin/env python3
import sys
import os
import json
import argparse
import logging
import signal
from datetime import datetime, timedelta
import time
import re
import appdirs
from functools import partial
from collections import namedtuple

from pkgutil import walk_packages
from pkg_resources import iter_entry_points

from acdcli.api import account, common, content, metadata, trash
from acdcli.api.common import RequestError
from acdcli.cache import *
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

__version__ = '0.2.2a1'
_app_name = 'acd_cli'

logger = logging.getLogger(_app_name)

# noinspection PyBroadException
# monkey patch the user agent
try:
    import requests.utils

    requests.utils.old_dau = requests.utils.default_user_agent

    def new_dau():
        return _app_name + '/' + __version__ + ' ' + requests.utils.old_dau()

    requests.utils.default_user_agent = new_dau
except:
    pass

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

# return values

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


def signal_handler(signal_, frame):
    # if db.Session:
    #     db.Session.rollback()
    sys.exit(KEYB_INTERR_RETVAL)


signal.signal(signal.SIGINT, signal_handler)
if hasattr(signal, 'SIGPIPE'):
    signal.signal(signal.SIGPIPE, signal_handler)


def pprint(d: dict):
    print(json.dumps(d, indent=4, sort_keys=True))


#
# Glue functions (API, cache)
#


class CacheConsts(object):
    CHECKPOINT_KEY = 'checkpoint'
    LAST_SYNC_KEY = 'last_sync'
    MAX_AGE = 30


def sync_node_list(full=False):
    cp = db.KeyValueStorage.get(CacheConsts.CHECKPOINT_KEY) if not full else None

    try:
        nodes, purged, ncp, full = metadata.get_changes(checkpoint=cp, include_purged=not not cp)
    except RequestError as e:
        logger.critical('Sync failed.')
        print(e)
        return 1

    if full:
        db.drop_all()
        db.init(CACHE_PATH)
    else:
        sync.remove_purged(purged)

    if len(nodes) > 0:
        sync.insert_nodes(nodes, partial=not full)
    db.KeyValueStorage.update(
        {CacheConsts.CHECKPOINT_KEY: ncp, CacheConsts.LAST_SYNC_KEY: time.time()})
    return


def old_sync():
    db.drop_all()
    db.init(CACHE_PATH)
    try:
        folders = metadata.get_folder_list()
        folders.extend(metadata.get_trashed_folders())
        files = metadata.get_file_list()
        files.extend(metadata.get_trashed_files())
    except RequestError as e:
        logger.critical('Sync failed.')
        print(e)
        return 1

    sync.insert_nodes(files + folders, partial=False)
    db.KeyValueStorage['sync_date'] = time.time()

#
# File transfer
#

RetryRetVal = namedtuple('RetryRetVal', ['ret_val', 'retry'])
RETRY_RETVALS = [UL_DL_FAILED]


def retry_on(ret_vals: list):
    """:param ret_vals: list of retry values on which execution should be repeated"""

    def wrap(f):
        def wrapped(*args, **kwargs):
            ret_val = 1
            try:
                ret_val = f(*args, **kwargs)
            except Exception as e:
                logger.error(e.__str__())
            h = kwargs.get('pg_handler')
            h.status = ret_val
            retry = ret_val in ret_vals
            if retry:
                h.reset()
            return RetryRetVal(ret_val, ret_val in ret_vals)

        return wrapped

    return wrap


def compare_hashes(hash1: str, hash2: str, file_name: str):
    if hash1 != hash2:
        logger.error('Hash mismatch between local and remote file for "%s".' % file_name)
        return HASH_MISMATCH

    logger.debug('Local and remote hashes match for "%s".' % file_name)
    return 0


def create_upload_jobs(path: str, parent_id: str, overwr: bool, force: bool, dedup: bool,
                       exclude: list, jobs: list) -> int:
    if not os.access(path, os.R_OK):
        logger.error('Path "%s" is not accessible.' % path)
        return INVALID_ARG_RETVAL

    if os.path.isdir(path):
        return traverse_ul_dir(path, parent_id, overwr, force, dedup, exclude, jobs)
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


def traverse_ul_dir(directory: str, parent_id: str, overwr: bool, force: bool, dedup: bool,
                    exclude: list, jobs: list) -> int:
    """Duplicates local directory structure."""

    if parent_id is None:
        parent_id = query.get_root_id()
    parent = query.get_node(parent_id)

    real_path = os.path.realpath(directory)
    short_nm = os.path.basename(real_path)

    curr_node = parent.get_child(short_nm)
    if not curr_node or not curr_node.is_available() or not parent.is_available():
        try:
            r = content.create_folder(short_nm, parent_id)
            logger.info('Created folder "%s"' % (parent.full_path() + short_nm))
            sync.insert_node(r)
            curr_node = query.get_node(r['id'])
        except RequestError as e:
            if e.status_code == 409:
                logger.error('Folder "%s" already exists. Please sync.' % short_nm)
            else:
                logger.error('Error creating remote folder "%s".' % short_nm)
            return ERR_CR_FOLDER
    elif curr_node.is_file():
        logger.error(
            'Cannot create remote folder "%s", because a file of the same name already exists.' % short_nm)
        return ERR_CR_FOLDER

    try:
        entries = sorted(os.listdir(directory))
    except OSError as e:
        logger.error('Skipping directory %s because of an error.' % directory)
        logger.info(e)
        return

    ret_val = 0
    for entry in entries:
        full_path = os.path.join(real_path, entry)
        ret_val |= create_upload_jobs(full_path, curr_node.id, overwr, force, dedup, exclude, jobs)

    return ret_val


@retry_on(RETRY_RETVALS)
def upload_file(path: str, parent_id: str, overwr: bool, force: bool, dedup: bool,
                pg_handler: progress.FileProgress=None) -> RetryRetVal:
    short_nm = os.path.basename(path)

    logger.info('Uploading %s' % path)

    cached_file = query.get_node(parent_id).get_child(short_nm)
    file_id = None
    if cached_file:
        file_id = cached_file.id

    if not file_id:
        if dedup and query.file_size_exists(os.path.getsize(path)):
            nodes = query.find_md5(hashing.hash_file(path))
            nodes = format.PathFormatter(nodes)
            if len(nodes) > 0:
                # print('Skipping upload of duplicate file "%s".' % short_nm)
                logger.info('Location of duplicates: %s' % nodes)
                pg_handler.done()
                return DUPLICATE

        try:
            hasher = hashing.IncrementalHasher()
            r = content.upload_file(path, parent_id,
                                    read_callbacks=[hasher.update, pg_handler.update],
                                    deduplication=dedup)
            sync.insert_node(r)
            file_id = r['id']
            md5 = query.get_node(file_id).md5
            return compare_hashes(hasher.get_result(), md5, short_nm)

        except RequestError as e:
            if e.status_code == 409:  # might happen if cache is outdated
                if not dedup:
                    logger.error('Uploading "%s" failed. Name collision with non-cached file. '
                                 'If you want to overwrite, please sync and try again.' % short_nm)
                else:
                    logger.error(
                        'Uploading "%s" failed. Name or hash collision with non-cached file.' % short_nm)
                    logger.info(e)
                # colliding node ID is returned in error message -> could be used to continue
                return CACHE_ASYNC
            elif e.status_code == 504 or e.status_code == 408:  # proxy timeout / request timeout
                logger.warning('Timeout while uploading "%s".' % short_nm)
                # TODO: wait; request parent folder's children
                return UL_TIMEOUT
            else:
                logger.error(
                    'Uploading "%s" failed. Code: %s, msg: %s' % (short_nm, e.status_code, e.msg))
                return UL_DL_FAILED

    # else: file exists
    rmod = (cached_file.modified - datetime(1970, 1, 1)) / timedelta(seconds=1)
    rmod = datetime.utcfromtimestamp(rmod)
    lmod = datetime.utcfromtimestamp(os.path.getmtime(path))
    lcre = datetime.utcfromtimestamp(os.path.getctime(path))

    logger.info('Remote mtime: %s, local mtime: %s, local ctime: %s' % (rmod, lmod, lcre))

    if not overwr and not force:
        logging.info('Skipping upload of existing file "%s".' % short_nm)
        pg_handler.done()
        return 0

    # ctime is checked because files can be overwritten by files with older mtime
    if rmod < lmod or (rmod < lcre and cached_file.size != os.path.getsize(path)) \
            or force:
        return overwrite(file_id, path, dedup=dedup, pg_handler=pg_handler).ret_val
    elif not force:
        logging.info('Skipping upload of "%s" because of mtime or ctime and size.' % short_nm)
        pg_handler.done()
        return 0


@retry_on(RETRY_RETVALS)
def overwrite(node_id, local_file, dedup=False,
              pg_handler: progress.FileProgress=None) -> RetryRetVal:
    hasher = hashing.IncrementalHasher()
    try:
        r = content.overwrite_file(node_id, local_file,
                                   read_callbacks=[hasher.update, pg_handler.update],
                                   deduplication=dedup)
        sync.insert_node(r)
        node = query.get_node(r['id'])
        md5 = node.md5

        return compare_hashes(md5, hasher.get_result(), local_file)
    except RequestError as e:
        logger.error('Error overwriting file. Code: %s, msg: %s' % (e.status_code, e.msg))
        return UL_DL_FAILED


def create_dl_jobs(node_id: str, local_path: str, exclude: list, jobs: list) -> int:
    """Populates passed jobs list with download partials."""
    local_path = local_path if local_path else ''

    node = query.get_node(node_id)
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


def traverse_dl_folder(node_id: str, local_path: str, exclude: list, jobs: list) -> int:
    """Duplicates remote folder structure."""

    if not local_path:
        local_path = os.getcwd()

    node = query.get_node(node_id)

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


@retry_on(RETRY_RETVALS)
def download_file(node_id: str, local_path: str,
                  pg_handler: progress.FileProgress=None) -> RetryRetVal:
    node = query.get_node(node_id)
    name, md5, size = node.name, node.md5, node.size
    # db.Session.remove()  # otherwise, sqlalchemy will complain if thread crashes

    logger.info('Downloading "%s"' % name)

    hasher = hashing.IncrementalHasher()
    try:
        content.download_file(node_id, name, local_path, length=size,
                              write_callbacks=[hasher.update, pg_handler.update])
    except RequestError as e:
        logger.error('Downloading "%s" failed. Code: %s, msg: %s' % (name, e.status_code, e.msg))
        return UL_DL_FAILED
    else:
        return compare_hashes(hasher.get_result(), md5, name)


def compare(local: str, remote_id):
    pass

#
# Subparser actions. Return value [typeof(None), int] will be used as sys exit status.
#

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


###

def sync_action(args: argparse.Namespace):
    print('Syncing...')
    r = sync_node_list(full=args.full)
    print('Done.')
    return r


def old_sync_action(args: argparse.Namespace):
    print('Syncing...')
    r = old_sync()
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
    db.remove_db_file(CACHE_PATH)


@nocache_action
@offline_action
def print_version_action(args: argparse.Namespace):
    print(' '.join([_app_name, __version__]))


@offline_action
def tree_action(args: argparse.Namespace):
    tree = query.tree(args.node, args.include_trash)
    tree = format.TreeFormatter(tree)
    for node in tree:
        print(node)


@nocache_action
def usage_action(args: argparse.Namespace):
    r = account.get_account_usage()
    print(r, end='')


@nocache_action
def quota_action(args: argparse.Namespace):
    r = account.get_quota()
    pprint(r)


def regex_helper(args: argparse.Namespace) -> list:
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
    excl_re = regex_helper(args)

    jobs = []
    ret_val = 0
    for path in args.path:
        if not os.path.exists(path):
            logger.error('Path "%s" does not exist.' % path)
            ret_val |= INVALID_ARG_RETVAL
            continue

        ret_val |= create_upload_jobs(path, args.parent, args.overwrite, args.force,
                                      args.deduplicate, excl_re, jobs)

    ql = QueuedLoader(args.max_connections, max_retries=args.max_retries)
    ql.add_jobs(jobs)

    return ret_val | ql.start()


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


def create_action(args: argparse.Namespace) -> int:
    parent, folder = os.path.split(args.new_folder)
    # no trailing slash
    if not folder:
        parent, folder = os.path.split(parent)

    if not folder:
        logger.error('Cannot create folder with empty name.')
        return INVALID_ARG_RETVAL

    if parent[-1:] == '' or parent[0] != '/':
        parent = '/' + parent
    p_id = query.resolve_path(parent)
    if not p_id:
        logger.error('Invalid parent path "%s".' % parent)
        return INVALID_ARG_RETVAL

    try:
        r = content.create_folder(folder, p_id)
    except RequestError as e:
        logger.debug(str(e.status_code) + e.msg)
        if e.status_code == 409:
            logger.warning('Folder "%s" already exists.' % folder)
        else:
            logger.error('Error creating folder "%s".' % folder)
            return ERR_CR_FOLDER
    else:
        sync.insert_node(r)


@no_autores_trash_action
@offline_action
def list_trash_action(args: argparse.Namespace):
    t_list = query.list_trash(args.recursive)
    for node in format.ListFormatter(t_list, recursive=args.recursive):
        print(node)


def trash_action(args: argparse.Namespace) -> int:
    try:
        r = trash.move_to_trash(args.node)
        sync.insert_node(r)
    except RequestError as e:
        print(e)
        return 1


def restore_action(args: argparse.Namespace) -> int:
    try:
        r = trash.restore(args.node)
    except RequestError as e:
        logger.error('Error restoring "%s"' % args.node, e)
        return 1
    sync.insert_node(r)


@offline_action
def resolve_action(args: argparse.Namespace) -> int:
    node = query.resolve_path(args.path)
    if node:
        print(node)
    else:
        return INVALID_ARG_RETVAL


@offline_action
def find_action(args: argparse.Namespace):
    r = query.find(args.name)
    r = format.LongIDFormatter(r)
    for node in r:
        print(node)
    if not r:
        return INVALID_ARG_RETVAL


@offline_action
def find_md5_action(args: argparse.Namespace) -> int:
    if len(args.md5) != 32:
        logger.critical('Invalid MD5 specified')
        return 2
    nodes = query.find_md5(args.md5)
    for node in format.LongIDFormatter(nodes):
        print(node)


@offline_action
def children_action(args: argparse.Namespace) -> int:
    nodes = query.list_children(args.node, args.recursive, args.include_trash)
    for entry in format.ListFormatter(nodes, recursive=args.recursive):
        print(entry)


def move_action(args: argparse.Namespace) -> int:
    try:
        r = metadata.move_node(args.child, args.parent)
        sync.insert_node(r)
    except RequestError as e:
        print(e)
        return 1


def rename_action(args: argparse.Namespace) -> int:
    try:
        r = metadata.rename_node(args.node, args.name)
        sync.insert_node(r)
    except RequestError as e:
        print(e)
        return 1


def add_child_action(args: argparse.Namespace) -> int:
    try:
        r = metadata.add_child(args.parent, args.child)
        sync.insert_node(r)
    except RequestError as e:
        print(e)
        return 1


def remove_child_action(args: argparse.Namespace) -> int:
    try:
        r = metadata.remove_child(args.parent, args.child)
        sync.insert_node(r)
    except RequestError as e:
        print(e)
        return 1


def metadata_action(args: argparse.Namespace) -> int:
    try:
        r = metadata.get_metadata(args.node)
        pprint(r)
    except RequestError as e:
        print(e)
        return INVALID_ARG_RETVAL


@offline_action
@nocache_action
def dump_sql_action(args: argparse.Namespace):
    db.dump_table_sql()


def mount_action(args: argparse.Namespace):
    import acdcli.fuse
    acdcli.fuse.mount(args.path)


@offline_action
def compare_action(args: argparse.Namespace):
    pass


#
# helper methods
#


# added for version 0.1.3 on 15-05-04
def migrate_cache_files():
    files = ['oauth_data', 'endpoint_data', 'nodes.db']
    old_dir = os.path.dirname(os.path.realpath(__file__))
    for file in files:
        curr_path = os.path.join(old_dir, file)
        if os.path.isfile(curr_path) and os.path.isfile(curr_path):
            new_path = os.path.join(CACHE_PATH, file)
            try:
                if not os.path.exists(new_path):
                    logger.info('Moving file "%s" from "%s" to "%s".' % (file, old_dir, CACHE_PATH))
                    os.rename(curr_path, new_path)
            except OSError:
                logger.warning(
                    'Error moving cache file "%s" from "%s" to "%s".' % (file, old_dir, CACHE_PATH))


def resolve_remote_path_args(args: argparse.Namespace, attrs: list, incl_trash: bool=True):
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
                v = query.resolve_path(val, trash=incl_trash)
                if not v:
                    logger.critical('Could not resolve path "%s".' % val)
                    sys.exit(INVALID_ARG_RETVAL)
                logger.info('Resolved "%s" to "%s"' % (val, v))
                setattr(args, id_attr, v)
            elif len(val) != 22:
                logger.critical('Invalid ID format: "%s".' % val)
                sys.exit(INVALID_ARG_RETVAL)


def set_log_level(args: argparse.Namespace):
    format_ = '%(asctime)s.%(msecs).03d [%(levelname)s] [%(name)s] - %(message)s'
    time_fmt = '%y-%m-%d %H:%M:%S'

    if not args.verbose and not args.debug:
        logging.basicConfig(level=logging.WARNING, format=format_, datefmt=time_fmt)

    if args.verbose:
        logging.basicConfig(level=logging.INFO, format=format_, datefmt=time_fmt)
        if args.verbose > 1:
            logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
            logging.getLogger('sqlalchemy.orm').setLevel(logging.INFO)
    elif args.debug:
        logging.basicConfig(level=logging.DEBUG, format=format_, datefmt=time_fmt)

        # these debug messages (prints) will not show up in log file
        import http.client

        http.client.HTTPConnection.debuglevel = 1

        if args.debug > 1:
            logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)
            logging.getLogger('sqlalchemy.orm').setLevel(logging.DEBUG)


def check_cache_age():
    last_sync = db.KeyValueStorage.get(CacheConsts.LAST_SYNC_KEY)
    if not last_sync:
        return
    last_sync = datetime.utcfromtimestamp(float(last_sync))
    age = (datetime.utcnow() - last_sync) / timedelta(days=1)
    if age > CacheConsts.MAX_AGE:
        logger.warning('Cache data may be outdated. Please sync.')
    else:
        logger.info('Last sync at %s.' % last_sync)


# noinspection PyProtectedMember
class Argument(object):
    """Simple argparse argument container"""

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def attach(self, subparser:argparse._ActionsContainer):
        subparser.add_argument(*self.args, **self.kwargs)


def main():
    utf_flag = False
    tty_flag = sys.stdout.isatty()
    enc = str.lower(sys.stdout.encoding)

    if not enc or (tty_flag and enc != 'utf-8'):
        import io

        sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.detach(), encoding='utf-8')
        utf_flag = True

    max_ret = Argument('--max-retries', '-r', action='store', type=int, default=0,
                       help='set the maximum number of retries [default: 0]')

    opt_parser = argparse.ArgumentParser(
        prog=_app_name, formatter_class=argparse.RawTextHelpFormatter,
        epilog='Hints: \n'
               '  * Remote locations may be specified as path in most cases, e.g. "/folder/file", or via ID \n'
               '  * If you need to enter a node ID that contains a leading dash (minus) sign, '
               'precede it by two dashes and a space, e.g. \'-- -xfH...\'\n'
               '  * actions marked with [+] have optional arguments'
               '')
    opt_parser.add_argument('-v', '--verbose', action='count',
                            help='prints some info messages to stderr; use "-vv" to also get sqlalchemy info')
    opt_parser.add_argument('-d', '--debug', action='count',
                            help='prints info and debug to stderr; use "-dd" to also get sqlalchemy debug messages')
    opt_parser.add_argument('-c', '--color', default=format.ColorMode['never'],
                            choices=format.ColorMode.keys(),
                            help='"never" [default] turns coloring off, '
                                 '"always" turns coloring on '
                                 'and "auto" colors listings when stdout is a tty '
                                 '[uses the Linux-style LS_COLORS environment variable]')
    opt_parser.add_argument('-nw', '--no-wait', action='store_true', help=argparse.SUPPRESS)

    subparsers = opt_parser.add_subparsers(title='action', dest='action')
    subparsers.required = True

    vers_sp = subparsers.add_parser('version', aliases=['v'], help='print version and exit\n')
    vers_sp.set_defaults(func=print_version_action)

    sync_sp = subparsers.add_parser('sync', aliases=['s'],
                                    help='[+] refresh node list cache; necessary for many actions')
    sync_sp.add_argument('--full', '-f', action='store_true', help='force a full sync')
    sync_sp.set_defaults(func=sync_action)

    old_sync_sp = subparsers.add_parser('old-sync', add_help=False)
    old_sync_sp.set_defaults(func=old_sync_action)

    clear_sp = subparsers.add_parser('clear-cache', aliases=['cc'],
                                     help='clear node cache [offline operation]\n\n')
    clear_sp.set_defaults(func=clear_action)

    tree_sp = subparsers.add_parser('tree', aliases=['t'],
                                    help='[+] print directory tree [offline operation]')
    tree_sp.add_argument('--include-trash', '-t', action='store_true')
    tree_sp.add_argument('node', nargs='?', default=None, help='root node for the tree')
    tree_sp.set_defaults(func=tree_action)

    list_c_sp = subparsers.add_parser('children', aliases=['ls', 'dir'],
                                      help='[+] list folder\'s children [offline operation]\n\n')
    list_c_sp.add_argument('--include-trash', '-t', action='store_true')
    list_c_sp.add_argument('--recursive', '-r', action='store_true')
    list_c_sp.add_argument('node')
    list_c_sp.set_defaults(func=children_action)

    find_sp = subparsers.add_parser('find', aliases=['f'],
                                    help='find nodes by name [offline operation] [case insensitive]')
    find_sp.add_argument('name')
    find_sp.set_defaults(func=find_action)

    find_hash_sp = subparsers.add_parser('find-md5', aliases=['fh'],
                                         help='find files by MD5 hash [offline operation]\n\n')
    find_hash_sp.add_argument('md5')
    find_hash_sp.set_defaults(func=find_md5_action)

    dummy_p = argparse.ArgumentParser().add_subparsers()
    re_dummy_sp = dummy_p.add_parser('', add_help=False)
    re_dummy_sp.add_argument('--max-connections', '-x', action='store', type=int, default=1,
                             help='set the maximum concurrent connections [default: 1]')
    max_ret.attach(re_dummy_sp)
    re_dummy_sp.add_argument('--exclude-ending', '-xe', action='append', dest='exclude_fe',
                             default=[],
                             help='exclude files whose endings match the given string, e.g. "bak" [case insensitive]')
    re_dummy_sp.add_argument('--exclude-regex', '-xr', action='append', dest='exclude_re',
                             default=[],
                             help='exclude files whose names match the given regular expression,'
                                  ' e.g. "^thumbs\.db$" [case insensitive]')

    upload_sp = subparsers.add_parser('upload', aliases=['ul'], parents=[re_dummy_sp],
                                      help='[+] file and directory upload to a remote destination')
    upload_sp.add_argument('--overwrite', '-o', action='store_true',
                           help='overwrite if local modification time is higher or local ctime is higher than remote '
                                'modification time and local/remote file sizes do not match.')
    upload_sp.add_argument('--force', '-f', action='store_true', help='force overwrite')
    upload_sp.add_argument('--deduplicate', '-d', action='store_true',
                           help='exclude duplicate files from upload')
    upload_sp.add_argument('path', nargs='+', help='a path to a local file or directory')
    upload_sp.add_argument('parent', help='remote parent folder')
    upload_sp.set_defaults(func=upload_action)

    overwrite_sp = subparsers.add_parser('overwrite', aliases=['ov'],
                                         help='overwrite file A [remote] with content of file B [local]')
    max_ret.attach(overwrite_sp)
    overwrite_sp.add_argument('node')
    overwrite_sp.add_argument('file')
    overwrite_sp.set_defaults(func=overwrite_action)

    download_sp = subparsers.add_parser('download', aliases=['dl'], parents=[re_dummy_sp],
                                        help='download a remote folder or file; will skip existing local files\n\n')
    download_sp.add_argument('node')
    download_sp.add_argument('path', nargs='?', default=None, help='local download path [optional]')
    download_sp.set_defaults(func=download_action)

    cr_fo_sp = subparsers.add_parser('create', aliases=['c', 'mkdir'],
                                     help='create folder using an absolute path\n\n')
    cr_fo_sp.add_argument('new_folder',
                          help='an absolute folder path, e.g. "/my/dir/"; trailing slash is optional')
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
                                   help='resolve a path to a node ID\n\n')
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
                                    help='print a node\'s metadata [raw JSON]')
    meta_sp.add_argument('node')
    meta_sp.set_defaults(func=metadata_action)

    de_sp = subparsers.add_parser('delete-everything', add_help=False)
    de_sp.set_defaults(func=delete_everything_action)

    # useful for interactive mode
    dn_sp = subparsers.add_parser('init', aliases=['i'], add_help=False)
    dn_sp.set_defaults(func=None)

    # dump sql database creation sequence to stdout
    dmp_sp = subparsers.add_parser('dumpsql', add_help=False)
    dmp_sp.set_defaults(func=dump_sql_action)

    fuse_sp = subparsers.add_parser('mount', add_help=False)
    fuse_sp.add_argument('path')
    fuse_sp.set_defaults(func=mount_action)

    plugin_log = [str(plugins.Plugin)]
    for plugin in plugins.Plugin:
        if plugin.check_version(__version__):
            log = []
            plugin.attach(subparsers, log)
            plugin_log.extend(log)
        else:
            plugin_log.append('Script version is not compatible with "%s".' % plugin)

    args = opt_parser.parse_args()

    set_log_level(args)
    for msg in plugin_log:
        logger.info(msg)
    if utf_flag:
        logger.info('Stdout/stderr encoding changed to UTF-8.')

    migrate_cache_files()

    if args.func not in offline_actions:
        if not common.init(CACHE_PATH):
            sys.exit(INIT_FAILED_RETVAL)

    if args.func not in nocache_actions:
        if not db.init(CACHE_PATH):
            sys.exit(INIT_FAILED_RETVAL)
        check_cache_age()

    format.init(args.color)

    if args.no_wait:
        common.BackOffRequest._wait = lambda: None

    autoresolve_attrs = ['child', 'parent', 'node']
    resolve_remote_path_args(args, autoresolve_attrs,
                             incl_trash=args.action not in no_autores_trash_actions)

    # call appropriate sub-parser action
    if args.func:
        sys.exit(args.func(args))


if __name__ == "__main__":
    main()

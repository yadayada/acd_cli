#!/usr/bin/env python3
import sys
import os
import json
import argparse
import logging
import signal
import datetime
import re

from bundled import appdirs

from cache import sync, query, db
from acd import common, content, metadata, account, trash
from acd.common import RequestError
import utils

# dynamically load all plugins
import plugins
import pkgutil
for finder, mod_name, ispkg in pkgutil.iter_modules(['plugins']):
    if not ispkg:
        __import__(finder.path + '.' + mod_name)

__version__ = '0.1.3'
_app_name = os.path.basename(__file__).split('.')[0]

logger = logging.getLogger(_app_name)

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

INVALID_ARG_RETVAL = 2
INIT_FAILED_RETVAL = 3
KEYB_INTERR_RETVAL = 4

# additional retval flags
UL_DL_FAILED = 8
UL_TIMEOUT = 16
HASH_MISMATCH = 32
ERR_CR_FOLDER = 64

SERVER_ERR = 512


def signal_handler(signal_, frame):
    if db.session:
        db.session.rollback()
    sys.exit(KEYB_INTERR_RETVAL)


signal.signal(signal.SIGINT, signal_handler)


def pprint(s):
    print(json.dumps(s, indent=4, sort_keys=True))


def sync_node_list(full=False):
    cp = sync.get_checkpoint()

    try:
        nodes, purged, ncp, full = metadata.get_changes(checkpoint=None if full else cp, include_purged=not full)
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
        sync.insert_nodes(nodes)
    sync.set_checkpoint(ncp)
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

    sync.insert_folders(folders)
    sync.insert_files(files)


def upload(path: str, parent_id: str, overwr: bool, force: bool, exclude: list) -> int:
    if not os.access(path, os.R_OK):
        logger.error('Path "%s" is not accessible.' % path)
        return INVALID_ARG_RETVAL

    if os.path.isdir(path):
        print('Current directory: %s' % path)
        return upload_folder(path, parent_id, overwr, force, exclude)
    elif os.path.isfile(path):
        short_nm = os.path.basename(path)
        for reg in exclude:
            if re.match(reg, short_nm):
                print('Skipping upload of "%s" because of exclusion pattern.' % short_nm)
                return 0
        print('Current file: %s' % short_nm)
        return upload_file(path, parent_id, overwr, force)


def compare_hashes(hash1: str, hash2: str, file_name: str):
    if hash1 != hash2:
        logger.warning('Hash mismatch between local and remote file for "%s".' % file_name)
        return HASH_MISMATCH

    logger.info('Local and remote hashes match for "%s".' % file_name)
    return 0


def upload_file(path: str, parent_id: str, overwr: bool, force: bool) -> int:
    short_nm = os.path.basename(path)

    cached_file = query.get_node(parent_id).get_child(short_nm)
    file_id = None
    if cached_file:
        file_id = cached_file.id

    if not file_id:
        try:
            hasher = utils.Hasher(path)
            r = content.upload_file(path, parent_id)
            sync.insert_node(r)
            file_id = r['id']
            cached_file = query.get_node(file_id)
            return compare_hashes(hasher.get_result(), cached_file.md5, short_nm)

        except RequestError as e:
            if e.status_code == 409:  # might happen if cache is outdated
                hasher.stop()
                logger.error('Uploading "%s" failed. Name collision with non-cached file. '
                             'If you want to overwrite, please sync and try again.' % short_nm)
                # colliding node ID is returned in error message -> could be used to continue
                return UL_DL_FAILED
            elif e.status_code == 504 or e.status_code == 408:  # proxy timeout / request timeout
                hasher.stop()
                logger.warning('Timeout while uploading "%s".' % short_nm)
                # TODO: wait; request parent folder's children
                return UL_TIMEOUT
            else:
                hasher.stop()
                logger.error('Uploading "%s" failed. Code: %s, msg: %s' % (short_nm, e.status_code, e.msg))
                return UL_DL_FAILED

    # else: file exists
    mod_time = (cached_file.modified - datetime.datetime(1970, 1, 1)) / datetime.timedelta(seconds=1)

    logger.info('Remote mtime: ' + str(mod_time) + ', local mtime: ' + str(os.path.getmtime(path))
                + ', local ctime: ' + str(os.path.getctime(path)))

    if not overwr and not force:
        print('Skipping upload of existing file "%s".' % short_nm)
        return 0

    # ctime is checked because files can be overwritten by files with older mtime
    if mod_time < os.path.getmtime(path) \
            or (mod_time < os.path.getctime(path) and cached_file.size != os.path.getsize(path)) \
            or force:
        return overwrite(file_id, path)
    elif not force:
        print('Skipping upload of "%s" because of mtime or ctime and size.' % short_nm)
        return 0
    else:
        hasher = utils.Hasher(path)


def upload_folder(folder: str, parent_id: str, overwr: bool, force: bool, exclude: list) -> int:
    if parent_id is None:
        parent_id = query.get_root_id()
    parent = query.get_node(parent_id)

    real_path = os.path.realpath(folder)
    short_nm = os.path.basename(real_path)

    curr_node = parent.get_child(short_nm)
    if not curr_node or curr_node.status == 'TRASH' or parent.status == 'TRASH':
        try:
            r = content.create_folder(short_nm, parent_id)
            sync.insert_node(r)
            curr_node = query.get_node(r['id'])
        except RequestError as e:
            if e.status_code == 409:
                logger.error('Folder "%s" already exists. Please sync.' % short_nm)
            else:
                logger.error('Error creating remote folder "%s".' % short_nm)
            return ERR_CR_FOLDER
    elif curr_node.is_file():
        logger.error('Cannot create remote folder "%s", because a file of the same name already exists.' % short_nm)
        return ERR_CR_FOLDER

    entries = sorted(os.listdir(folder))

    ret_val = 0
    for entry in entries:
        full_path = os.path.join(real_path, entry)
        ret_val |= upload(full_path, curr_node.id, overwr, force, exclude)

    return ret_val


def overwrite(node_id, local_file) -> int:
    hasher = utils.Hasher(local_file)
    try:
        r = content.overwrite_file(node_id, local_file)
        sync.insert_node(r)
        node = query.get_node(r['id'])
        return compare_hashes(node.md5, hasher.get_result(), local_file)
    except RequestError as e:
        hasher.stop()
        logger.error('Error overwriting file. Code: %s, msg: %s' % (e.status_code, e.msg))
        return UL_DL_FAILED


def download(node_id: str, local_path: str, exclude: list) -> int:
    node = query.get_node(node_id)

    if not node.is_available():
        return 0

    if node.is_folder():
        return download_folder(node_id, local_path, exclude)

    loc_name = node.name

    # # downloading a non-cached node
    # if not loc_name:
    # loc_name = node_id

    for reg in exclude:
        if re.match(reg, loc_name):
            print('Skipping download of "%s" because of exclusion pattern.' % loc_name)
            return 0

    hasher = utils.IncrementalHasher()

    try:
        print('Current file: %s' % loc_name)
        content.download_file(node_id, loc_name, local_path, hasher.update)
    except RequestError as e:
        logger.error('Downloading "%s" failed. Code: %s, msg: %s' % (loc_name, e.status_code, e.msg))
        return UL_DL_FAILED

    return compare_hashes(hasher.get_result(), node.md5, loc_name)


def download_folder(node_id: str, local_path: str, exclude: list) -> int:
    if not local_path:
        local_path = os.getcwd()

    node = query.get_node(node_id)

    if node.name is None:
        curr_path = os.path.join(local_path, 'acd')
    else:
        curr_path = os.path.join(local_path, node.name)

    print('Current path: %s' % curr_path)
    try:
        os.makedirs(curr_path, exist_ok=True)
    except OSError:
        logger.error('Error creating directory "%s".' % curr_path)
        return ERR_CR_FOLDER

    children = sorted(node.children)
    ret_val = 0
    for child in children:
        if child.status != 'AVAILABLE':
            continue
        if child.is_file():
            ret_val |= download(child.id, curr_path, exclude)
        elif child.is_folder():
            ret_val |= download_folder(child.id, curr_path, exclude)

    return ret_val


def compare(local, remote):
    pass


#
# """Subparser actions"""
#

def sync_action(args: argparse.Namespace):
    print('Syncing... ')
    r = sync_node_list(full=args.full)
    print('Done.')
    return r


def old_sync_action(args: argparse.Namespace):
    print('Syncing...')
    r = old_sync()
    print('Done.')
    return r


def clear_action(args: argparse.Namespace):
    db.drop_all()


def tree_action(args: argparse.Namespace):
    tree = query.tree(args.node, args.include_trash)
    tree = query.ListFormatter.format(tree)
    for node in tree:
        print(node)


def usage_action(args: argparse.Namespace):
    r = account.get_account_usage()
    print(r, end='')


def quota_action(args: argparse.Namespace):
    r = account.get_quota()
    pprint(r)


def regex_helper(args: argparse.Namespace) -> list:
    """Pre-compiles regex from string"""
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


def upload_action(args: argparse.Namespace) -> int:
    excl_re = regex_helper(args)

    ret_val = 0
    for path in args.path:
        if not os.path.exists(path):
            logger.error('Path "%s" does not exist.' % path)
            ret_val |= INVALID_ARG_RETVAL
            continue

        ret_val |= upload(path, args.parent, args.overwrite, args.force, excl_re)

    return ret_val


def overwrite_action(args: argparse.Namespace) -> int:
    if os.path.isfile(args.file):
        return overwrite(args.node, args.file)
    else:
        logger.error('Invalid file.')
        return INVALID_ARG_RETVAL


def download_action(args: argparse.Namespace) -> int:
    excl_re = regex_helper(args)

    return download(args.node, args.path, excl_re)


def create_action(args: argparse.Namespace) -> int:
    parent, folder = os.path.split(args.new_folder)
    # no trailing slash
    if not folder:
        parent, folder = os.path.split(parent)

    if not folder:
        logger.error('Cannot create folder with empty name.')
        return INVALID_ARG_RETVAL

    p_id = query.resolve_path(parent)
    if not p_id:
        logger.error('Invalid parent path "%s".' % parent)
        return INVALID_ARG_RETVAL

    try:
        r = content.create_folder(folder, p_id)
        sync.insert_folders([r])
    except RequestError as e:
        logger.debug(str(e.status_code) + e.msg)
        if e.status_code == 409:
            logger.warning('Folder "%s" already exists.' % folder)
        else:
            logger.error('Error creating folder "%s".' % folder)
            return ERR_CR_FOLDER


def list_trash_action(args: argparse.Namespace):
    t_list = query.list_trash(args.recursive)
    t_list = query.ListFormatter.format(t_list)
    for node in t_list:
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


def resolve_action(args: argparse.Namespace) -> int:
    node = query.resolve_path(args.path)
    if node:
        print(node)
    else:
        return INVALID_ARG_RETVAL


def find_action(args: argparse.Namespace):
    r = query.find(args.name)
    r = query.ListFormatter.format(r)
    for node in r:
        print(node)
    if not r:
        return INVALID_ARG_RETVAL


def find_md5_action(args: argparse.Namespace):
    nodes = query.find_md5(args.md5)
    nodes = query.ListFormatter.format(nodes)
    for node in nodes:
        print(node)


def children_action(args: argparse.Namespace) -> int:
    c_list = query.list_children(args.node, args.recursive, args.include_trash)
    c_list = query.ListFormatter.format(c_list)
    if c_list:
        for entry in c_list:
            print(entry)
    else:
        return 1


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
                logger.warning('Error moving cache file "%s" from "%s" to "%s".' % (file, old_dir, CACHE_PATH))


def resolve_remote_path_args(args: argparse.Namespace, attrs: list, exclude_actions: list):
    """Replaces certain attributes in Namespace by resolved node ID."""
    for id_attr in attrs:
        if hasattr(args, id_attr):
            val = getattr(args, id_attr)
            if not val:
                continue
            if '/' in val:
                incl_trash = args.action not in exclude_actions
                v = query.resolve_path(val, trash=incl_trash)
                if not v:
                    logger.error('Could not resolve path "%s".' % val)
                    sys.exit(INVALID_ARG_RETVAL)
                logger.info('Resolved "%s" to "%s"' % (val, v))
                setattr(args, id_attr, v)
            elif len(val) != 22:
                logger.critical('Invalid ID format: "%s".' % val)
                sys.exit(INVALID_ARG_RETVAL)


def set_log_level(args: argparse.Namespace):
    format_ = '%(asctime)s.%(msecs).03d [%(name)s] [%(levelname)s] - %(message)s'
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

        logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)
        logging.getLogger('sqlalchemy.orm').setLevel(logging.DEBUG)


def main():
    opt_parser = argparse.ArgumentParser(
        formatter_class=argparse.RawTextHelpFormatter,
        epilog='Hints: \n'
               '  * Remote locations may be specified as path in most cases, e.g. "/folder/file", or via ID \n'
               '  * If you need to enter a node ID that contains a leading dash (minus) sign, '
               'precede it by two dashes and a space, e.g. \'-- -xfH...\'\n'
               '  * actions marked with [+] have optional arguments'
               '')
    opt_parser.add_argument('-v', '--verbose', action='count',
                            help='prints some info messages to stderr; use "-vv" to also get sqlalchemy info.')
    opt_parser.add_argument('-d', '--debug', action='store_true', help='turn on debug mode')
    opt_parser.add_argument('-nw', '--no-wait', action='store_true', help=argparse.SUPPRESS)

    subparsers = opt_parser.add_subparsers(title='action', dest='action')
    subparsers.required = True

    sync_sp = subparsers.add_parser('sync', aliases=['s'],
                                    help='[+] refresh node list cache; necessary for many actions')
    sync_sp.add_argument('--full', '-f', action='store_true', help='force a full sync')
    sync_sp.set_defaults(func=sync_action)

    old_sync_sp = subparsers.add_parser('old-sync', help='old (full) syncing')
    old_sync_sp.set_defaults(func=old_sync_action)

    clear_sp = subparsers.add_parser('clear-cache', aliases=['cc'], help='clear node cache [offline operation]')
    clear_sp.set_defaults(func=clear_action)

    tree_sp = subparsers.add_parser('tree', aliases=['t'],
                                    help='[+] print directory tree [offline operation]')
    tree_sp.add_argument('--include-trash', '-t', action='store_true')
    tree_sp.add_argument('node', nargs='?', default=None, help='root node for the tree')
    tree_sp.set_defaults(func=tree_action)

    list_c_sp = subparsers.add_parser('children', aliases=['ls', 'dir'],
                                      help='[+] list folder\'s children [offline operation]')
    list_c_sp.add_argument('--include-trash', '-t', action='store_true')
    list_c_sp.add_argument('--recursive', '-r', action='store_true')
    list_c_sp.add_argument('node')
    list_c_sp.set_defaults(func=children_action)

    find_sp = subparsers.add_parser('find', aliases=['f'],
                                    help='find nodes by name [offline operation] [case insensitive]')
    find_sp.add_argument('name')
    find_sp.set_defaults(func=find_action)

    find_hash_sp = subparsers.add_parser('find-md5', aliases=['fh'], help='find files by MD5 hash [offline operation]')
    find_hash_sp.add_argument('md5')
    find_hash_sp.set_defaults(func=find_md5_action)

    re_dummy_sp = subparsers.add_parser('dummy', add_help=False)
    re_dummy_sp.add_argument('--exclude-ending', '-xe', action='append', dest='exclude_fe', default=[],
                             help='exclude files whose endings match the given string, e.g. "bak" [case insensitive]')
    re_dummy_sp.add_argument('--exclude-regex', '-xr', action='append', dest='exclude_re', default=[],
                             help='exclude files whose names match the given regular expression,'
                                  ' e.g. "^thumbs\.db$" [case insensitive]')

    upload_sp = subparsers.add_parser('upload', aliases=['ul'], parents=[re_dummy_sp],
                                      help='[+] file and directory upload to a remote destination')
    upload_sp.add_argument('--overwrite', '-o', action='store_true',
                           help='overwrite if local modification time is higher or local ctime is higher than remote '
                                'modification time and local/remote file sizes do not match.')
    upload_sp.add_argument('--force', '-f', action='store_true', help='force overwrite')
    upload_sp.add_argument('path', nargs='+', help='a path to a local file or directory')
    upload_sp.add_argument('parent', help='remote parent folder')
    upload_sp.set_defaults(func=upload_action)

    overwrite_sp = subparsers.add_parser('overwrite', aliases=['ov'],
                                         help='overwrite file A [remote] with content of file B [local]')
    overwrite_sp.add_argument('node')
    overwrite_sp.add_argument('file')
    overwrite_sp.set_defaults(func=overwrite_action)

    download_sp = subparsers.add_parser('download', aliases=['dl'], parents=[re_dummy_sp],
                                        help='download a remote folder or file; will overwrite local files')
    download_sp.add_argument('node')
    download_sp.add_argument('path', nargs='?', default=None, help='local download path [optional]')
    download_sp.set_defaults(func=download_action)

    cr_fo_sp = subparsers.add_parser('create', aliases=['c', 'mkdir'], help='create folder using an absolute path')
    cr_fo_sp.add_argument('new_folder', help='an absolute folder path, e.g. "/my/dir/"; trailing slash is optional')
    cr_fo_sp.set_defaults(func=create_action)

    trash_sp = subparsers.add_parser('list-trash', aliases=['lt'],
                                     help='[+] list trashed nodes [offline operation]')
    trash_sp.add_argument('--recursive', '-r', action='store_true')
    trash_sp.set_defaults(func=list_trash_action)

    m_trash_sp = subparsers.add_parser('trash', aliases=['rm'], help='move node to trash')
    m_trash_sp.add_argument('node')
    m_trash_sp.set_defaults(func=trash_action)

    rest_sp = subparsers.add_parser('restore', aliases=['re'], help='restore from trash')
    rest_sp.add_argument('node', help='ID of the node')
    rest_sp.set_defaults(func=restore_action)

    move_sp = subparsers.add_parser('move', aliases=['mv'], help='move node A into folder B')
    move_sp.add_argument('child')
    move_sp.add_argument('parent')
    move_sp.set_defaults(func=move_action)

    rename_sp = subparsers.add_parser('rename', aliases=['rn'], help='rename a node')
    rename_sp.add_argument('node')
    rename_sp.add_argument('name')
    rename_sp.set_defaults(func=rename_action)

    res_sp = subparsers.add_parser('resolve', aliases=['rs'], help='resolve a path to a node ID')
    res_sp.add_argument('path')
    res_sp.set_defaults(func=resolve_action)

    # maybe the child operations should not be exposed
    # they can be used for creating hardlinks
    add_c_sp = subparsers.add_parser('add-child', aliases=['ac'], help='add a node to a parent folder')
    add_c_sp.add_argument('parent')
    add_c_sp.add_argument('child')
    add_c_sp.set_defaults(func=add_child_action)

    rem_c_sp = subparsers.add_parser('remove-child', aliases=['rc'], help='remove a node from a parent folder')
    rem_c_sp.add_argument('parent')
    rem_c_sp.add_argument('child')
    rem_c_sp.set_defaults(func=remove_child_action)

    usage_sp = subparsers.add_parser('usage', aliases=['u'], help='show drive usage data')
    usage_sp.set_defaults(func=usage_action)

    quota_sp = subparsers.add_parser('quota', aliases=['q'], help='show drive quota [raw JSON]')
    quota_sp.set_defaults(func=quota_action)

    meta_sp = subparsers.add_parser('metadata', aliases=['m'], help='print a node\'s metadata [raw JSON]')
    meta_sp.add_argument('node')
    meta_sp.set_defaults(func=metadata_action)

    # useful for interactive mode
    dn_sp = subparsers.add_parser('init', aliases=['i'], add_help=False)
    dn_sp.set_defaults(func=None)

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

    migrate_cache_files()

    # offline actions
    if args.func not in [clear_action, tree_action, children_action, list_trash_action, find_action, resolve_action]:
        if not common.init(CACHE_PATH):
            sys.exit(INIT_FAILED_RETVAL)

    # online actions
    if args.func not in [usage_action, quota_action]:
        db.init(CACHE_PATH)

    if args.no_wait:
        common.BackOffRequest._wait = lambda: None

    autoresolve_attrs = ['child', 'parent', 'node']
    resolve_remote_path_args(args, autoresolve_attrs, [upload_action, list_trash_action])

    # call appropriate sub-parser action
    if args.func:
        sys.exit(args.func(args))


if __name__ == "__main__":
    main()

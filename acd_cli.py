#!/usr/bin/env python3
import sys
import os
import json
import argparse
import logging
import signal
import datetime
import re

from cache import sync, query, db
from acd import common, content, metadata, account, trash
from acd.common import RequestError
import utils

__version__ = '0.1.3'

# TODO: this should be xdg conforming
CACHE_PATH = os.path.dirname(os.path.realpath(__file__))
SETTINGS_PATH = CACHE_PATH

logger = logging.getLogger(os.path.basename(__file__).split('.')[0])

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
    if not full:
        logger.info('Getting changes with checkpoint "%s".' % cp if cp else '')

    try:
        nodes, ncp = metadata.get_changes(checkpoint=None if full else cp)
    except RequestError:
        logger.critical('Sync failed.')

    logger.info('%i nodes in change list.' % len(nodes))
    if len(nodes) > 0:
        sync.insert_nodes(nodes, partial=not full)
    sync.set_checkpoint(ncp)
    return


def old_sync():
    try:
        folders = metadata.get_folder_list()
        folders.extend(metadata.get_trashed_folders())
        files = metadata.get_file_list()
        files.extend(metadata.get_trashed_files())
    except RequestError:
        logger.critical('Sync failed.')
        return

    sync.insert_folders(folders)
    sync.insert_files(files)
    sync.set_checkpoint('')


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
                logger.warning('Timeout while uploading "%s".')
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

def sync_action(args):
    print('Syncing... ')
    sync_node_list(full=args.full)
    print('Done.')


def old_sync_action(args):
    print('Syncing...')
    old_sync()
    print('Done.')


def clear_action(args):
    db.drop_all()


def tree_action(args):
    tree = query.tree(args.node, args.include_trash)
    for node in tree:
        print(node)


def usage_action(args):
    r = account.get_account_usage()
    print(r, end='')


def quota_action(args):
    r = account.get_quota()
    pprint(r)


def regex_helper(args):
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


def upload_action(args):
    excl_re = regex_helper(args)

    ret_val = 0
    for path in args.path:
        if not os.path.exists(path):
            logger.error('Path "%s" does not exist.' % path)
            ret_val |= INVALID_ARG_RETVAL
            continue

        ret_val |= upload(path, args.parent, args.overwrite, args.force, excl_re)

    sys.exit(ret_val)


def overwrite_action(args):
    if utils.is_uploadable(args.file):
        sys.exit(overwrite(args.node, args.file))
    else:
        logger.error('Invalid file.')
        sys.exit(INVALID_ARG_RETVAL)


def download_action(args):
    excl_re = regex_helper(args)

    sys.exit(download(args.node, args.path, excl_re))


# TODO
def open_action(args):
    import subprocess

    n = query.get_node(args.node)
    # mime = mimetypes.guess_type(n.simple_name())[0]
    #
    # appl = ''
    # try:
    # appl = subprocess.check_output(['gvfs-mime', '--query', mime]).decode('utf-8')
    # appl = (appl.splitlines()[0]).split(':')[1]
    # except FileNotFoundError:
    # return

    r = metadata.get_metadata(args.node)
    try:
        link = r['tempLink']
    except KeyError:
        logger.critical('Could not get temporary URL for "%s".' % n.simple_name())
        return SERVER_ERR

    if sys.platform == 'linux':
        subprocess.call(['mimeopen', '--no-ask', link + '#' + n.simple_name()])


def create_action(args):
    # TODO: try to resolve first

    parent, folder = os.path.split(args.new_folder)
    # no trailing slash
    if not folder:
        parent, folder = os.path.split(parent)

    if not folder:
        logger.error('Cannot create folder with empty name.')
        sys.exit(INVALID_ARG_RETVAL)

    p_id = query.resolve_path(parent)
    if not p_id:
        logger.error('Invalid parent path "%s".' % parent)
        sys.exit(INVALID_ARG_RETVAL)

    try:
        r = content.create_folder(folder, p_id)
        sync.insert_folders([r], True)
    except RequestError as e:
        if e.status_code == 409:
            logger.warning('Folder "%s" already exists.' % folder)
        else:
            logger.error('Error creating folder "%s".' % folder)
        logger.debug(str(e.status_code) + e.msg)


def list_trash_action(args):
    t_list = query.list_trash(args.recursive)
    if t_list:
        print('\n'.join(t_list))


def trash_action(args):
    r = trash.move_to_trash(args.node)
    sync.insert_node(r)


def restore_action(args):
    try:
        r = trash.restore(args.node)
    except RequestError as e:
        logger.error('Error restoring "%s"' % args.node, e)
        return
    sync.insert_node(r)


def resolve_action(args):
    print(query.resolve_path(args.path))


def find_action(args):
    r = query.find(args.name)
    for node in r:
        print(node)


def children_action(args):
    c_list = query.list_children(args.node, args.recursive, args.include_trash)
    if c_list:
        for entry in c_list:
            print(entry)


def move_action(args):
    r = metadata.move_node(args.child, args.parent)
    sync.insert_node(r)


def rename_action(args):
    r = metadata.rename_node(args.node, args.name)
    sync.insert_node(r)


def add_child_action(args):
    r = metadata.add_child(args.parent, args.child)
    sync.insert_node(r)


def remove_child_action(args):
    r = metadata.remove_child(args.parent, args.child)
    sync.insert_node(r)


def metadata_action(args):
    r = metadata.get_metadata(args.node)
    pprint(r)


class Argument(object):
    """"""
    args = None
    kwargs = None

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def attach(self, subparser: argparse._ActionsContainer):
        subparser.add_argument(*self.args, **self.kwargs)


def main():
    opt_parser = argparse.ArgumentParser(
        formatter_class=argparse.RawTextHelpFormatter,
        epilog='Hints: \n'
               '  * Remote locations may be specified as path in most cases, e.g. "/folder/file", or via ID \n'
               '  * If you need to enter a node ID that contains a leading dash (minus) sign, '
               'precede it by two dashes and a space, e.g. \'-- -xfH...\'\n'
               '  * actions marked with [+] have optional arguments'
               '')
    opt_parser.add_argument('-v', '--verbose', action='store_true', help='print more stuff')
    opt_parser.add_argument('-d', '--debug', action='store_true', help='turn on debug mode')
    opt_parser.add_argument('-nw', '--no-wait', action='store_true', help=argparse.SUPPRESS)

    subparsers = opt_parser.add_subparsers(dest='action')
    subparsers.required = True

    sync_sp = subparsers.add_parser('sync', aliases=['s'],
                                    help='[+] refresh node list cache; necessary for many actions')
    sync_sp.add_argument('--full', '-f', action='store_true', help='force a full sync')
    sync_sp.set_defaults(func=sync_action)

    old_sync_sp = subparsers.add_parser('old-sync', help='old (full) syncing')
    old_sync_sp.set_defaults(func=old_sync_action)

    clear_nms = ['clear-cache', 'cc']
    clear_sp = subparsers.add_parser(clear_nms[0], aliases=clear_nms[1:], help='clear node cache [offline operation]')
    clear_sp.set_defaults(func=clear_action)

    tree_nms = ['tree', 't']
    tree_sp = subparsers.add_parser(tree_nms[0], aliases=tree_nms[1:],
                                    help='[+] print directory tree [offline operation]')
    tree_sp.add_argument('--include-trash', '-t', action='store_true')
    tree_sp.add_argument('node', nargs='?', default=None, help='root node for the tree')
    tree_sp.set_defaults(func=tree_action)

    xe_arg = Argument('--exclude-ending', '-xe', action='append', dest='exclude_fe', default=[],
                      help='exclude files whose endings match the given string, e.g. "bak" [case insensitive]')
    xr_arg = Argument('--exclude-regex', '-xr', action='append', dest='exclude_re', default=[],
                      help='exclude files whose names match the given regular expression,'
                           ' e.g. "^thumbs\.db$" [case insensitive]')

    upload_nms = ['upload', 'ul']
    upload_sp = subparsers.add_parser(upload_nms[0], aliases=upload_nms[1:],
                                      help='[+] file and directory upload to a remote destination')
    upload_sp.add_argument('--overwrite', '-o', action='store_true',
                           help='overwrite if local modification time is higher or local ctime is higher than remote '
                                'modification time and local/remote file sizes do not match.')
    upload_sp.add_argument('--force', '-f', action='store_true', help='force overwrite')
    xe_arg.attach(upload_sp)
    xr_arg.attach(upload_sp)
    upload_sp.add_argument('path', nargs='+', help='a path to a local file or directory')
    upload_sp.add_argument('parent', help='remote parent folder')
    upload_sp.set_defaults(func=upload_action)

    overwrite_sp = subparsers.add_parser('overwrite', aliases=['ov'],
                                         help='overwrite file A [remote] with content of file B [local]')
    overwrite_sp.add_argument('node')
    overwrite_sp.add_argument('file')
    overwrite_sp.set_defaults(func=overwrite_action)

    download_sp = subparsers.add_parser('download', aliases=['dl'],
                                        help='download a remote folder or file; will overwrite local files')
    xe_arg.attach(download_sp)
    xr_arg.attach(download_sp)
    download_sp.add_argument('node')
    download_sp.add_argument('path', nargs='?', default=None, help='local download path [optional]')
    download_sp.set_defaults(func=download_action)

    open_sp = subparsers.add_parser('open', aliases=['o'], help='open node [experimental]')
    open_sp.add_argument('node')
    open_sp.set_defaults(func=open_action)

    cr_fo_sp = subparsers.add_parser('create', aliases=['c', 'mkdir'], help='create folder using an absolute path')
    cr_fo_sp.add_argument('new_folder', help='an absolute folder path, e.g. "/my/dir/"; trailing slash is optional')
    cr_fo_sp.set_defaults(func=create_action)

    ls_trash_nms = ['list-trash', 'lt']
    trash_sp = subparsers.add_parser(ls_trash_nms[0], aliases=ls_trash_nms[1:],
                                     help='[+] list trashed nodes [offline operation]')
    trash_sp.add_argument('--recursive', '-r', action='store_true')
    trash_sp.set_defaults(func=list_trash_action)

    trash_nms = ['trash', 'rm']
    m_trash_sp = subparsers.add_parser(trash_nms[0], aliases=trash_nms[1:], help='move node to trash')
    m_trash_sp.add_argument('node')
    m_trash_sp.set_defaults(func=trash_action)

    rest_sp = subparsers.add_parser('restore', aliases=['re'], help='restore from trash')
    rest_sp.add_argument('node', help='ID of the node')
    rest_sp.set_defaults(func=restore_action)

    children_nms = ['children', 'ls']
    list_c_sp = subparsers.add_parser(children_nms[0], aliases=children_nms[1:],
                                      help='[+] list folder\'s children [offline operation]')
    list_c_sp.add_argument('--include-trash', '-t', action='store_true')
    list_c_sp.add_argument('--recursive', '-r', action='store_true')
    list_c_sp.add_argument('node')
    list_c_sp.set_defaults(func=children_action)

    move_sp = subparsers.add_parser('move', aliases=['mv'], help='move node A into folder B')
    move_sp.add_argument('child')
    move_sp.add_argument('parent')
    move_sp.set_defaults(func=move_action)

    rename_sp = subparsers.add_parser('rename', aliases=['rn'], help='rename a node')
    rename_sp.add_argument('node')
    rename_sp.add_argument('name')
    rename_sp.set_defaults(func=rename_action)

    resolve_nms = ['resolve', 'rs']
    res_sp = subparsers.add_parser(resolve_nms[0], aliases=resolve_nms[1:], help='resolve a path to a node ID')
    res_sp.add_argument('path')
    res_sp.set_defaults(func=resolve_action)

    find_nms = ['find', 'f']
    find_sp = subparsers.add_parser(find_nms[0], aliases=find_nms[1:],
                                    help='find nodes by name [offline operation] [case insensitive]')
    find_sp.add_argument('name')
    find_sp.set_defaults(func=find_action)

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

    # chn_sp = subparsers.add_parser('changes', aliases=['ch'], help='list changes (raw JSON)')
    # chn_sp.set_defaults(func=changes_action)

    args = opt_parser.parse_args()

    format_ = '%(asctime)s.%(msecs).03d [%(name)s] [%(levelname)s] - %(message)s'
    time_fmt = '%y-%m-%d %H:%M:%S'

    if not args.verbose and not args.debug:
        logging.basicConfig(level=logging.WARNING, format=format_, datefmt=time_fmt)

    if args.verbose:
        logging.basicConfig(level=logging.INFO, format=format_, datefmt=time_fmt)
        logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
        logging.getLogger('sqlalchemy.orm').setLevel(logging.INFO)
    elif args.debug:
        logging.basicConfig(level=logging.DEBUG, format=format_, datefmt=time_fmt)

        # these debug messages (prints) will not show up in log file
        import http.client

        http.client.HTTPConnection.debuglevel = 1

        r_logger = logging.getLogger("requests")
        r_logger.setLevel(logging.DEBUG)
        r_logger.propagate = True

        logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)
        logging.getLogger('sqlalchemy.orm').setLevel(logging.DEBUG)

    # offline actions
    if args.action not in clear_nms + tree_nms + children_nms + ls_trash_nms + find_nms + resolve_nms:
        if not common.init(CACHE_PATH):
            sys.exit(INIT_FAILED_RETVAL)

    db.init(CACHE_PATH)

    if args.no_wait:
        common.BackOffRequest._wait = lambda: None

    # auto-resolve node paths
    for id_attr in ['child', 'parent', 'node']:
        if hasattr(args, id_attr):
            val = getattr(args, id_attr)
            if not val:
                continue
            if '/' in val:
                incl_trash = args.action not in upload_nms + trash_nms
                v = query.resolve_path(val, trash=incl_trash)
                if not v:
                    logger.error('Could not resolve path "%s".' % val)
                    sys.exit(INVALID_ARG_RETVAL)
                logger.info('Resolved "%s" to "%s"' % (val, v))
                setattr(args, id_attr, v)
            elif len(val) != 22:
                logger.error('Invalid ID format: "%s".' % val)
                sys.exit(INVALID_ARG_RETVAL)

    # call appropriate sub-parser action
    args.func(args)


if __name__ == "__main__":
    main()

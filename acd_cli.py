#!/usr/bin/env python3
import sys
import os
import json
import argparse
import logging
import subprocess
import signal

from cache import sync, selection, db
from acd import oauth, content, metadata, account, trash, changes
from acd.common import RequestError
import utils

__version__ = '0.1.2'

logger = logging.getLogger(os.path.basename(__file__).split('.')[0])
sh = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s  [%(name)s] [%(levelname)s] - %(message)s')
sh.setFormatter(formatter)
logger.addHandler(sh)

INVALID_ARG_RETVAL = 2
KEYBOARD_INTERRUPT = 3


def signal_handler(signal, frame):
    db.session.rollback()
    sys.exit(KEYBOARD_INTERRUPT)

signal.signal(signal.SIGINT, signal_handler)


def pprint(s):
    print(json.dumps(s, indent=4))


def sync_node_list():
    try:
        folders = metadata.get_folder_list()
        folders.extend(metadata.get_trashed_folders())
        files = metadata.get_file_list()
        files.extend(metadata.get_trashed_files())
    except RequestError:
        print('Sync failed.')
        return

    sync.insert_folders(folders)
    sync.insert_files(files)


def upload(path, parent_id, overwr, force):
    if not os.access(path, os.R_OK):
        print('Path %s not accessible.' % path)
        return

    if os.path.isdir(path):
        print('Current directory: %s' % path)
        upload_folder(path, parent_id, overwr, force)
    elif os.path.isfile(path):
        print('Current file: %s' % path)
        upload_file(path, parent_id, overwr, force)


def upload_file(path, parent_id, overwr, force):
    hasher = utils.Hasher(path)
    short_nm = os.path.basename(path)

    cached_file = selection.get_node(parent_id).get_child(short_nm)
    if cached_file:
        file_id = cached_file.id
    else:
        file_id = None

    if not file_id:
        try:
            r = content.upload_file(path, parent_id)
            sync.insert_node(r)
            file_id = r['id']
        except RequestError as e:
            if e.status_code == 409:  # might happen if cache is outdated
                print('Uploading %s failed. Name collision with non-cached file. '
                      'If you want to overwrite, please sync and try again.')
                # colliding node ID is returned in error message -> could be used to continue
                return
            else:
                hasher.__stop__()
                print('Uploading "%s" failed. Code: %s, msg: %s' % (short_nm, e.status_code, e.msg))
                return
    else:
        if not overwr and not force:
            print('Skipping upload of existing file "%s".' % short_nm)
            hasher.__stop__()
            return

        if cached_file.size < os.path.getsize(path) or force:
            overwrite(file_id, path)
        elif not force:
            print('Skipping upload of "%s", because local file is smaller or of same size.')

    # might have changed
    cached_file = selection.get_node(file_id)

    if hasher.get_result() != cached_file.md5:
        print('Hash mismatch between local and remote file for "%s".' % short_nm)


def upload_folder(folder, parent_id, overwr, force):
    if parent_id is None:
        parent_id = selection.get_root_id()
    parent = selection.get_node(parent_id)

    real_path = os.path.realpath(folder)
    short_nm = os.path.basename(real_path)

    curr_node = parent.get_child(short_nm)
    if not curr_node or curr_node.status == 'TRASH':
        try:
            r = content.create_folder(short_nm, parent_id)
            sync.insert_node(r)
            curr_node = selection.get_node(r['id'])
        except RequestError as e:
            print('Error creating remote folder "%s.' % short_nm)
            if e.status_code == 409:
                print('Folder already exists. Please sync.')
                logger.error(e)
            return

    elif curr_node.is_file():
        print('Cannot create remote folder "%s", because a file of the same name already exists.' % short_nm)
        return

    entries = os.listdir(folder)

    for entry in entries:
        full_path = os.path.join(real_path, entry)
        upload(full_path, curr_node.id, overwr, force)


def overwrite(node_id, local_file):
    hasher = utils.Hasher(local_file)
    try:
        r = content.overwrite_file(node_id, local_file)
        sync.insert_node(r)
        if r['contentProperties']['md5'] != hasher.get_result():
            print('Hash mismatch between local and remote file for "%s".' % local_file)
    except RequestError as e:
        hasher.__stop__()
        print('Error overwriting file. Code: %s, msg: %s' % (e.status_code, e.msg))


def download(node_id, local_path):
    node = selection.get_node(node_id)

    if node.is_folder():
        download_folder(node_id, local_path)
        return
    loc_name = node.name
    # downloading a non-cached node
    if not loc_name:
        loc_name = node_id
    hasher = utils.IncrementalHasher()

    try:
        content.download_file(node_id, loc_name, local_path, hasher.update)
    except RequestError as e:
        print('Downloading "%s" failed. Code: %s, msg: %s' % (loc_name, e.status_code, e.msg))
        print()

    if hasher.get_result() != node.md5:
        print('Hash mismatch between local and remote file for "%s".' % loc_name)


def download_folder(node_id, local_path):
    if not local_path:
        local_path = os.getcwd()

    node = selection.get_node(node_id)

    curr_path = os.path.join(local_path, node.name)
    try:
        os.makedirs(curr_path, exist_ok=True)
    except OSError:
        print('Error creating directory "%s".' % curr_path)
        return
    children = node.children
    for child in children:
        if child.is_file():
            download(child.id, curr_path)
        elif child.is_folder():
            download_folder(child.id, curr_path)


def compare(local, remote):
    pass


#
# """Subparser actions"""
#

def sync_action(args):
    print('Syncing... ', end='')
    sys.stdout.flush()
    sync_node_list()
    print('Done.')


def clear_action(args):
    db.drop_all()


def tree_action(args):
    tree = selection.node_list(trash=args.include_trash)
    for node in tree:
        print(node)


def usage_action(args):
    r = account.get_account_usage()
    pprint(r)


def quota_action(args):
    args
    r = account.get_quota()
    pprint(r)


def upload_action(args):

    for path in args.path:
        if not os.path.exists(path):
            print('Path "%s" does not exist.' % path)
            continue

        upload(path, args.parent, args.overwrite, args.force)


def overwrite_action(args):
    if utils.is_uploadable(args.file):
        overwrite(args.node, args.file)
    else:
        print('Invalid file.')
        sys.exit(INVALID_ARG_RETVAL)


def download_action(args):
    loc_path = None
    try:
        loc_path = args.path
    except IndexError:
        pass
    download(args.node, loc_path)


# TODO: check os
def stream_action(args):
    r = metadata.get_metadata(args.node)
    link = r['tempLink']
    subprocess.call(['xdg-open', link])


def create_action(args):
    parent, folder = os.path.split(args.new_folder)
    if not folder:
        parent, folder = os.path.split(parent)

    p_path = selection.resolve_path(parent)
    if not p_path:
        print('Invalid parent path.')
        sys.exit(INVALID_ARG_RETVAL)

    try:
        r = content.create_folder(folder, p_path)
        sync.insert_folders([r], True)
    except RequestError as e:
        if e.status_code == 409:
            print('Folder "%s" already exists.' % folder)
        else:
            print('Error creating folder "%s".' % folder)
        logger.debug(str(e.status_code) + e.msg)


def list_trash_action(args):
    t_list = selection.list_trash(args.recursive)
    if t_list:
        print('\n'.join(t_list))


def trash_action(args):
    r = trash.move_to_trash(args.node)
    sync.insert_node(r)


def restore_action(args):
    r = trash.restore(args.node)
    sync.insert_node(r)


def resolve_action(args):
    print(selection.resolve_path(args.path))


def children_action(args):
    c_list = selection.list_children(args.node, args.recursive, args.include_trash)
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


def changes_action(args):
    r = changes.get_changes()
    pprint(r)


def metadata_action(args):
    r = metadata.get_metadata(args.node)
    pprint(r)


def main():
    opt_parser = argparse.ArgumentParser(
        epilog='Hint: If you need to enter a node id that contains a leading dash (minus) sign, ' +
               'precede it by two dashes and a space, e.g. \'-- -xfH...\'')
    opt_parser.add_argument('--verbose', '-v', action='store_true', help='print more stuff')
    opt_parser.add_argument('--debug', '-d', action='store_true', help='turn on debug mode')

    subparsers = opt_parser.add_subparsers(dest='action')
    subparsers.required = True

    sync_sp = subparsers.add_parser('sync', aliases=['s'], help='refresh node list cache; necessary for many actions')
    sync_sp.set_defaults(func=sync_action)

    clear_sp = subparsers.add_parser('clear-cache', aliases=['cc'], help='clear node cache')
    clear_sp.set_defaults(func=clear_action)

    tree_sp = subparsers.add_parser('tree', aliases=['t'], help='print directory tree [uses cached data]')
    tree_sp.add_argument('--include-trash', '-t', action='store_true')
    tree_sp.set_defaults(func=tree_action)

    upload_sp = subparsers.add_parser('upload', aliases=['ul'],
                                      help='file and directory upload to a remote destination')
    upload_sp.add_argument('--overwrite', '-o', action='store_true', help='overwrite smaller remote files')
    upload_sp.add_argument('--force', '-f', action='store_true', help='force overwrite')
    upload_sp.add_argument('path', nargs="*", help='a path to a local file or directory')
    upload_sp.add_argument('parent', help='remote parent folder')
    upload_sp.set_defaults(func=upload_action)

    overwrite_sp = subparsers.add_parser('overwrite', aliases=['ov'],
                                         help='overwrite node A [remote] with file B [local]')
    overwrite_sp.add_argument('node')
    overwrite_sp.add_argument('file')
    overwrite_sp.set_defaults(func=overwrite_action)

    download_sp = subparsers.add_parser('download', aliases=['dl'],
                                        help='download a remote file; will overwrite local files')
    download_sp.add_argument('node')
    download_sp.add_argument('path', nargs='?', help='local download path')
    download_sp.set_defaults(func=download_action)

    # stream_sp = subparsers.add_parser('stream')
    # stream_sp.add_argument('node')
    # stream_sp.set_defaults(func=stream_action)

    cr_fo_sp = subparsers.add_parser('create', aliases=['c', 'mkdir'], help='create folder')
    cr_fo_sp.add_argument('new_folder')
    cr_fo_sp.set_defaults(func=create_action)

    trash_sp = subparsers.add_parser('list-trash', aliases=['lt'], help='list trashed nodes [uses cached data]')
    trash_sp.add_argument('--recursive', '-r', action='store_true')
    trash_sp.set_defaults(func=list_trash_action)

    m_trash_sp = subparsers.add_parser('trash', aliases=['tr'], help='move to trash')
    m_trash_sp.add_argument('node')
    m_trash_sp.set_defaults(func=trash_action)

    rest_sp = subparsers.add_parser('restore', aliases=['re'], help='restore from trash')
    rest_sp.add_argument('node', help='id of the node')
    rest_sp.set_defaults(func=resolve_action)

    list_c_sp = subparsers.add_parser('children', aliases=['ls'], help='list folder\'s children [uses cached data]')
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

    res_sp = subparsers.add_parser('resolve', aliases=['rs'], help='resolve a path to a node id')
    res_sp.add_argument('path')
    res_sp.set_defaults(func=resolve_action)

    # maybe the child operations should not be exposed
    # they can be used for creating hardlinks
    add_c_sp = subparsers.add_parser('add-child', help='add a node to a parent folder')
    add_c_sp.add_argument('parent')
    add_c_sp.add_argument('child')
    add_c_sp.set_defaults(func=add_child_action)

    rem_c_sp = subparsers.add_parser('remove-child', help='remove a node from a parent folder')
    rem_c_sp.add_argument('parent')
    rem_c_sp.add_argument('child')
    rem_c_sp.set_defaults(func=remove_child_action)

    usage_sp = subparsers.add_parser('usage', help='show drive usage data')
    usage_sp.set_defaults(func=usage_action)

    quota_sp = subparsers.add_parser('quota', help='show drive quota')
    quota_sp.set_defaults(func=quota_action)

    meta_sp = subparsers.add_parser('metadata', help='print a node\'s metadata')
    meta_sp.add_argument('node')
    meta_sp.set_defaults(func=metadata_action)

    chn_sp = subparsers.add_parser('changes', help='list changes')
    chn_sp.set_defaults(func=changes_action)

    args = opt_parser.parse_args()

    if args.action not in ['tree', 'children', 'list-trash']:
        oauth.get_data()

    # if args.action in ['create', 'resolve', 'upload'] and not selection.get_root_node():
    #     print('Cache empty. Forcing sync.')
    #     sync_action()

    # TODO: resolve unique names
    # auto-resolve node paths
    for id_attr in ['child', 'parent', 'node']:
        if hasattr(args, id_attr):
            val = getattr(args, id_attr)
            if not val:
                continue
            if '/' in val:
                val = selection.resolve_path(val)
                if not val:
                    print('Could not resolve path.')
                    sys.exit(INVALID_ARG_RETVAL)
                setattr(args, id_attr, val)
            elif len(val) != 22:
                print('Invalid ID format.')
                sys.exit(INVALID_ARG_RETVAL)

    if not args.debug and not args.verbose:
        logging.basicConfig(level=logging.WARNING)
    elif args.verbose:
        logging.basicConfig(level=logging.INFO)
        logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
        logging.getLogger('sqlalchemy.orm').setLevel(logging.INFO)
    else:
        logging.basicConfig(level=logging.DEBUG)

        # these debug messages (prints) will not show up in log file
        import http.client
        http.client.HTTPConnection.debuglevel = 1

        r_logger = logging.getLogger("requests")
        r_logger.setLevel(logging.DEBUG)
        r_logger.propagate = True

        logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)
        logging.getLogger('sqlalchemy.orm').setLevel(logging.DEBUG)

        # handler = logging.FileHandler(os.path.basename(__file__).split('.')[0] + '.log')
        # handler.setLevel(logging.DEBUG)
        #
        # formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        # handler.setFormatter(formatter)
        #
        # logging.getLogger().addHandler(handler)

    # call appropriate sub-parser action
    args.func(args)


if __name__ == "__main__":
    main()

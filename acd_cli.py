#!/usr/bin/env python3
import sys
import os
import json
import argparse
import subprocess

from cache import sync, selection, db
from acd import oauth, content, metadata, account, trash, changes
from acd.common import RequestError
import utils

__version__ = '0.1.2'

INVALID_ARG_RETVAL = 2


def pprint(s):
    print(json.dumps(s, indent=4))


def sync_node_list():
    try:
        folders = metadata.get_folder_list()
        folders.extend(metadata.get_trashed_folders())
        files = metadata.get_file_list()
        files.extend(metadata.get_trashed_files())
    except RequestError:
        print('Aborting sync.')
        raise

    sync.insert_folders(folders)
    sync.insert_files(files)


def upload(path, parent_id):
    if os.path.isdir(path):
        upload_folder(path, parent_id)
        return
    if utils.is_uploadable(path):
        # TODO: check cache for existing child node
        hasher = utils.Hasher(path)
        short_nm = os.path.basename(path)
        file_id = None
        try:
            r = content.upload_file(path, parent_id)
            sync.insert_node(r)
            file_id = r['id']
        except RequestError as e:
            if e.status_code == 409:  # might happen, if cache is outdated
                print('Skipping upload of existing file "%s".' % short_nm)
                file_id = selection.get_node(parent_id).get_child(short_nm).id
            else:
                print('Uploading "%s" failed. Code: %s, msg: %s' % e.status_code, e.msg)
                return

        cache_file = selection.get_node(file_id)

        if hasher.get_result() != cache_file.md5:
            print('Hash mismatch between local and remote file for "%s".' % short_nm)
            # pprint(r)
    else:
        print('Invalid path.')
        sys.exit(INVALID_ARG_RETVAL)


def upload_folder(folder, parent_id):
    if parent_id is None:
        parent_id = selection.get_root_id()
    parent = selection.get_node(parent_id)

    real_path = os.path.realpath(folder)
    short_nm = os.path.basename(real_path)

    curr_node = parent.get_child(short_nm)
    if not curr_node:
        try:
            r = content.create_folder(short_nm, parent_id)
            sync.insert_node(r)
            curr_node = selection.get_node(r['id'])
        except RequestError:
            print('Error creating folder "%s.' % short_nm)
            return

    elif curr_node.is_file():
        print('Cannot create remote folder "%s", because a file of the same name already exists.' % short_nm)
        return

    entries = os.listdir(folder)

    for entry in entries:
        full_path = os.path.join(real_path, entry)
        if os.path.isdir(full_path):
            print('Current directory: ', folder)
            upload_folder(full_path, curr_node.id)
        elif os.path.isfile(full_path):
            upload(full_path, curr_node.id)


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
        print('Downloading "%" failed. Code: %s, msg: %s' % loc_name, e.status_code, e.msg)
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
    if args.action == 'sync':
        print('Syncing... ', end='')
        sys.stdout.flush()
        sync_node_list()
        print('Done.')


def clear_action(args):
    db.drop_all()


def tree_action(args):
    tree = selection.node_list(trash=args.include_trash)
    print('\n'.join(tree))


def usage_action(args):
    r = account.get_account_usage()
    pprint(r)


def quota_action(args):
    args
    r = account.get_quota()
    pprint(r)


def upload_action(args):
    parent = None
    try:
        parent = args.parent
    except IndexError:
        pass
    upload(args.file, parent)


def overwrite_action(args):
    if utils.is_uploadable(args.file):
        hasher = utils.Hasher(args.file)
        r = content.overwrite_file(args.node, args.file)
        # pprint(r)
        sync.insert_node(r)
        if r['contentProperties']['md5'] != hasher.get_result():
            print('Hash mismatch between local and remote file for "%s".' % args.file)
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

    r = content.create_folder(folder, p_path)
    # pprint(r)
    sync.insert_folders([r], True)


def list_trash_action(args):
    t_list = selection.list_trash(args.recursive)
    if t_list:
        print('\n'.join(t_list))


def trash_action(args):
    r = trash.move_to_trash(args.node)
    # pprint(r)

    sync.insert_node(r)


def restore_action(args):
    r = trash.restore(args.node)
    pprint(r)
    sync.insert_node(r)


def resolve_action(args):
    print(selection.resolve_path(args.path))


def children_action(args):
    c_list = selection.list_children(args.node, args.recursive, args.include_trash)
    if c_list:
        print('\n'.join(c_list))


def move_action(args):
    r = metadata.move_node(args.child, args.parent)
    # pprint(r)
    sync.insert_node(r)


def rename_action(args):
    print('Not implemented yet.')


def add_child_action(args):
    r = metadata.add_child(args.parent, args.child)
    # pprint(r)
    sync.insert_node(r)


def remove_child_action(args):
    r = metadata.remove_child(args.parent, args.child)
    # pprint(r)
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
    opt_parser.add_argument('--debug', action='store_true', help='turn on debug mode')

    subparsers = opt_parser.add_subparsers(dest='action')
    subparsers.required = True

    sync_sp = subparsers.add_parser('sync', help='refresh node list cache')
    sync_sp.set_defaults(func=sync_action)

    clear_sp = subparsers.add_parser('clear-cache', help='clear node cache')
    clear_sp.set_defaults(func=clear_action)

    tree_sp = subparsers.add_parser('tree', help='print directory tree')
    tree_sp.add_argument('--include-trash', '-t', action='store_true')
    tree_sp.set_defaults(func=tree_action)

    upload_sp = subparsers.add_parser('upload', aliases=['u'], help='upload a file or folder')
    upload_sp.add_argument('file', help='name of local file')
    upload_sp.add_argument('parent', nargs='?', help='parent folder (optional)')
    upload_sp.set_defaults(func=upload_action)

    overwrite_sp = subparsers.add_parser('overwrite', help='overwrite node A [remote] with file B [local]')
    overwrite_sp.add_argument('node')
    overwrite_sp.add_argument('file')
    overwrite_sp.set_defaults(func=overwrite_action)

    download_sp = subparsers.add_parser('download', help='download a remote file; will overwrite local files')
    download_sp.add_argument('node')
    download_sp.add_argument('path', nargs='?', help='local download path')
    download_sp.set_defaults(func=download_action)

    # stream_sp = subparsers.add_parser('stream')
    # stream_sp.add_argument('node')
    # stream_sp.set_defaults(func=stream_action)

    cr_fo_sp = subparsers.add_parser('create', help='create folder')
    cr_fo_sp.add_argument('new_folder')
    cr_fo_sp.set_defaults(func=create_action)

    trash_sp = subparsers.add_parser('list-trash', aliases=['lt'])
    trash_sp.add_argument('--recursive', '-r', action='store_true')
    trash_sp.set_defaults(func=list_trash_action)

    m_trash_sp = subparsers.add_parser('trash', help='move to trash')
    m_trash_sp.add_argument('node')
    m_trash_sp.set_defaults(func=trash_action)

    rest_sp = subparsers.add_parser('restore', help='restore from trash')
    rest_sp.add_argument('node', help='id of the node')
    rest_sp.set_defaults(func=resolve_action)

    list_c_sp = subparsers.add_parser('children', help='list folders\'s children')
    list_c_sp.add_argument('--include-trash', '-t', action='store_true')
    list_c_sp.add_argument('--recursive', '-r', action='store_true')
    list_c_sp.add_argument('node')
    list_c_sp.set_defaults(func=children_action)

    move_sp = subparsers.add_parser('move', help='move node A into folder B')
    move_sp.add_argument('child')
    move_sp.add_argument('parent')
    move_sp.set_defaults(func=move_action)

    rename_sp = subparsers.add_parser('rename', help='rename a node')
    rename_sp.add_argument('node')
    rename_sp.add_argument('name')
    rename_sp.set_defaults(func=rename_action)

    res_sp = subparsers.add_parser('resolve', help='resolves a path to a node id')
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

    oauth.get_data()

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

    args.func(args)


if __name__ == "__main__":
    main()
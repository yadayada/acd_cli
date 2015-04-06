#!/usr/bin/env python3
import sys
import os
import argparse
from pprint import pprint

from cache import sync, selection, db
from acd import oauth, content, metadata, account, trash, changes
from acd.common import RequestError
import utils

__version__ = 0.1

INVALID_ARG_RETVAL = 2


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


def main():
    opt_parser = argparse.ArgumentParser(
        epilog='Hint: If you need to enter a node id that contains a leading dash (minus) sign, ' +
               'precede it by two dashes and a space, e.g. \'-- -xfH...\'')
    opt_parser.add_argument('--debug', action='store_true', help='turn on debug mode')

    subparsers = opt_parser.add_subparsers(dest='action')
    subparsers.required = True

    node_sp = subparsers.add_parser('sync', help='refresh node list cache')

    tree_sp = subparsers.add_parser('tree', help='print directory tree')
    tree_sp.add_argument('--include-trash', '-t', action='store_true')

    upload_sp = subparsers.add_parser('upload', help='upload a file')
    upload_sp.add_argument('name', help='name of local file')
    upload_sp.add_argument('parent', nargs='?', help='parent folder (optional)')

    download_sp = subparsers.add_parser('download', help='download a remote file')
    download_sp.add_argument('node')

    cr_fo_sp = subparsers.add_parser('create', help='create folder')
    cr_fo_sp.add_argument('new_folder')

    trash_sp = subparsers.add_parser('list-trash')

    m_trash_sp = subparsers.add_parser('trash', help='move to trash')
    m_trash_sp.add_argument('node')

    rest_sp = subparsers.add_parser('restore', help='restore from trash')
    rest_sp.add_argument('node', help='id of the node')

    list_c_sp = subparsers.add_parser('children', help='list folders\'s children')
    list_c_sp.add_argument('node')
    list_c_sp.add_argument('--include-trash', '-t', action='store_true')

    move_sp = subparsers.add_parser('move', help='move node A into folder B')
    move_sp.add_argument('child')
    move_sp.add_argument('parent')

    res_sp = subparsers.add_parser('resolve', help='resolves a path to a node id')
    res_sp.add_argument('path')

    # maybe the child operations should not be exposed
    # they can be used for creating hardlinks
    add_c_sp = subparsers.add_parser('add-child', help='add a node to a parent folder')
    add_c_sp.add_argument('parent')
    add_c_sp.add_argument('child')

    rem_c_sp = subparsers.add_parser('remove-child', help='remove a node from a parent folder')
    rem_c_sp.add_argument('parent')
    rem_c_sp.add_argument('child')

    usage_sp = subparsers.add_parser('usage', help='show drive usage data')
    quota_sp = subparsers.add_parser('quota', help='show drive quota')

    meta_sp = subparsers.add_parser('metadata', help='print a node\'s metadata' )
    meta_sp.add_argument('node')

    chn_sp = subparsers.add_parser('list-changes', help='list changes')

    args = opt_parser.parse_args()

    oauth.get_data()

    # auto-resolve node paths
    for id_attr in ['child', 'parent', 'node']:
        if hasattr(args, id_attr):
            val = getattr(args, id_attr)
            if val and '/' in val:
                val = selection.resolve_path(val)
                if not val:
                    print('Could not resolve path.')
                    sys.exit(INVALID_ARG_RETVAL)
                setattr(args, id_attr, val)

    if args.action == 'sync':
        print('Syncing... ', end='')
        sys.stdout.flush()
        sync_node_list()
        print('Done.')

    if args.action == 'tree':
        tree = selection.node_tree(args.include_trash)
        print('\n'.join(tree))

    elif args.action == 'usage':
        r = account.get_account_usage()
        pprint(r)
    elif args.action == 'quota':
        r = account.get_quota()
        pprint(r)

    elif args.action == 'upload':
        parent = None
        try:
            parent = args.parent
        except IndexError:
            pass
        if utils.is_uploadable(args.name):
            hasher = utils.Hasher(args.name)
            r = content.upload_file(args.name, parent)
            if hasher.get_result() != r['contentProperties']['md5']:
                print('Hash mismatch.')
            pprint(r)
            sync.insert_files([r], True)
        else:
            print('Invalid file name.')
            sys.exit(INVALID_ARG_RETVAL)

    elif args.action == 'download':
        loc_name = selection.get_name(args.node)
        if not loc_name:
            loc_name = args.node
        content.download_file(args.node, loc_name)

    elif args.action == 'create':
        parent, folder = os.path.split(args.new_folder)
        if not folder:
            parent, folder = os.path.split(parent)

        if parent[-1:] != '/':
            parent += '/'
        p_path = selection.resolve_path(parent)
        if not p_path:
            print('Invalid parent path.')
            sys.exit(INVALID_ARG_RETVAL)

        r = content.create_folder(folder, p_path)
        pprint(r)
        sync.insert_folders([r], True)

    elif args.action == 'list-trash':
        t_list = selection.list_trash()
        if t_list:
            print('\n'.join(t_list))

    elif args.action == 'trash':
        r = trash.move_to_trash(args.node)
        pprint(r)

        if r['kind'] == 'FILE':
            sync.insert_files([r], True)
        elif r['kind'] == 'FOLDER':
            sync.insert_folders([r], True)

    elif args.action == 'restore':
        r = trash.restore(args.node)
        pprint(r)

    elif args.action == 'resolve':
        print(selection.resolve_path(args.path))

    elif args.action == 'children':
        c_list = selection.list_children(args.node, args.include_trash)
        if c_list:
            print('\n'.join(c_list))

    elif args.action == 'move':
        r = metadata.move_node(args.child, args.parent)
        pprint(r)

        if r['kind'] == 'FILE':
            sync.insert_files([r], True)
        elif r['kind'] == 'FOLDER':
            sync.insert_folders([r], True)

    elif args.action == 'add-child':
        r = metadata.add_child(args.parent, args.child)
        pprint(r)

    elif args.action == 'remove-child':
        r = metadata.remove_child(args.parent, args.child)
        pprint(r)

    elif args.action == 'list-changes':
        r = changes.get_changes()
        pprint(r)

    elif args.action == 'metadata':
        r = metadata.get_metadata(args.node)
        pprint(r)


if __name__ == "__main__":
    main()
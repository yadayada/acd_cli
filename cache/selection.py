import os

import cache.db as db


def get_node(id):
    return db.session.query(db.Node).filter_by(id=id).first()


def get_root_node():
    return db.session.query(db.Folder).filter_by(name=None).first()


def get_root_id():
    root = get_root_node()
    if root:
        return root.id


def get_name(id):
    node = db.session.query(db.Node).filter_by(id=id).first()
    if not node:
        return
    return node.name


def list_children(folder_id, recursive=False, trash=False):
    """ Creates formatted list of folder's
    :param folder_id: folder's id
    :return: list of node names, folders first
    """
    folder = db.session.query(db.Folder).filter_by(id=folder_id).first()
    if not folder:
        print('Not a folder or not found.')
        return []

    return node_list(folder, False, recursive, trash)


def node_list(root=None, add_root=True, recursive=True, trash=False, path='', n_list=[]):
    """
    Generates formatted list of (non-)trashed nodes
    :db.Folder root: start folder
    :bool add_root: whether to add the root node to the list and prepend its path to its children
    :bool recursive: whether to traverse hierarchy
    :bool trash: whether to include trash
    :str path: the path on which this method incarnation was reached
    :return: list of nodes in absolute path representation
    """

    if not root:
        root = get_root_node()
        if not root:
            return []

    if add_root:
        n_list.append(root.long_id_str(path))
        path += root.simple_name()

    children = sorted(root.children)

    for child in children:
        if child.status == 'TRASH' and not trash:
            continue
        if isinstance(child, db.Folder) and recursive:
            node_list(child, True, recursive, trash, path, n_list)
        else:
            n_list.append(child.long_id_str(path))

    return n_list


def list_trash(recursive=False):
    trash_nodes = db.session.query(db.Node).filter(db.Node.status == 'TRASH').all()
    trash_nodes = sorted(trash_nodes)

    nodes = []
    for node in trash_nodes:
        nodes.append(node.long_id_str())
        if isinstance(node, db.Folder) and recursive:
            nodes.extend(node_list(node, False, True, True, node.full_path()))

    return nodes


# TODO
def find(name):
    # use SQL LIKE
    pass


def resolve_path(path, root=None):
    """Resolves absolute path, if fully unique"""
    if not path or (not root and '/' not in path):
        return

    segments = path.split('/')
    if segments[0] == '' and not root:
        root = get_root_node()

    if len(segments) == 1 or segments[1] == '':
        return root.id

    if isinstance(root, db.File):
        return

    segments = segments[1:]

    children = []  # possibly non-unique trash children
    for child in root.children:
        if child.name == segments[0]:
            if child.status != 'TRASH':
                return resolve_path('/'.join(segments), child)
            children.append(child)

    ids = []
    for trash_child in children:
        res = resolve_path('/'.join(segments), trash_child)
        if res:
            ids.append(res)
    if len(ids) == 1:
        return ids[0]
        # else:
        # print('Could resolve non fully unique (i.e. trash) path "%s"' % path)
import os

import cache.db as db


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


def list_children(folder_id, trash=False):
    """ Creates formatted list of folder's
    :param folder_id: folder's id
    :return: list of node names, folders first
    """
    folder = db.session.query(db.Folder).filter_by(id=folder_id).first()
    if not folder:
        print('Not a folder or not found.')
        return []

    c = folder.children
    c = sorted(c, key=lambda n: ('a' if isinstance(n, db.Folder) else 'b') + n.simple_name())

    children = []
    for node in c:
        if trash or not node.status == 'TRASH':
            children.append(node.id_str())
    return children


# TODO: filter nodes with trashed parents
def node_tree(trash=False, root=None, n_list=None):
    """
    Tree of non-trashed nodes
    :bool trash: whether to include trash
    :return: list of nodes in absolute path representation
    """

    if not root:
        root = get_root_node()
    if not n_list:
        n_list = []

    children = sorted(root.children, key=lambda n: ('a' if isinstance(n, db.Folder) else 'b') + n.simple_name())

    n_list.append(root.long_id_str())
    for child in children:
        if child.status == 'TRASH' and not trash:
            continue
        if isinstance(child, db.Folder):
            node_tree(trash, child, n_list)
        else:
            n_list.append(child.long_id_str())

    return n_list


def list_trash():
    nodes = db.session.query(db.Node).filter(db.Node.status == 'TRASH')

    node_list = []
    for node in nodes:
        node_list.append(node.long_id_str())

    return sorted(node_list)


# TODO
def find(name):
    # use SQL LIKE
    pass


def resolve_path(path):
    """
    Resolves non-trashed path name
    :param path: absolute path
    :return: node id corresponding to path or None
    """
    if path == '/':
        return get_root_id()

    dir_, file = os.path.split(path)

    if not file:
        dir_, file = os.path.split(dir_)  # move folder name into 'file'

    if path[-1:] == '/':
        nodes = db.session.query(db.Folder).filter(db.Folder.name == file)
    else:
        nodes = db.session.query(db.File).filter(db.File.name == file)

    for n in nodes:
        if n.status != 'TRASH' and n.full_path() == path:
            return n.id

    return
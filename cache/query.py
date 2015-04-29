import logging

import cache.db as db

logger = logging.getLogger(__name__)


def get_node(node_id):
    return db.session.query(db.Node).filter_by(id=node_id).first()


# may be broken
def get_root_node():
    return db.session.query(db.Folder).filter_by(name=None).first()


def get_root_id():
    root = get_root_node()
    if root:
        return root.id


def is_folder(node_id):
    return db.session.query(db.Folder).filter_by(id=node_id).first() is not None


def tree(root_id=None, trash=False):
    if root_id is None:
        return node_list(trash=trash)

    folder = db.session.query(db.Folder).filter_by(id=root_id).first()
    if not folder:
        logger.error('Not a folder or not found: "%s".' % root_id)
        return []

    return node_list(folder, True, True, trash)


def list_children(folder_id, recursive=False, trash=False):
    """ Creates formatted list of folder's children
    :param folder_id: valid folder's id
    :return: list of node names, folders first
    """
    folder = db.session.query(db.Folder).filter_by(id=folder_id).first()
    if not folder:
        logger.warning('Not a folder or not found: "%s".' % folder_id)
        return []

    return node_list(folder, False, recursive, trash)


def node_list(root=None, add_root=True, recursive=True, trash=False, path='', n_list=None):
    """
    Generates formatted list of (non-)trashed nodes
    :param root: start folder
    :type root: db.Folder
    :param add_root: whether to add the (uppermost) root node to the list and prepend its path to its children
    :type add_root: bool
    :param recursive: whether to traverse hierarchy
    :type recursive: bool
    :param trash: whether to include trash
    :type trash: bool
    :param path: the path on which this method incarnation was reached
    :type path: str
    :return: list of nodes in absolute path representation
    """

    if not root:
        root = get_root_node()
        if not root:
            return []

    if n_list is None:
        n_list = []

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


def find(name):
    q = db.session.query(db.Node).filter(db.Node.name.like('%' + name + '%'))
    q = sorted(q, key=lambda x: x.full_path())

    nodes = []
    for node in q:
        nodes.append(node.long_id_str())
    return nodes


def resolve_path(path, root=None, trash=True):
    """Resolves absolute path to node id if fully unique"""
    if not path or (not root and '/' not in path):
        return

    segments = path.split('/')
    if segments[0] == '' and not root:
        root = get_root_node()
        # empty cache
        if not root:
            return

    if not root:
        return

    if len(segments) == 1 or segments[1] == '':
        return root.id

    segments = segments[1:]

    children = []  # possibly non-unique trash children
    for child in root.children:
        if child.name == segments[0]:
            if child.status != 'TRASH':
                return resolve_path('/'.join(segments), child)
            children.append(child)

    if not trash:
        return
    ids = []
    for trash_child in children:
        res = resolve_path('/'.join(segments), trash_child)
        if res:
            ids.append(res)
    if len(ids) == 1:
        return ids[0]
    else:
        logger.info('Could not resolve non fully unique (i.e. trash) path "%s"' % path)
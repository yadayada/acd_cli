import logging

import cache.db as db

logger = logging.getLogger(__name__)


class Bunch:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def __str__(self):
        return str(self.__dict__)


class ListFormatter(object):
    @staticmethod
    def format(bunches: list):
        """:param bunches Bunch list"""
        return LongIDFormatter.format(bunches)


class LongIDFormatter(ListFormatter):
    @staticmethod
    def format(bunches):
        list_ = []
        for bunch in bunches:
            list_.append(bunch.node.long_id_str(bunch.path))
        return list_


# TODO
class TreeFormatter(ListFormatter):
    pass


class IDFormatter(ListFormatter):
    @staticmethod
    def format(bunches: list):
        list_ = []
        for bunch in bunches:
            list_.append(bunch.node.id)
        return list_


def get_node(node_id) -> db.Node:
    return db.session.query(db.Node).filter_by(id=node_id).first()


# may be broken
def get_root_node() -> db.Folder:
    return db.session.query(db.Folder).filter_by(name=None).first()


def get_root_id() -> str:
    root = get_root_node()
    if root:
        return root.id


def tree(root_id=None, trash=False) -> list:
    if root_id is None:
        return node_list(trash=trash)

    folder = db.session.query(db.Folder).filter_by(id=root_id).first()
    if not folder:
        logger.error('Not a folder or not found: "%s".' % root_id)
        return []

    return node_list(folder, True, True, trash)


def list_children(folder_id, recursive=False, trash=False):
    """ Creates Bunch list of folder's children
    :param folder_id: valid folder's id
    :return: list of node names, folders first
    """
    folder = db.session.query(db.Folder).filter_by(id=folder_id).first()
    if not folder:
        logger.warning('Not a folder or not found: "%s".' % folder_id)
        return []

    return node_list(folder, False, recursive, trash)


def node_list(root: db.Folder=None, add_root=True, recursive=True, trash=False, path='', n_list=None, depth=0) -> list:
    """ Generates Bunch list of (non-)trashed nodes
    :param root: start folder
    :param add_root: whether to add the (uppermost) root node to the list and prepend its path to its children
    :param recursive: whether to traverse hierarchy
    :param trash: whether to include trash
    :param path: the path on which this method incarnation was reached
    :type path: str
    :return: list of Bunches including node and path attributes
    """

    if not root:
        root = get_root_node()
        if not root:
            return []

    if n_list is None:
        n_list = []

    if add_root:
        n_list.append(Bunch(node=root, path=path, depth=depth))
        path += root.simple_name()

    children = sorted(root.children)

    for child in children:
        if child.status == 'TRASH' and not trash:
            continue
        if isinstance(child, db.Folder) and recursive:
            node_list(child, True, recursive, trash, path, n_list, depth + 1)
        else:
            n_list.append(Bunch(node=child, path=path, depth=depth))

    return n_list


def list_trash(recursive=False):
    trash_nodes = db.session.query(db.Node).filter(db.Node.status == 'TRASH').all()
    trash_nodes = sorted(trash_nodes)

    nodes = []
    for node in trash_nodes:
        nodes.append(Bunch(node=node, path=node.containing_folder()))
        if isinstance(node, db.Folder) and recursive:
            nodes.extend(node_list(node, False, True, True, node.full_path()))

    return nodes


def find(name) -> list:
    q = db.session.query(db.Node).filter(db.Node.name.like('%' + name + '%'))
    q = sorted(q, key=lambda x: x.full_path())

    nodes = []
    for node in q:
        nodes.append(Bunch(node=node, path=node.containing_folder()))
    return nodes


def find_md5(md5) -> list:
    q = db.session.query(db.File).filter_by(md5=md5)
    q = sorted(q, key=lambda x: x.full_path())

    nodes = []
    for node in q:
        nodes.append(Bunch(node=node, path=node.containing_folder()))
    return nodes


def resolve_path(path, root=None, trash=True) -> str:
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
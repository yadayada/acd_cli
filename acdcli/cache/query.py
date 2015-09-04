"""
Collection of common database queries.
"""

import logging
from functools import lru_cache
from sqlalchemy import func

from . import schema

logger = logging.getLogger(__name__)


class Bunch:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def __str__(self):
        return str(self.__dict__)


class QueryMixin(object):
    def get_node(self, node_id: str) -> schema.Node:
        return self.Session.query(schema.Node).filter_by(id=node_id).first()

    def conflicting_node(self, name: str, parent_id: str):
        """Finds conflicting node in folder specified by parent_id."""
        p = self.get_node(parent_id)
        if p:
            for c in p.children:
                if c.is_available() and c.name == name:
                    return c

    @lru_cache()
    def get_root_node(self) -> schema.Folder:
        for f in self.Session.query(schema.Folder).filter_by(name=None):
            if len(f.parents) == 0:
                return f

    def get_root_id(self) -> str:
        root = self.get_root_node()
        if root:
            return root.id

    def get_node_count(self) -> int:
        return self.Session.query(schema.Node).count()

    def get_file_count(self) -> int:
        return self.Session.query(schema.File).count()

    def calculate_usage(self) -> int:
        u = self.Session.query(func.sum(schema.File.size)).scalar()
        return u if u else 0

    def file_size(self, id: str) -> int:
        return self.Session.query(schema.File).filter_by(id=id).first().size

    def tree(self, root_id: str=None, trash=False):
        if root_id is None:
            return self.walk_nodes(trash=trash)

        folder = self.Session.query(schema.Folder).filter_by(id=root_id).first()
        if not folder:
            logger.error('Not a folder or not found: "%s".' % root_id)
            return

        return self.walk_nodes(folder, True, True, trash)

    def list_children(self, folder_id: str, recursive=False, trash=False):
        """ Creates Bunches of folder's children
        :param folder_id: valid folder's id
        """
        folder = self.Session.query(schema.Folder).filter_by(id=folder_id).first()
        if not folder:
            logger.warning('Not a folder or not found: "%s".' % folder_id)
            return []

        return self.walk_nodes(folder, False, recursive, trash)

    # TODO: refashion this to return a tuple like os.walk
    def walk_nodes(self, root: schema.Folder=None, add_root=True, recursive=True, trash=False,
                   path='', depth=0):
        """ Generates Bunches of (non-)trashed nodes
        :param root: start folder
        :param add_root: whether to add the root node and prepend its path to its children
        :param recursive: whether to traverse hierarchy
        :param trash: whether to include trash
        :param path: the path on which this method incarnation was reached
        :rtype: Iterable[Bunch]
        :return: list of Bunches including node and path attributes
        """

        if not root:
            root = self.get_root_node()
            if not root:
                return

        if add_root:
            yield Bunch(node=root, path=path, depth=depth)
            path += root.simple_name()

        if not recursive:
            children = sorted(root.children)
        else:
            children = sorted(root.children, key=lambda x: ('b' if x.is_folder() else 'a') + x.name)

        for child in children:
            if child.status == 'TRASH' and not trash:
                continue
            if isinstance(child, schema.Folder) and recursive:
                for node in self.walk_nodes(child, True, recursive, trash, path, depth + 1):
                    yield node
            else:
                yield Bunch(node=child, path=path, depth=depth + 1)

    def list_trash(self, recursive=False):
        trash_nodes = self.Session().query(schema.Node).filter(schema.Node.status == 'TRASH').all()
        trash_nodes = sorted(trash_nodes)

        for node in trash_nodes:
            yield Bunch(node=node, path=node.containing_folder())
            if isinstance(node, schema.Folder) and recursive:
                for child in self.walk_nodes(node, False, True, True, node.full_path()):
                    yield child

    def find(self, name: str):
        q = self.Session.query(schema.Node).filter(schema.Node.name.like('%' + name + '%'))
        q = sorted(q, key=lambda x: x.full_path())

        for node in q:
            yield Bunch(node=node, path=node.containing_folder())

    def find_md5(self, md5: str):
        q = self.Session.query(schema.File).filter_by(md5=md5)
        q = sorted(q, key=lambda x: x.full_path())

        for node in q:
            yield Bunch(node=node, path=node.containing_folder())

    def find_regex(self, regex: str):
        q = self.Session.query(schema.Node).filter(schema.Node.name.op('REGEXP')(regex))
        q = sorted(q, key=lambda x: x.full_path())

        for node in q:
            yield Bunch(node=node, path=node.containing_folder())

    def file_size_exists(self, size: int) -> bool:
        """Returns whether cache contains one or more file(s) of given size."""
        return self.Session.query(schema.File).filter_by(size=size).count()

    def resolve_path(self, path: str, trash=True) -> tuple:
        """Resolves absolute path to node ID"""
        node, _ = self.resolve(path, None, trash)
        return node.id if node else None

    def resolve(self, path: str, root=None, trash=True) -> tuple:
        """Resolves absolute path to (node, parent) tuple if fully unique"""
        if not path or (not root and '/' not in path):
            return None, None

        segments = path.split('/')
        if segments[0] == '' and not root:
            root = self.get_root_node()

        if not root:
            return None, None

        if len(segments) == 1 or segments[1] == '':
            return root, None

        segments = segments[1:]

        # TODO
        if root.is_file() or (not root.is_available() and not trash):
            return None, None

        children = []  # possibly non-unique trash children
        for child in root.children:
            if child.name == segments[0]:
                if child.is_available():
                    n, p = self.resolve('/'.join(segments), child, trash)
                    return n, (p if p else root)
                children.append(child)

        if not trash:
            return None, None
        ids = []
        for trash_child in children:
            res, _ = self.resolve('/'.join(segments), trash_child)
            if res:
                ids.append(res)
        if len(ids) == 1:
            return ids[0], root
        elif len(ids) == 0:
            logger.debug('Could not resolve path "%s"' % path)
        else:
            logger.info('Could not resolve non fully unique (i.e. trash) path "%s"' % path)

        return None, None

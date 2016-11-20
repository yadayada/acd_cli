import logging
from datetime import datetime
from .cursors import cursor

logger = logging.getLogger(__name__)


def datetime_from_string(dt: str) -> datetime:
    try:
        dt = datetime.strptime(dt, '%Y-%m-%d %H:%M:%S.%f+00:00')
    except ValueError:
        dt = datetime.strptime(dt, '%Y-%m-%d %H:%M:%S+00:00')
    return dt


CONFLICTING_NODE_SQL = """SELECT n.*, f.* FROM nodes n
                  JOIN parentage p ON n.id = p.child
                  LEFT OUTER JOIN files f ON n.id = f.id
                  WHERE p.parent = (?) AND LOWER(name) = (?) AND status = 'AVAILABLE'
                  ORDER BY n.name"""

CHILDREN_SQL = """SELECT n.*, f.* FROM nodes n
                  JOIN parentage p ON n.id = p.child
                  LEFT OUTER JOIN files f ON n.id = f.id
                  WHERE p.parent = (?)
                  ORDER BY n.name"""

CHILDRENS_NAMES_SQL = """SELECT n.name FROM nodes n
                JOIN parentage p ON n.id = p.child
                WHERE p.parent = (?) AND n.status == 'AVAILABLE'
                ORDER BY n.name"""

NUM_CHILDREN_SQL = """SELECT COUNT(n.id) FROM nodes n
                    JOIN parentage p ON n.id = p.child
                    WHERE p.parent = (?) AND n.status == 'AVAILABLE'"""

NUM_PARENTS_SQL = """SELECT COUNT(n.id) FROM nodes n
                    JOIN parentage p ON n.id = p.parent
                    WHERE p.child = (?) AND n.status == 'AVAILABLE'"""

NUM_NODES_SQL = 'SELECT COUNT(*) FROM nodes'
NUM_FILES_SQL = 'SELECT COUNT(*) FROM files'
NUM_FOLDERS_SQL = 'SELECT COUNT(*) FROM nodes WHERE type == "folder"'

CHILD_OF_SQL = """SELECT n.*, f.* FROM nodes n
                  JOIN parentage p ON n.id = p.child
                  LEFT OUTER JOIN files f ON n.id = f.id
                  WHERE n.name = (?) AND p.parent = (?)
                  ORDER BY n.status"""

NODE_BY_ID_SQL = """SELECT n.*, f.* FROM nodes n LEFT OUTER JOIN files f ON n.id = f.id
                    WHERE n.id = (?)"""

USAGE_SQL = 'SELECT SUM(size) FROM files'

FIND_BY_NAME_SQL = """SELECT n.*, f.* FROM nodes n
                      LEFT OUTER JOIN files f ON n.id = f.id
                      WHERE n.name LIKE ?
                      ORDER BY n.name"""

FIND_BY_REGEX_SQL = """SELECT n.*, f.* FROM nodes n
                      LEFT OUTER JOIN files f ON n.id = f.id
                      WHERE n.name REGEXP ?
                      ORDER BY n.name"""

FIND_BY_MD5_SQL = """SELECT n.*, f.* FROM nodes n
                      LEFT OUTER JOIN files f ON n.id = f.id
                      WHERE f.md5 == (?)
                      ORDER BY n.name"""

FIND_FIRST_PARENT_SQL = """SELECT n.* FROM nodes n
                        JOIN parentage p ON n.id = p.parent
                        WHERE p.child = (?)
                        ORDER BY n.status, n.id"""

# TODO: exclude files in trashed folders?!
FILE_SIZE_EXISTS_SQL = """SELECT COUNT(*) FROM files f
                          JOIN nodes n ON n.id = f.id
                          WHERE f.size == (?) AND n.status == 'AVAILABLE'"""


class Node(object):
    def __init__(self, row):
        self.id = row['id']
        self.type = row['type']
        self.name = row['name']
        self.description = row['description']
        self.cre = row['created']
        self.mod = row['modified']
        self.updated = row['updated']
        self.status = row['status']

        try:
            self.md5 = row['md5']
        except IndexError:
            self.md5 = None
        try:
            self.size = row['size']
        except IndexError:
            self.size = 0

    def __lt__(self, other):
        return self.name < other.name

    def __hash__(self):
        return hash(self.id)

    def __repr__(self):
        return 'Node(%r, %r)' % (self.id, self.name)

    @property
    def is_folder(self):
        return self.type == 'folder'

    @property
    def is_file(self):
        return self.type == 'file'

    @property
    def is_available(self):
        return self.status == 'AVAILABLE'

    @property
    def is_trashed(self):
        return self.status == 'TRASH'

    @property
    def created(self):
        return datetime_from_string(self.cre)

    @property
    def modified(self):
        return datetime_from_string(self.mod)

    @property
    def simple_name(self):
        if self.is_file:
            return self.name
        return (self.name if self.name else '') + '/'


class QueryMixin(object):
    def get_node(self, id) -> 'Union[Node|None]':
        with cursor(self._conn) as c:
            c.execute(NODE_BY_ID_SQL, [id])
            r = c.fetchone()
            if r:
                return Node(r)

    def get_root_node(self):
        return self.get_node(self.root_id)

    def get_conflicting_node(self, name: str, parent_id: str):
        """Finds conflicting node in folder specified by *parent_id*, if one exists."""
        with cursor(self._conn) as c:
            c.execute(CONFLICTING_NODE_SQL, [parent_id, name.lower()])
            r = c.fetchone()
            if r:
                return Node(r)

    def resolve(self, path: str, trash=False) -> 'Union[Node|None]':
        segments = list(filter(bool, path.split('/')))
        if not segments:
            if not self.root_id:
                return
            with cursor(self._conn) as c:
                c.execute(NODE_BY_ID_SQL, [self.root_id])
                r = c.fetchone()
                return Node(r)

        parent = self.root_id
        for i, segment in enumerate(segments):
            with cursor(self._conn) as c:
                c.execute(CHILD_OF_SQL, [segment, parent])
                r = c.fetchone()
                r2 = c.fetchone()

            if not r:
                return
            r = Node(r)

            if not r.is_available:
                if not trash:
                    return
                if r2:
                    logger.debug('None-unique trash name "%s" in %s.' % (segment, parent))
                    return
            if i + 1 == len(segments):
                return r
            if r.is_folder:
                parent = r.id
                continue
            else:
                return

    def childrens_names(self, folder_id) -> 'List[str]':
        with cursor(self._conn) as c:
            c.execute(CHILDRENS_NAMES_SQL, [folder_id])
            kids = []
            row = c.fetchone()
            while row:
                kids.append(row['name'])
                row = c.fetchone()
            return kids

    def get_node_count(self) -> int:
        with cursor(self._conn) as c:
            c.execute(NUM_NODES_SQL)
            r = c.fetchone()[0]
        return r

    def get_folder_count(self) -> int:
        with cursor(self._conn) as c:
            c.execute(NUM_FOLDERS_SQL)
            r = c.fetchone()[0]
        return r

    def get_file_count(self) -> int:
        with cursor(self._conn) as c:
            c.execute(NUM_FILES_SQL)
            r = c.fetchone()[0]
        return r

    def calculate_usage(self):
        with cursor(self._conn) as c:
            c.execute(USAGE_SQL)
            r = c.fetchone()
        return r[0] if r and r[0] else 0

    def num_children(self, folder_id) -> int:
        with cursor(self._conn) as c:
            c.execute(NUM_CHILDREN_SQL, [folder_id])
            num = c.fetchone()[0]
            return num

    def num_parents(self, node_id) -> int:
        with cursor(self._conn) as c:
            c.execute(NUM_PARENTS_SQL, [node_id])
            num = c.fetchone()[0]
            return num

    def get_child(self, folder_id, child_name) -> 'Union[Node|None]':
        with cursor(self._conn) as c:
            c.execute(CHILD_OF_SQL, [child_name, folder_id])
            r = c.fetchone()
        if r:
            r = Node(r)
            if r.is_available:
                return r

    def list_children(self, folder_id, trash=False) -> 'Tuple[List[Node], List[Node]]':
        files = []
        folders = []

        with cursor(self._conn) as c:
            c.execute(CHILDREN_SQL, [folder_id])
            node = c.fetchone()
            while node:
                node = Node(node)
                if node.is_available or trash:
                    if node.is_file:
                        files.append(node)
                    elif node.is_folder:
                        folders.append(node)
                node = c.fetchone()

        return folders, files

    def list_trashed_children(self, folder_id) -> 'Tuple[List[Node], List[Node]]':
        folders, files = self.list_children(folder_id, True)
        folders[:] = [f for f in folders if f.is_trashed]
        files[:] = [f for f in files if f.is_trashed]
        return folders, files

    def first_path(self, node_id: str) -> str:
        if node_id == self.root_id:
            return '/'
        with cursor(self._conn) as c:
            c.execute(FIND_FIRST_PARENT_SQL, (node_id,))
            r = c.fetchone()
        node = Node(r)
        if node.id == self.root_id:
            return node.simple_name
        return self.first_path(node.id) + node.name + '/'

    def find_by_name(self, name: str) -> 'List[Node]':
        nodes = []
        with cursor(self._conn) as c:
            c.execute(FIND_BY_NAME_SQL, ['%' + name + '%'])
            r = c.fetchone()
            while r:
                nodes.append(Node(r))
                r = c.fetchone()
        return nodes

    def find_by_md5(self, md5) -> 'List[Node]':
        nodes = []
        with cursor(self._conn) as c:
            c.execute(FIND_BY_MD5_SQL, (md5,))
            r = c.fetchone()
            while r:
                nodes.append(Node(r))
                r = c.fetchone()
        return nodes

    def find_by_regex(self, regex) -> 'List[Node]':
        nodes = []
        with cursor(self._conn) as c:
            c.execute(FIND_BY_REGEX_SQL, (regex,))
            r = c.fetchone()
            while r:
                nodes.append(Node(r))
                r = c.fetchone()
        return nodes

    def file_size_exists(self, size) -> bool:
        with cursor(self._conn) as c:
            c.execute(FILE_SIZE_EXISTS_SQL, [size])
            no = c.fetchone()[0]

        return bool(no)

from sqlalchemy import *
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, backref
from datetime import datetime, timedelta

_Base = declarative_base()

_parentage_table = Table('parentage', _Base.metadata,
                         Column('parent', String(50), ForeignKey('folders.id'), primary_key=True),
                         Column('child', String(50), ForeignKey('nodes.id'), primary_key=True)
                         )


class Metadate(_Base):
    """Some kind of metadate (added in v1)."""
    __tablename__ = 'metadata'

    key = Column(String(64), primary_key=True)
    value = Column(String)

    def __init__(self, key: str, value: str):
        self.key = key
        self.value = value


class Label(_Base):
    """A node label (added in v1)."""
    __tablename__ = 'labels'

    id = Column(String(50), ForeignKey('nodes.id'), primary_key=True)
    name = Column(String(256), primary_key=True)


# TODO: cycle safety for full_path()
class Node(_Base):
    """The base node type."""

    __tablename__ = 'nodes'

    # apparently 22 chars; max length is 22 for folders according to API doc ?!
    id = Column(String(50), primary_key=True, unique=True)
    type = Column(String(15))
    name = Column(String(256))
    description = Column(String(500))

    created = Column(DateTime)
    modified = Column(DateTime)
    updated = Column(DateTime)

    # "pending" status seems to be reserved for not yet finished uploads
    status = Column(Enum('AVAILABLE', 'TRASH', 'PURGED', 'PENDING'))

    __mapper_args__ = {
        'polymorphic_identity': 'node',
        'polymorphic_on': type
    }

    def __lt__(self, other):
        """Compares this node to another one on same path level.
        Sorts case-sensitive, Folder first. """
        if isinstance(self, Folder):
            if isinstance(other, File):
                return True
            return self.name < other.name
        if isinstance(other, Folder):
            return False
        if self.name is None:
            return True
        if other.name is None:
            return False
        return self.name < other.name

    def __hash__(self):
        return hash(self.id)

    def is_file(self) -> bool:
        return isinstance(self, File)

    def is_folder(self) -> bool:
        return isinstance(self, Folder)

    def is_available(self) -> bool:
        return self.status == 'AVAILABLE'

    def id_str(self) -> str:
        """short id string containing id, stat, name"""
        return '[{}] [{}] {}'.format(self.id, self.status[0], self.simple_name())

    def containing_folder(self) -> str:
        if len(self.parents) == 0:
            return ''
        return self.parents[0].full_path()

    parents = relationship('Folder', secondary=_parentage_table,
                           primaryjoin=id == _parentage_table.c.child,
                           backref=backref('children', lazy='dynamic')
                           )


class File(Node):
    __tablename__ = 'files'

    id = Column(String(50), ForeignKey('nodes.id'), primary_key=True, unique=True)
    md5 = Column(String(32))
    size = Column(BigInteger)

    __mapper_args__ = {
        'polymorphic_identity': 'file'
    }

    def __init__(self, id: str, name: str, created: datetime, modified: datetime,
                 md5: str, size: int, status: Enum):
        self.id = id
        self.name = name
        self.created = created.replace(tzinfo=None)
        self.modified = modified.replace(tzinfo=None)
        self.md5 = md5
        self.size = size
        self.status = status

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return False
        return (self.id == other.id and self.name == other.name
                and self.created - other.created == timedelta(0)
                and self.modified - other.modified == timedelta(0)
                and self.md5 == other.md5 and self.size == other.size
                and self.status == other.status)

    def __repr__(self):
        return 'File(%r, %r)' % (self.id, self.name)

    def __hash__(self):
        return hash(self.id)

    def simple_name(self) -> str:
        """file name"""
        return self.name

    def full_path(self) -> str:
        """absolute path of file (first containing folder chain)"""
        if len(self.parents) == 0:
            if self.name:
                return self.name
            return ''
        return self.parents[0].full_path() + self.name

    @property
    def nlinks(self):
        return sum(1 for p in self.parents if p.is_available())


class Folder(Node):
    __tablename__ = 'folders'

    id = Column(String(50), ForeignKey('nodes.id'), primary_key=True, unique=True)

    __mapper_args__ = {
        'polymorphic_identity': 'folder'
    }

    def __init__(self, id: str, name: str, created: datetime, modified: datetime, status: Enum):
        self.id = id
        self.name = name
        self.created = created.replace(tzinfo=None)
        self.modified = modified.replace(tzinfo=None)
        self.status = status

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return False
        return (self.id == other.id
                and self.name == other.name
                and self.created == other.created
                and self.modified == other.modified
                and self.status == other.status)

    def __repr__(self):
        return 'Folder(%r, %r)' % (self.id, self.name)

    def __hash__(self):
        return hash(self.id)

    def simple_name(self) -> str:
        return (self.name if self.name else '') + '/'

    # path of first occurrence
    def full_path(self) -> str:
        if len(self.parents) == 0:
            return '/'
        return self.parents[0].full_path() + self.simple_name()

    def get_child(self, name: str) -> 'Union[Node, None]':
        """Gets non-trashed child by name. """
        for child in self.children:
            if child.name == name and child.status == 'AVAILABLE':
                return child
        return

    def available_children(self) -> 'Generator[Node]':
        for c in self.children:
            if c.is_available():
                yield c

    @property
    def nlinks(self) -> int:
        """Number of hard links ('.', '', and children)."""
        nlinks = 2
        for c in self.children:
            if c.is_folder() and c.is_available():
                nlinks += 1
        return nlinks


class _KeyValueStorage(object):
    def __init__(self, Session):
        self.Session = Session

    def __getitem__(self, key: str):
        val = self.Session.query(Metadate).filter_by(key=key).first()
        if val:
            return val.value
        else:
            raise KeyError

    def __setitem__(self, key: str, value: str):
        md = Metadate(key, value)
        self.Session.merge(md)
        self.Session.commit()

    def __len__(self):
        return self.Session.query(Metadate).count()

    def get(self, key: str, default: str = None):
        val = self.Session.query(Metadate).filter_by(key=key).first()
        return val.value if val else default

    def update(self, dict_: dict):
        for key in dict_.keys():
            self.__setitem__(key, dict_[key])

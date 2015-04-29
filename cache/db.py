import os
import logging
from sqlalchemy import *
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import timedelta

import cache.sync

logger = logging.getLogger(__name__)

session = None
engine = None

Base = declarative_base()

DB_SCHEMA_VER = 1

parentage_table = Table('parentage', Base.metadata,
                        Column('parent', String(50), ForeignKey('folders.id'), primary_key=True),
                        Column('child', String(50), ForeignKey('nodes.id'), primary_key=True)
                        )


class Metadate(Base):
    """added in v1"""
    __tablename__ = 'metadata'

    key = Column(String(64), primary_key=True)
    value = Column(String)

    def __init__(self, key, value):
        self.key = key
        self.value = value


class Label(Base):
    """added in v1"""
    __tablename__ = 'labels'

    id = Column(String(50), ForeignKey('nodes.id'), primary_key=True)
    name = Column(String(256), primary_key=True)


# TODO: cycle safety for full_path()
class Node(Base):
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
        """ Compares this Node to another one on same path level. Sorts case-sensitive, Folder first. """
        if isinstance(self, Folder):
            if isinstance(other, File):
                return True
            return self.name < other.name
        if isinstance(other, Folder):
            return False
        return self.name < other.name

    def is_file(self):
        return isinstance(self, File)

    def is_folder(self):
        return isinstance(self, Folder)

    def id_str(self):
        return '[{}] [{}] {}'.format(self.id, self.status[0], self.simple_name())

    def long_id_str(self, path=None):
        if path is None:
            path = self.containing_folder()
        return '[{}] [{}] {}{}'.format(self.id, self.status[0], path,
                                       ('' if not self.name else self.name)
                                       + ('/' if isinstance(self, Folder) else ''))

    def containing_folder(self):
        if len(self.parents) == 0:
            return ''
        return self.parents[0].full_path()

    parents = relationship('Folder', secondary=parentage_table,
                           primaryjoin=id == parentage_table.c.child,
                           secondaryjoin=id == parentage_table.c.parent,
                           backref='children'
                           )


class File(Node):
    __tablename__ = 'files'

    id = Column(String(50), ForeignKey('nodes.id'), primary_key=True, unique=True)
    md5 = Column(String(32))
    size = Column(BigInteger)

    __mapper_args__ = {
        'polymorphic_identity': 'file'
    }

    def __init__(self, id, name, created, modified, md5, size, status):
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

    def simple_name(self):
        return self.name

    def full_path(self):
        if len(self.parents) == 0:
            return self.name
        return self.parents[0].full_path() + self.name


class Folder(Node):
    __tablename__ = 'folders'

    id = Column(String(50), ForeignKey('nodes.id'), primary_key=True, unique=True)

    __mapper_args__ = {
        'polymorphic_identity': 'folder'
    }

    def __init__(self, id, name, created, modified, status):
        self.id = id
        self.name = name
        self.created = created.replace(tzinfo=None)
        self.modified = modified.replace(tzinfo=None)
        self.status = status

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return false
        return (self.id == other.id
                and self.name == other.name
                and self.created == other.created
                and self.modified == other.modified
                and self.status == other.status)

    def __repr__(self):
        return 'Folder(%r, %r)' % (self.id, self.name)

    def simple_name(self):
        return (self.name if self.name is not None else '') + '/'

    # path of first occurrence
    def full_path(self):
        if len(self.parents) == 0:
            return '/'
        return self.parents[0].full_path() + (self.name if self.name is not None else '') + '/'

    def get_child(self, name):
        """ Gets non-trashed child by name. """
        for child in self.children:
            if child.name == name and child.status != 'TRASH':
                return child
        return


"""End of 'schema'"""


def init(path=''):
    db_path = os.path.join(path, 'nodes.db')

    global session
    global engine
    engine = create_engine('sqlite:///%s' % db_path)

    empty = not os.path.exists(db_path)
    if not empty:
        empty = not engine.has_table(Node.__tablename__)
    if empty:
        r = engine.execute('PRAGMA user_version = %i;' % DB_SCHEMA_VER)
        r.close()

    logger.info('Cache %sconsidered empty.' % ('' if empty else 'not '))

    Base.metadata.create_all(engine)
    _session = sessionmaker(bind=engine)
    session = _session()

    if empty:
        return

    r = engine.execute('PRAGMA user_version;')
    ver = r.first()[0]
    r.close()

    logger.info('DB schema version is %s.' % ver)

    if DB_SCHEMA_VER > ver:
        _migrate(ver)

    oldest = cache.sync.max_age()
    if oldest:
        logger.info('Oldest node info is %f days old.' % oldest)
        if oldest > 30:
            logger.warning('Cache is outdated. Please perform a full sync.')


def drop_all():
    Base.metadata.drop_all(engine)
    logger.info('Dropped all tables.')


def _migrate(schema):
    migrations = [_0_to_1]

    conn = engine.connect()
    trans = conn.begin()
    try:
        for update_ in migrations[schema:]:
            logger.warning('Updating db schema from %i to %i.' % (schema, schema + 1))
            update_(conn)
            schema += 1
        trans.commit()
    except:
        trans.rollback()
        raise

    conn.close()


def _0_to_1(conn):
    conn.execute('ALTER TABLE nodes ADD updated DATETIME;')
    conn.execute('ALTER TABLE nodes ADD description VARCHAR(500);')
    conn.execute('PRAGMA user_version = 1;')
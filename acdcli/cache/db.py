import os
import logging
import re
from sqlalchemy import *
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session, relationship, backref
from sqlalchemy.exc import DatabaseError
from sqlalchemy.event import listens_for
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

Session = None
engine = None

Base = declarative_base()

DB_SCHEMA_VER = 1
DB_FILENAME = 'nodes.db'

parentage_table = Table('parentage', Base.metadata,
                        Column('parent', String(50), ForeignKey('folders.id'), primary_key=True),
                        Column('child', String(50), ForeignKey('nodes.id'), primary_key=True)
                        )


class Metadate(Base):
    """added in v1"""
    __tablename__ = 'metadata'

    key = Column(String(64), primary_key=True)
    value = Column(String)

    def __init__(self, key: str, value: str):
        self.key = key
        self.value = value


class _KeyValueStorage(object):
    @staticmethod
    def __getitem__(key: str):
        val = Session.query(Metadate).filter_by(key=key).first()
        if val:
            return val.value
        else:
            raise KeyError

    @staticmethod
    def __setitem__(key: str, value: str):
        md = Metadate(key, value)
        Session.merge(md)
        Session.commit()

    @staticmethod
    def __len__():
        return Session.query(Metadate).count()

    @staticmethod
    def get(key: str, default: str=None):
        val = Session.query(Metadate).filter_by(key=key).first()
        return val.value if val else default

    @classmethod
    def update(cls, dict_: dict):
        for key in dict_.keys():
            cls.__setitem__(key, dict_[key])

# next best thing to a subscriptable class
KeyValueStorage = _KeyValueStorage()


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

    parents = relationship('Folder', secondary=parentage_table,
                           primaryjoin=id == parentage_table.c.child,
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


class Folder(Node):
    __tablename__ = 'folders'

    id = Column(String(50), ForeignKey('nodes.id'), primary_key=True, unique=True)

    __mapper_args__ = {
        'polymorphic_identity': 'folder'
    }

    # noinspection PyShadowingBuiltins
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

    def get_child(self, name: str) -> Node:
        """ Gets non-trashed child by name. """
        for child in self.children:
            if child.name == name and child.status != 'TRASH':
                return child
        return

    def available_children(self):
        for c in self.children:
            if c.is_available():
                yield c


"""End of 'schema'"""


IntegrityCheckType = dict(full=0, quick=1, none=2)


def init(path='', check=IntegrityCheckType['full']):
    logger.info('Initializing cache with path "%s".' % os.path.realpath(path))
    db_path = os.path.join(path, DB_FILENAME)

    # doesn't seem to work on Windows
    from ctypes import util, CDLL

    try:
        lib = util.find_library('sqlite3')
    except OSError:
        logger.info('Skipping sqlite thread-safety test.')
    else:
        if lib:
            dll = CDLL(lib)
            if dll and not dll.sqlite3_threadsafe():
                # http://www.sqlite.org/c3ref/threadsafe.html
                logger.warning('Your sqlite3 version was compiled without mutexes. '
                               'It is not thread-safe.')

    global Session
    global engine
    engine = create_engine('sqlite:///%s' % db_path, connect_args={'check_same_thread': False})

    # check for serialized mode

    uninitialized = not os.path.exists(db_path)
    if not uninitialized:
        try:
            uninitialized = not engine.has_table(Metadate.__tablename__) and \
                            not engine.has_table(Node.__tablename__) and \
                            not engine.has_table(File.__tablename__) and \
                            not engine.has_table(Folder.__tablename__)
        except DatabaseError:
            logger.critical('Error opening database.')
            return False

    integrity_check(check)

    if uninitialized:
        r = engine.execute('PRAGMA user_version = %i;' % DB_SCHEMA_VER)
        r.close()

    logger.info('Cache %sconsidered uninitialized.' % ('' if uninitialized else 'not '))

    def _regex_match(pattern: str, name: str):
        if name is None:
            return False
        return re.match(pattern, name, re.I) is not None

    @listens_for(engine, 'begin')
    def _on_engine_begin(link):
        link.connection.create_function('REGEXP', 2, _regex_match)

    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    Session = scoped_session(session_factory)

    if uninitialized:
        return True

    r = engine.execute('PRAGMA user_version;')
    ver = r.first()[0]
    r.close()

    logger.info('DB schema version is %s.' % ver)

    if DB_SCHEMA_VER > ver:
        _migrate(ver)

    return True


def integrity_check(type_: IntegrityCheckType):
    if type_ == IntegrityCheckType['full']:
        r = engine.execute('PRAGMA integrity_check;')
    elif type_ == IntegrityCheckType['quick']:
        r = engine.execute('PRAGMA quick_check;')
    else:
        return
    if r.first()[0] != 'ok':
        logger.warn('Sqlite database integrity check failed. '
                    'You may need to clear the cache if you encounter any errors.')


def dump_table_sql():
    def dump(sql, *multiparams, **params):
        print(sql.compile(dialect=engine.dialect))
    engine = create_engine('sqlite://', strategy='mock', executor=dump)
    Base.metadata.create_all(engine, checkfirst=False)


def drop_all():
    Base.metadata.drop_all(engine)
    logger.info('Dropped all tables.')


def remove_db_file(path: str):
    db_path = os.path.join(path, DB_FILENAME)
    try:
        os.remove(db_path)
    except OSError:
        logger.critical('Error removing database file "%s".' % db_path)


def _migrate(schema: int):
    """ Migrate database to highest schema
    :param schema: current (cache file) schema version to upgrade from
    """

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

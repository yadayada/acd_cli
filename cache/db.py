from sqlalchemy import *
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import timedelta

Base = declarative_base()

parentage_table = Table('parentage', Base.metadata,
                        Column('parent', String(50), ForeignKey('folders.id'), primary_key=True),
                        Column('child', String(50), ForeignKey('nodes.id'), primary_key=True)
                        )


# TODO: cycle safety for full_path()
class Node(Base):
    __tablename__ = 'nodes'

    id = Column(String(50), primary_key=True, unique=True)
    type = Column(String(15))

    created = Column(DateTime)
    modified = Column(DateTime)

    # "pending" status seems to be reserved for not yet finished uploads
    status = Column(Enum('AVAILABLE', 'TRASH', 'PURGED', 'PENDING'))

    __mapper_args__ = {
        'polymorphic_identity': 'node',
        'polymorphic_on': type
    }

    def id_str(self):
        return '[{}] [{}] {}'.format(self.id, self.status[0], self.simple_name())

    def long_id_str(self):
        return '[{}] [{}] {}'.format(self.id, self.status[0], self.full_path())

    parents = relationship('Folder', secondary=parentage_table,
                           primaryjoin=id == parentage_table.c.child,
                           secondaryjoin=id == parentage_table.c.parent,
                           backref='children'
                           )


class File(Node):
    __tablename__ = 'files'

    id = Column(String(50), ForeignKey('nodes.id'), primary_key=True, unique=True)
    name = Column(String(256), nullable=False)
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
            # print(self, 'has no parent.')
            return self.name
        return self.parents[0].full_path() + self.name


class Folder(Node):
    __tablename__ = 'folders'

    # max id length is 22 according to API doc
    id = Column(String(50), ForeignKey('nodes.id'), primary_key=True, unique=True)
    name = Column(String(256))

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

    def full_path(self):
        if len(self.parents) == 0:
            return '/'
        return self.parents[0].full_path() \
            + (self.name if self.name is not None else '') + '/'


engine = create_engine('sqlite:///nodes.db')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
session = Session()
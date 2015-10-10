import os
import logging
import re
from sqlalchemy import *
from sqlalchemy.orm import sessionmaker, scoped_session, relationship, backref
from sqlalchemy.exc import DatabaseError
from sqlalchemy.event import listen

from . import schema
from .query import QueryMixin
from .sync import SyncMixin

logger = logging.getLogger(__name__)


def _regex_match(pattern: str, col: str):
    if col is None:
        return False
    return re.match(pattern, col, re.IGNORECASE) is not None


class NodeCache(QueryMixin, SyncMixin):
    _DB_SCHEMA_VER = 1
    _DB_FILENAME = 'nodes.db'

    IntegrityCheckType = dict(full=0, quick=1, none=2)

    def __init__(self, path='', check=IntegrityCheckType['full']):
        logger.info('Initializing cache with path "%s".' % os.path.realpath(path))
        db_path = os.path.join(path, NodeCache._DB_FILENAME)

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

        self.engine = create_engine('sqlite:///%s' % db_path,
                                    connect_args={'check_same_thread': False})

        # check for serialized mode

        listen(self.engine, 'begin',
               lambda conn: conn.connection.create_function('REGEXP', 2, _regex_match))

        initialized = os.path.exists(db_path)
        if initialized:
            try:
                initialized = self.engine.has_table(schema.Metadate.__tablename__) and \
                              self.engine.has_table(schema.Node.__tablename__) and \
                              self.engine.has_table(schema.File.__tablename__) and \
                              self.engine.has_table(schema.Folder.__tablename__)
            except DatabaseError as e:
                logger.critical('Error opening database: %s' % str(e))
                raise e

        self.integrity_check(check)

        if not initialized:
            r = self.engine.execute('PRAGMA user_version = %i;' % NodeCache._DB_SCHEMA_VER)
            r.close()

        logger.info('Cache is %sinitialized.' % ('' if initialized else 'not '))

        schema._Base.metadata.create_all(self.engine)
        session_factory = sessionmaker(bind=self.engine)
        self.Session = scoped_session(session_factory)

        self.KeyValueStorage = schema._KeyValueStorage(self.Session)

        if not initialized:
            return

        r = self.engine.execute('PRAGMA user_version;')
        ver = r.first()[0]
        r.close()

        logger.info('DB schema version is %s.' % ver)

        if NodeCache._DB_SCHEMA_VER > ver:
            self._migrate(ver)

    def integrity_check(self, type_: IntegrityCheckType):
        if type_ == NodeCache.IntegrityCheckType['full']:
            r = self.engine.execute('PRAGMA integrity_check;')
        elif type_ == NodeCache.IntegrityCheckType['quick']:
            r = self.engine.execute('PRAGMA quick_check;')
        else:
            return
        if r.first()[0] != 'ok':
            logger.warn('Sqlite database integrity check failed. '
                        'You may need to clear the cache if you encounter any errors.')

    def dump_table_sql(self):
        def dump(sql, *multiparams, **params):
            print(sql.compile(dialect=self.engine.dialect))
        engine = create_engine('sqlite://', strategy='mock', executor=dump)
        schema._Base.metadata.create_all(engine, checkfirst=False)

    def drop_all(self):
        schema._Base.metadata.drop_all(self.engine)
        logger.info('Dropped all tables.')

    def _migrate(self, schema: int):
        """ Migrate database to highest schema
        :param schema: current (cache file) schema version to upgrade from
        """

        migrations = [NodeCache._0_to_1]

        conn = self.engine.connect()
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

    @staticmethod
    def _0_to_1(conn):
        conn.execute('ALTER TABLE nodes ADD updated DATETIME;')
        conn.execute('ALTER TABLE nodes ADD description VARCHAR(500);')
        conn.execute('PRAGMA user_version = 1;')


def remove_db_file(path: str):
    db_path = os.path.join(path, NodeCache._DB_FILENAME)
    try:
        os.remove(db_path)
    except OSError:
        logger.critical('Error removing database file "%s".' % db_path)
        return False
    return True

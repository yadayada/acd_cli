import configparser
import logging
import os
import re
import sqlite3
import sys
from threading import local

from acdcli.utils.conf import get_conf

from .cursors import *
from .format import FormatterMixin
from .query import QueryMixin
from .schema import SchemaMixin
from .sync import SyncMixin

logger = logging.getLogger(__name__)

_ROOT_ID_SQL = 'SELECT id FROM nodes WHERE name IS NULL AND type == "folder" ORDER BY created'


_SETTINGS_FILENAME = 'cache.ini'

_def_conf = configparser.ConfigParser()
_def_conf['sqlite'] = dict(filename='nodes.db', busy_timeout=30000, journal_mode='wal')
_def_conf['blacklist'] = dict(folders=[])



class IntegrityError(Exception):
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return repr(self.msg)


def _create_conn(path: str) -> sqlite3.Connection:
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row # allow dict-like access on rows with col name
    return c


def _regex_match(pattern: str, cell: str) -> bool:
    if cell is None:
        return False
    return re.match(pattern, cell, re.IGNORECASE) is not None


class NodeCache(SchemaMixin, QueryMixin, SyncMixin, FormatterMixin):
    IntegrityCheckType = dict(full=0, quick=1, none=2)
    """types of SQLite integrity checks"""

    def __init__(self, cache_path: str='', settings_path='', check=IntegrityCheckType['full']):
        self._conf = get_conf(settings_path, _SETTINGS_FILENAME, _def_conf)

        self.db_path = os.path.join(cache_path, self._conf['sqlite']['filename'])
        self.tl = local()

        self.integrity_check(check)
        try:
            self.init()
        except sqlite3.DatabaseError as e:
            raise IntegrityError(e)

        self._conn.create_function('REGEXP', _regex_match.__code__.co_argcount, _regex_match)

        with cursor(self._conn) as c:
            c.execute(_ROOT_ID_SQL)
            row = c.fetchone()
            if not row:
                self.root_id = ''
                return
            first_id = row['id']

            if c.fetchone():
                raise IntegrityError('Could not uniquely identify root node.')

            self.root_id = first_id

        self._execute_pragma('busy_timeout', self._conf['sqlite']['busy_timeout'])
        if sys.version_info[:3] != (3, 6, 0):
            self._execute_pragma('journal_mode', self._conf['sqlite']['journal_mode'])

    @property
    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self.tl, '_conn'):
            self.tl._conn = _create_conn(self.db_path)
        return self.tl._conn

    def _execute_pragma(self, key, value) -> str:
        with cursor(self._conn) as c:
            c.execute('PRAGMA %s=%s;' % (key, value))
            r = c.fetchone()
        if r:
            logger.debug('Set %s to %s. Result: %s.' % (key, value, r[0]))
            return r[0]

    @classmethod
    def remove_db_file(cls, cache_path='', settings_path='') -> bool:
        """Removes database file."""

        import os
        import random
        import string
        import tempfile

        conf = get_conf(settings_path, _SETTINGS_FILENAME, _def_conf)
        db_path = os.path.join(cache_path, conf['sqlite']['filename'])

        tmp_name = ''.join(random.choice(string.ascii_lowercase) for _ in range(16))
        tmp_name = os.path.join(tempfile.gettempdir(), tmp_name)

        try:
            os.rename(db_path, tmp_name)
        except OSError:
            logger.critical('Error renaming/removing database file "%s".' % db_path)
            return False
        else:
            try:
                os.remove(tmp_name)
            except OSError:
                logger.info('Database file was moved, but not deleted.')
        return True

    def integrity_check(self, type_: IntegrityCheckType):
        """Performs a `self-integrity check
        <https://www.sqlite.org/pragma.html#pragma_integrity_check>`_ on the database."""

        with cursor(self._conn) as c:
            if type_ == NodeCache.IntegrityCheckType['full']:
                r = c.execute('PRAGMA integrity_check;')
            elif type_ == NodeCache.IntegrityCheckType['quick']:
                r = c.execute('PRAGMA quick_check;')
            else:
                return
            r = c.fetchone()
            if not r or r[0] != 'ok':
                logger.warn('Sqlite database integrity check failed. '
                            'You may need to clear the cache if you encounter any errors.')

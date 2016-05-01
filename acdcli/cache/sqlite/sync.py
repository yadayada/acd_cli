"""
Syncs Amazon Node API objects with SQLite database.
"""

import logging
from datetime import datetime
from itertools import islice
from .cursors import mod_cursor
import dateutil.parser as iso_date

logger = logging.getLogger(__name__)


# prevent sqlite3 from throwing too many arguments errors (#145)
def gen_slice(list_, length=100):
    it = iter(list_)
    while True:
        slice_ = [_ for _ in islice(it, length)]
        if not slice_:
            return
        yield slice_


def placeholders(args):
    return '(%s)' % ','.join('?' * len(args))


class SyncMixin(object):
    """Sync mixin to the :class:`NodeCache <acdcli.cache.db.NodeCache>`"""

    def remove_purged(self, purged: list):
        """Removes purged nodes from database

        :param purged: list of purged node IDs"""

        if not purged:
            return

        for slice_ in gen_slice(purged):
            with mod_cursor(self._conn) as c:
                c.execute('DELETE FROM nodes WHERE id IN %s' % placeholders(slice_), slice_)
                c.execute('DELETE FROM files WHERE id IN %s' % placeholders(slice_), slice_)
                c.execute('DELETE FROM parentage WHERE parent IN %s' % placeholders(slice_), slice_)
                c.execute('DELETE FROM parentage WHERE child IN %s' % placeholders(slice_), slice_)
                c.execute('DELETE FROM labels WHERE id IN %s' % placeholders(slice_), slice_)

        logger.info('Purged %i node(s).' % len(purged))

    def insert_nodes(self, nodes: list, partial=True):
        """Inserts mixed list of files and folders into cache."""
        files = []
        folders = []
        for node in nodes:
            if node['status'] == 'PENDING':
                continue
            kind = node['kind']
            if kind == 'FILE':
                if not 'name' in node or not node['name']:
                    logger.warning('Skipping file %s because its name is empty.' % node['id'])
                    continue
                files.append(node)
            elif kind == 'FOLDER':
                if (not 'name' in node or not node['name']) \
                and (not 'isRoot' in node or not node['isRoot']):
                    logger.warning('Skipping non-root folder %s because its name is empty.'
                                   % node['id'])
                    continue
                folders.append(node)
            elif kind != 'ASSET':
                logger.warning('Cannot insert unknown node type "%s".' % kind)
        self.insert_folders(folders)
        self.insert_files(files)

        self.insert_parentage(files + folders, partial)

    def insert_node(self, node: dict):
        """Inserts single file or folder into cache."""
        if not node:
            return
        self.insert_nodes([node])

    def insert_folders(self, folders: list):
        """ Inserts list of folders into cache. Sets 'update' column to current date.

        :param folders: list of raw dict-type folders"""

        if not folders:
            return

        with mod_cursor(self._conn) as c:
            for f in folders:
                c.execute(
                    'INSERT OR REPLACE INTO nodes '
                    '(id, type, name, description, created, modified, updated, status) '
                    'VALUES (?, "folder", ?, ?, ?, ?, ?, ?)',
                    [f['id'], f.get('name'), f.get('description'),
                     iso_date.parse(f['createdDate']), iso_date.parse(f['modifiedDate']),
                     datetime.utcnow(),
                     f['status']
                     ]
                )

        logger.info('Inserted/updated %d folder(s).' % len(folders))

    def insert_files(self, files: list):
        if not files:
            return

        with mod_cursor(self._conn) as c:
            for f in files:
                c.execute('INSERT OR REPLACE INTO nodes '
                          '(id, type, name, description, created, modified, updated, status)'
                          'VALUES (?, "file", ?, ?, ?, ?, ?, ?)',
                          [f['id'], f.get('name'), f.get('description'),
                           iso_date.parse(f['createdDate']), iso_date.parse(f['modifiedDate']),
                           datetime.utcnow(),
                           f['status']
                           ]
                          )
                c.execute('INSERT OR REPLACE INTO files (id, md5, size) VALUES (?, ?, ?)',
                          [f['id'],
                           f.get('contentProperties', {}).get('md5',
                                                              'd41d8cd98f00b204e9800998ecf8427e'),
                           f.get('contentProperties', {}).get('size', 0)
                           ]
                          )

        logger.info('Inserted/updated %d file(s).' % len(files))

    def insert_parentage(self, nodes: list, partial=True):
        if not nodes:
            return

        if partial:
            with mod_cursor(self._conn) as c:
                for slice_ in gen_slice(nodes):
                    c.execute('DELETE FROM parentage WHERE child IN %s' % placeholders(slice_),
                              [n['id'] for n in slice_])

        with mod_cursor(self._conn) as c:
            for n in nodes:
                for p in n['parents']:
                    c.execute('INSERT OR IGNORE INTO parentage VALUES (?, ?)', [p, n['id']])

        logger.info('Parented %d node(s).' % len(nodes))

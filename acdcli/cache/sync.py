"""
Syncs Amazon Node API objects with SQLite database.
"""

import logging
from datetime import datetime, timedelta

try:
    import dateutil.parser as iso_date
except ImportError:
    # noinspection PyPep8Naming
    class iso_date(object):
        @staticmethod
        def parse(str_: str):
            return datetime.strptime(str_, '%Y-%m-%dT%H:%M:%S.%fZ')

from . import schema

logger = logging.getLogger(__name__)


class SyncMixin(object):
    def remove_purged(self, purged: list):
        """:param purged: list of purged node ids"""
        if not purged:
            return

        conn = self.engine.connect()
        trans = conn.begin()

        conn.execute(schema.Node.__table__.delete().where(schema.Node.id.in_(purged)))
        conn.execute(schema.File.__table__.delete().where(schema.File.id.in_(purged)))
        conn.execute(schema.Folder.__table__.delete().where(schema.Folder.id.in_(purged)))
        conn.execute(schema._parentage_table.delete()
                     .where(schema._parentage_table.columns.parent.in_(purged)))
        conn.execute(schema._parentage_table.delete()
                     .where(schema._parentage_table.columns.child.in_(purged)))

        conn.execute(schema.Label.__table__.delete().where(schema.Label.id.in_(purged)))

        trans.commit()
        conn.close()

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
                files.append(node)
            elif kind == 'FOLDER':
                folders.append(node)
            elif kind != 'ASSET':
                logger.warning('Cannot insert unknown node type "%s".' % kind)
        self.insert_folders(folders)
        self.insert_files(files)

        self.insert_parentage(files + folders, partial)

    def insert_node(self, node: schema.Node):
        """Inserts single file or folder into cache."""
        if not node:
            return
        self.insert_nodes([node])

    def insert_folders(self, folders: list):
        """ Inserts list of folders into cache. Sets 'update' column to current date.
        :param folders: list of raw dict-type folders
        """
        if not folders:
            return

        stmt1 = str(schema.Node.__table__.insert())
        stmt1 = stmt1.replace('INSERT INTO', 'INSERT OR REPLACE INTO')

        stmt2 = str(schema.Folder.__table__.insert())
        stmt2 = stmt2.replace('INSERT INTO', 'INSERT OR REPLACE INTO')

        conn = self.engine.connect()
        trans = conn.begin()

        conn.execute(
            stmt1,
            [dict(id=f['id'],
                  type='folder',
                  name=f.get('name'),
                  description=f.get('description'),
                  created=iso_date.parse(f['createdDate']),
                  modified=iso_date.parse(f['modifiedDate']),
                  updated=datetime.utcnow(),
                  status=f['status']
                  ) for f in folders
             ]
        )
        conn.execute(stmt2, [dict(id=f['id']) for f in folders])

        trans.commit()
        conn.close()

        logger.info('Inserted/updated %d folder(s).' % len(folders))

    def insert_files(self, files: list):
        if not files:
            return

        stmt1 = str(schema.Node.__table__.insert())
        stmt1 = stmt1.replace('INSERT INTO', 'INSERT OR REPLACE INTO')

        stmt2 = str(schema.File.__table__.insert())
        stmt2 = stmt2.replace('INSERT INTO', 'INSERT OR REPLACE INTO')

        conn = self.engine.connect()
        trans = conn.begin()

        conn.execute(
            stmt1,
            [dict(id=f['id'],
                  type='file',
                  name=f.get('name'),
                  description=f.get('description'),
                  created=iso_date.parse(f['createdDate']),
                  modified=iso_date.parse(f['modifiedDate']),
                  updated=datetime.utcnow(),
                  status=f['status']
                  ) for f in files
             ]
        )
        conn.execute(
            stmt2,
            [dict(id=f['id'],
                  md5=f.get('contentProperties', {}).get('md5', 'd41d8cd98f00b204e9800998ecf8427e'),
                  size=f.get('contentProperties', {}).get('size', 0)
                  ) for f in files
             ]
        )

        trans.commit()
        conn.close()

        logger.info('Inserted/updated %d file(s).' % len(files))

    def insert_parentage(self, nodes: list, partial=True):
        if not nodes:
            return

        conn = self.engine.connect()
        trans = conn.begin()

        if partial:
            conn.execute('DELETE FROM parentage WHERE child IN (%s)' %
                         ', '.join([('"%s"' % n['id']) for n in nodes]))
        for n in nodes:
            for p in n['parents']:
                conn.execute('INSERT OR IGNORE INTO parentage VALUES (?, ?)', p, n['id'])
        trans.commit()
        conn.close()

        logger.info('Parented %d node(s).' % len(nodes))

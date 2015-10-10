"""
Syncs Amazon Node API objects with SQLite database.
"""

import logging
from datetime import datetime, timedelta
from itertools import islice

try:
    import dateutil.parser as iso_date
except ImportError:
    # noinspection PyPep8Naming
    class iso_date(object):
        @staticmethod
        def parse(str_: str):
            return datetime.strptime(str_, '%Y-%m-%dT%H:%M:%S.%fZ')

from .schema import Node, File, Folder, Label, _parentage_table

logger = logging.getLogger(__name__)


# prevent sqlite3 from throwing too many arguments errors (#145)
def gen_slice(list_, length=100):
    it = iter(list_)
    while True:
        slice_ = [_ for _ in islice(it, length)]
        if not slice_:
            return
        yield slice_


class SyncMixin(object):
    def remove_purged(self, purged: list):
        """Removes purged nodes from database
        :param purged: list of purged node IDs"""
        if not purged:
            return

        for slice_ in gen_slice(purged):
            with self.engine.connect() as conn:
                with conn.begin():
                    conn.execute(Node.__table__.delete().where(Node.id.in_(slice_)))
                    conn.execute(File.__table__.delete().where(File.id.in_(slice_)))
                    conn.execute(Folder.__table__.delete().where(Folder.id.in_(slice_)))
                    conn.execute(_parentage_table.delete()
                                 .where(_parentage_table.columns.parent.in_(slice_)))
                    conn.execute(_parentage_table.delete()
                                 .where(_parentage_table.columns.child.in_(slice_)))

                    conn.execute(Label.__table__.delete().where(Label.id.in_(slice_)))

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

    def insert_node(self, node: dict):
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

        stmt1 = str(Node.__table__.insert())
        stmt1 = stmt1.replace('INSERT INTO', 'INSERT OR REPLACE INTO')

        stmt2 = str(Folder.__table__.insert())
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

        stmt1 = str(Node.__table__.insert())
        stmt1 = stmt1.replace('INSERT INTO', 'INSERT OR REPLACE INTO')

        stmt2 = str(File.__table__.insert())
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
            for slice_ in gen_slice(nodes):
                with self.engine.connect() as conn:
                    with conn.begin():
                        conn.execute('DELETE FROM parentage WHERE child IN (%s)' %
                                     ', '.join([('"%s"' % n['id']) for n in slice_]))

        with self.engine.connect() as conn:
            with conn.begin():
                for n in nodes:
                    for p in n['parents']:
                        conn.execute('INSERT OR IGNORE INTO parentage VALUES (?, ?)', p, n['id'])

        logger.info('Parented %d node(s).' % len(nodes))

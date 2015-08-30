"""
Syncs Amazon Node API objects with sqlite database
"""

import logging
from sqlalchemy.exc import *
from datetime import datetime, timedelta

try:
    import dateutil.parser as iso_date
except ImportError:
    # noinspection PyPep8Naming
    class iso_date(object):
        @staticmethod
        def parse(str_: str):
            return datetime.strptime(str_, '%Y-%m-%dT%H:%M:%S.%fZ')

from . import db

logger = logging.getLogger(__name__)


def remove_purged(purged: list):
    if not purged:
        return

    for p_id in purged:
        db.Session.query(db.Node).filter_by(id=p_id).delete()
    db.Session.commit()
    logger.info('Purged %i node(s).' % len(purged))


def insert_nodes(nodes: list, partial=True):
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
    insert_folders(folders)
    insert_files(files)

    insert_parentage(files + folders, partial)


def insert_node(node: db.Node):
    """Inserts single file or folder into cache."""
    if not node:
        return
    insert_nodes([node])


def insert_folders(folders: list):
    """ Inserts list of folders into cache. Sets 'update' column to current date.
    :param folders: list of raw dict-type folders
    """

    if not folders:
        return

    for folder in folders:
        logger.debug(folder)

        # root folder has no name key
        f_name = folder.get('name')
        f = db.Folder(folder['id'], f_name,
                      iso_date.parse(folder['createdDate']),
                      iso_date.parse(folder['modifiedDate']),
                      folder['status'])
        f.updated = datetime.utcnow()
        db.Session.merge(f)

    try:
        db.Session.commit()
    except IntegrityError:
        logger.warning('Error inserting folder(s).')
        db.Session.rollback()

    logger.info('Inserted/updated %d folder(s).' % len(folders))


def insert_files(files: list):
    if not files:
        return

    stmt1 = str(db.Node.__table__.insert())
    stmt1 = stmt1.replace('INSERT INTO', 'INSERT OR REPLACE INTO')

    stmt2 = str(db.File.__table__.insert())
    stmt2 = stmt2.replace('INSERT INTO', 'INSERT OR REPLACE INTO')

    conn = db.engine.connect()
    trans = conn.begin()

    conn.execute(
        stmt1,
        [dict(id=f['id'], type='file', name=f.get('name'), description=f.get('description'),
              created=iso_date.parse(f['createdDate']),
              modified=iso_date.parse(f['modifiedDate']),
              updated=datetime.utcnow(),
              status=f['status']
              ) for f in files
         ]
    )
    conn.execute(
        stmt2,
        [dict(id=f['id'], md5=f.get('contentProperties', {}).get('md5', 'd41d8cd98f00b204e9800998ecf8427e'),
              size=f.get('contentProperties', {}).get('size', 0)
              ) for f in files
         ]
    )

    trans.commit()

    logger.info('Inserted/updated %d file(s).' % len(files))


def insert_parentage(nodes: list, partial=True):
    if not nodes:
        return

    conn = db.engine.connect()
    trans = conn.begin()

    if partial:
        conn.execute('DELETE FROM parentage WHERE child IN (%s)' %
                     ', '.join(['"' + n['id'] + '"' for n in nodes]))
    for n in nodes:
        for p in n['parents']:
            conn.execute('INSERT OR IGNORE INTO parentage VALUES (?, ?)', p, n['id'])
    trans.commit()

    logger.info('Parented %d node(s).' % len(nodes))

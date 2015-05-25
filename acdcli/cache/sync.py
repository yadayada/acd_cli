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
    session = db.Session()
    for p_id in purged:
        session.query(db.Node).filter_by(id=p_id).delete()
    session.commit()
    logger.info('Purged %i nodes.' % len(purged))


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
        pass
    insert_nodes([node])


def insert_folders(folders: list):
    """ Inserts list of folders into cache. Sets 'update' column to current date.
    :param folders: list of raw dict-type folders
    """

    session = db.Session()
    for folder in folders:
        logger.debug(folder)

        # root folder has no name key
        f_name = folder.get('name')
        f = db.Folder(folder['id'], f_name,
                      iso_date.parse(folder['createdDate']),
                      iso_date.parse(folder['modifiedDate']),
                      folder['status'])
        f.updated = datetime.utcnow()
        session.merge(f)

    try:
        session.commit()
    except IntegrityError:
        logger.warning('Error inserting folders.')
        session.rollback()

    logger.info('Inserted/updated %d folders.' % len(folders))

# file movement is detected by updated modifiedDate
def insert_files(files: list):
    stmt1 = str(db.Node.__table__.insert())
    stmt1 = stmt1.replace('INSERT INTO', 'INSERT OR REPLACE INTO')

    stmt2 = str(db.File.__table__.insert())
    stmt2 = stmt2.replace('INSERT INTO', 'INSERT OR REPLACE INTO')

    db.engine.execute(
        stmt1,
        [dict(id=f['id'], type='file', name=f.get('name'), description=f.get('description'),
              created=iso_date.parse(f['createdDate']),
              modified=iso_date.parse(f['modifiedDate']),
              updated=datetime.utcnow(),
              status=f['status']
              ) for f in files
         ]
    )
    db.engine.execute(
        stmt2,
        [dict(id=f['id'], md5=f.get('contentProperties', {}).get('md5', 'd41d8cd98f00b204e9800998ecf8427e'),
              size=f.get('contentProperties', {}).get('size', 0)
              ) for f in files
         ]
    )

    logger.info('Inserted/updated %d files.' % len(files))

def insert_parentage(nodes: list, partial=True):
    conn = db.engine.connect()
    trans = conn.begin()

    if partial:
        conn.execute('DELETE FROM parentage WHERE child IN (%s)' %
                     ', '.join(['"' + n['id'] + '"' for n in nodes]))
    for n in nodes:
        for p in n['parents']:
            conn.execute('INSERT OR IGNORE INTO parentage VALUES (?, ?)', p, n['id'])
    trans.commit()

    logger.info('Parented %d nodes.' % len(nodes))
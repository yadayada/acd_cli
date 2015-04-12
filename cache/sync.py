"""
Syncs Amazon Node API objects with sqlite database
"""

import logging
from sqlalchemy.exc import *
import dateutil.parser as iso_date

from cache import db

logger = logging.getLogger(__name__)


def insert_node(node):
    if not node:
        pass
    if node['kind'] == 'FILE':
        insert_files([node], True)
    elif node['kind'] == 'FOLDER':
        insert_folders([node], True)
    else:
        logging.warning('Cannot insert unknown node type.')


def insert_folders(folders, partial=False):
    """
    Inserts lists folders
    :param folders: list of raw dict-type folders
    :param partial: whether the list of folders is not complete
    """

    ins = 0
    dup = 0
    upd = 0
    dtd = 0

    parents = []
    for folder in folders:
        logger.debug(folder)

        # root folder has no name key
        f_name = folder.get('name')
        f = db.Folder(folder['id'], f_name,
                      iso_date.parse(folder['createdDate']),
                      iso_date.parse(folder['modifiedDate']),
                      folder['status'])
        ef = db.session.query(db.Folder).filter_by(id=folder['id']).first()

        if not ef:
            db.session.add(f)
            ins += 1
        else:
            if f == ef:
                dup += 1
            else:
                upd += 1
            db.session.delete(ef)
            db.session.add(f)

        parents.append((f.id, folder['parents']))

    if not partial:
        for db_folder in db.session.query(db.Folder):
            for folder in folders:
                if db_folder.id == folder['id']:
                    break
            else:
                db.session.delete(db_folder)
                dtd += 1

    try:
        db.session.commit()
    except IntegrityError:
        logger.warning('Error inserting folders.')
        db.session.rollback()

    if ins > 0:
        logger.info(str(ins) + ' folder(s) inserted.')
    if dup > 0:
        logger.info(str(dup) + ' duplicate folders not inserted.')
    if upd > 0:
        logger.info(str(upd) + ' folder(s) updated.')
    if dtd > 0:
        logger.info(str(dtd) + ' folder(s) deleted.')

    conn = db.engine.connect()
    for rel in parents:
        for p in rel[1]:
            conn.execute('INSERT OR IGNORE INTO parentage VALUES (?, ?)', p, rel[0])


# file movement is detected by updated modifiedDate
def insert_files(files, partial=False):
    ins = 0
    dup = 0
    upd = 0
    dtd = 0

    with db.session.no_autoflush:
        for file in files:
            props = {}
            try:
                props = file['contentProperties']
            except KeyError:  # empty files
                props['md5'] = 'd41d8cd98f00b204e9800998ecf8427e'
                props['size'] = 0

            f = db.File(file['id'], file['name'],
                        iso_date.parse(file['createdDate']),
                        iso_date.parse(file['modifiedDate']),
                        props['md5'], props['size'],
                        file['status'])
            ef = db.session.query(db.File).filter_by(id=file['id']).first()

            if not ef:
                db.session.add(f)
                ins += 1
            else:
                if f == ef:
                    dup += 1
                else:
                    upd += 1
                db.session.delete(ef)
                db.session.add(f)

            for p in file['parents']:
                p_folder = db.session.query(db.Folder).filter_by(id=p).first()
                if p_folder is None:
                    # print('Parent folder of [%s] not found.' % f.name)
                    logger.warning('Node %s [%s] has no parent %s.' % (f.id, f.name, p_folder))
                elif f not in p_folder.children:
                    f.parents.append(db.session.query(db.Folder).filter_by(id=p).first())

    if not partial:
        for db_file in db.session.query(db.File):
            found = False
            for file in files:
                if db_file.id == file['id']:
                    found = True
                    break
            if not found:
                db.session.delete(db_file)
                dtd += 1

    try:
        db.session.commit()
    except ValueError:
        logger.warning('Error inserting files.')
        db.session.rollback()

    if ins > 0:
        logger.info(str(ins) + ' file(s) inserted.')
    if upd > 0:
        logger.info(str(upd) + ' file(s) updated.')
    if dup > 0:
        logger.info(str(dup) + ' duplicate files not inserted.')
    if dtd > 0:
        logger.info(str(dtd) + ' file(s) deleted.')
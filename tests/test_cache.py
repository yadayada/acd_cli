import unittest
import os

from acdcli.cache import db, sync, query
from .test_helper import gen_file, gen_folder, gen_bunch_of_nodes


class CacheTestCase(unittest.TestCase):
    path = os.path.join(os.path.dirname(__file__), 'dummy_files')

    def setUp(self):
        db.remove_db_file(self.path)
        db.init(self.path)

    def tearDown(self):
        db.remove_db_file(self.path)

    def testEmpty(self):
        self.assertEqual(query.get_node_count(), 0)

    def testInsertFolder(self):
        folder = gen_folder()
        sync.insert_node(folder)
        n = query.get_node(folder['id'])
        self.assertEqual(n.id, folder['id'])
        self.assertEqual(query.get_node_count(), 1)

    def testInsertFile(self):
        root = gen_folder()
        sync.insert_node(root)
        file = gen_file([root])
        sync.insert_node(file)
        n = query.get_node(file['id'])
        self.assertEqual(len(n.parents), 1)
        self.assertEqual(query.get_node_count(), 2)

    def testFileMovement(self):
        root = gen_folder()
        folder = gen_folder([root])
        self.assertNotEqual(root['id'], folder['id'])

        file = gen_file([root])
        sync.insert_nodes([root, file])
        n = query.get_node(file['id'])
        self.assertEqual(n.parents[0].id, root['id'])

        file['parents'] = [folder['id']]
        sync.insert_nodes([folder, file])
        self.assertEqual(n.parents[0].id, folder['id'])

        self.assertEqual(len(n.parents), 1)
        self.assertEqual(query.get_node_count(), 3)

    def testPurge(self):
        root = gen_folder()
        file = gen_file([root])

        sync.insert_nodes([root, file])
        self.assertEqual(query.get_node_count(), 2)
        self.assertIsInstance(query.get_node(file['id']), db.File)

        sync.remove_purged([file['id']])
        self.assertIsNone(query.get_node(file['id']))
        self.assertEqual(query.get_node_count(), 1)

    def testMultiParentNode(self):
        root = gen_folder()
        folder = gen_folder([root])
        file = gen_file([root])
        file['parents'].append(folder['id'])
        self.assertEqual(len(file['parents']), 2)

        sync.insert_nodes([root, folder, file])
        self.assertEqual(query.get_node_count(), 3)
        self.assertEqual(query.get_node(file['id']).parents.__len__(), 2)

    def testListChildren(self):
        folders, files = gen_bunch_of_nodes(25)
        sync.insert_nodes(files + folders)
        children = query.list_children(folders[0]['id'], recursive=True, trash=True)
        self.assertEqual(sum(1 for _ in children), len(files + folders) - 1)

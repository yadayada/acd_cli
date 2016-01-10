import unittest
import os

from acdcli.cache import db, schema
from .test_helper import gen_file, gen_folder, gen_bunch_of_nodes


class CacheTestCase(unittest.TestCase):
    path = os.path.join(os.path.dirname(__file__), 'dummy_files')

    def setUp(self):
        self.cache = db.NodeCache(self.path)

    def tearDown(self):
        self.cache.remove_db_file()

    def testEmpty(self):
        self.assertEqual(self.cache.get_node_count(), 0)

    def testInsertFolder(self):
        folder = gen_folder()
        self.cache.insert_node(folder)
        n = self.cache.get_node(folder['id'])
        self.assertEqual(n.id, folder['id'])
        self.assertEqual(self.cache.get_node_count(), 1)

    def testInsertFile(self):
        root = gen_folder()
        self.cache.insert_node(root)
        file = gen_file([root])
        self.cache.insert_node(file)
        n = self.cache.get_node(file['id'])
        self.assertEqual(len(n.parents), 1)
        self.assertEqual(self.cache.get_node_count(), 2)

    def testFileMovement(self):
        root = gen_folder()
        folder = gen_folder([root])
        self.assertNotEqual(root['id'], folder['id'])

        file = gen_file([root])
        self.cache.insert_nodes([root, file])
        n = self.cache.get_node(file['id'])
        self.assertEqual(n.parents[0].id, root['id'])

        file['parents'] = [folder['id']]
        self.cache.insert_nodes([folder, file])

        self.cache.Session.expunge(n)
        n = self.cache.get_node(file['id'])
        self.assertEqual(n.parents[0].id, folder['id'])

        self.assertEqual(len(n.parents), 1)
        self.assertEqual(self.cache.get_node_count(), 3)

    def testPurge(self):
        root = gen_folder()
        file = gen_file([root])

        self.cache.insert_nodes([root, file])
        self.assertEqual(self.cache.get_node_count(), 2)
        self.assertIsInstance(self.cache.get_node(file['id']), schema.File)

        self.cache.remove_purged([file['id']])
        self.assertIsNone(self.cache.get_node(file['id']))
        self.assertEqual(self.cache.get_node_count(), 1)

    def testMultiParentNode(self):
        root = gen_folder()
        folder = gen_folder([root])
        file = gen_file([root])
        file['parents'].append(folder['id'])
        self.assertEqual(len(file['parents']), 2)

        self.cache.insert_nodes([root, folder, file])
        self.assertEqual(self.cache.get_node_count(), 3)
        self.assertEqual(self.cache.get_node(file['id']).parents.__len__(), 2)

    def testListChildren(self):
        folders, files = gen_bunch_of_nodes(25)
        self.cache.insert_nodes(files + folders)
        children = self.cache.list_children(folders[0]['id'], recursive=True, trash=True)
        self.assertEqual(sum(1 for _ in children), len(files + folders) - 1)

    def testCalculateUsageEmpty(self):
        self.assertEqual(self.cache.calculate_usage(), 0)

    def testCalculateUsageEmpty2(self):
        self.cache.insert_node(gen_folder())
        self.assertEqual(self.cache.calculate_usage(), 0)

    def testCalculateUsage(self):
        folders, files = gen_bunch_of_nodes(50)
        self.cache.insert_nodes(folders + files)
        ttlsz = sum(f['contentProperties']['size'] for f in files)
        self.assertEqual(self.cache.calculate_usage(), ttlsz)

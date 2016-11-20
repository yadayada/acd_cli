import unittest
import os

from acdcli.cache import db, schema
from .test_helper import gen_file, gen_folder, gen_bunch_of_nodes


class CacheTestCase(unittest.TestCase):
    path = os.path.join(os.path.dirname(__file__), 'dummy_files')

    def setUp(self):
        self.cache = db.NodeCache(self.path)

    def tearDown(self):
        db.NodeCache.remove_db_file(self.path)

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
        self.assertEqual(self.cache.get_node_count(), 2)

    def testFileMovement(self):
        root = gen_folder()
        folder = gen_folder([root])
        self.assertNotEqual(root['id'], folder['id'])

        file = gen_file([root])
        self.cache.insert_nodes([root, file])

        _, rc = self.cache.list_children(root['id'], True)
        self.assertIn(file['id'], [n.id for n in rc])

        file['parents'] = [folder['id']]
        self.cache.insert_nodes([folder, file])

        _, rc = self.cache.list_children(root['id'], True)
        _, fc = self.cache.list_children(folder['id'], True)

        self.assertIn(file['id'], [n.id for n in fc])
        self.assertNotIn(file['id'], [n.id for n in rc])

    def testPurge(self):
        root = gen_folder()
        file = gen_file([root])

        self.cache.insert_nodes([root, file])
        self.assertEqual(self.cache.get_node_count(), 2)
        self.assertTrue(self.cache.get_node(file['id']).is_file)

        self.cache.remove_purged([file['id']])
        self.assertIsNone(self.cache.get_node(file['id']))
        self.assertEqual(self.cache.get_node_count(), 1)

    def testMultiParentNode(self):
        root = gen_folder()
        folder = gen_folder([root])
        folder['status'] = 'AVAILABLE'

        file = gen_file([root])
        file['parents'].append(folder['id'])
        self.assertEqual(len(file['parents']), 2)

        self.cache.insert_nodes([root, folder, file])
        self.assertEqual(self.cache.get_node_count(), 3)
        self.assertEqual(self.cache.num_parents(file['id']), 2)

    def testListChildren(self):
        root = gen_folder()
        folders = [gen_folder([root]) for _ in range(25)]
        files = [gen_file([root]) for _ in range(25)]
        self.cache.insert_nodes(files + folders)
        fo, fi = self.cache.list_children(root['id'], trash=True)
        self.assertEqual(len(fo) + len(fi), len(files + folders))

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

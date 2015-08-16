import random
import string
import unittest


def gen_rand_name():
    return str.join('', (random.choice(string.ascii_letters + string.digits) for _ in range(64)))


def gen_rand_id():
    return str.join('', (random.choice(string.ascii_letters + string.digits + '-_')
                         for _ in range(22)))


def gen_rand_md5():
    return str.join('', (random.choice(string.ascii_lowercase + string.digits) for _ in range(32)))


def gen_folder(folders: list=None):
    folder = {
        'createdBy': 'acd_cli_oa-<user>',
        'createdDate': '2015-01-01T00:00:00.00Z',
        'eTagResponse': 'AbCdEfGhI01',
        'id': gen_rand_id(),
        'isShared': False,
        'kind': 'FOLDER',
        'labels': [],
        'modifiedDate': '2015-01-01T00:00:00.000Z',
        'name': gen_rand_name(),
        'parents': [],
        'restricted': False,
        'status': 'AVAILABLE' if not folders else random.choice(['TRASH', 'AVAILABLE']),
        'version': random.randint(1, 20)
    }
    if not folders:
        folder['name'] = None
        folder['isRoot'] = True
    elif len(folders) == 1:
        folder['parents'] = [folders[0]['id']]
    else:
        folder['parents'] = [folders[random.randint(0, len(folders) - 1)]['id']]
    return folder


def gen_file(folders: list):
    file = {
        'contentProperties': {'contentType': 'text/plain',
                              'extension': 'txt',
                              'md5': gen_rand_md5(),
                              'size': random.randint(0, 32 * 1024 ** 3),
                              'version': random.randint(1, 20)},
        'createdBy': 'acd_cli_oa-<user>',
        'createdDate': '2015-01-01T00:00:00.00Z',
        'eTagResponse': 'AbCdEfGhI01',
        'id': gen_rand_id(),
        'isShared': False,
        'kind': 'FILE',
        'labels': [],
        'modifiedDate': '2015-01-01T00:00:00.000Z',
        'name': gen_rand_name(),
        'parents': [folders[random.randint(0, len(folders) - 1)]['id']],
        'restricted': False,
        'status': random.choice(['AVAILABLE', 'TRASH']),
        'version': random.randint(1, 20)
    }
    return file


def gen_bunch_of_nodes(count: int):
    folders = []
    files = []
    for _ in range(int(count / 2)):
        folders.append(gen_folder(folders))
    for _ in range(int(count / 2)):
        files.append(gen_file(folders))

    return folders, files


class HelperTestCase(unittest.TestCase):
    def setUp(self):
        pass

    def tearDown(self):
        pass

    def testCreateRootFolder(self):
        folder = gen_folder()
        self.assertIn('isRoot', folder)
        self.assertListEqual(folder['parents'], [])

    def testCreateNonRootFolder(self):
        root = gen_folder()
        folder = gen_folder([root])
        self.assertNotIn('isRoot', folder)
        self.assertListEqual(folder['parents'], [root['id']])

    def testMultiFolders(self):
        folders = []
        for _ in range(100):
            folders.append(gen_folder(folders))
        self.assertEqual(1, sum(f.get('isRoot', 0) for f in folders))
        self.assertEqual(99, sum(len(f['parents']) for f in folders))

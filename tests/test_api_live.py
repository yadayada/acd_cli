"""Real, live Amazon Cloud Drive API tests"""

import unittest
import logging
import os
import io
import random
import string
import mmap

from acdcli.api import account, common, content, metadata, trash, oauth
from acdcli.api.common import RequestError
from acdcli.utils import hashing

logging.basicConfig(level=logging.INFO)
common.BackOffRequest._wait = lambda: None
path = os.path.join(os.path.dirname(__file__), 'cache_files')
common.init(path)


def gen_rand_nm():
    return str.join('', (random.choice(string.ascii_letters + string.digits) for _ in range(64)))


def gen_rand_sz():
    return random.randint(1, 32 * 1024)


def gen_rand_file(size=gen_rand_sz()) -> tuple:
    fn = gen_rand_nm()
    with open(fn, 'wb') as f:
        f.write(os.urandom(size))
    return fn, size


def gen_rand_anon_mmap(size=gen_rand_sz()) -> tuple:
    mmo = mmap.mmap(-1, size)
    mmo.write(os.urandom(size))
    mmo.seek(0)
    return mmo


def do_not_run(func):
    return lambda x: None

content._CHUNK_SIZE = content.CHUNK_SIZE
content._CONSECUTIVE_DL_LIMIT = content.CONSECUTIVE_DL_LIMIT

import sys

print(sys.argv)


class APILiveTestCase(unittest.TestCase):
    def setUp(self):
        self.assertTrue(os.path.isfile(os.path.join(path, 'oauth_data')))
        self.assertTrue(os.path.isfile(os.path.join(path, 'endpoint_data')))

    def tearDown(self):
        content.CHUNK_SIZE = content._CHUNK_SIZE
        content.CONSECUTIVE_DL_LIMIT = content._CONSECUTIVE_DL_LIMIT

    #
    # common.py
    #

    def test_back_off_error(self):
        common.BackOffRequest.get(common.get_content_url())
        self.assertEqual(common.BackOffRequest._BackOffRequest__retries, 1)

    #
    # account.py
    #

    def test_get_quota(self):
        account.get_quota()

    def test_get_usage(self):
        account.get_account_usage()

    #
    # content.py
    #

    def test_upload(self):
        fn, sz = gen_rand_file()
        md5 = hashing.hash_file(fn)
        n = content.upload_file(fn)
        self.assertIn('id', n)
        self.assertEqual(n['contentProperties']['size'], sz)
        self.assertEqual(n['contentProperties']['md5'], md5)
        n = trash.move_to_trash(n['id'])
        os.remove(fn)

    def test_upload_stream(self):
        fn = gen_rand_nm()
        mmo = gen_rand_anon_mmap()
        h = hashing.IncrementalHasher()
        n = content.upload_stream(mmo, fn, parent=None, read_callbacks=[h.update])
        self.assertEqual(n['contentProperties']['md5'], h.get_result())
        trash.move_to_trash(n['id'])

    def test_overwrite(self):
        fn, _ = gen_rand_file()
        n = content.create_file(fn)
        self.assertIn('id', n)
        n = content.overwrite_file(n['id'], fn)
        self.assertEqual(n['contentProperties']['version'], 2)
        trash.move_to_trash(n['id'])

    def test_download(self):
        fn, sz = gen_rand_file()
        self.assertTrue(sz < content.CONSECUTIVE_DL_LIMIT)
        md5 = hashing.hash_file(fn)
        n = content.upload_file(fn)
        self.assertIn('id', n)
        os.remove(fn)
        self.assertFalse(os.path.exists(fn))
        content.download_file(n['id'], fn)
        md5_dl = hashing.hash_file(fn)
        self.assertEqual(md5, md5_dl)
        trash.move_to_trash(n['id'])
        os.remove(fn)

    def test_download_chunked(self):
        ch_sz = gen_rand_sz()
        content.CHUNK_SIZE = ch_sz
        fn, sz = gen_rand_file(size=5 * ch_sz)
        md5 = hashing.hash_file(fn)
        n = content.upload_file(fn)
        self.assertEqual(n['contentProperties']['md5'], md5)
        os.remove(fn)
        self.assertFalse(os.path.exists(fn))
        f = io.BytesIO()
        content.chunked_download(n['id'], f, length=sz)
        trash.move_to_trash(n['id'])
        dl_md5 = hashing.hash_bytes(f)
        self.assertEqual(sz, f.tell())
        self.assertEqual(md5, dl_md5)

    def test_incomplete_download(self):
        ch_sz = gen_rand_sz()
        content.CHUNK_SIZE = ch_sz
        fn, sz = gen_rand_file(size=5 * ch_sz)
        md5 = hashing.hash_file(fn)
        n = content.upload_file(fn)
        self.assertEqual(n['contentProperties']['md5'], md5)
        os.remove(fn)
        self.assertFalse(os.path.exists(fn))
        with self.assertRaises(RequestError) as cm:
            content.download_file(n['id'], fn, length=sz + 1)

        #os.remove(fn + content.PARTIAL_SUFFIX)
        self.assertEqual(cm.exception.status_code, RequestError.CODE.INCOMPLETE_RESULT)
        content.download_file(n['id'], fn, length=sz)
        trash.move_to_trash(n['id'])
        os.remove(fn)

    def test_download_resume(self):
        ch_sz = gen_rand_sz()
        content.CHUNK_SIZE = ch_sz
        content.CONSECUTIVE_DL_LIMIT = ch_sz
        fn, sz = gen_rand_file(size=5 * ch_sz)
        md5 = hashing.hash_file(fn)
        n = content.upload_file(fn)
        self.assertEqual(n['contentProperties']['md5'], md5)
        os.remove(fn)
        self.assertFalse(os.path.exists(fn))
        p_fn = fn + content.PARTIAL_SUFFIX
        with open(p_fn, 'wb') as f:
            content.chunked_download(n['id'], f, length=int(sz * random.random()))
        self.assertLess(os.path.getsize(p_fn), sz)
        content.download_file(n['id'], fn)
        trash.move_to_trash(n['id'])
        dl_md5 = hashing.hash_file(fn)
        self.assertEqual(md5, dl_md5)
        os.remove(fn)

    def test_create_file(self):
        name = gen_rand_nm()
        node = content.create_file(name)
        trash.move_to_trash(node['id'])
        self.assertEqual(node['name'], name)
        self.assertEqual(node['parents'][0], metadata.get_root_id())

    def test_get_root_id(self):
        id = metadata.get_root_id()
        self.assertTrue(common.is_valid_id(id))

    # helper
    def create_random_dir(self):
        nm = gen_rand_nm()
        n = content.create_folder(nm)
        self.assertIn('id', n)
        return n['id']

    def test_mkdir(self):
        f_id = self.create_random_dir()
        trash.move_to_trash(f_id)

    #
    # metadata.py
    #

    @do_not_run
    def test_get_changes(self):
        nodes, purged_nodes, checkpoint, reset = metadata.get_changes(include_purged=False)
        self.assertGreaterEqual(len(nodes), 1)
        self.assertEqual(len(purged_nodes), 0)
        self.assertTrue(reset)
        nodes, purged_nodes, checkpoint, reset = metadata.get_changes(checkpoint=checkpoint)
        self.assertEqual(len(nodes), 0)
        self.assertEqual(len(purged_nodes), 0)
        self.assertFalse(reset)

    def test_move_node(self):
        f_id = self.create_random_dir()
        node = content.create_file(gen_rand_nm())
        old_parent = node['parents'][0]
        node = metadata.move_node(node['id'], old_parent, f_id)
        self.assertEqual(node['parents'][0], f_id)
        trash.move_to_trash(f_id)
        trash.move_to_trash(node['id'])

    def test_rename_node(self):
        nm = gen_rand_nm()
        nm2 = gen_rand_nm()
        node = content.create_file(nm)
        self.assertEqual(node['name'], nm)
        node = metadata.rename_node(node['id'], nm2)
        self.assertEqual(node['name'], nm2)
        trash.move_to_trash(node['id'])

    #
    # trash.py
    #

    def test_trash(self):
        # unnecessary
        pass

    def test_restore(self):
        f_id = self.create_random_dir()
        n = trash.move_to_trash(f_id)
        self.assertEqual(n['status'], 'TRASH')
        n = trash.restore(n['id'])
        self.assertEqual(n['status'], 'AVAILABLE')
        n = trash.move_to_trash(n['id'])
        self.assertEqual(n['status'], 'TRASH')

    def test_purge(self):
        f_id = self.create_random_dir()
        n = trash.move_to_trash(f_id)
        self.assertEqual(n['status'], 'TRASH')
        with self.assertRaises(RequestError):
            trash.purge(n['id'])

"""Real, live Amazon Cloud Drive API tests"""

import unittest
import logging
import os
import io
import sys
import random
import string
import mmap
import tempfile

from acdcli.api import client, content, common
from acdcli.api.common import RequestError
from acdcli.utils import hashing

logging.basicConfig(level=logging.INFO)
path = os.path.join(os.path.dirname(__file__), 'cache_files')


def gen_rand_sz():
    return random.randint(1, 32 * 1024)


def gen_rand_nm():
    return str.join('', (random.choice(string.ascii_letters + string.digits) for _ in range(32)))


def gen_temp_file(size=gen_rand_sz()) -> tuple:
    f = tempfile.NamedTemporaryFile(mode='w+b')
    f.write(os.urandom(size))
    f.seek(0)
    return f, os.path.getsize(f.name)


def gen_rand_anon_mmap(size=gen_rand_sz()) -> tuple:
    mmo = mmap.mmap(-1, size)
    mmo.write(os.urandom(size))
    mmo.seek(0)
    return mmo, size


def do_not_run(func):
    return lambda x: None

print(sys.argv)


class APILiveTestCase(unittest.TestCase):
    def setUp(self):
        self.acd_client = client.ACDClient(path)
        self.acd_client.BOReq._wait = lambda: None
        self.assertTrue(os.path.isfile(os.path.join(path, 'oauth_data')))
        self.assertTrue(os.path.isfile(os.path.join(path, 'endpoint_data')))

    def tearDown(self):
        pass

    #
    # common.py
    #

    def test_back_off_error(self):
        self.acd_client.BOReq.get(self.acd_client.content_url)
        self.assertEqual(self.acd_client.BOReq._BackOffRequest__retries, 1)

    #
    # account.py
    #

    def test_get_quota(self):
        q = self.acd_client.get_quota()
        self.assertIn('quota', q)
        self.assertIn('available', q)

    def test_get_usage(self):
        self.acd_client.get_account_usage()

    #
    # content.py
    #

    def test_upload(self):
        f, sz = gen_temp_file()
        md5 = hashing.hash_file_obj(f)
        n = self.acd_client.upload_file(f.name)
        self.assertIn('id', n)
        self.assertEqual(n['contentProperties']['size'], sz)
        self.assertEqual(n['contentProperties']['md5'], md5)
        n = self.acd_client.move_to_trash(n['id'])

    def test_upload_stream(self):
        s, sz = gen_rand_anon_mmap()
        fn = gen_rand_nm()
        h = hashing.IncrementalHasher()

        n = self.acd_client.upload_stream(s, fn, parent=None, read_callbacks=[h.update])
        self.assertEqual(n['contentProperties']['md5'], h.get_result())
        self.assertEqual(n['contentProperties']['size'], sz)

        self.acd_client.move_to_trash(n['id'])

    def test_upload_stream_empty(self):
        empty_stream = io.BufferedReader(io.BytesIO())
        fn = gen_rand_nm()

        n = self.acd_client.upload_stream(empty_stream, fn, parent=None)
        self.assertEqual(n['contentProperties']['md5'], 'd41d8cd98f00b204e9800998ecf8427e')
        self.assertEqual(n['contentProperties']['size'], 0)

        self.acd_client.move_to_trash(n['id'])

    def test_overwrite(self):
        f, sz = gen_temp_file()
        h = hashing.IncrementalHasher()

        n = self.acd_client.create_file(os.path.basename(f.name))
        self.assertIn('id', n)

        n = self.acd_client.overwrite_file(n['id'], f.name, [h.update])
        self.assertEqual(n['contentProperties']['version'], 2)
        self.assertEqual(n['contentProperties']['md5'], h.get_result())

        self.acd_client.move_to_trash(n['id'])

    def test_overwrite_stream(self):
        s, sz = gen_rand_anon_mmap()
        fn = gen_rand_nm()
        h = hashing.IncrementalHasher()

        n = self.acd_client.create_file(fn)
        self.assertIn('id', n)

        n = self.acd_client.overwrite_stream(s, n['id'], [h.update])
        self.assertEqual(n['contentProperties']['md5'], h.get_result())
        self.assertEqual(n['contentProperties']['size'], sz)

        empty_stream = io.BufferedReader(io.BytesIO())
        n = self.acd_client.overwrite_stream(empty_stream, n['id'])
        self.assertEqual(n['contentProperties']['md5'], 'd41d8cd98f00b204e9800998ecf8427e')
        self.assertEqual(n['contentProperties']['size'], 0)

        self.acd_client.move_to_trash(n['id'])

    def test_download(self):
        f, sz = gen_temp_file()
        self.assertTrue(sz < self.acd_client._conf.getint('transfer', 'dl_chunk_size'))
        md5 = hashing.hash_file_obj(f)
        n = self.acd_client.upload_file(f.name)
        self.assertIn('id', n)

        f.close()
        self.assertFalse(os.path.exists(f.name))

        self.acd_client.download_file(n['id'], f.name)
        md5_dl = hashing.hash_file(f.name)
        self.assertEqual(md5, md5_dl)
        self.acd_client.move_to_trash(n['id'])

    def test_download_chunked(self):
        ch_sz = gen_rand_sz()
        self.acd_client._conf['transfer']['dl_chunk_size'] = str(ch_sz)
        f, sz = gen_temp_file(size=5 * ch_sz)
        md5 = hashing.hash_file_obj(f)

        n = self.acd_client.upload_file(f.name)
        self.assertEqual(n['contentProperties']['md5'], md5)
        f.close()
        self.assertFalse(os.path.exists(f.name))

        f = io.BytesIO()
        self.acd_client.chunked_download(n['id'], f, length=sz)
        self.acd_client.move_to_trash(n['id'])
        dl_md5 = hashing.hash_file_obj(f)
        self.assertEqual(sz, f.tell())
        self.assertEqual(md5, dl_md5)

    def test_incomplete_download(self):
        ch_sz = gen_rand_sz()
        self.acd_client._conf['transfer']['dl_chunk_size'] = str(ch_sz)
        f, sz = gen_temp_file(size=5 * ch_sz)
        md5 = hashing.hash_file_obj(f)

        n = self.acd_client.upload_file(f.name)
        self.assertEqual(n['contentProperties']['md5'], md5)
        f.close()

        with self.assertRaises(RequestError) as cm:
            self.acd_client.download_file(n['id'], f.name, length=sz + 1)

        self.assertEqual(cm.exception.status_code, RequestError.CODE.INCOMPLETE_RESULT)
        self.acd_client.download_file(n['id'], f.name, length=sz)
        self.acd_client.move_to_trash(n['id'])
        os.remove(f.name)

    def test_download_resume(self):
        ch_sz = gen_rand_sz()
        self.acd_client._conf['transfer']['dl_chunk_size'] = str(ch_sz)
        f, sz = gen_temp_file(size=5 * ch_sz)
        md5 = hashing.hash_file(f.name)
        n = self.acd_client.upload_file(f.name)
        self.assertEqual(n['contentProperties']['md5'], md5)
        f.close()

        basename = os.path.basename(f.name)
        self.assertFalse(os.path.exists(f.name))
        p_fn = basename + content.PARTIAL_SUFFIX
        with open(p_fn, 'wb') as f:
            self.acd_client.chunked_download(n['id'], f, length=int(sz * random.random()))
        self.assertLess(os.path.getsize(p_fn), sz)
        self.acd_client.download_file(n['id'], basename)
        self.acd_client.move_to_trash(n['id'])
        dl_md5 = hashing.hash_file(basename)
        self.assertEqual(md5, dl_md5)
        os.remove(basename)

    def test_create_file(self):
        name = gen_rand_nm()
        node = self.acd_client.create_file(name)
        self.acd_client.move_to_trash(node['id'])
        self.assertEqual(node['name'], name)
        self.assertEqual(node['parents'][0], self.acd_client.get_root_id())

    def test_get_root_id(self):
        id = self.acd_client.get_root_id()
        self.assertTrue(common.is_valid_id(id))

    # helper
    def create_random_dir(self):
        nm = gen_rand_nm()
        n = self.acd_client.create_folder(nm)
        self.assertIn('id', n)
        return n['id']

    def test_mkdir(self):
        f_id = self.create_random_dir()
        self.acd_client.move_to_trash(f_id)

    #
    # metadata.py
    #

    @do_not_run
    def test_get_changes(self):
        nodes, purged_nodes, checkpoint, reset = self.acd_client.get_changes(include_purged=False)
        self.assertGreaterEqual(len(nodes), 1)
        self.assertEqual(len(purged_nodes), 0)
        self.assertTrue(reset)
        nodes, purged_nodes, checkpoint, reset = self.acd_client.get_changes(checkpoint=checkpoint)
        self.assertEqual(len(nodes), 0)
        self.assertEqual(len(purged_nodes), 0)
        self.assertFalse(reset)

    def test_move_node(self):
        f_id = self.create_random_dir()
        node = self.acd_client.create_file(gen_rand_nm())
        old_parent = node['parents'][0]
        node = self.acd_client.move_node(node['id'], f_id)
        self.assertEqual(node['parents'][0], f_id)
        self.acd_client.move_to_trash(f_id)
        self.acd_client.move_to_trash(node['id'])

    def test_rename_node(self):
        nm = gen_rand_nm()
        nm2 = gen_rand_nm()
        node = self.acd_client.create_file(nm)
        self.assertEqual(node['name'], nm)
        node = self.acd_client.rename_node(node['id'], nm2)
        self.assertEqual(node['name'], nm2)
        self.acd_client.move_to_trash(node['id'])

    #
    # trash.py
    #

    def test_trash(self):
        # unnecessary
        pass

    def test_restore(self):
        f_id = self.create_random_dir()
        n = self.acd_client.move_to_trash(f_id)
        self.assertEqual(n['status'], 'TRASH')
        n = self.acd_client.restore(n['id'])
        self.assertEqual(n['status'], 'AVAILABLE')
        n = self.acd_client.move_to_trash(n['id'])
        self.assertEqual(n['status'], 'TRASH')

    def test_purge(self):
        f_id = self.create_random_dir()
        n = self.acd_client.move_to_trash(f_id)
        self.assertEqual(n['status'], 'TRASH')
        with self.assertRaises(RequestError):
            self.acd_client.purge(n['id'])

import unittest
from mock import patch, mock_open, MagicMock, sentinel
import os
import sys
import json
import httpretty

import acd_cli

from acdcli.cache import db

from .test_helper import gen_file, gen_folder, gen_bunch_of_nodes

path = os.path.join(os.path.dirname(__file__), 'dummy_files')
acd_cli.CACHE_PATH = path


def run_main() -> int:
    try:
        acd_cli.main()
    except SystemExit as e:
        return e.code


def devnull():
    """Redirect stdout to /dev/null"""
    sys.stdout = open(os.devnull, 'w')


class ActionTestCase(unittest.TestCase):
    stdout = sys.stdout

    def setUp(self):
        sys.argv = [acd_cli._app_name, '-nw']
        self.cache = db.NodeCache(path)

    def tearDown(self):
        sys.stdout = self.stdout
        db.remove_db_file(path)

    # tests

    def testHelp(self):
        devnull()
        sys.argv.append('-h')
        self.assertEqual(run_main(), 0)

    def testClearCache(self):
        sys.argv.append('cc')
        self.assertEqual(run_main(), None)

    def testClearCacheNonExist(self):
        db.remove_db_file(path)
        sys.argv.append('cc')
        self.assertEqual(run_main(), acd_cli.ERROR_RETVAL)

    # listing

    @patch('sys.stdout.write')
    def testTree(self, print_):
        files, folders = gen_bunch_of_nodes(50)

        self.cache.insert_nodes(files + folders)
        sys.argv.extend(['tree', '-t'])
        self.assertEqual(run_main(), None)
        self.assertEqual(len(print_.mock_calls), 100)

    @patch('sys.stdout.write')
    def testList(self, print_):
        db.NodeCache(path)
        folder = gen_folder([])
        files = [gen_file([folder]) for _ in range(50)]

        self.cache.insert_nodes(files + [folder])
        sys.argv.extend(['ls', '-t', '/'])
        self.assertEqual(run_main(), None)
        self.assertEqual(len(print_.mock_calls), 100)

    # find actions

    # transfer actions

    # create

    # trashing

    # move/rename, resolve

    # child ops

    # stats

    # FUSE

    # @httpretty.activate
    # def testMount(self):
    #     httpretty. \
    #         register_uri(httpretty.GET, acd_cli.acd_client.metadata_url + 'account/quota',
    #                      body=json.dumps({'available:': 100, 'quota': 100}))
    #
    #     sys.argv.extend(['-d', 'mount', '-i', '0',
    #                      os.path.join(os.path.dirname(__file__), 'dummy_files/mountpoint')])
    #     self.cache.insert_nodes([gen_folder()])
    #     self.assertEqual(run_main(), None)

    def testUnmount(self):
        sys.argv.append('umount')
        self.assertEqual(run_main(), 0)

    # undocumented actions

    def testInit(self):
        sys.argv.append('init')
        acd_cli.cache.insert_nodes([gen_folder()])
        self.assertEqual(run_main(), None)

    def testDumpSQL(self):
        devnull()
        sys.argv.append('dumpsql')
        self.assertEqual(run_main(), None)

    # misc

    def testCheckCacheEmpty(self):
        sys.argv.extend(['ls', '/'])
        self.assertEqual(run_main(), acd_cli.INIT_FAILED_RETVAL)

    def testCheckCacheNonEmpty(self):
        folder = gen_folder()
        self.cache.insert_nodes([folder])
        sys.argv.extend(['ls', '/'])
        self.assertEqual(run_main(), None)

    # helper functions

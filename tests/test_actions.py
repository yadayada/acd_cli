import unittest
from mock import patch, mock_open, MagicMock, sentinel
import os
import sys

import acd_cli

from acdcli.cache import db, sync
from acdcli.api import common, account, metadata, oauth

from .test_helper import gen_file, gen_folder, gen_bunch_of_nodes

common.BackOffRequest._wait = lambda: None
path = os.path.join(os.path.dirname(__file__), 'dummy_files')
acd_cli.CACHE_PATH = path


def run_main() -> int:
    try:
        acd_cli.main()
    except SystemExit as e:
        return e.code


def devnull():
    sys.stdout = open(os.devnull, 'w')


class ActionTestCase(unittest.TestCase):
    stdout = sys.stdout

    def setUp(self):
        sys.argv = [acd_cli._app_name]

    def tearDown(self):
        sys.stdout = self.stdout

    # tests

    def testHelp(self):
        devnull()
        sys.argv.append('-h')
        self.assertEqual(run_main(), 0)

    def testClearCache(self):
        sys.argv.append('cc')
        db.init(path)
        self.assertEqual(run_main(), None)

    def testClearCacheNonExist(self):
        sys.argv.append('cc')
        self.assertEqual(run_main(), acd_cli.ERROR_RETVAL)

    # listing

    @patch('acd_cli.print')
    def testTree(self, print_):
        db.init(path)
        files, folders = gen_bunch_of_nodes(50)

        sync.insert_nodes(files + folders)
        sys.argv.extend(['tree', '-t'])
        self.assertEqual(run_main(), None)
        self.assertEqual(len(print_.mock_calls), 51)

    @patch('acd_cli.print')
    def testList(self, print_):
        db.init(path)
        folder = gen_folder([])
        files = [gen_file([folder]) for _ in range(50)]

        sync.insert_nodes(files + [folder])
        sys.argv.extend(['ls', '-t', '/'])
        self.assertEqual(run_main(), None)
        self.assertEqual(len(print_.mock_calls), 50)

    # find actions

    # transfer actions

    # create

    # trashing

    # move/rename, resolve

    # child ops

    # stats

    # FUSE

    # undocumented actions

    def testInit(self):
        sys.argv.append('init')
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
        db.init(path)
        folder = gen_folder()
        sync.insert_nodes([folder])
        sys.argv.extend(['ls', '/'])
        self.assertEqual(run_main(), None)

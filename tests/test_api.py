"""Isolated API unit tests."""

import unittest
import httpretty
from mock import patch, mock_open, MagicMock
import logging
import os
import json
import time

import acdcli.api.oauth as oauth

from acdcli.api.account import _Usage
from acdcli.api.common import *
from acdcli.api.client import ACDClient

from .test_helper import gen_rand_id

logging.basicConfig(level=logging.INFO)
path = os.path.join(os.path.dirname(__file__), 'dummy_files')


class APITestCase(unittest.TestCase):
    def setUp(self):
        self.acd = ACDClient(path)
        self.acd.BOReq._wait = lambda: None

    def testMetadataUrl(self):
        self.assertEqual(self.acd.metadata_url, 'https://cdws.us-east-1.amazonaws.com/drive/v1/')

    def testContentUrl(self):
        self.assertEqual(self.acd.content_url, 'https://content-na.drive.amazonaws.com/cdproxy/')

    def testValidID0(self):
        self.assertTrue(is_valid_id('abcdefghijklmnopqrstuv'))

    def testValidID1(self):
        self.assertTrue(is_valid_id('0123456789012345678901'))

    def testValidID2(self):
        self.assertTrue(is_valid_id('a0b1c2d3e4f5g6h7i8j9k0'))

    def testValidID3(self):
        self.assertTrue(is_valid_id('a0b1c2d3e4f--6h7i8j9k0'))

    def testValidIDs(self):
        for _ in range(1000):
            self.assertTrue(is_valid_id(gen_rand_id()))

    def testInvalidID0(self):
        self.assertFalse(is_valid_id(''))

    def testInvalidID1(self):
        self.assertFalse(is_valid_id('äbcdéfghíjklmnöpqrstüv'))

    def testInvalidID2(self):
        self.assertFalse(is_valid_id('abcdefghijklmnopqrstu'))

    #
    # account
    #

    @httpretty.activate
    def testUsage(self):
        httpretty. \
            register_uri(httpretty.GET, self.acd.metadata_url + 'account/usage',
                         body=json.dumps({"lastCalculated": "2014-08-13T23:17:41.365Z",
                                          "video": {"billable": {"bytes": 23524252, "count": 22},
                                                    "total": {"bytes": 23524252, "count": 22}},
                                          "other": {"billable": {"bytes": 29999771, "count": 871},
                                                    "total": {"bytes": 29999771, "count": 871}},
                                          "doc": {"billable": {"bytes": 807170, "count": 10},
                                                  "total": {"bytes": 807170, "count": 10}},
                                          "photo": {"billable": {"bytes": 9477988, "count": 25},
                                                    "total": {"bytes": 9477988, "count": 25}}})
                         )
        self.assertIsInstance(self.acd.get_account_usage(), _Usage)

    @httpretty.activate
    def testUsageEmpty(self):
        httpretty.register_uri(httpretty.GET, self.acd.metadata_url + 'account/usage', body='{}')
        self.assertEqual(str(self.acd.get_account_usage()), '')

    #
    # metadata
    #

    @httpretty.activate
    def testChanges(self):
        httpretty.register_uri(httpretty.POST, self.acd.metadata_url + 'changes',
                               body='{"checkpoint": "foo", "reset": true, '
                                    '"nodes": [ {"kind": "FILE", "status": "TRASH"} ], '
                                    '"statusCode": 200}\n'
                                    '{"end": true}')
        tmp = self.acd.get_changes()
        changesets = [c for c in self.acd._iter_changes_lines(tmp)]
        self.assertEqual(len(changesets), 1)
        changeset = changesets[0]
        self.assertEqual(len(changeset.nodes), 1)
        self.assertEqual(len(changeset.purged_nodes), 0)
        self.assertEqual(changeset.checkpoint, 'foo')
        self.assertTrue(changeset.reset)

    @httpretty.activate
    def testChangesMissingEnd(self):
        httpretty.register_uri(httpretty.POST, self.acd.metadata_url + 'changes',
                               body='{"checkpoint": "foo", "reset": true, "nodes": [], '
                                    '"statusCode": 200}\n')
        tmp = self.acd.get_changes()
        changesets = [c for c in self.acd._iter_changes_lines(tmp)]
        self.assertEqual(len(changesets), 1)
        changeset = changesets[0]
        self.assertEqual(len(changeset.nodes), 0)
        self.assertEqual(len(changeset.purged_nodes), 0)
        self.assertEqual(changeset.checkpoint, 'foo')
        self.assertTrue(changeset.reset)

    @httpretty.activate
    def testChangesCorruptJSON(self):
        httpretty.register_uri(httpretty.POST, self.acd.metadata_url + 'changes',
                               body='{"checkpoint": }')
        with self.assertRaises(RequestError):
            tmp = self.acd.get_changes()
            [cs for cs in self.acd._iter_changes_lines(tmp)]

    #
    # oauth
    #

    dummy_token = {'access_token': 'foo', 'expires_in': 3600, 'refresh_token': 'bar'}

    def testOAuthActualHandler(self):
        self.assertIsInstance(self.acd.handler, oauth.AppspotOAuthHandler)

    @httpretty.activate
    def testOAuthAppSpotRefresh(self):
        httpretty.register_uri(httpretty.POST, oauth.AppspotOAuthHandler.APPSPOT_URL,
                               body=json.dumps(self.dummy_token))

        exp_token = {'access_token': '', 'expires_in': 3600, 'exp_time': 0.0, 'refresh_token': ''}

        mock_file = mock_open(read_data=json.dumps(exp_token))
        os.path.isfile = MagicMock()
        with patch('builtins.open', mock_file, create=True):
            with patch('os.fsync', MagicMock):
                with patch('os.rename', MagicMock):
                    h = oauth.AppspotOAuthHandler('')

        mock_file.assert_any_call(oauth.OAuthHandler.OAUTH_DATA_FILE)
        self.assertIn(oauth.OAuthHandler.KEYS.EXP_TIME, h.oauth_data)
        self.assertGreater(h.oauth_data[oauth.OAuthHandler.KEYS.EXP_TIME], time.time())
        mock_file().write.assert_any_call(str(h.oauth_data[oauth.AppspotOAuthHandler.KEYS.EXP_TIME]))

    def testOAuthLocalRefresh(self):
        # TODO: find out how to mock multiple files
        pass

    def testOAuthValidation(self):
        s = json.dumps(self.dummy_token)
        o = oauth.OAuthHandler.validate(s)
        self.assertIsInstance(o, dict)

    def testOAuthValidationMissingRefresh(self):
        inv = json.dumps({'access_token': 'foo', 'expires_in': 3600})
        with self.assertRaises(RequestError):
            oauth.OAuthHandler.validate(inv)

    def testOAuthValidationMissingAccess(self):
        inv = json.dumps({'expires_in': 3600, 'refresh_token': 'bar'})
        with self.assertRaises(RequestError):
            oauth.OAuthHandler.validate(inv)

    def testOAuthValidationMissingExpiration(self):
        inv = json.dumps({'access_token': 'foo', 'refresh_token': 'bar'})
        with self.assertRaises(RequestError):
            oauth.OAuthHandler.validate(inv)

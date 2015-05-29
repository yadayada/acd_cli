"""Isolated API unit tests."""

import unittest
import httpretty
from mock import patch, mock_open, MagicMock, sentinel
import logging
import os
import json
import time

from acdcli.api import common, account, metadata, oauth

logging.basicConfig(level=logging.INFO)
common.BackOffRequest._wait = lambda: None
path = os.path.join(os.path.dirname(__file__), 'dummy_files')


class APITestCase(unittest.TestCase):
    def setUp(self):
        common.init(path)

    def testMetadataUrl(self):
        self.assertEqual(common.get_metadata_url(), 'https://cdws.us-east-1.amazonaws.com/drive/v1/')

    def testContentUrl(self):
        self.assertEqual(common.get_content_url(), 'https://content-na.drive.amazonaws.com/cdproxy/')

    #
    # account
    #

    @httpretty.activate
    def testUsage(self):
        httpretty. \
            register_uri(httpretty.GET, common.get_metadata_url() + 'account/usage',
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
        self.assertIsInstance(account.get_account_usage(), account._Usage)

    @httpretty.activate
    def testUsageEmpty(self):
        httpretty.register_uri(httpretty.GET, common.get_metadata_url() + 'account/usage', body='{}')
        self.assertEqual(str(account.get_account_usage()), '')

    #
    # metadata
    #

    @httpretty.activate
    def testChanges(self):
        httpretty.register_uri(httpretty.POST, common.get_metadata_url() + 'changes',
                               body='{"checkpoint": "foo", "reset": true, '
                                    '"nodes": [ {"kind": "FILE", "status": "TRASH"} ], "statusCode": 200}\n'
                                    '{"end": true}')
        nodes, purged_nodes, checkpoint, reset = metadata.get_changes()
        self.assertEqual(len(nodes), 1)
        self.assertEqual(len(purged_nodes), 0)
        self.assertEqual(checkpoint, 'foo')
        self.assertTrue(reset)

    @httpretty.activate
    def testChangesMissingEnd(self):
        httpretty.register_uri(httpretty.POST, common.get_metadata_url() + 'changes',
                               body='{"checkpoint": "foo", "reset": true, "nodes": [], "statusCode": 200}\n')
        nodes, purged_nodes, checkpoint, reset = metadata.get_changes()
        self.assertEqual(len(nodes), 0)
        self.assertEqual(len(purged_nodes), 0)
        self.assertEqual(checkpoint, 'foo')
        self.assertTrue(reset)

    @httpretty.activate
    def testChangesCorruptJSON(self):
        httpretty.register_uri(httpretty.POST, common.get_metadata_url() + 'changes',
                               body='{"checkpoint": }')
        self.assertRaises(common.RequestError, metadata.get_changes)

    #
    # oauth
    #

    dummy_token = {'access_token': 'foo', 'expires_in': 3600, 'refresh_token': 'bar'}

    def testOAuthActualHandler(self):
        self.assertIsInstance(oauth.handler, oauth.AppspotOAuthHandler)

    @httpretty.activate
    def testOAuthAppSpotRefresh(self):
        httpretty.register_uri(httpretty.POST, oauth.AppspotOAuthHandler.APPSPOT_URL,
                               body=json.dumps(self.dummy_token))

        exp_token = {'access_token': '', 'expires_in': 3600, 'exp_time': 0.0, 'refresh_token': ''}

        mock_file = mock_open(read_data=json.dumps(exp_token))
        os.path.isfile = MagicMock()
        with patch('builtins.open', mock_file, create=True):
            with patch('os.fsync', MagicMock):
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
        with self.assertRaises(common.RequestError):
            oauth.OAuthHandler.validate(inv)

    def testOAuthValidationMissingAccess(self):
        inv = json.dumps({'expires_in': 3600, 'refresh_token': 'bar'})
        with self.assertRaises(common.RequestError):
            oauth.OAuthHandler.validate(inv)

    def testOAuthValidationMissingExpiration(self):
        inv = json.dumps({'access_token': 'foo', 'refresh_token': 'bar'})
        with self.assertRaises(common.RequestError):
            oauth.OAuthHandler.validate(inv)
"""Isolated API unit tests."""

import unittest
import httpretty
import logging
import os
import json

from acdcli.api import common, account, metadata

logging.basicConfig(level=logging.INFO)
common.BackOffRequest._wait = lambda: None
path = os.path.join(os.path.dirname(__file__), 'dummy_files')
common.init(path)


class APITestCase(unittest.TestCase):
    def setUp(self):
        pass

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
__version__ = '0.3'
__all__ = ('account', 'common', 'content', 'metadata', 'trash')

"""
================
Node JSON Format
================

This is the usual node JSON format for a file::
    {
           'contentProperties': {'contentType': 'text/plain',
                                 'extension': 'txt',
                                 'md5': 'd41d8cd98f00b204e9800998ecf8427e',
                                 'size': 0,
                                 'version': 1},
           'createdBy': '<security-profile-nm>-<user>',
           'createdDate': '2015-01-01T00:00:00.00Z',
           'eTagResponse': 'AbCdEfGhI01',
           'id': 'AbCdEfGhIjKlMnOpQr0123',
           'isShared': False,
           'kind': 'FILE',
           'labels': [],
           'modifiedDate': '2015-01-01T00:00:00.000Z',
           'name': 'empty.text',
           'parents': ['0123AbCdEfGhIjKlMnOpQr'],
           'restricted': False,
           'status': 'AVAILABLE',
           'version': 1
    }

The ``modifiedDate`` and ``version`` keys get updated each time the content or metadata is updated.
``contentProperties['version']`` gets updated on overwrite.

"""
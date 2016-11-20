"""
*******
ACD API
*******

Usage
=====
::

    from api import client
    acd_client = client.ACDClient()
    root = acd_client.get_root_id()
    children = acd_client.list_children(root)
    for child in children:
        print(child['name'])
    # ...

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
           'description': '',
           'eTagResponse': 'AbCdEfGhI01',
           'id': 'AbCdEfGhIjKlMnOpQr0123',
           'isShared': False,
           'kind': 'FILE',
           'labels': [],
           'modifiedDate': '2015-01-01T00:00:00.000Z',
           'name': 'empty.txt',
           'parents': ['0123AbCdEfGhIjKlMnOpQr'],
           'restricted': False,
           'status': 'AVAILABLE',
           'version': 1
    }

The ``modifiedDate`` and ``version`` keys get updated each time the content or metadata is updated.
``contentProperties['version']`` gets updated on overwrite.

A folder's JSON looks similar, but it lacks the ``contentProperties`` dictionary.

``isShared`` is set to ``False`` even when a node is actually shared.

.. CAUTION::
   ACD allows hard links for folders!

"""

__version__ = '0.9.2'

# monkey patch the user agent
try:
    import requests.utils

    if 'old_dau' not in dir(requests.utils):
        requests.utils.old_dau = requests.utils.default_user_agent

        def new_dau():
            return __name__ + '/' + __version__ + ' ' + requests.utils.old_dau()

        requests.utils.default_user_agent = new_dau
except:
    pass

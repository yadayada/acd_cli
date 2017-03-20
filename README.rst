|Donate| |Gitter| |PyVersion| |Status| |License| |Build| |PyPiVersion|

acd\_cli
========

**acd\_cli** provides a command line interface to Amazon Drive and allows Unix users to mount
their drive using FUSE for read and (sequential) write access. It is currently in beta stage.

Node Cache Features
-------------------

- local caching of node metadata in an SQLite database
- addressing of remote nodes via a pathname (e.g. ``/Photos/kitten.jpg``)
- file search

CLI Features
------------

- tree or flat listing of files and folders
- simultaneous uploads/downloads, retry on error
- basic plugin support

File Operations
~~~~~~~~~~~~~~~

- upload/download of single files and directories
- streamed upload/download
- folder creation
- trashing/restoring
- moving/renaming nodes

Documentation
-------------

The full documentation is available at `<https://acd-cli.readthedocs.io>`_.

Quick Start
-----------

Have a look at the `known issues`_, then follow the `setup guide <docs/setup.rst>`_ and
`authorize <docs/authorization.rst>`_. You may then use the program as described in the
`usage guide <docs/usage.rst>`_.

CLI Usage Example
-----------------

In this example, a two-level folder hierarchy is created in an empty drive.
Then, a relative local path ``local/spam`` is uploaded recursively using two connections.
::

    $ acd_cli sync
      Getting changes...
      Inserting nodes..

    $ acd_cli ls /
      [PHwiEv53QOKoGFGqYNl8pw] [A] /

    $ acd_cli mkdir /egg/
    $ acd_cli mkdir /egg/bacon/

    $ acd_cli upload -x 2 local/spam/ /egg/bacon/
      [################################]   100.0% of  100MiB  12/12  654.4KB/s

    $ acd_cli tree
      /
          egg/
              bacon/
                  spam/
                      sausage
                      spam
      [...]


The standard node listing format includes the node ID, the first letter of its status
and its full path. Possible statuses are "AVAILABLE" and "TRASH".

Known Issues
------------

It is not possible to upload files using Python 3.2.3, 3.3.0 and 3.3.1 due to a bug in
the http.client module.

API Restrictions
~~~~~~~~~~~~~~~~

- the current upload file size limit is 50GiB
- uploads of large files >10 GiB may be successful, yet a timeout error is displayed
  (please check the upload by syncing manually)
- storage of node names is case-preserving, but not case-sensitive
  (this should not concern Apple users)
- it is not possible to share or delete files

Contribute
----------

Have a look at the `contributing guidelines <CONTRIBUTING.rst>`_.

Recent Changes
--------------

0.3.2
~~~~~
* added ``--remove-source-files`` argument to upload action
* added ``--times`` argument to download action for preservation of modification times
* added streamed overwrite action
* fixed upload of directories containing broken symlinks
* disabled FUSE autosync by default
* added timeout handling for uploads of large files
* fixed exit status >=256
* added config files
* added syncing to/from file
* fixed download of files with failed (incomplete) chunks

0.3.1
~~~~~

* general improvements for FUSE
* FUSE write support added
* added automatic logging
* sphinx documentation added

0.3.0
~~~~~

* FUSE read support added

0.2.2
~~~~~

* sync speed-up
* node listing format changed
* optional node listing coloring added (for Linux or via LS_COLORS)
* re-added possibility for local OAuth

0.2.1
~~~~~

* curl dependency removed
* added job queue, simultaneous transfers
* retry on error

0.2.0
~~~~~

* setuptools support
* workaround for download of files larger than 10 GiB
* automatic resuming of downloads


.. |Donate| image:: https://img.shields.io/badge/paypal-donate-blue.svg
   :alt: Donate via PayPal
   :target: https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id=V4V4HVSAH4VW8

.. |Gitter| image:: https://img.shields.io/badge/GITTER-join%20chat-brightgreen.svg
   :alt: Join the Gitter chat
   :target: https://gitter.im/yadayada/acd_cli

.. |PyPiVersion| image:: https://img.shields.io/pypi/v/acdcli.svg
   :alt: PyPi
   :target: https://pypi.python.org/pypi/acdcli

.. |PyVersion| image:: https://img.shields.io/badge/python-3.2+-blue.svg
   :alt:

.. |Status| image:: https://img.shields.io/badge/status-beta-yellow.svg
   :alt:

.. |License| image:: https://img.shields.io/badge/license-GPLv2+-blue.svg
   :alt:

.. |Build| image:: https://img.shields.io/travis/yadayada/acd_cli.svg
   :alt:
   :target: https://travis-ci.org/yadayada/acd_cli

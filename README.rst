|Donate| |Gitter| |PyVersion| |Status| |License| |Build| |PyPiVersion| |PyPiDownloadsMonth|

acd\_cli
========

**acd\_cli** provides a command line interface to Amazon Cloud Drive and allows mounting your
cloud drive using FUSE for read and write access. It is currently in beta stage.

Node Cache Features
-------------------

- caching of local node metadata in an SQLite database
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

Quick Start
-----------

Installation
~~~~~~~~~~~~

Please check which pip command is appropriate for Python 3 packages in your environment.
I will be using 'pip3' as superuser in the examples.

The easiest way is to directly install from PyPI.
::

   pip3 install --upgrade --pre acdcli


The most up-to-date way is to directly install from github.
::

   pip3 install --upgrade git+https://github.com/yadayada/acd_cli.git


Further setup options and dependencies are described in the `setup guide <docs/setup.rst>`_.

First Run
~~~~~~~~~

On the first start of the program (try ``acd_cli sync``), you will have to complete the OAuth procedure.
A browser tab will open and you will be asked to log in or grant access for 'acd\_cli\_oa'.
Signing in or clicking on 'Continue' will download a JSON file named ``oauth_data``,
which must be placed in the cache directory displayed on screen (e.g. ``/home/<USER>/.cache/acd_cli``).

You may view the source code of the Appspot app that is used to handle the server part
of the OAuth procedure at https://tensile-runway-92512.appspot.com/src.

Advanced Users
++++++++++++++

If you have security concerns regarding the Appspot authentication, have a look at Amazon's 
`ACD getting started guide 
<https://developer.amazon.com/public/apis/experience/cloud-drive/content/getting-started>`_.
Select all permissions for your security profile and add a redirect URL to ``http://localhost``.

Put your own security profile data in a file called ``client_data`` in the cache directory.
It needs to be created prior to starting the program and adhere to the following form.

.. code :: json

 {
     "CLIENT_ID": "",
     "CLIENT_SECRET": ""
 }

The procedure is similar to the Appspot one above, the difference is that you will
be asked to paste the redirect URL into your shell.

Usage
-----

acd_cli can be run as ``acd_cli`` or ``acdcli``.

Most actions need the node cache to be initialized and up-to-date, so please run a sync.
A sync will fetch the changes since the last sync or the full node list if the cache is empty.

The following actions are built in
::

        sync (s)            refresh node list cache; necessary for many actions
        clear-cache (cc)    clear node cache [offline operation]

        tree (t)            print directory tree [offline operation]
        children (ls)       list a folder's children [offline operation]

        find (f)            find nodes by name [offline operation] [case insensitive]
        find-md5 (fm)       find files by MD5 hash [offline operation]
        find-regex (fr)     find nodes by regular expression [offline operation] [case insensitive]

        upload (ul)         file and directory upload to a remote destination
        overwrite (ov)      overwrite file A [remote] with content of file B [local]
        stream (st)         upload the standard input stream to a file
        download (dl)       download a remote folder or file; will skip existing local files
        cat                 output a file to the standard output stream

        create (c, mkdir)   create folder using an absolute path

        list-trash (lt)     list trashed nodes [offline operation]
        trash (rm)          move node to trash
        restore (re)        restore node from trash

        move (mv)           move node A into folder B
        rename (rn)         rename a node

        resolve (rs)        resolve a path to a node ID [offline operation]

        usage (u)           show drive usage data
        quota (q)           show drive quota [raw JSON]
        metadata (m)        print a node's metadata [raw JSON]

        mount               mount the cloud drive at a local directory
        umount              unmount cloud drive(s)

Please run ``acd_cli --help`` to get a current list of the available actions. A list of further
arguments of an action and their order can be printed by calling ``acd_cli [action] --help``.

Most node arguments may be specified as a 22 character ID or a UNIX-style path.
Trashed nodes' paths might not be able to be resolved correctly; use their ID instead.

There are more detailed instructions for `file transfer actions <docs/transfer.rst>`_ and
`find actions <docs/find.rst>`_.

Mounting
~~~~~~~~

First, create an empty mount directory, then run ``acd_cli mount path/to/mountpoint``.
To unmount later, run ``acd_cli umount``.

Further information can be found in the `FUSE documentation <docs/FUSE.rst>`_.

Exit Status
~~~~~~~~~~~

When the script is done running, its exit status can be checked for flags. If no error occurs,
the exit status will be 0. Possible flag values are:

===========================  =======
        flag                  value
===========================  =======
general error                    1
argument error                   2
failed file transfer             8
upload timeout                  16
hash mismatch                   32
error creating folder           64
file size mismatch             128
cache outdated                 256
remote duplicate               512
duplicate inode               1024
file/folder name collision    2048
===========================  =======

If multiple errors occur, their values will be compounded by a binary OR operation.

Proxy support
~~~~~~~~~~~~~

`Requests <https://github.com/kennethreitz/requests>`_ supports HTTP(S) proxies via environment
variables. Since all connections to Amazon Cloud Drive are using HTTPS, you need to
set the variable ``HTTPS_PROXY``. The following example shows how to do that in a bash-compatible
environment.
::

    $ export HTTPS_PROXY="https://user:pass@1.2.3.4:8080/"

CLI Usage Example
-----------------

In this example, a two-level folder hierarchy is created in an empty cloud drive.
Then, a relative local path ``local/spam`` is uploaded recursively using two connections.
::

    $ acd_cli sync
      Syncing...
      Done.

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


The standard node listing format includes the node ID, the first letter of its status and its full path.
Possible statuses are "AVAILABLE" and "TRASH".

Known Issues
------------

It is not possible to upload files using Python 3.2.3, 3.3.0 and 3.3.1.

If you encounter Unicode problems, check that your locale is set correctly or use the ``--utf``
argument to force the script to use UTF-8 output encoding.
Windows users may try to execute the provided `reg file <assets/win_codepage.reg>`_
(tested with Windows 8.1) to set the command line interface encoding to cp65001.

API Restrictions
~~~~~~~~~~~~~~~~

- the current upload file size limit is 50GiB
- uploads of large files >10 GiB may be successful, yet a timeout error is displayed (please check manually)
- storage of node names is case-preserving, but not case-sensitive (this concerns Linux users mainly)
- it is not possible to share or delete files

Contribute
----------

Have a look at the `contributing guidelines <CONTRIBUTING.rst>`_.

Recent Changes
--------------

..
    0.3.1
    ~~~~~

    * general improvements for FUSE
    * FUSE write support added

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
   :target: https://gitter.im/cloud-drive/acd_cli

.. |PyPiVersion| image:: https://img.shields.io/pypi/v/acdcli.svg
   :alt: PyPi
   :target: https://pypi.python.org/pypi/acdcli

.. |PyVersion| image:: https://img.shields.io/badge/python-3.2+-blue.svg
   :alt:

.. |Status| image:: https://img.shields.io/badge/status-beta-yellow.svg
   :alt:

.. |License| image:: https://img.shields.io/badge/license-GPLv2+-blue.svg
   :alt:

.. |PyPiDownloadsMonth| image:: https://img.shields.io/pypi/dm/acdcli.svg
   :alt:
   :target: https://pypi.python.org/pypi/acdcli

.. |Build| image:: https://img.shields.io/travis/yadayada/acd_cli.svg
   :alt:
   :target: https://travis-ci.org/yadayada/acd_cli

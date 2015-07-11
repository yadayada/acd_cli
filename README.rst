|Donate| |Gitter| |PyVersion| |Status| |License| |PyPiVersion| |PyPiDownloadsMonth|

acd\_cli
========

**acd\_cli** provides a command line interface to Amazon Cloud Drive and allows mounting your
cloud drive using FUSE for *read* access. It is currently in beta stage.

Features
--------

- local node caching
- addressing of remote nodes via a pathname (e.g. ``/Photos/kitten.jpg``)
- simultaneous uploads/downloads, retry on error
- basic plugin support

File Operations
~~~~~~~~~~~~~~~

- tree or flat listing of files and folders
- upload/download of single files and directories
- folder creation
- trashing/restoring
- moving/renaming nodes

Quick Start
-----------

Installation
~~~~~~~~~~~~

The easiest way is to directly install from PyPI. Please check which pip command is
appropriate for Python 3 packages in your environment. I will be using 'pip3' in the examples.
::

   pip3 install --upgrade acdcli


The most up-to-date way is to directly install from github.
::

   pip3 install --upgrade git+https://github.com/yadayada/acd_cli.git


If you do not want to install, have a look at the necessary dependencies_.

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

Alternatively, you may put your own security profile data in a file called ``client_data`` in the cache directory.
It needs to be created prior to starting the program and adhere to the following form.

.. code :: json

 {
     "CLIENT_ID": "",
     "CLIENT_SECRET": ""
 }

Your security profile must be able to redirect to ``http://localhost``.
The procedure is similar to the above, the difference is that you will
be asked to paste the redirect URL into your shell.

Usage
-----

Most actions need the node cache to be initialized and up-to-date, so please run a sync.
A sync will fetch the changes since the last sync or the full node list if the cache is empty.

The following actions are built in
::

        sync (s)            refresh node list cache; necessary for many actions
        clear-cache (cc)    clear node cache [offline operation]

        tree (t)            print directory tree [offline operation]
        children (ls)       list a folder's children [offline operation]
        find (f)            find nodes by name [offline operation]
        find-md5 (fm)       find files by MD5 hash [offline operation]

        upload (ul)         file and directory upload to a remote destination
        overwrite (ov)      overwrite file A [remote] with content of file B [local]
        download (dl)       download a remote folder or file; will skip existing local files

        create (c, mkdir)   create folder using an absolute path

        list-trash (lt)     list trashed nodes [offline operation]
        trash (rm)          move node to trash
        restore (re)        restore node from trash

        move (mv)           move node A into folder B
        rename (rn)         rename a node

        resolve (rs)        resolve a path to a node ID

        usage (u)           show drive usage data
        quota (q)           show drive quota [raw JSON]
        metadata (m)        print a node's metadata [raw JSON]

        mount               mount the cloud drive at a local directory

Please run ``acd_cli --help`` to get a current list of the available actions.
You may also get a list of further arguments and their order of an action by calling ``acd_cli [action] --help``.

You may provide most node arguments as a 22 character ID or a UNIX-style path.
Trashed nodes' paths might not be able to be resolved correctly; use their ID instead.

The number of concurrent transfers can be specified using the argument ``-x [no]``.

When uploading/downloading large amounts of files, it is advisable to save the log messages to a file.
This can be done by using the verbose argument and appending ``2> >(tee acd.log >&2)`` to the command.

Files can be excluded via optional parameter by file ending, e.g. ``-xe bak``,
or regular expression on the whole file name, e.g. ``-xr "^thumbs\.db$"``.
Both exclusion methods are case insensitive.

Exit Status
~~~~~~~~~~~

When the script is done running, its exit status can be checked for flags. If no error occurs,
the exit status will be 0. Possible flag values are:

=====================    =======
        flag              value
=====================    =======
argument error               2
failed file transfer         8
upload timeout              16
hash mismatch               32
error creating folder       64
file size mismatch         128
cache outdated             256
duplicate                  512
=====================    =======

If multiple errors occur, their values will be compounded by a binary OR operation.

Mounting
~~~~~~~~

First, create an empty mount directory, then run ``acd_cli mount path/to/mountpoint``.
To unmount later, run ``fusermount -u path/to/mountpoint``.

=====================  ===========
Feature                 Working
=====================  ===========
Basic operations
----------------------------------
List directory           ✅
Read                     ✅
Write                    ❌
Rename                   ✅
Move                     ✅
Trashing                 ✅ [#]_
OS-level trashing        partially [#]_
View trash               ❌
Misc
----------------------------------
Automatic sync           ❌
Hard links               partially [#]_
Symbolic links           ❌
=====================  ===========

.. [#] equivalent to a filesystem level permanent delete
.. [#] restoration info cannot be written, manual restoring should work
.. [#] manually created hard links will be listed

Proxy support
~~~~~~~~~~~~~

`Requests <https://github.com/kennethreitz/requests>`_ supports HTTP(S) proxies via environment
variables. Since all connections to Amazon Cloud Drive are using HTTPS, you need to
set the variable ``HTTPS_PROXY``. The following example shows how to do that in a bash-compatible
environment.
::

    $ export HTTPS_PROXY="https://user:pass@1.2.3.4:8080/"

Usage Example
-------------

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

Uninstalling
------------

Please run ``acd_cli delete-everything`` first to delete your authentication and node data in the cache path.
Then, use pip to uninstall::

    pip3 uninstall acdcli

Then, revoke the permission for ``acd_cli_oa`` to access your cloud drive in your Amazon profile,
more precisely at https://www.amazon.com/ap/adam.


Known Issues
------------

It is not possible to upload files using Python 3.2.3, 3.3.0 and 3.3.1.

If you encounter Unicode problems, check that your locale is set correctly or use the ``--utf``
argument to force the script to use UTF-8 output encoding.
Windows users may try to execute the provided `reg file <assets/win_codepage.reg>`_
(tested with Windows 8.1) to set the command line interface encoding to cp65001.


API Restrictions
~~~~~~~~~~~~~~~~

- at the time being, it is not advisable to upload files larger than 9GiB
- uploads of large files >10 GiB may be successful, yet a timeout error is displayed (please check manually)
- the maximum (upload) file size seems to be in the range of 40 and 100 GiB
- storage of node names is case-preserving, but not case-sensitive (this concerns Linux users mainly)
- it is not possible to share or delete files

Contribute
----------

Have a look at the `contributing guidelines <CONTRIBUTING.rst>`_.

.. _dependencies:

Dependencies
------------

Python Packages
~~~~~~~~~~~~~~~

- appdirs
- dateutils (recommended)
- requests >= 2.1.0
- requests-toolbelt (recommended)
- sqlalchemy

Recommended packages are not strictly necessary; but they will be preferred to
workarounds (in the case of dateutils) and bundled modules (requests-toolbelt).

If you want to the dependencies using your distribution's packaging system and
are using a distro based on Debian 'jessie', the necessary packages are
``python3-appdirs python3-dateutil python3-requests python3-sqlalchemy``.

FUSE
~~~~

For the mounting feature, fuse >= 2.6 is needed according to pyfuse. On a
Debian-based distribution, the according package should simply be named 'fuse'.

Recent Changes
--------------

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
   :alt: Join the chat at https://gitter.im/cloud-drive/acd_cli
   :target: https://gitter.im/cloud-drive/acd_cli?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge

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

acd\_cli
========

**acd\_cli** aims to provide a command line interface to Amazon Cloud Drive written in Python 3. 
It is currently in alpha stage.

Features
--------

 -  local node caching
 -  addressing of remote nodes via a pathname (e.g. ``/Photos/kitten.jpg``)
 -  basic plugin support

File operations
~~~~~~~~~~~~~~~

 - tree or flat listing of files and folders
 - upload/download of single files and directories
 - folder creation
 - trashing/restoring
 - moving/renaming nodes

Quick start
-----------

Installation
~~~~~~~~~~~~

After downloading, run the appropriate pip command for Python 3 in the project's root directory like so:
::

    pip3 install .

First Run
~~~~~~~~~

On the first start of the program (try ``acd_cli sync``), you will have to complete the OAuth procedure.
A browser tab will open and you will be asked to log in or grant access for 'acd\_cli\_oa'.
Signing in or clicking on 'Continue' will download a JSON file named ``oauth_data``,
which must be placed in the cache directory displayed on screen (e.g. ``/home/<USER>/.cache/acd_cli``).

You may view the Appspot source code at https://tensile-runway-92512.appspot.com/src.

Usage
-----

Most actions need the node cache to be initialized and up-to-date, so  please run a sync.
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
        download (dl)       download a remote folder or file; will overwrite local files
        create (c, mkdir)   create folder using an absolute path
        list-trash (lt)     list trashed nodes [offline operation]
        trash (rm)          move node to trash
        restore (re)        restore from trash
        move (mv)           move node A into folder B
        rename (rn)         rename a node
        resolve (rs)        resolve a path to a node ID
        add-child (ac)      add a node to a parent folder
        remove-child (rc)   remove a node from a parent folder
        usage (u)           show drive usage data
        quota (q)           show drive quota [raw JSON]
        metadata (m)        print a node's metadata [raw JSON]

Please run ``acd_cli.py --help`` to get a current list of the available actions.
You may also get a list of further arguments and their order of an action by calling ``acd_cli.py [action] --help``.

You may provide most node arguments as a 22 character ID or a UNIX-style path.
Trashed nodes' paths might not be able to be resolved correctly; use their ID instead.

When uploading/downloading large amounts of files, it is advisable to save the log messages to a file.
This can be done by appending ``2> >(tee acd.log >&2)`` to the command.

Files can be excluded via optional parameter by file ending, e.g. ``-xe bak``,
or regular expression on the whole file name, e.g. ``-xr "^thumbs\.db$"``.
Both exclusion methods are case insensitive.

When the script is done running, its exit status can be checked for flags. If no error occurs,
the exit status will be 0. Possible flag values are:

 - argument error -- 2
 - failed file transfer -- 8
 - upload timeout -- 16
 - hash mismatch -- 32
 - error creating folder -- 64.

If multiple errors occur, their values will be compounded by a binary OR operation.

Usage example
-------------

::

    $ acd_cli sync
      Syncing... Done.
    $ acd_cli tree
      [PHwiEv53QOKoGFGqYNl8pw] [A] /
    $ acd_cli create /egg/
    $ acd_cli create /egg/bacon/
    $ acd_cli upload local/spam/ /egg/bacon/
      Current directory: local/spam/
      Current file: local/spam/sausage
      [##################################################] 100.00% of 20.0MiB
      Current file: local/spam/lobster
      [##################################################] 100.00% of 10.0MiB
      [...]
    $ acd_cli tree
      [PHwiEv53QOKoGFGqYNl8pw] [A] /
      [         ...          ] [A] /egg/
      [         ...          ] [A] /egg/bacon/
      [         ...          ] [A] /egg/bacon/spam/
      [         ...          ] [A] /egg/bacon/spam/sausage
      [...]

Known Issues
------------

API Restrictions
~~~~~~~~~~~~~~~~

 -  uploads of large files >10 GiB may be successful, yet a timeout error is displayed (please check manually)
 -  the maximum (upload) file size seems to be in the range of 40 and 100 GiB
 -  storage of node names is case-preserving, but not case-sensitive (this concerns Linux users mainly)

Contribute
----------

Feel free to use the bug tracker to add issues.
You might find the ``--verbose`` and - to a lesser extent - ``--debug`` options helpful.

If you want to contribute code, have a look at Github's general guide how to do that
https://guides.github.com/activities/contributing-to-open-source/#contributing
There is also a :ref:`TODO` list.

Dependencies
------------

 - appdirs
 - dateutils (recommended)
 - pycurl
 - requests >= 1.0.0
 - sqlalchemy

If you want to get these manually and are using a distribution based on Debian 'jessie', 
the necessary packages are
``python3-appdirs python3-dateutil python3-pycurl python3-requests python3-sqlalchemy``.

Recent Changes
~~~~~~~~~~~~~~

0.2.0
+++++
 * setuptools support
 * workaround for download of files larger than 10 GiB
 * automatic resuming of downloads

0.1.3
+++++
 * plugin mechanism added
 * OAuth now via Appspot; security profile no longer necessary
 * back-off algorithm for API requests implemented

0.1.2
+++++
new:
 * overwriting of files
 * recursive upload/download
 * hashing of downloaded files
 * clear-cache action

fixes:
 * remove-child accepted status code
 * fix for upload of files with Unicode characters

other:
 * changed database schema

Usage
-----

acd_cli may be invoked as ``acd_cli`` or ``acdcli``.

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

There are more detailed instructions for :doc:`file transfer actions <transfer>`,
:doc:`find actions <find>` and :doc:`FUSE documentation <FUSE>`.

Logs will automatically be saved into the cache directory.

Global Flags/Parameters
~~~~~~~~~~~~~~~~~~~~~~~

..
  not using reST's option list here because it does not support (?) --foo={bar1,bar2} type args

``--verbose`` (``-v``) and ``--debug`` (``-d``) will print additional messages to standard error.

``--no-log`` (``-nl``) will disable the automatic logging feature that saves log files to the
cache directory.

``--color`` will set the coloring mode according to the specified argument (``auto``, ``never``
or ``always``). Coloring is turned off by default; it is used for file/folder listings.

``--check`` (``-c``) sets the start-up database integrity check mode. The default is to perform a
``full`` check. Setting the check to ``quick`` or ``none`` may speed up the initialization for
large databases.

``--utf`` (``-u``) will force the output to be encoded in UTF-8, regardless
of the system's settings.


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
error deleting source file    4096
===========================  =======

If multiple errors occur, their values will be compounded by a binary OR operation.

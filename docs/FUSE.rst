FUSE module
===========

Status
------

The FUSE module will never provide anything as good and reliable as a local filesystem. 
See the `bug tracker <https://github.com/yadayada/acd_cli/labels/FUSE>`_ for issues that
may occur. 

acd\_cli's FUSE module has the following filesystem features implemented:

=====================  ===========
Feature                 Working
=====================  ===========
Basic operations
----------------------------------
List directory           ✓
Read                     ✓
Write                    ✓ [#]_
Rename                   ✓
Move                     ✓
Trashing                 ✓
OS-level trashing        ✓ [#]_
View trash               ❌
Misc
----------------------------------
Automatic sync           ✓
ctime/mtime update       ❌
Custom permissions       ❌
Hard links               partially [#]_
Symbolic links           ❌ [#]_
=====================  ===========

.. [#] partial writes are not possible (i.e. writes at random offsets)
.. [#] restoring might not work
.. [#] manually created hard links will be displayed, but it is discouraged to use them
.. [#] soft links are not part of the ACD API

Usage
-----

The command to mount the (root of the) cloud drive to the empty directory ``path/to/mountpoint`` is
::

    acd_cli mount path/to/mountpoint

A cloud drive folder may be mounted similarly, by
::

    acd_cli mount --modules="subdir,subdir=/folder" path/to/mountpoint

Unmounting is usually achieved by the following command
::

    fusermount -u path/to/mountpoint

If the mount is busy, Linux users can use the ``--lazy`` (``-z``) flag.
There exists a convenience action ``acd_cli umount`` that unmounts all ACDFuse mounts on
Linux and Mac OS.

.. NOTE::
    Changes made to your cloud drive storage not using acd\_cli will no longer be synchronized
    automatically. See the ``--interval`` option below to re-enable automatic synchronization.

.. WARNING::
    Using acd_cli's CLI commands (e.g. upload or sync) while having the cloud drive mounted
    may lead to errors or corruption of the node cache.

Mount Options
~~~~~~~~~~~~~

For further information on the most of the options below, see your :manpage:`mount.fuse(8)` man page.

To convert the node's standard character set (UTF-8) to the system locale, the modules argument
may be used, e.g. ``--modules="iconv,to_code=CHARSET"``.

--allow-other, -ao        allow all users to access the mountpoint (may need extra configuration)
--allow-root, -ar         allow the root user to access the mountpoint (may need extra configuration)
--foreground, -fg         do not detach process until filesystem is destroyed (blocks)
--gid GID                 override the group ID (defaults to the user's gid)
--interval INT, -i INT    set the node cache sync (refresh) interval to INT seconds
--nlinks, -n              calculate the number of links for folders (slower)
--nonempty, -ne           allow mounting to a non-empty mount point
--read-only, -ro          disallow write operations (does not affect cache refresh)
--single-threaded, -st    disallow multi-threaded FUSE operations
--uid UID                 override the user ID (defaults to the user's uid)
--umask UMASK             override the standard permission bits

Automatic Remount
~~~~~~~~~~~~~~~~~

Please make sure your network connection is up before you try to run the mount command.

Linux users may use the systemd service file from the assets directory
to have the clouddrive automatically remounted on login.
Alternative ways are to add a crontab entry using the ``@reboot`` keyword or to add an
fstab entry like so:
::

  acdmount    /mount/point    fuse    _netdev    0    0


For this to work, an executable shell script /usr/bin/acdmount must be created
::
  
  #!/bin/bash

  acd_cli mount $1

Library Path
~~~~~~~~~~~~

If you want or need to override the standard libfuse path, you may set the environment variable
`LIBFUSE_PATH` to the full path of libfuse, e.g.
::

   export LIBFUSE_PATH="/lib/x86_64-linux-gnu/libfuse.so.2"

This is particularly helpful if the libfuse library is properly installed, but not found.

Deleting Nodes
~~~~~~~~~~~~~~

"Deleting" directories or files from the file system will only trash them in your cloud drive.
Calling rmdir on a directory will always move it into the trash, even if it is not empty.

Logging
~~~~~~~

For debugging purposes, the recommended command to run is
::

    acd_cli -d -nl mount -i0 -fg path/to/mountpoint

That command will disable the automatic refresh (i.e. sync) of the node cache (`-i0`) and disable
detaching from the console.

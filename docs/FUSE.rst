FUSE module
===========

The FUSE support is still in its early stage and may be
(`prone to bugs <https://github.com/yadayada/acd_cli/labels/FUSE>`_).
acd\_cli's FUSE module has the following filesystem features implemented:

=====================  ===========
Feature                 Working
=====================  ===========
Basic operations
----------------------------------
List directory           ✅
Read                     ✅
Write                    ✅ [#]_
Rename                   ✅
Move                     ✅
Trashing                 ✅
OS-level trashing        ✅ [#]_
View trash               ❌
Misc
----------------------------------
Automatic sync           ✅
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

    acd_cli mount --modules="subdir=/folder" path/to/mountpoint

Unmounting is done by the following command
::

    fusermount -u path/to/mountpoint

or, more conveniently, by calling ``acd_cli umount``. If the mount is busy, the `lazy` argument
(``-z``) can be used.

To convert the node's standard character set (UTF-8) to the system locale, the modules argument
may be used, e.g. ``--modules="iconv,to_code=CHARSET"``.

For debugging purposes, the recommended command to run is
::

    acd_cli -d mount -i0 -fg path/to/mountpoint


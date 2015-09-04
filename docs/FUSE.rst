FUSE module
===========

The FUSE support is still in its early stage and may be prone to bugs
(`<https://github.com/yadayada/acd_cli/labels/FUSE>`_).
acd\_cli has the following features implemented:

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

For debugging purposes, the recommended command to run is

::

    acdcli -d mount -i0 -fg /mount/point


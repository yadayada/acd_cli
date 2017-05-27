Finding nodes
=============

The find actions will search for normal (active) and trashed nodes and list them.

find
----

The find action will perform a case-insensitive search for files and folders that include the
name or name segment given as argument, so e.g. ``acdcli find foo`` will find "foo", "Foobar", etc.

find-md5
--------

find-md5 will search for files that match the MD5 hash given. The location of a local file may be
determined like so:
::

   acdcli find-md5 `md5sum local/file | cut -d" " -f1`

find-regex
----------

find-regex searches for the specified `regex <https://docs.python.org/3.2/library/re.html>`_
in nodes' names.

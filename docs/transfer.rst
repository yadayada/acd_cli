File transfer
=============

acd\_cli offers multi-file transfer actions - upload and download -
and single-file transfer actions - overwrite, stream and cat.

Multi-file transfers can be done with concurrent connections by specifying the argument ``-x NUM``.

Actions
-------

Upload
~~~~~~

The upload action will upload files or recursively upload directories.

Syntax:
::

   acdcli upload /local/path [/local/next_path [...]] /remote/path


Overwrite
~~~~~~~~~

The upload action overwrites the content of a remote file with a local file.

Syntax:
::

    acdcli overwrite /local/path /remote/path

Download
~~~~~~~~

The download action can download a single file or recursively download a directory.

Syntax:
::

    acdcli download /remote/path [/local/path]

If the local path is omitted, the destination path will be the current working directory.

Stream
~~~~~~

This action will upload the standard input stream to a file.

Syntax:
::

some_process | acdcli stream file_name /remote/path

Cat
~~~

This action outputs the content of a file to standard output.

Retry
-----

Upload, download and overwrite allow retries by specifying the argument ``-r MAX_RETRIES``

Exclusion
---------

Files may be excluded from upload or download by regex on their name or by file ending.
Additionally, paths can be excluded from upload. Regexes and file endings are case-insensitive.

It is possible to specify multiple exclusion arguments of the same kind.

Deduplication
-------------

Server-side deduplication prevents completely uploaded files from being saved as a node if another
file with the same MD5 checksum already exists.
acd\_cli can prevent uploading duplicates by checking local files' sizes and MD5s.
Empty files are never regarded duplicates.

Logging
-------

When uploading/downloading large amounts of files, it is advisable to save the log messages to a file.
This can be done by using the verbose argument and appending ``2> >(tee acd.log >&2)`` to the command.
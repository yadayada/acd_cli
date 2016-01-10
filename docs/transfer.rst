File transfer
=============

acd\_cli offers multi-file transfer actions - upload and download -
and single-file transfer actions - overwrite, stream and cat.

Multi-file transfers can be done with concurrent connections by specifying the argument ``-x NUM``.
If remote folder hierarchies or local directory hierarchies need to be created, this will be done
prior to the file transfers.

Actions
-------

``upload``
~~~~~~~~~~

The upload action will upload files or recursively upload directories.
Existing files will not be changed, normally.

Syntax:
::

   acdcli upload /local/path [/local/next_path [...]] /remote/path

If the ``--overwrite`` (``-o``) argument is specified, a remote file will be updated if
a) the local file's modification time is higher or
b) the local file's creation time is higher and the file size is different.
The ``--force`` (``-f``) argument can be used to force overwrite.

.. hint::
  When uploading large files (>10GiB), a warning about a timeout may be displayed. You then need to
  wait a few minutes, sync and manually check if the file was uploaded correctly.

``overwrite``
~~~~~~~~~~~~~

The upload action overwrites the content of a remote file with a local file.

Syntax:
::

    acdcli overwrite /local/path /remote/path

``download``
~~~~~~~~~~~~

The download action can download a single file or recursively download a directory.
If a file already exists locally, it will not be overwritten.

Syntax:
::

    acdcli download /remote/path [/local/path]

If the local path is omitted, the destination path will be the current working directory.

``stream``
~~~~~~~~~~

This action will upload the standard input stream to a file.

Syntax:
::

    some_process | acdcli stream file_name /remote/path

If the ``--overwrite`` (``-o``) argument is specified, the remote file will be overwritten if
it exists.

``cat``
~~~~~~~

This action outputs the content of a file to standard output.

Abort/Resume
------------

Incomplete file downloads will be resumed automatically. Aborted file uploads are not resumable
at the moment.

Folder or directory hierarchies that were created for a transfer do not need to be recreated when
resuming a transfer.

Retry
-----

Failed upload, download and overwrite actions allow retries on error
by specifying the ``--max-retries|-r`` argument, e.g. ``acd_cli <ACTION> -r MAX_RETRIES``.

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

Syncing
=======

**acd\_cli** keeps a local cache of node metadata to reduce latency. Syncing simply
means updating the local cache with current data from Amazon Drive.
[An Amazon Drive `node` may be file or folder.]

Regular syncing
---------------

Regular syncing ``acd_cli sync`` should be the preferred method to update the metadata for
your whole Drive account. When invoked for the first time, it will get a complete list of
the file and folder metadata. For later uses, it will utilize the saved checkpoint from the
last sync to only fetch the metadata that has changed since then.

The ``--full`` (``-f``) flag forces the cache to be cleared before syncing, resulting in
a non-incremental, full sync.

Sync changesets may also be written to or inserted from a file.

Incomplete sync
+++++++++++++++

For large syncsets, for instance when doing a full sync, you may get the error message
"Root node not found. Sync may have been incomplete." Please try to resume the sync process
later, omitting the ``--full`` flag if you had specified it prior.

Partial syncing
---------------

Partial syncing may be a quick-and-dirty way to synchronize the metadata of a single directory 
with a smallish number of files and folders. E.g. ``acd_cli psync /`` will non-recursively fetch
the metadata for the root folder.

The ``--recursive`` (``-r``) flag will also descend into the specified folder's subfolders.
It is not advisible to use this flag for folders with many subfolders

The partial sync action will need to fetch node metadata in batches of 200. T
Please be aware that when using regular and partial syncing alternatingly, your metadata
may be in an inconsistent state.

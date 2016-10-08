Configuration
=============

Some module constants may be set in INI-style configuration files. If you want to override
the defaults as described below, create a plain text file for the module using the section heading
as the file name in the settings directory.

acd\_cli.ini
------------

::

  [download]
  ;do not delete corrupt files
  keep_corrupt = False
  
  ;do not delete partially downloaded files
  keep_incomplete = True

  [upload]
  ;waiting time for timed-out uploads/overwrittes to appear remotely [minutes]
  timeout_wait = 10

acd\_client.ini
---------------

::

  [endpoints]
  filename = endpoint_data

  ;sets the validity of the endpoint URLs, 3 days by default [seconds]
  validity_duration = 259200

  [transfer]
  ;sets the read/write chunk size for the local file system [bytes]
  fs_chunk_size = 131072

  ;sets maximal consecutive chunk size for downloads, 500MiB by default [bytes]
  ;this limit was introduced because, in the past, files >10GiB could not be downloaded in one piece
  dl_chunk_size = 524288000

  ;sets the number of retries for failed chunk requests
  chunk_retries = 1

  ;sets the connect and idle timeout [seconds]
  ;the idle timeout will be used in both timeout scenarios for some old requests versions
  ;refer to the requests docs http://docs.python-requests.org/en/master/user/advanced/
  connection_timeout = 30
  idle_timeout = 60

  [proxies]
  ;none by default

A proxy may be set by adding a protocol to proxy mapping like
``https = https://user:pass@1.1.1.1:1234`` to the proxies section.

cache.ini
---------

::

  [sqlite]
  filename = nodes.db

  ;sets the time to sleep if a table is locked [milliseconds]
  busy_timeout = 30000

  ;https://www.sqlite.org/pragma.html#pragma_journal_mode
  journal_mode = wal

  [blacklist]

  ;files contained in folders in this list will be excluded from being saved
  ;into the cache (not currently implemented)
  folders = []

fuse.ini
--------

::

  [read]
  ;maximal number of simultaneously opened chunks per file
  open_chunk_limit = 10

  ;sets the connection/idle timeout when creating or reading a chunk [seconds]
  timeout = 5

  [write]
  ;number of buffered chunks in the write queue
  ;the size of the chunks may vary (e.g. 512B, 4KB, or 128KB)
  buffer_size = 32

  ;sets the timeout for putting a chunk into the queue [seconds]
  timeout = 30

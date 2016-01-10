TODO
----

General / API
~~~~~~~~~~~~~

* switch to multiprocessing (?)
* metalink support (?)

API
~~~

* support of node labels
* support for assets (?)
* favorite support (feature not yet announced officially)
* rip out the Appspot authentication handler
* fix upload of 0-byte streams

CLI
~~~

* unify the find action
* check symlink behavior for different Python versions (#95)

FUSE
~~~~

* invalidate chunks of StreamedResponseCache (implement a time-out)
* respect flags when opening files
* use a filesystem test suite

File Transfer
~~~~~~~~~~~~~

* more sophisticated progress handler that supports offsets
* copy local mtime on upload (#58)
* add path exclusion by argument for download

User experience
~~~~~~~~~~~~~~~

* shell completion for remote directories (#127)
* even nicer help formatting
* log coloring

Tests
~~~~~

* cache methods
* more functional tests
* fuse module

Documentation
~~~~~~~~~~~~~

* write how-to on packaging plugins (sample setup.py)

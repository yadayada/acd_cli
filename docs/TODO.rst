TODO
----

General
~~~~~~~

* favorite support (feature not yet announced officially)
* support of node labels
* support for assets (?)
* unify the find action
* switch to multiprocessing
* metalink support (?)
* symlink behavior (#95)

FUSE
~~~~

* invalidate chunks of StreamedResponseCache
* fix multi-threading

File Transfer
~~~~~~~~~~~~~

* autosplit large files (#32)
* more sophisticated progress handler that supports offsets
* copy local mtime on upload (#58)
* add path exclusion by argument for download
* piped overwrite

User experience
~~~~~~~~~~~~~~~

* shell completion for remote directories
* even nicer help formatting
* log coloring

Tests
~~~~~

* cache methods
* more functional tests
* fuse module

Documentation
~~~~~~~~~~~~~

* add a main sphinx page
* write how-to on packaging plugins (sample setup.py)

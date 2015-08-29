Setting up acd\_cli
===================

The `readme <../README.rst>`_ describes the recommended PIP installation methods.

If you are worried about Python dependencies or possibly messing up your system, use a virtualenv.

PIP errors
----------

A version incompatibility may arise with PIP when upgrading the requests package.
PIP will throw the following error:
::

    ImportError: cannot import name 'IncompleteRead'

Run these commands to fix it:
::

    apt-get remove python3-pip
    easy_install3 pip

This will remove the distribution's pip3 package and replace it with a version that is compatible
with the newer requests package.

Distribution-specific packages
------------------------------

There are two packages for Arch Linux in the AUR,
`acd_cli-git <https://aur4.archlinux.org/packages/acd_cli-git/>`_ and
`acd_cli <https://aur.archlinux.org/packages/acd_cli/>`_.

You can use the `Makefile <../assets/Makefile>`_ to build Debian (``make deb``)
or RedHat packages (``make rpm``). It will also build the required requests-toolbelt package.

.. _dependencies:

Dependencies
------------

Python Packages
~~~~~~~~~~~~~~~

- `appdirs <https://github.com/ActiveState/appdirs>`_
- `dateutils <https://github.com/paxan/python-dateutil>`_ (recommended)
- `requests <https://github.com/kennethreitz/requests>`_ >= 2.1.0
- `requests-toolbelt <https://github.com/sigmavirus24/requests-toolbelt>`_ (recommended)
- `sqlalchemy <https://bitbucket.org/zzzeek/sqlalchemy/>`_

Recommended packages are not strictly necessary; but they will be preferred to
workarounds (in the case of dateutils) and bundled modules (requests-toolbelt).

If you want to the dependencies using your distribution's packaging system and
are using a distro based on Debian 'jessie', the necessary packages are
``python3-appdirs python3-dateutil python3-requests python3-sqlalchemy``.

FUSE
~~~~

For the mounting feature, fuse >= 2.6 is needed according to
`pyfuse <https://github.com/terencehonles/fusepy>`_.
On a Debian-based distribution, the necessary package should be named simply 'fuse'.

Uninstalling
------------

Please run ``acd_cli delete-everything`` first to delete your authentication
and node data in the cache path. Then, use pip to uninstall
::

    pip3 uninstall acdcli

Then, revoke the permission for ``acd_cli_oa`` to access your cloud drive in your Amazon profile,
more precisely at https://www.amazon.com/ap/adam.
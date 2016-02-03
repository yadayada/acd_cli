Setting up acd\_cli
===================

Check which Python 3 version is installed on your system, e.g. by running
::

   python3 -V

If it is Python 3.2.3, 3.3.0 or 3.3.1, you need to upgrade to a higher minor version.

You may now proceed to install using PIP, your Arch package manager or build Debian/RedHat
packages.

Installation with PIP
---------------------

If you are new to Python, worried about dependencies or about
possibly messing up your system, create and activate virtualenv like so:
::

   cd /parent/path/to/your/new/virtualenv
   virtualenv acdcli
   source acdcli/bin/activate

You are now safe to install and test acd\_cli. When you are finished, the environment can be
disabled by simply closing your shell or running ``deactivate``.

Please check which pip command is appropriate for Python 3 packages in your environment.
I will be using 'pip3' as superuser in the examples.

The recommended and most up-to-date way is to directly install the master branch from GitHub.
::

   pip3 install --upgrade git+https://github.com/yadayada/acd_cli.git

The easiest way is to directly install from PyPI.
::

   pip3 install --upgrade --pre acdcli


PIP Errors
~~~~~~~~~~

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

Installation on Arch/Debian/RedHat
----------------------------------

Arch Linux
~~~~~~~~~~

There are two packages for Arch Linux in the AUR,
`acd_cli-git <https://aur4.archlinux.org/packages/acd_cli-git/>`_, which is linked to the
master branch of the GitHub repository, and
`acd_cli <https://aur.archlinux.org/packages/acd_cli/>`_, which is linked to the PyPI release.

Building deb/rpm packages
~~~~~~~~~~~~~~~~~~~~~~~~~

You will need to have `fpm <https://github.com/jordansissel/fpm>`_ installed to build packages.

There is a `Makefile <../assets/Makefile>`_ that includes commands to build Debian packages
(``make deb``) or RedHat packages (``make rpm``). It will also build the required 
requests-toolbelt package.
fpm may also be able to build packages for other distributions or operating systems.


Environment Variables
---------------------

Cache Path and Settings Path
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

You will find the current path settings in the output of ``acd_cli -v init``.

The cache path is where acd\_cli stores OAuth data, the node cache, logs etc. You
may override the cache path by setting the ``ACD_CLI_CACHE_PATH`` environment variable.

.. The settings path is where various configuration files are stored.
   The default path may be overriden the ``ACD_CLI_SETTINGS_PATH`` environment variable.

Proxy support
~~~~~~~~~~~~~
 
`Requests <https://github.com/kennethreitz/requests>`_ supports HTTP(S) proxies via environment
variables. Since all connections to Amazon Cloud Drive are using HTTPS, you need to
set the variable ``HTTPS_PROXY``. The following example shows how to do that in a bash-compatible
environment.
::

    export HTTPS_PROXY="https://user:pass@1.2.3.4:8080/"

You can also use HTTP proxies supporting CONNECT method:
::

    export HTTPS_PROXY="http://1.2.3.4:8888/"

Locale
~~~~~~

If you need non-ASCII file/directory names, please check that your system's locale is set correctly.

Dependencies
------------

FUSE
~~~~

For the mounting feature, fuse >= 2.6 is needed according to
`fusepy <https://github.com/terencehonles/fusepy>`_.
On a Debian-based distribution, the package should be named simply 'fuse'.

Python Packages
~~~~~~~~~~~~~~~

Under normal circumstances, it should not be necessary to install the dependencies manually.

- `appdirs <https://github.com/ActiveState/appdirs>`_
- `colorama <https://github.com/tartley/colorama>`_
- `dateutils <https://github.com/paxan/python-dateutil>`_ (recommended)
- `requests <https://github.com/kennethreitz/requests>`_ >= 2.1.0
- `requests-toolbelt <https://github.com/sigmavirus24/requests-toolbelt>`_
- `sqlalchemy <https://bitbucket.org/zzzeek/sqlalchemy/>`_

Recommended packages are not strictly necessary; but they will be preferred to
workarounds (in the case of dateutils).

If you want to the dependencies using your distribution's packaging system and
are using a distro based on Debian 'jessie', the necessary packages are
``python3-appdirs python3-colorama python3-dateutil python3-requests python3-sqlalchemy``.

Uninstalling
------------

Please run ``acd_cli delete-everything`` first to delete your authentication
and node data in the cache path. Then, use pip to uninstall
::

    pip3 uninstall acdcli

Then, revoke the permission for ``acd_cli_oa`` to access your cloud drive in your Amazon profile,
more precisely at https://www.amazon.com/ap/adam.

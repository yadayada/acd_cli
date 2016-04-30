Frequently Asked Questions
==========================

Why Did I Get an UnicodeEncodeError?
------------------------------------

If you encounter Unicode problems, check that your locale is set correctly.
Alternatively, you may use the ``--utf`` argument to force acd\_cli to use UTF-8 output encoding
regardless of your console's current encoding.

Windows users may import the provided reg file (assets/win_codepage.reg),
tested with Windows 8.1, to set the command line interface encoding to cp65001.

What Is acd\_cli's Installation Path?
-------------------------------------

On unixoid operating systems the acd\_cli script may be located by running ``which acd_cli``
or, if that does not yield a result, by executing ``pip3 show -f acdcli``.

Where Does acd\_cli Store its Cache and Settings?
-------------------------------------------------

You can see which paths are used in the log output of ``acd_cli -v init``.

My Sync Fails. What Should I Do?
--------------------------------

If you are doing an incremental synchronization (i.e. you have synchronized before) and it fails,
a full sync might work ``acd_cli sync -f``.

If the sync times out, consider increasing the idle timeout (refer to the 
:doc:`config documentation <configuration>`).

You may also want to try the deprecated (and undocumented) synchronization method ``acd_cli old-sync`` 
if you happen to have only up to a few thousand files and folders in total.

How Do I Pass a Node ID Starting with ``-`` (dash/minus/hyphen)?
----------------------------------------------------------------

Precede the node ID by two minuses and a space to have it be interpreted as parameter
and not as an argument, e.g. ``-- -AbCdEfGhIjKlMnOpQr012``.

Can I Share or Delete Files/Folders?
------------------------------------

No. It is not possible to share or delete using the Cloud Drive API. Please do it manually
using the `Web interface <https://www.amazon.com/clouddrive>`_.

What Do I Do When I get an `sqlite3.OperationalError: database is locked` error?
--------------------------------------------------------------------------------

Please limit the number or running acd\_cli processes to one. For example, do not have an
active FUSE mount while simultaneously uploading via command line.

Why Does Python Crash When executing acd\_cli on Mac OS?
--------------------------------------------------------

There is an `issue with the _scproxy module <http://bugs.python.org/issue13829>`_.
Please precede your usual commands by ``env no_proxy='*'`` to prevent it from causing crashes.

How Do I Share Directories from ACDFuse with Samba?
---------------------------------------------------

By default, only the user that originally mounted the FUSE filesystem has access permissions.
To lift this restriction, run the ``mount`` command with the ``--allow-other`` option.
You may need to edit your system's setting before being able to use this mount option,
e.g. in /etc/fuse.conf.

Do Transfer Speeds Vary Depending on Geolocation?
-------------------------------------------------

Amazon may be throttling users not located in the U.S. To quote the Terms of Use,

    The Service is offered in the United States. We may restrict access from other locations.
    There may be limits on the types of content you can store and share using the Service,
    such as file types we don't support, and on the number or type of devices you can use
    to access the Service. We may impose other restrictions on use of the Service.

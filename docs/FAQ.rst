Frequently Asked Questions
==========================

Why did I get an UnicodeEncodeError?
------------------------------------

If you encounter Unicode problems, check that your locale is set correctly.
Alternatively, you may use the ``--utf`` argument to force acd\_cli to use UTF-8 output encoding
regardless of your console's current encoding. T

Windows users may import the provided reg file (assets/win_codepage.reg),
tested with Windows 8.1, to set the command line interface encoding to cp65001.

Where Does acd\_cli Store its Cache and Settings?
-------------------------------------------------

You can see which paths are used in the log output of ``acd_cli -v init``.

How Do I Pass a Node ID Starting with ``-`` (dash/minus/hyphen)?
----------------------------------------------------------------

Precede the node ID by two minuses and a space to have it be interpreted as parameter
and not as an argument, e.g. ``-- -AbCdEfGhIjKlMnOpQr012``.

Can I Share or Delete Files/Folders?
------------------------------------

No. It is not possible to share or delete using the Cloud Drive API. Please do it manually
using the `Web interface <https://www.amazon.com/clouddrive>`_.

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
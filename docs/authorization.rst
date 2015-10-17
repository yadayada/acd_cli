Authorization
-------------

Before you can use the program, you will have to complete the OAuth procedure with Amazon.
There is a fast and simple way and a safe way.

Simple (Appspot)
++++++++++++++++

You will not have to prepare anything to initiate this authorization method, just
run, for example, ``acd_cli init``.

A browser (tab) will open and you will be asked to log into your Amazon account
or grant access for 'acd\_cli\_oa'.
Signing in or clicking on 'Continue' will download a JSON file named ``oauth_data``, which must be
placed in the cache directory displayed on screen (e.g. ``/home/<USER>/.cache/acd_cli``).

You may view the source code of the Appspot app that is used to handle the server part
of the OAuth procedure at https://tensile-runway-92512.appspot.com/src.

Advanced Users (Security Profile)
+++++++++++++++++++++++++++++++++

You must create a security profile and have it whitelisted. Have a look at Amazon's
`ACD getting started guide
<https://developer.amazon.com/public/apis/experience/cloud-drive/content/getting-started>`_.
Select all permissions for your security profile and add a redirect URL to ``http://localhost``.

Put your own security profile data in a file called ``client_data`` in the cache directory
and have it adhere to the following form.

.. code :: json

 {
     "CLIENT_ID": "amzn1.application-oa2-client.0123456789abcdef0123456789abcdef",
     "CLIENT_SECRET": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
 }

You may now run ``acd_cli -v init``.
The authentication procedure is similar to the one above. A browser (tab) will be
opened and you will be asked to log in. Unless you have a local webserver running on port 80,
you will be redirected to your browser's error page. Just copy the URL
(e.g. ``http://localhost/?code=AbCdEfGhIjKlMnOpQrSt&scope=clouddrive%3Aread_all+clouddrive%3Awrite``)
into the console.

Changing authorization methods
++++++++++++++++++++++++++++++

If you want to change between authorization methods, go to your cache path (it is stated in the
output of ``acd_cli -v init``) and delete the file ``oauth_data`` and, if it exists, ``client_data``.

Contributing guidelines
=======================

Using the Issue Tracker
-----------------------

The issue tracker is not a forum! This does not mean there is no need for good etiquette, but
that you should not post unnecessary information. Each reply will cause a notification to be
sent to all of the issue's participants and some of them might consider it spam.

For minor corrections or additions, try to update your posts rather than writing a new reply.
Use strike-through markdown for corrections and put updates at the bottom of your original post.

+1ing an issue or "me, too" replies will not get anything done faster.

Adding Issues
+++++++++++++

If you have a question, please read the documentation and search the issue tracker.
If you still have a question, please consider using the `Gitter chat 
<https://gitter.im/yadayada/acd_cli>`_ or sending an e-mail to 
`acd_cli@mail.com <mailto:acd_cli@mail.com>`_ instead of opening an issue.

If you absolutely must open an issue, check that you are using the latest master commit and
there is no existing issue that fits your problem (including closed and unresolved issues).
Try to reproduce the issue on another machine or ideally on another operating system, if possible.

Please provide as much possibly relevant information as you can. This should at least contain:

- your operating system and Python version, e.g. as determined by
  :code:`python3 -c 'import platform as p; print("%s\n%s" % (p.python_version(), p.platform()))'`
- the command/s you used
- what happened
- what you think should have happened instead (and maybe give a reason)

You might find the ``--verbose`` and, to a lesser extent, ``--debug`` flags helpful.

Use `code block markup <https://guides.github.com/features/mastering-markdown/>`_ for console
output, log messages, etc.

Code
----

There are no real programming guidelines as of yet. Please use function annotations for typing
like specified in PEP 3107 and, to stay 3.2-compliant, stringified `PEP 484 type hints
<https://docs.python.org/3/library/typing.html>`_ where appropriate.
The limit on line length is 100 characters.

It is a generally a good idea to explicitly announce that you are working on an issue.

Please squash your commits and add yourself to the `contributors list <docs/contributors.rst>`_
before making a pull request.

Have a look at `Github's general guide how to contribute
<https://guides.github.com/activities/contributing-to-open-source/#contributing>`_.
It is not necessary to create a feature branch, i.e. you may commit to the master branch.

There is also a `TODO <docs/TODO.rst>`_ list of some of the open tasks.

Donations
---------

You might also want to consider `making a donation
<https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id=V4V4HVSAH4VW8>`_
to further the development of acd\_cli.

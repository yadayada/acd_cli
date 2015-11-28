"""
This is a template that you can use for adding custom plugins.
"""

from . import *


class TestPlugin(Plugin):
    MIN_VERSION = '0.3.1'

    @classmethod
    def attach(cls, subparsers: argparse.ArgumentParser, log: list, **kwargs):
        """ Attaches this plugin to the top-level argparse subparser group
        :param subparsers the action subparser group
        :param log a list to put initialization log messages in
         """
        p = subparsers.add_parser('test', add_help=False)
        p.add_argument('--silent', action='store_true', default=False)
        p.set_defaults(func=cls.action)

        log.append(str(cls) + ' attached.')

    @classmethod
    def action(cls, args: argparse.Namespace) -> int:
        """ This is where the magic happens.
        Return a zero for success, a non-zero int for failure. """
        if not args.silent:
            print('This plugin works.')

        # args.cache.do_something()
        # args.acd_client.do_something()

        return 0

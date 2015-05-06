"""
This is a template that you can use for adding custom plugins. May be subject to changes in the near future.
"""

from plugins import *


class TestPlugin(Plugin):
    MIN_VERSION = '0.1.3'

    @classmethod
    def attach(cls, subparsers: argparse.ArgumentParser, log: list, **kwargs):
        """ Attaches this plugin to the argparse action subparser group
        :param subparsers the action subparser group
        :param log a list to put log messages in
         """
        p = subparsers.add_parser('test', add_help=False)
        p.add_argument('--silent', action='store_true', default=False)
        p.set_defaults(func=cls.action)

        log.append(str(cls) + ' attached.')

    @staticmethod
    def action(args: argparse.Namespace) -> int:
        """ This is where the magic happens. Return a zero for success, a non-zero int for failure. """
        if not args.silent:
            print('This plugin works.')
        return 0
from plugins import *


class StreamPlugin(Plugin):
    MIN_VERSION = '0.1.3'

    @classmethod
    def attach(cls, subparsers: argparse.ArgumentParser, log: list, **kwargs):
        p = subparsers.add_parser('stream', aliases=['st'], add_help=False)
        p.add_argument('node')
        p.set_defaults(func=cls.action)

        log.append(str(cls) + ' attached.')

    @staticmethod
    def action(args: argparse.Namespace) -> int:
        import subprocess
        import logging
        import sys
        from acd import metadata
        from cache import query

        logger = logging.getLogger(__name__)

        n = query.get_node(args.node)
        r = metadata.get_metadata(args.node)
        try:
            link = r['tempLink']
        except KeyError:
            logger.critical('Could not get temporary URL for "%s".' % n.simple_name())
            return 1

        if sys.platform == 'linux':
            subprocess.call(['mimeopen', '--no-ask', link + '#' + n.simple_name()])
        else:
            logger.critical('OS not supported.')
            return 1
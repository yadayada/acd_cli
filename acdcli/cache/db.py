import configparser
import logging
import os

from . import *
from . import format

logger = logging.getLogger(__name__)


_SETTINGS_FILENAME = 'cache.ini'

_def_conf = configparser.ConfigParser()
_def_conf['backend'] = dict(backend='sqlite')
_def_conf['sqlite'] = dict(filename='nodes.db', busy_timeout=30000, journal_mode='wal')
_def_conf['blacklist'] = dict(folders= [])

class IntegrityError(Exception):
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return repr(self.msg)

def _get_conf(path='') -> configparser.ConfigParser:
    conf = configparser.ConfigParser()
    conf.read_dict(_def_conf)

    conffn = os.path.join(path, _SETTINGS_FILENAME)
    try:
        with open(conffn) as cf:
            conf.read_file(cf)
    except OSError:
        pass

    return conf


IntegrityCheckType = dict(full=0, quick=1, none=2)


def get_cache(cache_path: str='', settings_path='', check=IntegrityCheckType['full']):
    conf = _get_conf(settings_path)
    
    import importlib
    mod = importlib.import_module('..%s.db' % conf['backend']['backend'], __name__)
    nc = mod.NodeCache(conf, cache_path, check)

    format.cache = nc
    format.init()

    return nc

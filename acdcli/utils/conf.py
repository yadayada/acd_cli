import configparser
import logging
import os

logger = logging.getLogger(__name__)


def get_conf(path, filename, default_conf: configparser.ConfigParser) \
        -> configparser.ConfigParser:
    conf = configparser.ConfigParser()
    conf.read_dict(default_conf)

    conffn = os.path.join(path, filename)
    try:
        with open(conffn) as cf:
            conf.read_file(cf)
    except OSError:
        pass

    logger.debug('configuration resulting from merging default and %s: %s' % (filename, 
        {section: dict(conf[section]) for section in conf}))

    return conf

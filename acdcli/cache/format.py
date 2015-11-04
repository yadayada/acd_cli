"""
Formatters for query Bundle iterables. Capable of ANSI-type coloring using colors defined in
:envvar:`LS_COLORS`.
"""

import os
import sys
import datetime

colors = filter(None, os.environ.get('LS_COLORS', '').split(':'))
colors = dict(c.split('=') for c in colors)
# colors is now a mapping of 'type': 'color code' or '*.ext' : 'color code'

seq_tpl = '\x1B[%sm'
res = seq_tpl % colors.get('rs', '')  # reset code
dir_fmt = seq_tpl % colors.get('di', '') + '%s' + res  # dir text
nor_fmt = seq_tpl % colors.get('no', '') + '%s' + res  # 'normal' colored text

ColorMode = dict(auto=0, always=1, never=2)


def init(color=ColorMode['auto']):
    """Disables pre-initialized coloring if never mode specified or stdout is a tty.

    :param color: the color mode to use, defaults to auto"""

    # TODO: fix tty detection
    if color == ColorMode['never'] \
            or not res \
            or (color == ColorMode['auto'] and not sys.__stdout__.isatty()):
        global get_adfixes, color_path, color_status, seq_tpl, nor_fmt
        get_adfixes = lambda _: ('', '')
        color_path = lambda x: x
        color_status = lambda x: x[0]
        seq_tpl = '%s'
        nor_fmt = '%s'


def color_file(name: str) -> str:
    """Colorizes a file name according to its file ending."""
    parts = name.split('.')
    if len(parts) > 1:
        ext = parts.pop()
        code = colors.get('*.' + ext)
        if code:
            return seq_tpl % code + name + res

    return nor_fmt % name


def color_path(path: str) -> str:
    """Colorizes a path string."""
    segments = path.split('/')
    path_segments = [dir_fmt % s for s in segments[:-1]]
    last_seg = segments[-1] if segments[-1:] else ''
    file_seg = color_file(last_seg)
    return '/'.join(path_segments + [file_seg])


def color_status(status):
    """Creates a colored one-character status abbreviation."""
    if status == 'AVAILABLE':
        return seq_tpl % '32' + status[0] + res  # green
    if status == 'TRASH':
        return seq_tpl % '31' + status[0] + res  # red


def date_str(time_: datetime.datetime) -> str:
    """Creates colored date string similar to ls -l."""
    if time_.year == datetime.date.year:
        last_seg = str(time_.year).rjust(5)
    else:
        last_seg = '{0.hour:02}:{0.minute:02}'.format(time_)
    return nor_fmt % ('{0:%b} %s %s'.format(time_) % (str(time_.day).rjust(2), last_seg))


def size_nlink_str(node, size_bytes=False):
    """Creates a right-justified size/nlinks string."""
    from acdcli.utils.progress import file_size_str

    if node.is_file():
        if not size_bytes:
            return nor_fmt % file_size_str(node.size).rjust(7)
        return nor_fmt % str(node.size).rjust(11)
    elif node.is_folder():
        return nor_fmt % str(node.nlinks).rjust(7 if not size_bytes else 11)
    return ''


class ListFormatter(object):
    def __new__(cls, bunches, **kwargs):
        return LSFormatter(bunches, **kwargs)


class LSFormatter(ListFormatter):
    """An ls-like formatter."""
    def __new__(cls, bunches, recursive=False, long=False, size_bytes=False) -> 'Generator[str]':
        is_first = True
        for bunch in bunches:
            node = bunch.node
            children = 0 if not node.is_folder() else node.children.count()
            if bunch.path is None:
                bunch.path = node.containing_folder()
            if recursive and node.is_folder() and not is_first and children > 0:
                yield ''
            yield '[{}] [{}] {}{}{}{}'.format(
                nor_fmt % node.id,
                color_status(node.status),
                (size_nlink_str(node, size_bytes=size_bytes) + ' ') if long else '',
                (date_str(node.modified) + ' ') if long else '',
                color_path(bunch.path) if node.is_folder() and children else '',
                color_path(node.simple_name())
            )
            is_first = False


class LongIDFormatter(ListFormatter):
    def __new__(cls, bunches) -> 'Generator[str]':
        for bunch in bunches:
            node = bunch.node
            if bunch.path is None:
                bunch.path = node.containing_folder()
            yield '[{}] [{}] {}{}'.format(
                nor_fmt % node.id,
                color_status(node.status),
                color_path(bunch.path),
                color_path(node.simple_name())
            )


class TreeFormatter(ListFormatter):
    """A simple tree formatter that indicates parentship by indentation
    (i.e. does not display graphical branches like :program:`tree`)."""
    def __new__(cls, bunches) -> 'Generator[str]':
        for bunch in bunches:
            pre = ''
            if bunch.depth > 0:
                pre = ' ' * 4 * bunch.depth
            yield pre + color_path(bunch.node.simple_name())


class IDFormatter(ListFormatter):
    """"""
    def __new__(cls, bunches) -> 'Generator[str]':
        for bunch in bunches:
            yield bunch.node.id


class PathFormatter(ListFormatter):
    def __new__(cls, bunches) -> 'Generator[str]':
        for bunch in bunches:
            yield bunch.node.full_path()

"""
Formatters for query Bundle iterables. Capable of ANSI-type coloring using colors defined in
:envvar:`LS_COLORS`.
"""

import os
import sys
import datetime

from .cursors import cursor

try:
    colors = filter(None, os.environ.get('LS_COLORS', '').split(':'))
    colors = dict(c.split('=') for c in colors)
    # colors is now a mapping of 'type': 'color code' or '*.ext' : 'color code'
except:
    colors = {}

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
    elif status == 'TRASH':
        return seq_tpl % '31' + status[0] + res  # red
    return status[0]


def date_str(time_: datetime.datetime) -> str:
    """Creates colored date string similar to the one in ls -l."""
    if time_.year == datetime.date.year:
        last_seg = str(time_.year).rjust(5)
    else:
        last_seg = '{0.hour:02}:{0.minute:02}'.format(time_)
    return nor_fmt % ('{0:%b} %s %s'.format(time_) % (str(time_.day).rjust(2), last_seg))


class FormatterMixin(object):
    def size_nlink_str(self, node, size_bytes=False):
        """Creates a right-justified size/nlinks string."""
        from acdcli.utils.progress import file_size_str

        if node.is_file:
            if not size_bytes:
                return nor_fmt % file_size_str(node.size).rjust(7)
            return nor_fmt % str(node.size).rjust(11)
        elif node.is_folder:
            return nor_fmt % str(self.num_children(node.id)).rjust(7 if not size_bytes else 11)
        return ''

    def file_entry(self, file, long=False, size_bytes=False) -> str:
        return '[{}] [{}] {}{}{}'.format(
            nor_fmt % file.id,
            color_status(file.status),
            (self.size_nlink_str(file, size_bytes=size_bytes) + ' ') if long else '',
            (date_str(file.modified) + ' ') if long else '',
            color_path(file.name)
        )

    def ls_format(self, folder_id, folder_path=None, recursive=False,
                  trash_only=False, trashed_children=False,
                  long=False, size_bytes=False) -> 'Generator[str]':

        if folder_path is None:
            folder_path = []

        if trash_only:
            folders, files = self.list_trashed_children(folder_id)
        else:
            folders, files = self.list_children(folder_id, trashed_children)

        if recursive:
            for file in files:
                yield self.file_entry(file, long, size_bytes)

            if files and folders:
                yield ''

        is_first = True
        for folder in folders:
            children = self.num_children(folder.id)
            if recursive and not is_first and children > 0:
                yield ''
            yield '[{}] [{}] {}{}{}{}'.format(
                nor_fmt % folder.id,
                color_status(folder.status),
                (self.size_nlink_str(folder, size_bytes=size_bytes) + ' ') if long else '',
                (date_str(folder.modified) + ' ') if long else '',
                color_path('/'.join(folder_path) + '/') if folder_path else '',
                color_path(folder.name + '/')
            )
            is_first = False

            if recursive:
                for n in self.ls_format(folder.id,
                                        [f for f in folder_path] + [folder.name],
                                        recursive, False, trashed_children, long, size_bytes):
                    yield n

        if not recursive:
            for file in files:
                yield self.file_entry(file, long, size_bytes)

    def tree_format(self, node, path, trash=False, dir_only=False,
                    depth=0, max_depth=None) -> 'Generator[str]':
        """A simple tree formatter that indicates parentship by indentation
        (i.e. does not display graphical branches like :program:`tree`)."""

        indent = ' ' * 4 * depth
        yield indent + color_path(node.simple_name)
        if max_depth is not None and depth >= max_depth:
            return

        indent += ' ' * 4
        folders, files = self.list_children(node.id, trash)
        for folder in folders:
            for line in self.tree_format(folder, '', trash, dir_only, depth + 1, max_depth):
                yield line

        if not dir_only:
            for file in files:
                yield indent + color_path(file.simple_name)

    @staticmethod
    def id_format(nodes) -> 'Generator[str]':
        for node in nodes:
            yield node.id

    def long_id_format(self, nodes) -> 'Generator[str]':
        for node in nodes:
            path = self.first_path(node.id)
            yield '[{}] [{}] {}{}'.format(
                nor_fmt % node.id,
                color_status(node.status),
                color_path(path),
                color_path(node.simple_name)
            )

    def path_format(self, nodes):
        for node in nodes:
            yield self.first_path(node.id) + node.name

"""Formatters for query bundle iterables"""


import os
import sys

colors = filter(None, os.environ.get('LS_COLORS', '').split(':'))
colors = dict(c.split('=') for c in colors)
# colors is now a mapping of 'type': 'color code' or '*.ext' : 'color code'

seq_tpl = '\x1B[%sm'
res = seq_tpl % colors.get('rs', '')  # reset code
dir_fmt = seq_tpl % colors.get('di', '') + '%s' + res  # dir text
nor_fmt = seq_tpl % colors.get('no', '') + '%s' + res  # 'normal' colored text

ColorMode = dict(auto=0, always=1, never=2)


def init(color=ColorMode['auto']):
    if color == ColorMode['never'] \
            or not res \
            or (color == ColorMode['auto'] and not sys.__stdout__.isatty()):
        global get_adfixes, color_path, color_status, nor_fmt
        get_adfixes = lambda _: ('', '')
        color_path = lambda x: x
        color_status = lambda x: x[0]
        nor_fmt = '%s'


def color_file(name: str) -> str:
    parts = name.split('.')
    if len(parts) > 1:
        ext = parts.pop()
        code = colors.get('*.' + ext)
        if code:
            return seq_tpl % code + name + res

    return nor_fmt % name


def color_path(path: str) -> str:
    segments = path.split('/')
    path_segments = [dir_fmt % s for s in segments[:-1]]
    last_seg = segments[-1] if segments[-1:] else ''
    file_seg = color_file(last_seg)
    return '/'.join(path_segments + [file_seg])


def color_status(status):
    if status == 'AVAILABLE':
        return seq_tpl % '32' + status[0] + res  # green
    if status == 'TRASH':
        return seq_tpl % '31' + status[0] + res  # red


class ListFormatter(object):
    @staticmethod
    def __new__(cls, bunches, **kwargs):
        return LSFormatter(bunches, **kwargs)


class LSFormatter(ListFormatter):
    @staticmethod
    def __new__(cls, bunches, recursive=False):
        is_first = True
        for bunch in bunches:
            node = bunch.node
            children = 0 if not node.is_folder() else len(node.children)
            if bunch.path is None:
                bunch.path = node.containing_folder()
            if recursive and node.is_folder() and not is_first and children > 0:
                yield ''
            yield '[{}] [{}] {}{}'.format(
                nor_fmt % node.id,
                color_status(node.status),
                color_path(bunch.path) if node.is_folder() and children else '',
                color_path(node.simple_name())
            )
            is_first = False


class LongIDFormatter(ListFormatter):
    @staticmethod
    def __new__(cls, bunches):
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
    @staticmethod
    def __new__(cls, bunches):
        prev = None
        for bunch in bunches:
            pre = ''
            if bunch.depth > 0:
                pre = ' ' * 4 * bunch.depth
            yield pre + color_path(bunch.node.simple_name())
            prev = bunch



class IDFormatter(ListFormatter):
    @staticmethod
    def __new__(cls, bunches):
        for bunch in bunches:
            yield bunch.node.id


class PathFormatter(ListFormatter):
    @staticmethod
    def __new__(cls, bunches):
        for bunch in bunches:
            yield bunch.node.full_path()

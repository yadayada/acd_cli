import time
import sys
from math import floor, log10
from collections import deque


class FileProgress(object):
    __slots__ = ('current', 'status', 'total')

    def __init__(self, total_sz: int, current: int=0):
        self.total = total_sz
        self.current = current
        self.status = None

    def update(self, chunk):
        self.current += chunk.__sizeof__()

    def reset(self):
        self.current = 0

    def done(self):
        self.current = self.total


class MultiProgress(object):
    """Container that accumulates multiple FileProgress objects"""

    def __init__(self):
        self._progresses = []
        self._last_inv = None
        self._last_prog = 0
        self._last_speeds = deque([0] * 10, 10)

    def end(self):
        self.print_progress()
        print()
        failed = sum(1 for s in self._progresses if s.status)
        if failed:
            print('%d file(s) failed.' % failed)

    def add(self, progress: FileProgress):
        self._progresses.append(progress)

    def print_progress(self):
        total = 0
        current = 0
        complete = 0
        for p in self._progresses:
            total += p.total
            current += p.current
            if p.total <= p.current:
                complete += 1

        if current > total:
            total = current
        self._print(total, current, len(self._progresses), complete)

    def _print(self, total_sz: int, current_sz: int, total_items: int, done: int):
        """Prints a line that includes a progress bar, total and current transfer size,
        total and done items, average speed, and ETA. Uses ANSI escape codes."""

        if not self._last_inv:
            self._last_inv = time.time()

        t = time.time()
        duration = t - self._last_inv
        speed = (current_sz - self._last_prog) / duration if duration else 0
        rate = float(current_sz) / total_sz if total_sz else 1
        self._last_speeds.append(speed)

        avg_speed = float(sum(self._last_speeds)) / len(self._last_speeds)
        eta = float(total_sz - current_sz) / avg_speed if avg_speed else 0

        self._last_inv, self._last_prog = t, current_sz

        percentage = round(rate * 100, ndigits=2) if rate <= 1 else 100
        completed = "#" * int(percentage / 4)
        spaces = " " * (25 - len(completed))
        item_width = floor(log10(total_items))
        sys.stdout.write('[%s%s] %s%% of %s  %s/%d %s  %s\x1b[K\r'
                         % (completed, spaces, ('%3.1f' % percentage).rjust(5),
                            (file_size_str(total_sz)).rjust(7),
                            str(done).rjust(item_width + 1), total_items,
                            (speed_str(avg_speed)).rjust(10), time_str(eta).rjust(7)))
        sys.stdout.flush()


def speed_str(num: int, suffix='B', time_suffix='/s') -> str:
    for unit in ['', 'K', 'M', 'G', 'T', 'P', 'E', 'Z']:
        if abs(num) < 1000.0:
            return "%3.1f%s%s%s" % (num, unit, suffix, time_suffix)
        num /= 1000.0
    return "%.1f%s%s%s" % (num, 'Y', suffix, time_suffix)


def file_size_str(num: int, suffix='B') -> str:
    for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
        if abs(num) < 1024.0:
            return "%4.0f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Yi', suffix)


def time_str(num: float) -> str:
    if num <= 0:
        return '0s'
    if num < 60:
        return '%02ds' % num
    elif num < 3600:
        seconds = num % 60 // 1
        minutes = (num - seconds) // 60
        return '%02d:%02dm' % (minutes, seconds)
    elif num <= 86400:
        minutes = num % 3600 // 60
        hours = (num - minutes) // 3600
        return '%02d:%02dh' % (hours, minutes)
    elif num <= 31536000:
        hours = num % 86400 // 3600
        days = (num - hours) // 86400
        if days >= 100:
            return '%id' % days
        return '%id %02dh' % (days, hours)
    else:
        return '>1 year'

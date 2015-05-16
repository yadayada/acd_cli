import time
import sys
from math import floor, log10
from collections import deque

from . import format


class FileProgress(object):
    status = None

    def __init__(self, total_sz: int, current: int=0):
        self.total = total_sz
        self.current = current

    def update(self, chunk):
        self.current += sys.getsizeof(chunk)

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

        self._print(total, current, len(self._progresses), complete)

    def _print(self, total_sz: int, current_sz: int, total_items: int, done: int):
        if not self._last_inv:
            self._last_inv = time.time()

        t = time.time()
        duration = t - self._last_inv
        speed = (current_sz - self._last_prog) / duration if duration else 0
        rate = float(current_sz) / total_sz if total_sz else 1
        self._last_speeds.append(speed)

        avg_speed = float(sum(self._last_speeds)) / len(self._last_speeds)

        self._last_inv, self._last_prog = t, current_sz

        percentage = round(rate * 100, ndigits=2)
        completed = "#" * int(percentage / 3)
        spaces = " " * (33 - len(completed))
        item_width = floor(log10(total_items))
        sys.stdout.write('[%s%s] %s%% of %s %s/%d %s\r'
                         % (completed, spaces, ('%3.1f' % percentage).rjust(5),
                            (format.file_size_str(total_sz)).rjust(7), str(done).rjust(item_width + 1), total_items,
                            (format.speed_str(avg_speed)).rjust(10)))
        sys.stdout.flush()
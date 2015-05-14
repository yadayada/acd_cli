import time
import sys

from . import format


class Progress:
    """line progress indicator"""
    start = None

    def __init__(self, total_size: int=0, current_size: int=0, hidden=False):
        self.total_size = total_size
        self.current_size = current_size
        self.hidden = hidden

    def __del__(self):
        if not self.hidden:
            print()

    def print_progress(self, total_sz: int, current: int):
        if not self.start:
            self.start = time.time()

        if total_sz:
            duration = time.time() - self.start
            if duration:
                speed = current / duration
            else:
                speed = 0
            if total_sz:
                rate = float(current) / total_sz
            else:
                rate = 1
            percentage = round(rate * 100, ndigits=2)
            completed = "#" * int(percentage / 3)
            spaces = " " * (33 - len(completed))
            sys.stdout.write('[%s%s] %s%% of %s, %s\r'
                             % (completed, spaces, ('%4.1f' % percentage).rjust(5),
                                (format.file_size_str(total_sz)).rjust(9), (format.speed_str(speed)).rjust(10)))
            sys.stdout.flush()

    def new_chunk(self, chunk):
        self.current_size += sys.getsizeof(chunk)
        if not self.hidden:
            self.print_progress(self.total_size, self.current_size)
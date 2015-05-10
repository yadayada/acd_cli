import time
import sys

from acdcli.utils import format


class Progress:
    """line progress indicator"""
    start = None

    # noinspection PyUnusedLocal
    def curl_ul_progress(self, total_dl_sz: int, downloaded: int, total_ul_sz: int, uploaded: int):
        self.print_progress(total_ul_sz, uploaded)

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
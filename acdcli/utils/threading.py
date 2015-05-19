import time
import logging
import queue
from threading import Thread, Event, Lock

from . import progress

_logger = logging.getLogger(__name__)


class QueuedLoader(object):
    MAX_NUM_WORKERS = 8
    MAX_RETRIES = 4

    def __init__(self, workers=1, print_progress=True, max_retries=0):
        self.workers = min(abs(workers), self.MAX_NUM_WORKERS)
        self.q = queue.Queue()
        self.halt = False
        self.exit_stat = 0
        self.stat_lock = Lock()
        self.print_progress = print_progress
        self.retries = min(abs(max_retries), self.MAX_RETRIES)

        self.mp = progress.MultiProgress()

    def _print_prog(self):
        while not self.halt:
            self.mp.print_progress()
            time.sleep(0.3)
        self.mp.end()

    def _worker_task(self, num: int):
        while True:
            try_ = 0
            f = self.q.get()
            while try_ <= self.retries:
                rr = f()
                if not rr.retry:
                    break
                f.keywords.get('pg_handler').reset()
                try_ += 1

            with self.stat_lock:
                self.exit_stat |= rr.ret
            self.q.task_done()

    def add_jobs(self, jobs: list):
        for job in jobs:
            h = job.keywords.get('pg_handler')
            self.mp.add(h)
            self.q.put(job)

    def start(self) -> int:
        _logger.info('%d jobs in queue.' % self.q.qsize())

        p = None
        print_progress = self.print_progress and self.q.qsize() > 0
        if print_progress:
            p = Thread(target=self._print_prog)
            p.daemon = True
            p.start()

        for i in range(self.workers):
            t = Thread(target=self._worker_task, args=(i,), name='worker-' + str(i))
            t.daemon = True
            t.start()

        self.q.join()
        self.halt = True
        if p:
            p.join()

        return self.exit_stat

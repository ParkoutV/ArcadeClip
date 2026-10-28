"""Bounded, ordered prefetch with deterministic worker shutdown."""
from queue import Queue, Empty, Full
from threading import Event, Thread


def prefetch(source, cancel, capacity=2):
    queue, stopped = Queue(maxsize=capacity), Event()

    def put(item):
        while not stopped.is_set() and not cancel.is_set():
            try:
                queue.put(item, timeout=.05)
                return
            except Full:
                pass

    def produce():
        try:
            for item in source:
                if stopped.is_set() or cancel.is_set():
                    break
                put((True, item))
        except BaseException as error:
            put((False, error))
        finally:
            close = getattr(source, 'close', None)
            if close:
                close()
            put((False, None))

    worker = Thread(target=produce, name='analysis-prefetch', daemon=True)
    worker.start()
    try:
        while True:
            from analysis_common import check_cancel
            check_cancel(cancel)
            try:
                ok, item = queue.get(timeout=.05)
            except Empty:
                continue
            if not ok:
                if item is not None:
                    raise item
                return
            yield item
            del item
    finally:
        stopped.set()
        worker.join()
        while not queue.empty():
            queue.get_nowait()

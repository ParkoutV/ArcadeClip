import threading
import unittest
from concurrent.futures import CancelledError
from pipeline import prefetch


class PipelineTests(unittest.TestCase):
    def test_order_and_producer_error(self):
        def source():
            yield 1
            yield 2
            raise ValueError('producer failed')
        iterator = prefetch(source(), threading.Event())
        self.assertEqual(next(iterator), 1)
        self.assertEqual(next(iterator), 2)
        with self.assertRaisesRegex(ValueError, 'producer failed'):
            next(iterator)

    def test_close_and_cancel_release_bounded_producer(self):
        for cancel_run in (False, True):
            cancel, closed = threading.Event(), threading.Event()
            produced = []
            def source():
                try:
                    for number in range(10000):
                        produced.append(number)
                        yield number
                finally:
                    closed.set()
            iterator = prefetch(source(), cancel, capacity=2)
            next(iterator)
            if cancel_run:
                cancel.set()
                with self.assertRaises(CancelledError):
                    next(iterator)
            else:
                iterator.close()
            self.assertTrue(closed.is_set())
            self.assertLessEqual(len(produced), 5)
            self.assertFalse(any(t.name == 'analysis-prefetch' for t in threading.enumerate()))

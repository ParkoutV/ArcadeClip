"""Reset evidence must split repeats without mistaking normal score progression."""
import threading
import unittest
from unittest.mock import Mock

import av
from PIL import Image

from freeplay import FreePlayObserver, ResetTracker
from profiles import validate_profile


class FreePlayTests(unittest.TestCase):
    def events(self, values):
        tracker = ResetTracker()
        for t, value in enumerate(values):
            tracker.feed(t, value)
        return tracker.events

    def test_both_reset_directions_and_no_duplicate_during_hold(self):
        self.assertEqual(self.events([10, 20, 0, 0, 0, 10, 20, 0, 0]),
                         [(1, 2, 3), (6, 7, 8)])
        self.assertEqual(self.events([100, 90, 101, 101, 101]), [(1, 2, 3)])
        self.assertEqual(self.events([100.9, 100.8, 101, 101]), [(1, 2, 3)])
        self.assertEqual(self.events([.1, .2, 0, 0]), [(1, 2, 3)])

    def test_normal_endpoint_arrival_and_initial_endpoint_do_not_split(self):
        for values in ([0, 0, 10, 50, 100, 101, 101], [101, 101, 90, 20, 0, 0],
                       [0, 0, 0], [101, 101, 101], [10, 20, 0, 21],
                       [10, 20, None, 0, 0], [10, 20, 0, None, 0]):
            with self.subTest(values=values):
                self.assertEqual(self.events(values), [])

    def test_strict_ocr_confidence_and_sampling(self):
        read = Mock(side_effect=[('10.0000%', .99), ('20.0000％', .99),
                                 ('0.0000%', .99), ('0%', .99), ('101x', .99), ('0', .5)])
        observer = FreePlayObserver(read, [0, 0, 1, 1], [20, 20], 0, 1, threading.Event())
        frame = av.VideoFrame.from_image(Image.new('RGB', (20, 20)))
        for t in (0, .5, 1, 2, 3, 4, 5):
            observer.observe(t, frame)
        self.assertEqual(read.call_count, 6)
        self.assertEqual(observer.tracker.events, [(1, 2, 3)])
        self.assertIsNone(observer.tracker.previous)

    def test_split_only_inside_recognized_candidate_with_prior_evidence(self):
        observer = FreePlayObserver(None, None, None, 0, 1, threading.Event())
        observer.tracker.events = [(1, 2, 3), (4, 5, 6), (8, 9, 10)]
        rows = observer.split([{'start': 0, 'end': 4, 'image_url': 'a.png'},
                               {'start': 4, 'end': 8, 'image_url': None},
                               {'start': 9, 'end': 12, 'image_url': 'a.png'}])
        self.assertEqual([(r['start'], r['end']) for r in rows], [(0, 2), (2, 4), (4, 8), (9, 12)])

    def test_profile_requires_boolean_and_preserves_option(self):
        profile = {'version': 1, 'name': 'test', 'size': [100, 100],
                   'regions': {'jacket': [0, 0, 1, 1]}, 'recognition': {'freeplay_resets': True}}
        self.assertTrue(validate_profile(profile)['recognition']['freeplay_resets'])
        profile['recognition']['freeplay_resets'] = 1
        with self.assertRaises(ValueError):
            validate_profile(profile)

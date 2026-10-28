"""Native D3D11 tests; opt in on an ARM64 Windows machine with video hardware."""
import os
import gc
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import av
import numpy as np
from PIL import Image
from media import frame_at
from video_sampling import samples
from gpu_image import GPUImageConverter


@unittest.skipUnless(os.environ.get('ARCADECLIP_TEST_GPU') == '1', 'Native GPU test opt-in')
class GPUImageTests(unittest.TestCase):
    def test_independent_options_and_pipeline_preserve_pixels_and_timestamps(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'options.mp4'
            self.video(path, 90)
            box = [.103, .137, .803, .837]
            expected = list(samples(path, 0, 2, .5, threading.Event(), region=box))
            for decode in (False, True):
                for convert in (False, True):
                    for pipeline in (False, True):
                        with self.subTest(decode=decode, convert=convert, pipeline=pipeline):
                            metrics = dict(decode_s=0., convert_s=0., decoded_frames=0, sample_frames=0)
                            actual = list(samples(path, 0, 2, .5, threading.Event(), region=box,
                                          gpu=decode, gpu_convert=convert, pipelined=pipeline, metrics=metrics))
                            self.assertEqual([t for t, _ in expected], [t for t, _ in actual])
                            self.assertEqual(metrics['sample_frames'], 4)
                            self.assertEqual(metrics['converter'].startswith('GPU'), convert)
                            for (_, left), (_, right) in zip(expected, actual):
                                self.assertEqual(left.size, right.size)
                                self.assertLess(np.abs(np.asarray(left).astype(float)-np.asarray(right)).mean(), 5)

    def video(self, path, rotation=0, mirror=False):
        image = Image.new('RGB', (320, 192), 'red')
        image.paste('blue', (160, 0, 320, 96))
        image.paste('green', (0, 96, 160, 192))
        image.paste('white', (160, 96, 320, 192))
        with av.open(str(path), 'w') as container:
            stream = container.add_stream('libx264', rate=30)
            stream.width, stream.height, stream.pix_fmt = 320, 192, 'yuv420p'
            stream.set_display_rotation(rotation, hflip=mirror)
            for _ in range(60):
                for packet in stream.encode(av.VideoFrame.from_image(image)):
                    container.mux(packet)
            for packet in stream.encode():
                container.mux(packet)

    def test_gpu_crop_rotation_matches_cpu_and_selection_is_sparse(self):
        with tempfile.TemporaryDirectory() as directory:
            for angle in (0, 90, 180, 270):
                path = Path(directory) / f'{angle}.mp4'
                self.video(path, angle)
                box = [.103, .137, .803, .837]
                expected = frame_at(path, 0, region=box)['image']
                metrics = dict(decode_s=0., convert_s=0., decoded_frames=0, sample_frames=0)
                count = 0
                original = GPUImageConverter.convert
                def convert(instance, *args, **kwargs):
                    nonlocal count
                    count += 1
                    return original(instance, *args, **kwargs)
                with patch.object(GPUImageConverter, 'convert', convert):
                    rows = list(samples(path, 0, 2, 1, threading.Event(), gpu=True,
                                        region=box, metrics=metrics))
                self.assertEqual(count, 2)
                self.assertEqual(metrics['sample_frames'], 2)
                self.assertGreater(metrics['decoded_frames'], 50)
                for _, actual in rows:
                    self.assertEqual(actual.size, expected.size)
                    difference = np.abs(np.asarray(actual).astype(float)-np.asarray(expected))
                    self.assertLess(difference.mean(), 5)

    def test_cancel_closes_native_converter_and_preserves_live_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'cancel.mp4'
            self.video(path)
            cancel = threading.Event()
            retained = []
            iterator = samples(path, 0, 2, 1, cancel, gpu=True,
                               on_frame=lambda seconds, frame: retained.append(frame) if not retained else None)
            first = next(iterator)[1]
            cancel.set()
            from concurrent.futures import CancelledError
            with self.assertRaises(CancelledError):
                next(iterator)
            gc.collect()
            self.assertEqual(retained[0].width, 320)
            self.assertEqual(first.size, (320, 192))
            retained.clear()
            gc.collect()

    def test_unsupported_mirror_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'mirror.mp4'
            self.video(path, mirror=True)
            with self.assertRaises(ValueError):
                list(samples(path, 0, 2, 1, threading.Event(), gpu=True))

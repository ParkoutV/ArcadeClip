"""Exercise the OCR process boundary with a deterministic stand-in worker."""
from concurrent.futures import CancelledError
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from PIL import Image
from ocr_bridge import RemoteOCR


class OCRBridgeTests(unittest.TestCase):
    def connect(self, body, cancel=None):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        script = Path(directory.name) / 'worker.py'
        script.write_text(body, encoding='utf-8')
        real_popen = subprocess.Popen
        def spawn(arguments, **options):
            return real_popen([sys.executable, '-u', str(script)], **options)
        with patch('ocr_bridge.subprocess.Popen', side_effect=spawn):
            remote = RemoteOCR(sys.executable, directory.name, cancel or threading.Event(), lambda _: None)
        self.addCleanup(remote.close)
        return remote

    def test_reuses_process_and_preserves_rgb_pixels(self):
        worker = '''import base64,json,sys
print('ARCADECLIP_OCR {"ready":true}',flush=True)
for line in sys.stdin:
    request=json.loads(line)
    assert request['size']==[2,3]
    assert base64.b64decode(request['pixels'])==bytes([255,0,0])*6
    print('ARCADECLIP_OCR '+json.dumps({'text':'player 123','score':0.99}),flush=True)
'''
        remote = self.connect(worker)
        for _ in range(2):
            self.assertEqual(remote(Image.new('RGB', (2, 3), 'red')), ('player 123', .99))
        self.assertIsNone(remote.process.poll())
        remote.close()
        self.assertIsNotNone(remote.process.poll())

    def test_cancel_terminates_waiting_worker(self):
        cancel = threading.Event()
        remote = self.connect('import time\nprint(\'ARCADECLIP_OCR {"ready":true}\',flush=True)\ntime.sleep(30)', cancel)
        timer = threading.Timer(.1, cancel.set)
        timer.start()
        self.addCleanup(timer.join)
        with self.assertRaises(CancelledError):
            remote(Image.new('RGB', (2, 3)))
        self.assertIsNotNone(remote.process.poll())

    def test_worker_failure_is_reported_without_waiting_forever(self):
        remote = self.connect('print(\'ARCADECLIP_OCR {"ready":true}\',flush=True)\ninput()\nraise SystemExit(3)')
        with self.assertRaisesRegex(RuntimeError, 'exited'):
            remote(Image.new('RGB', (2, 3)))

    def test_initialization_error(self):
        with self.assertRaisesRegex(RuntimeError, 'model missing'):
            self.connect('print(\'ARCADECLIP_OCR {"error":"model missing"}\',flush=True)')

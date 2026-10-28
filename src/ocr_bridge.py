"""Image-only IPC to the isolated x64 OCR runtime in Windows bundles."""
import base64
from concurrent.futures import CancelledError
import json
import logging
from pathlib import Path
import queue
import subprocess
import threading
import weakref

PREFIX = 'ARCADECLIP_OCR '


def bundled_worker():
    root = Path(__file__).resolve().parent.parent
    manifest = root / 'portable-runtime.json'
    if not manifest.is_file():
        manifest = root / 'arm64-portable.json'  # Existing ARM64 installations.
    if not manifest.is_file():
        return None
    path = (root / json.loads(manifest.read_text())['ocr_python']).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise RuntimeError('Bundled OCR runtime is missing or invalid.')
    return path


def _stop(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    for stream in (process.stdin, process.stdout):
        if stream:
            stream.close()


def _listen(stream, responses):
    try:
        for line in stream:
            if line.startswith(PREFIX):
                responses.put(json.loads(line[len(PREFIX):]))
            else:
                logging.debug('OCR worker: %s', line.rstrip())
    except (OSError, ValueError) as error:
        responses.put({'error': str(error)})
    finally:
        responses.put({'error': 'OCR worker exited unexpectedly.'})


class RemoteOCR:
    def __init__(self, python, directory, cancel, report):
        self.cancel = cancel
        self.responses = queue.Queue()
        self.process = subprocess.Popen(
            [str(python), '-u', str(Path(__file__).with_name('ocr_worker.py')), str(directory)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding='utf-8', bufsize=1,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.finalizer = weakref.finalize(self, _stop, self.process)
        threading.Thread(target=_listen, args=(self.process.stdout, self.responses), daemon=True).start()
        try:
            while True:
                response = self._receive()
                if response.get('ready'):
                    break
                if 'progress' in response:
                    report(response['progress'])
        except BaseException:
            self.close()
            raise

    def close(self):
        self.finalizer()

    def _receive(self):
        while True:
            if self.cancel.is_set():
                self.close()
                raise CancelledError()
            try:
                response = self.responses.get(timeout=.1)
            except queue.Empty:
                continue
            if 'error' in response:
                raise RuntimeError(response['error'])
            return response

    def __call__(self, image):
        if self.cancel.is_set():
            self.close()
            raise CancelledError()
        image = image.convert('RGB')
        request = {'size': image.size, 'pixels': base64.b64encode(image.tobytes()).decode('ascii')}
        try:
            self.process.stdin.write(json.dumps(request) + '\n')
            self.process.stdin.flush()
            response = self._receive()
            return response['text'], float(response['score'])
        except BaseException:
            self.close()
            raise

"""Local FFmpeg publishers verify actual RTMP/SRT ingest and stop/EOF handling."""
from pathlib import Path
import argparse
import faulthandler
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import stream_ingest
from sources import _media_duration, find_tool


def verify(protocol, manual_stop):
    ffmpeg = find_tool('ffmpeg')
    with socket.socket(type=socket.SOCK_DGRAM if protocol == 'srt' else socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    info = stream_ingest.obs_connection_info(protocol, '127.0.0.1', port, 'test-stream')
    cancel, stop = threading.Event(), threading.Event()
    errors, results = [], []
    with tempfile.TemporaryDirectory(prefix='ingest-check-') as tmp:
        part = Path(tmp) / 'received.ts'
        def receive():
            try:
                results.append(stream_ingest._listen_part(ffmpeg, info, part, cancel, lambda _: None,
                                                         idle_timeout=15, stop_event=stop))
            except BaseException as error:
                errors.append(error)
        thread = threading.Thread(target=receive)
        thread.start()
        time.sleep(1)
        target = info['server_url'] + '/test-stream' if protocol == 'rtmp' else info['server_url']
        args = [ffmpeg, '-hide_banner', '-v', 'error', '-re', '-f', 'lavfi', '-i',
                'testsrc2=size=160x90:rate=10', '-f', 'lavfi', '-i', 'sine=frequency=440',
                '-t', '30' if manual_stop else '9', '-c:v', 'libx264', '-preset', 'ultrafast',
                '-g', '10', '-c:a', 'aac', '-f', 'flv' if protocol == 'rtmp' else 'mpegts', target]
        options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
        try:
            with subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL, **options) as sender:
                try:
                    deadline = time.monotonic() + 20
                    while time.monotonic() < deadline and not errors:
                        if part.is_file() and part.stat().st_size > 0:
                            break
                        time.sleep(.1)
                    if errors:
                        raise errors[0]
                    assert part.is_file() and part.stat().st_size > 0, 'No bytes received'
                    before = part.stat().st_size
                    time.sleep(1)
                    assert part.stat().st_size > before, 'File did not grow while publisher was live'
                    if manual_stop:
                        stop.set()
                    thread.join(15)
                    assert not thread.is_alive(), 'Receiver failed to finish after stop/EOF'
                    if errors:
                        raise errors[0]
                    assert results == [True], results
                    duration = _media_duration(part)
                    if not manual_stop:
                        assert abs(duration - 9) < .3, f'Tail lost at publisher EOF: {duration:.2f}s'
                    import av
                    with av.open(str(part)) as media:
                        assert next(media.decode(video=0), None) is not None
                    with av.open(str(part)) as media:
                        assert next(media.decode(audio=0), None) is not None
                    print(f'{protocol} {"manual stop" if manual_stop else "publisher EOF"}: '
                          f'grew during broadcast, decoded A/V, {duration:.2f}s', flush=True)
                finally:
                    if sender.poll() is None:
                        sender.kill()
                    sender.wait(timeout=5)
        finally:
            cancel.set()
            thread.join(5)


def verify_hls():
    ffmpeg = find_tool('ffmpeg')
    cancel, stop = threading.Event(), threading.Event()
    errors = []
    with tempfile.TemporaryDirectory(prefix='hls-ingest-check-') as tmp:
        root = Path(tmp)
        class QuietHandler(SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=tmp))
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        args = [ffmpeg, '-v', 'error', '-re', '-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=10',
                '-f', 'lavfi', '-i', 'sine=frequency=440', '-t', '35', '-c:v', 'libx264',
                '-preset', 'ultrafast', '-g', '10', '-c:a', 'aac', '-f', 'hls', '-hls_time', '1',
                '-hls_list_size', '20', '-hls_flags', 'omit_endlist', str(root / 'live.m3u8')]
        options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
        receiver = None
        try:
            with subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL, **options) as publisher:
                try:
                    deadline = time.monotonic() + 15
                    while len(list(root.glob('*.ts'))) < 6 and time.monotonic() < deadline:
                        time.sleep(.1)
                    assert len(list(root.glob('*.ts'))) >= 6
                    fmt = dict(url=f'http://127.0.0.1:{server.server_port}/live.m3u8',
                               protocol='m3u8_native', vcodec='h264', acodec='aac')
                    path = root / 'recorded.mkv'
                    def receive():
                        try:
                            # Test transport is loopback HTTP; production requires verified HTTPS.
                            with patch.object(stream_ingest, '_youtube_live_inputs', return_value=[fmt]), \
                                 patch.object(stream_ingest, 'ffmpeg_https_args', return_value=[]):
                                stream_ingest._receive_youtube_part({}, path, cancel, lambda _: None, stop)
                        except BaseException as error:
                            errors.append(error)
                    receiver = threading.Thread(target=receive)
                    receiver.start()
                    deadline = time.monotonic() + 15
                    while time.monotonic() < deadline and not errors:
                        if path.exists() and path.stat().st_size > 1000:
                            break
                        time.sleep(.1)
                    if errors:
                        raise errors[0]
                    assert path.exists() and path.stat().st_size > 1000
                    size = path.stat().st_size
                    time.sleep(2)
                    assert path.stat().st_size > size
                    stop.set()
                    receiver.join(8)
                    assert not receiver.is_alive()
                    if errors:
                        raise errors[0]
                    import av
                    with av.open(str(path)) as media:
                        frames = list(media.decode(video=0))
                    with av.open(str(path)) as media:
                        assert next(media.decode(audio=0), None) is not None
                    assert len(frames) > 10
                    # A live-edge capture must exclude the six seconds already published.
                    published = len(list(root.glob('*.ts')))
                    assert len(frames) / 10 < published - 3, (len(frames), published)
                    print(f'hls live edge: file grew, decoded {len(frames)} video frames and audio, '
                          'excluded earlier broadcast segments', flush=True)
                finally:
                    stop.set()
                    if receiver:
                        receiver.join(8)
                    if publisher.poll() is None:
                        publisher.kill()
                    publisher.wait(timeout=5)
        finally:
            server.shutdown()
            server.server_close()
            server_thread.join(3)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--tools', type=Path)
    parser.add_argument('--hls-only', action='store_true')
    args = parser.parse_args()
    if args.tools:
        os.environ['PATH'] = str(args.tools.resolve()) + os.pathsep + os.environ.get('PATH', '')
    faulthandler.dump_traceback_later(90, exit=True)
    if not args.hls_only:
        for protocol in ('rtmp', 'srt'):
            for manual in (True, False):
                verify(protocol, manual)
    verify_hls()
    faulthandler.cancel_dump_traceback_later()

"""Exercise the shipped runtime, media pipeline, Qt playback and optional real OCR."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--bundle', type=Path, required=True)
parser.add_argument('--ocr', action='store_true')
args = parser.parse_args()
BUNDLE = args.bundle.resolve()
ARCH = json.loads((BUNDLE / 'portable-runtime.json').read_text())['architecture']
sys.path.insert(0, str(BUNDLE / 'src'))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
ctypes.windll.kernel32.SetErrorMode(0x8003)
sys.stdout.reconfigure(encoding='utf-8')


def main():
    from architecture import process_architecture
    assert process_architecture() == ARCH
    assert Path(sys.executable).resolve() == (BUNDLE / 'runtime/python.exe').resolve()
    import av
    from PIL import Image, ImageDraw, ImageFont
    from export import export_clips
    from media import frame_at
    from sources import find_tool
    from text_recognition import make_ocr
    from PySide6.QtCore import QTimer, QUrl
    from PySide6.QtMultimedia import QMediaPlayer, QVideoSink
    from PySide6.QtWidgets import QApplication
    output = ROOT / '.validation-data' / ARCH
    output.mkdir(parents=True, exist_ok=True)
    def run(command):
        result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)
        assert result.returncode == 0, (command, result.returncode, result.stderr)
        return result.stdout
    versions = {name: run([find_tool(name), '--version' if name == 'deno' else '-version']).splitlines()[0]
                for name in ('ffmpeg', 'ffprobe', 'deno')}
    source = output / 'source.mp4'
    run([find_tool('ffmpeg'), '-y', '-v', 'error', '-f', 'lavfi', '-i',
         'testsrc2=size=320x180:rate=30:duration=3', '-f', 'lavfi', '-i',
         'sine=frequency=440:sample_rate=48000:duration=3', '-c:v', 'libx264',
         '-preset', 'ultrafast', '-c:a', 'aac', str(source)])
    image = frame_at(source, .5)['image']
    assert image.size == (320, 180)
    for mode in ('fast', 'accurate'):
        result = export_clips([{'source': str(source), 'start': .5, 'end': 2.0}],
                              output / mode, threading.Event(), lambda _: None, mode=mode)
        assert not result['failed'] and len(result['saved']) == 1, result
        with av.open(result['saved'][0]) as container:
            assert next(container.decode(video=0)).width == 320
    print(ARCH + ' decode, copy, H.264/AAC export: passed', flush=True)
    application = QApplication([])
    player, sink = QMediaPlayer(), QVideoSink()
    frames, errors = [], []
    player.setVideoSink(sink)
    sink.videoFrameChanged.connect(lambda frame: frames.append(frame.isValid()))
    player.errorOccurred.connect(lambda code, text: errors.append(text))
    player.setSource(QUrl.fromLocalFile(str(source)))
    player.play()
    QTimer.singleShot(3000, application.quit)
    application.exec()
    player.stop()
    assert any(frames) and not errors, (frames, errors)
    print(ARCH + ' Qt FFmpeg video playback: passed', flush=True)
    ocr = None
    if args.ocr:
        read = make_ocr(output / 'data', threading.Event(), print)
        try:
            image = Image.new('RGB', (500, 80), 'white')
            ImageDraw.Draw(image).text((8, 8), 'PLAYER 12345', font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 48), fill='black')
            text, confidence = read(image)
            assert '12345' in text and confidence > .5, (text, confidence)
            ocr = {'text': text, 'confidence': confidence}
            print('Native OCR on ' + ARCH + ':', ocr, flush=True)
        finally:
            if hasattr(read, 'close'):
                read.close()
    versions['python'] = sys.version
    versions['qt_video_frames'] = len(frames)
    versions['ocr'] = ocr
    (output / 'smoke-result.json').write_text(json.dumps(versions, indent=2))
    return 0


if __name__ == '__main__':
    code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)

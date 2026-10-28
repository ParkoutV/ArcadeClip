"""Visible native preview smoke; run using the bundled ARM64 Python.

python run/verify_preview.py VIDEO --output .validation-data/preview --seconds 5
Uses repository sources unless --bundle is supplied. Does not touch user settings.
"""
import argparse
import ctypes
import json
import os
from pathlib import Path
import platform
import sys
import time

parser = argparse.ArgumentParser()
parser.add_argument('video', type=Path)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--seconds', type=float, default=5)
parser.add_argument('--bundle', type=Path)
args = parser.parse_args()
if os.name == 'nt':
    # A failing diagnostic must return its native exit status, not leave a modal
    # Windows Error Reporting dialog blocking the user's desktop.
    ctypes.windll.kernel32.SetErrorMode(0x8003)
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str((args.bundle or root) / 'src'))
os.environ.setdefault('QSG_INFO', '1')
from PySide6.QtCore import QTimer, QPointF
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtCore import QPoint, Qt
from preview import Preview

app = QApplication([])
preview = Preview()
preview.resize(1100, 720)
preview.show()
frames = []
errors = []
preview.frameChanged.connect(lambda: frames.append((time.perf_counter(), preview.frame_time)))
preview.player.errorOccurred.connect(lambda code, message: errors.append(message))
preview.load(args.video.resolve())
preview.set_regions({'jacket': [.3, .3, .6, .6]})
preview.set_region_kind('jacket')
preview.player.play()
started = time.perf_counter()

def manipulate():
    anchor = QPointF(preview.canvas.rect().center())
    before = preview.canvas.normalized_point(anchor)
    preview.canvas.zoom(1.5, anchor)
    assert preview.canvas.normalized_point(anchor) == before
    preview.canvas.pan += QPointF(30, 20)
    preview.canvas.update()
    rect = preview.canvas.video_rect()
    start = QPoint(round(rect.x() + rect.width() * .4), round(rect.y() + rect.height() * .4))
    end = QPoint(round(rect.x() + rect.width() * .6), round(rect.y() + rect.height() * .6))
    QTest.mousePress(preview.canvas, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseRelease(preview.canvas, Qt.MouseButton.LeftButton, pos=end)
    assert all(abs(a-b) < .005 for a, b in zip(preview.regions['jacket'], [.4, .4, .6, .6]))
    preview.player.play()

def finish():
    preview.player.pause()
    elapsed = time.perf_counter() - started
    args.output.mkdir(parents=True, exist_ok=True)
    widget = preview.canvas.video_widget
    result = {
        'architecture': platform.machine(), 'platform': app.platformName(),
        'renderer': 'quick' if widget else 'software',
        'graphics_api': str(widget.quickWindow().rendererInterface().graphicsApi()) if widget else None,
        'elapsed': elapsed, 'frames': len([v for _, v in frames if v is not None]),
        'last_pts': preview.frame_time, 'cpu_snapshots': preview.canvas.snapshot_count,
        'width': preview.canvas.image_size.width(), 'height': preview.canvas.image_size.height(),
        'errors': errors, 'regions': preview.regions,
    }
    # Read back only for the test artifact, after measuring normal playback.
    if widget:
        widget.grabFramebuffer().save(str(args.output / 'gpu-frame.png'))
    preview.grab().save(str(args.output / 'preview.png'))
    (args.output / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result), flush=True)
    preview.clear()
    preview.close()
    app.exit(0 if result['frames'] > 10 and not errors and widget and result['cpu_snapshots'] == 0 else 1)

QTimer.singleShot(1500, manipulate)
QTimer.singleShot(round(args.seconds * 1000), finish)
sys.exit(app.exec())

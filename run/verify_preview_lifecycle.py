"""Native GPU orientation, source-switch and teardown regression smoke."""
import ctypes
import os
from pathlib import Path
import sys
import time

if os.name == 'nt':
    ctypes.windll.kernel32.SetErrorMode(0x8003)
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'src'))
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtMultimedia import QVideoFrame, QtVideo
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from preview import Preview
from profile_panel import ProfilePanel

app = QApplication([])
app.setQuitOnLastWindowClosed(False)
source = root / '.validation-data/preview-1080p60.mp4'

def wait_for(condition, seconds=5):
    deadline = time.monotonic() + seconds
    while not condition() and time.monotonic() < deadline:
        QTest.qWait(20)
    assert condition(), 'Native preview deadline exceeded'

for cycle in range(4):
    preview = Preview()
    panel = ProfilePanel(preview)
    panel.name.setText('Lifecycle check')
    preview.resize(900, 600)
    preview.show()
    panel.show()
    assert preview.canvas.video_widget is not None
    try:
        for switch in range(3):
            preview.load(source)
            preview.set_regions({'jacket': [.25, .25, .75, .75]})
            panel.kind.setCurrentIndex(panel.kind.findData('jacket'))
            preview.player.play()
            wait_for(lambda: preview.frame_time is not None and preview.frame_time > .1)
            panel.hide()
            count = preview.canvas.snapshot_count
            QTest.qWait(100)
            assert preview.canvas.snapshot_count == count
            panel.show()
        preview.clear()
        # Check the renderer against the CPU orientation contract using colored
        # quadrants, presentation rotation and mirroring.
        image = QImage(160, 80, QImage.Format.Format_RGB32)
        for y in range(80):
            for x in range(160):
                image.setPixelColor(x, y, Qt.GlobalColor.red if x < 80 else Qt.GlobalColor.blue)
        for rotation in (QtVideo.Rotation.None_, QtVideo.Rotation.Clockwise90,
                         QtVideo.Rotation.Clockwise180, QtVideo.Rotation.Clockwise270):
            for mirrored in (False, True):
                frame = QVideoFrame(image)
                frame.setRotation(rotation)
                frame.setMirrored(mirrored)
                preview.canvas.set_frame(frame)
                preview.canvas.video_sink.setVideoFrame(frame)
                QTest.qWait(50)
                expected = preview.canvas.image
                rendered = preview.canvas.video_widget.grabFramebuffer()
                rect = preview.canvas.video_rect()
                scale = rendered.width() / preview.canvas.width()
                for u, v in ((.25, .25), (.75, .25), (.25, .75), (.75, .75)):
                    a = expected.pixelColor(int(u * expected.width()), int(v * expected.height()))
                    b = rendered.pixelColor(round((rect.x()+u*rect.width())*scale),
                                            round((rect.y()+v*rect.height())*scale))
                    assert abs(a.red()-b.red()) < 12 and abs(a.blue()-b.blue()) < 12, (rotation, mirrored, a, b)
        # Close while both media players are active, not only after an idle test.
        preview.load(source)
        preview.player.play()
        wait_for(lambda: preview.frame_time is not None)
    finally:
        panel.release()
        panel.close()
        preview.close()
        panel.deleteLater()
        preview.deleteLater()
        QTest.qWait(100)
    print(f'cycle {cycle + 1}: source switches, orientation/mirror, hidden crops, close OK', flush=True)
print('GPU_LIFECYCLE_OK', flush=True)

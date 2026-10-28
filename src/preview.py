"""Video playback and normalized recognition-region editing."""
from i18n import tr
import math
import os
from pathlib import Path

from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, QUrl, Signal, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QTransform
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink, QVideoFrame
from PySide6.QtWidgets import QApplication, QComboBox, QHBoxLayout, QLabel, QPushButton, QSlider, QProxyStyle, QStyle, QVBoxLayout, QWidget


REGIONS = {"jacket": (tr('자켓'), "#58c4ef"), "achievement": (tr('1P 달성률'), "#ffc857"),
           "player": (tr('1P 이름'), "#e986c5"), "player2": (tr('2P 이름'), "#a9df73"),
           "achievement2": (tr('2P 달성률'), "#b6a2ff")}


class SeekSliderStyle(QProxyStyle):
    def styleHint(self, hint, option=None, widget=None, returnData=None):
        if hint == QStyle.StyleHint.SH_Slider_AbsoluteSetButtons:
            return (Qt.MouseButton.LeftButton | Qt.MouseButton.MiddleButton).value
        return super().styleHint(hint, option, widget, returnData)


class _VideoOverlay(QWidget):
    """Widget annotations above the GPU surface, without intercepting input."""

    def __init__(self, canvas):
        super().__init__(canvas)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)

    def paintEvent(self, event):
        self.parent().paint_canvas(QPainter(self), video=False)


class VideoCanvas(QWidget):
    regionChanged = Signal(str, object)
    editStarted = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._image = QImage()
        self._frame = QVideoFrame()
        self.image_size = QSize()
        self.snapshot_count = 0
        self.video_widget = None
        self.video_sink = None
        self.overlay = None
        self.regions = {}
        self.kind = ""
        self.show_regions = True
        self.offset_box = None
        self._start = None
        self._end = None
        self.zoom_scale = 1.
        self.pan = QPointF()
        self._pan_start = None
        self._pan_button = Qt.MouseButton.NoButton
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setToolTip(tr('Ctrl + 드래그 또는 오른쪽 버튼 드래그: 영상 화면 이동\nCtrl + 휠, Ctrl + +, Ctrl + −: 확대·축소\nCtrl + 휠 버튼 클릭, Ctrl + 0: 영상 맞춤'))
        self.setMinimumSize(240, 180)
        self.setAccessibleName(tr('영상 미리보기 및 인식 영역'))
        self.controls_hint = QLabel(tr("드래그: 영역 지정   Ctrl + 드래그 또는 오른쪽 버튼 드래그: 영상 화면 이동\nCtrl + 휠: 확대·축소   Ctrl + 휠 버튼 클릭: 영상 맞춤"), self)
        self.controls_hint.setWordWrap(True)
        self.controls_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.controls_hint.setStyleSheet("background: rgba(16,20,27,205); color: white; font-size: 16px; padding: 8px; border-radius: 8px;")
        self.controls_hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.controls_hint.hide()
        QApplication.instance().installEventFilter(self)

    def enable_video(self):
        """Use Qt's GPU renderer; keep headless/software execution available."""
        if (os.environ.get("ARCADECLIP_PREVIEW_RENDERER") == "software"
                or QApplication.platformName() in ("offscreen", "minimal")):
            return
        from PySide6.QtQuickWidgets import QQuickWidget
        widget = QQuickWidget(self)
        widget.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        widget.setSource(QUrl.fromLocalFile(str(Path(__file__).parent / "assets/preview.qml")))
        if widget.status() == QQuickWidget.Status.Error:
            import logging
            logging.getLogger(__name__).warning("GPU preview unavailable: %s", widget.errors())
            widget.deleteLater()
            return
        self.video_widget = widget
        self.video_sink = widget.rootObject().property("videoSink")
        self.overlay = _VideoOverlay(self)
        widget.setGeometry(self.rect())
        self.overlay.setGeometry(self.rect())
        widget.show()
        self.overlay.show()
        self.controls_hint.raise_()

    @property
    def image(self):
        """Materialize a CPU snapshot only when a consumer actually needs pixels."""
        if self._image.isNull() and self._frame.isValid():
            image = self._frame.toImage()
            image = image.transformed(QTransform().rotate(self._frame.rotation().value))
            if self._frame.mirrored():
                image = image.mirrored(True, False)
            self._image = image
            self.snapshot_count += 1
        return self._image

    def set_frame(self, frame):
        previous_size = self.image_size
        self._frame = QVideoFrame(frame)
        self._image = QImage()
        size = frame.surfaceFormat().viewport().size()
        if size.isEmpty():
            size = frame.size()
        rotation = frame.surfaceFormat().rotation().value + frame.rotation().value
        self.image_size = size.transposed() if rotation % 180 else size
        # VideoOutput schedules its own GPU rendering. Static annotations do not
        # need a QWidget repaint for each decoded frame.
        if self.video_widget is None or self.image_size != previous_size:
            self.update()

    def update(self, *args):
        if self.video_widget is not None:
            rect = self.video_rect()
            root = self.video_widget.rootObject()
            for key, value in (("videoX", rect.x()), ("videoY", rect.y()),
                               ("videoWidth", rect.width()), ("videoHeight", rect.height())):
                if root.property(key) != value:
                    root.setProperty(key, value)
            self.overlay.update()
        super().update(*args)

    def release(self):
        """Stop watching the application's events.

        An application-wide filter is held by the application, which would keep this
        widget and everything it owns alive for the rest of the run.
        """
        QApplication.instance().removeEventFilter(self)
        self.set_image(QImage())

    def closeEvent(self, event):
        self.release()
        super().closeEvent(event)

    def update_cursor(self, ctrl=None):
        if ctrl is None:
            ctrl = bool(QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier)
        self.setCursor(Qt.CursorShape.ClosedHandCursor if self._pan_start is not None else
                       Qt.CursorShape.OpenHandCursor if ctrl else
                       Qt.CursorShape.CrossCursor if self.kind else Qt.CursorShape.ArrowCursor)

    def eventFilter(self, watched, event):
        if (event.type() in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease)
                and isinstance(watched, QWidget) and watched.window() is self.window()
                and event.key() == Qt.Key.Key_Control):
            self.update_cursor(event.type() == QEvent.Type.KeyPress)
        # Not super(): delegating from a filter installed on the application re-enters
        # the filter chain, and with one canvas per window that nests until it breaks.
        return False

    def enterEvent(self, event):
        self.update_cursor()
        super().enterEvent(event)

    def resizeEvent(self, event):
        if self.video_widget is not None:
            self.video_widget.setGeometry(self.rect())
            self.overlay.setGeometry(self.rect())
            self.update()
        self.controls_hint.setFixedWidth(max(1, self.width()-28))
        self.controls_hint.adjustSize()
        self.controls_hint.move(14, max(0, self.height()-self.controls_hint.height()-12))
        super().resizeEvent(event)

    def video_rect(self):
        if self.image_size.isEmpty():
            return QRectF()
        size = self.image_size.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        width, height = size.width() * self.zoom_scale, size.height() * self.zoom_scale
        return QRectF((self.width() - width) / 2 + self.pan.x(),
                      (self.height() - height) / 2 + self.pan.y(), width, height)

    def reset_view(self):
        self.zoom_scale, self.pan = 1., QPointF()
        self._pan_start = None
        self._pan_button = Qt.MouseButton.NoButton
        self.update_cursor()
        self.update()

    def zoom(self, factor, anchor=None):
        if self.image_size.isEmpty():
            return
        anchor = anchor or QPointF(self.rect().center())
        point = self.normalized_point(anchor)
        self.zoom_scale = max(1., min(12., self.zoom_scale * factor))
        rect = self.video_rect()
        self.pan += anchor - QPointF(rect.x() + point.x() * rect.width(), rect.y() + point.y() * rect.height())
        if self.zoom_scale == 1:
            self.pan = QPointF()
        self.update()

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom(1.25 ** (event.angleDelta().y() / 120), event.position())
            event.accept()
        else:
            event.ignore()

    def keyPressEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.key() in (Qt.Key.Key_Plus, Qt.Key.Key_Equal, Qt.Key.Key_Minus):
                self.zoom(.8 if event.key() == Qt.Key.Key_Minus else 1.25)
                return
            if event.key() == Qt.Key.Key_0:
                self.reset_view()
                return
        super().keyPressEvent(event)

    def normalized_point(self, point):
        rect = self.video_rect()
        if rect.isEmpty():
            return None
        return QPointF(max(0., min(1., (point.x() - rect.x()) / rect.width())),
                       max(0., min(1., (point.y() - rect.y()) / rect.height())))

    def set_image(self, image):
        self._frame = QVideoFrame()
        self._image = image
        self.image_size = image.size()
        if self.video_sink is not None:
            self.video_sink.setVideoFrame(QVideoFrame(image) if not image.isNull() else QVideoFrame())
        self.update()

    def set_regions(self, regions):
        checked = {}
        for kind, box in regions.items():
            if kind not in REGIONS or len(box) != 4:
                raise ValueError(tr('인식 영역 형식이 올바르지 않습니다.'))
            x0, y0, x1, y1 = map(float, box)
            if not all(math.isfinite(v) for v in (x0, y0, x1, y1)) or not (
                    0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
                raise ValueError(tr('인식 영역은 영상 안의 사각형이어야 합니다.'))
            checked[kind] = [x0, y0, x1, y1]
        self.regions = checked
        self.update()

    def paintEvent(self, event):
        if self.video_widget is None:
            self.paint_canvas(QPainter(self), video=True)

    def paint_canvas(self, painter, *, video):
        if video:
            painter.fillRect(self.rect(), QColor("#10141b"))
        rect = self.video_rect()
        if rect.isEmpty():
            painter.setPen(QColor("#adb7c5"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, tr('영상을 선택하세요'))
            return
        if video:
            painter.drawImage(rect, self.image)
        if not self.show_regions:
            return
        def draw_label(point, text):
            painter.save()
            font = painter.font()
            font.setPointSize(12)
            font.setBold(True)
            painter.setFont(font)
            metrics = painter.fontMetrics()
            label_rect = QRectF(point.x()+4, point.y()+4, metrics.horizontalAdvance(text)+12, metrics.height()+6)
            painter.fillRect(label_rect, QColor(0, 0, 0, 195))
            painter.setPen(QColor("white"))
            painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, text)
            painter.restore()
        boxes = dict(self.regions)
        if self._start is not None and self._end is not None:
            boxes[self.kind] = self._drag_box()
        for kind, (x0, y0, x1, y1) in boxes.items():
            label, color = REGIONS[kind]
            box = QRectF(rect.x() + x0 * rect.width(), rect.y() + y0 * rect.height(),
                         (x1 - x0) * rect.width(), (y1 - y0) * rect.height())
            painter.setPen(QPen(QColor(color), 2))
            painter.drawRect(box)
            draw_label(box.topLeft(), label)

        if self.offset_box:
            x0, y0, x1, y1 = self.offset_box
            box = QRectF(rect.x() + x0 * rect.width(), rect.y() + y0 * rect.height(),
                         (x1 - x0) * rect.width(), (y1 - y0) * rect.height())
            painter.setPen(QPen(QColor("#70ef90"), 3, Qt.PenStyle.DashLine))
            painter.drawRect(box)
            draw_label(box.topLeft() + QPointF(0, 28), tr('보정된 자켓'))

    def _drag_box(self):
        return [min(self._start.x(), self._end.x()), min(self._start.y(), self._end.y()),
                max(self._start.x(), self._end.x()), max(self._start.y(), self._end.y())]

    def mousePressEvent(self, event):
        self.setFocus()
        if self._pan_start is not None or self._start is not None:
            return
        if event.button() == Qt.MouseButton.RightButton or (
                event.button() == Qt.MouseButton.LeftButton
                and event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self._pan_start = event.position()
            self._pan_button = event.button()
            self.update_cursor()
            return
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.button() == Qt.MouseButton.MiddleButton:
                self.reset_view()
            return
        if event.button() != Qt.MouseButton.LeftButton or not self.kind:
            return
        if not self.video_rect().contains(event.position()):
            return
        self.editStarted.emit()
        self._start = self._end = self.normalized_point(event.position())
        self.update()

    def mouseMoveEvent(self, event):
        if self._pan_start is not None:
            self.pan += event.position() - self._pan_start
            self._pan_start = event.position()
            self.update()
            return
        if self._start is not None:
            self._end = self.normalized_point(event.position())
            self.update()

    def mouseReleaseEvent(self, event):
        if self._pan_start is not None:
            if event.button() != self._pan_button:
                return
            self.pan += event.position() - self._pan_start
            self._pan_start = None
            self._pan_button = Qt.MouseButton.NoButton
            self.update_cursor(bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier))
            self.update()
            return
        if self._start is None or event.button() != Qt.MouseButton.LeftButton:
            return
        self._end = self.normalized_point(event.position())
        box = self._drag_box()
        self._start = self._end = None
        if ((box[2] - box[0]) * self.image_size.width() >= 2
                and (box[3] - box[1]) * self.image_size.height() >= 2):
            self.regions[self.kind] = box
            self.regionChanged.emit(self.kind, box[:])
        self.update()


class Preview(QWidget):
    regionChanged = Signal(str, object)
    frameChanged = Signal()
    seekStarted = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.audio.setVolume(.7)
        self.canvas = VideoCanvas(self)
        self.canvas.enable_video()
        self.frame_time = None
        self._generation = 0
        self._exact_frame = False
        self.fallback_duration = 0
        self._priming = False
        self.sink = None
        self._frame_slot = None
        self._pending_seek = None
        self.seek_timer = QTimer(self)
        self.seek_timer.setSingleShot(True)
        self.seek_timer.setInterval(40)
        self.seek_timer.timeout.connect(self.flush_seek)
        self.play_button = QPushButton(tr('재생'))
        self.play_button.setFixedWidth(90)
        self.play_button.clicked.connect(self.toggle_playback)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setAccessibleName(tr('영상 재생 위치'))
        self.seek_style = SeekSliderStyle()
        self.seek_style.setParent(self.slider)
        self.slider.setStyle(self.seek_style)
        self.slider.actionTriggered.connect(self._seek_slider)
        self.time_label = QLabel("00:00:00 / 00:00:00")
        controls = QHBoxLayout()
        controls.addWidget(self.play_button)
        controls.addWidget(self.slider, 1)
        controls.addWidget(self.time_label)
        self.speed_combo = QComboBox()
        self.speed_combo.setMinimumWidth(78)
        self.speed_combo.setAccessibleName(tr('재생 배속'))
        for rate in (.5, 1., 1.5, 2.):
            self.speed_combo.addItem(f"{rate:g}×", rate)
        self.speed_combo.setCurrentIndex(1)
        self.speed_combo.currentIndexChanged.connect(
            lambda _: self.player.setPlaybackRate(self.speed_combo.currentData()))
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(70)
        self.volume_slider.setMaximumWidth(120)
        self.volume_slider.setAccessibleName(tr('음량'))
        self.volume_slider.valueChanged.connect(lambda value: self.audio.setVolume(value / 100))
        settings = QHBoxLayout()
        settings.addWidget(QLabel(tr('배속')))
        settings.addWidget(self.speed_combo)
        settings.addStretch()
        settings.addWidget(QLabel(tr('음량')))
        settings.addWidget(self.volume_slider)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas, 1)
        layout.addLayout(controls)
        layout.addLayout(settings)
        self.player.durationChanged.connect(self._duration_changed)
        self.player.positionChanged.connect(self._position_changed)
        self.player.playbackStateChanged.connect(self._playback_changed)
        self.canvas.editStarted.connect(self.player.pause)
        self.canvas.regionChanged.connect(self.regionChanged)

    @property
    def regions(self):
        return {kind: box[:] for kind, box in self.canvas.regions.items()}

    def set_regions(self, regions):
        self.canvas.set_regions(regions)

    def set_region_kind(self, kind):
        if kind and kind not in REGIONS:
            raise ValueError(tr('알 수 없는 인식 영역입니다.'))
        self.canvas.kind = kind
        self.canvas._start = self.canvas._end = None
        self.canvas.update_cursor()
        self.canvas.update()

    def release(self):
        """Detach native playback before Qt destroys its rendering surface."""
        self.clear()
        self.canvas.release()

    def closeEvent(self, event):
        self.release()
        super().closeEvent(event)

    def clear(self):
        self._generation += 1
        self.seek_timer.stop()
        self._pending_seek = None
        # Stop before detaching: FFmpeg renderer destruction can otherwise wait for
        # the Python GIL while stop() waits for that renderer (Windows/PySide6).
        self.player.stop()
        self.player.setVideoSink(None)
        self.player.setSource(QUrl())
        if self.sink is not None:
            if self._frame_slot is not None:
                self.sink.videoFrameChanged.disconnect(self._frame_slot)
            if self.sink is not self.canvas.video_sink:
                self.sink.deleteLater()
            self.sink = None
            self._frame_slot = None
        self.frame_time = None
        self._exact_frame = False
        self.fallback_duration = 0
        self.canvas._start = self.canvas._end = None
        self.canvas.reset_view()
        self.canvas.set_image(QImage())
        self.set_regions({})
        self._duration_changed(0)
        self.frameChanged.emit()

    def effective_duration(self) -> int:
        duration = self.player.duration()
        return duration if duration > 0 else self.fallback_duration

    def load(self, path: Path, duration: float = 0):
        self.clear()
        if isinstance(duration, (int, float)) and math.isfinite(duration) and duration > 0:
            self.fallback_duration = round(duration * 1000)
        generation = self._generation
        self.sink = self.canvas.video_sink or QVideoSink(self)
        self._frame_slot = lambda frame: self._receive_frame(frame, generation)
        self.sink.videoFrameChanged.connect(self._frame_slot)
        resolved = Path(os.path.abspath(os.path.expanduser(path)))
        self.player.setSource(QUrl.fromLocalFile(str(resolved)))
        self.player.setVideoSink(self.sink)
        self.player.pause()
        self._prime_initial_media(resolved)

    def _prime_initial_media(self, path: Path):
        if not path.is_file():
            if self.fallback_duration > 0 and self.player.duration() <= 0:
                self._duration_changed(self.fallback_duration)
            return
        if self.fallback_duration <= 0:
            meta_file = path.parent / "source.json"
            if meta_file.is_file():
                try:
                    import json
                    meta = json.loads(meta_file.read_text(encoding="utf-8"))
                    local_dur = meta.get("local_duration")
                    if isinstance(local_dur, (int, float)) and math.isfinite(local_dur) and local_dur > 0:
                        self.fallback_duration = round(local_dur * 1000)
                except (OSError, ValueError):
                    pass
        try:
            import av
            from PIL.ImageQt import ImageQt
            from media import oriented_image
            from video_sampling import video_duration
            with av.open(str(path)) as container:
                if self.fallback_duration <= 0:
                    dur = video_duration(container)
                    if dur is not None and math.isfinite(dur) and dur > 0:
                        self.fallback_duration = round(dur * 1000)
                if self.canvas.image_size.isEmpty() and container.streams.video:
                    stream = container.streams.video[0]
                    for frame in container.decode(stream):
                        qimg = QImage(ImageQt(oriented_image(frame))).copy()
                        if not qimg.isNull():
                            self._priming = True
                            try:
                                self.canvas.set_image(qimg)
                            finally:
                                self._priming = False
                            self.frame_time = 0.0
                            self.frameChanged.emit()
                        break
        except Exception:
            pass
        if self.fallback_duration > 0 and self.player.duration() <= 0:
            self._duration_changed(self.fallback_duration)

    def _receive_frame(self, frame, generation):
        if self._priming or generation != self._generation or self._exact_frame or not frame.isValid():
            return
        self.canvas.set_frame(frame)
        self.frame_time = frame.startTime() / 1_000_000 if frame.startTime() >= 0 else None
        self.frameChanged.emit()

    def show_frame(self, image: QImage, seconds: float):
        self.player.pause()
        self._exact_frame = True
        self.canvas.set_image(image)
        self.frame_time = seconds
        self.frameChanged.emit()

    def _seek_slider(self, action):
        seconds = self.slider.sliderPosition() / 1000
        self.seekStarted.emit()
        self.request_seek(seconds)

    def request_seek(self, seconds):
        """Coalesce scrubbing input, retaining only the latest requested target."""
        if not math.isfinite(seconds):
            return
        if self.seek_timer.isActive():
            self._pending_seek = seconds
        else:
            self.seek(seconds)
            self.seek_timer.start()

    def flush_seek(self):
        if self._pending_seek is not None:
            self.seek(self._pending_seek)

    def seek(self, seconds):
        if not math.isfinite(seconds):
            return
        self.seek_timer.stop()
        self._pending_seek = None
        self._exact_frame = False
        duration = self.effective_duration()
        target = max(0, round(seconds * 1000))
        self.player.setPosition(min(duration, target) if duration > 0 else target)

    def toggle_playback(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self._exact_frame = False
            self.player.play()

    def _playback_changed(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._exact_frame = False
        self.play_button.setText(tr('일시정지') if state == QMediaPlayer.PlaybackState.PlayingState else tr('재생'))

    def _duration_changed(self, milliseconds):
        effective = milliseconds if milliseconds > 0 else self.fallback_duration
        self.slider.setRange(0, min(effective, 2_147_483_647))
        self._position_changed(self.player.position())

    def _position_changed(self, milliseconds):
        if not self.slider.isSliderDown():
            self.slider.setValue(milliseconds)
        def clock(ms):
            seconds = ms // 1000
            return f"{seconds // 3600:02}:{seconds // 60 % 60:02}:{seconds % 60:02}"
        self.time_label.setText(f"{clock(milliseconds)} / {clock(self.effective_duration())}")

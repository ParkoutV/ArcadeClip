"""Optional Free Play reset evidence from the existing video decode pass."""
import re

from analysis_common import check_cancel
from media import oriented_image


class ResetTracker:
    """Require a directional run and two consecutive exact endpoint readings.

    A rising score can reset to 0; a falling remaining score can reset to 101.
    This avoids treating a normal increasing score reaching 101 as a restart.
    Events retain the pre-reset evidence time so they cannot bridge song changes.
    """
    def __init__(self):
        self.previous = None
        self.direction = 0
        self.pending = None
        self.events = []

    def feed(self, seconds, value):
        if value is None:
            self.previous = self.pending = None
            self.direction = 0
            return
        if self.pending is not None:
            before, boundary, endpoint = self.pending
            self.pending = None
            if value == endpoint:
                self.events.append((before, boundary, seconds))
                self.previous = (seconds, value)
                self.direction = 0
                return
        if self.previous is not None:
            timestamp, previous = self.previous
            if ((value == 0 and previous > 0 and self.direction > 0)
                    or (value == 101 and previous < 101 and self.direction < 0)):
                self.pending = (timestamp, seconds, value)
            elif abs(value - previous) >= .0001:
                self.direction = 1 if value > previous else -1
        self.previous = (seconds, value)


class FreePlayObserver:
    def __init__(self, read, region, size, start, interval, cancel, gpu_convert=None):
        self.read, self.region, self.size = read, region, size
        self.target, self.interval, self.cancel = start, interval, cancel
        self.tracker = ResetTracker()
        self.converter = None
        self.gpu_convert = gpu_convert

    def observe(self, seconds, frame):
        if seconds + 1e-7 < self.target:
            return
        self.target = seconds + self.interval
        check_cancel(self.cancel)
        use_gpu = frame.format.name == 'd3d11' if self.gpu_convert is None else self.gpu_convert
        if use_gpu and self.converter is None:
            from gpu_image import GPUImageConverter
            self.converter = GPUImageConverter()
        if not use_gpu and frame.format.name == 'd3d11':
            frame = frame.reformat(format='nv12')
        image = (self.converter.convert(frame, region=self.region, reference_size=self.size)
                 if self.converter else oriented_image(frame, region=self.region, reference_size=self.size))
        text, confidence = self.read(image)
        del image
        # Strict parsing: a stray digit must not manufacture a reset endpoint.
        match = re.fullmatch(r"\s*(\d{1,3}(?:\.\d{1,4})?)\s*[%％]?\s*", text)
        value = float(match[1]) if match and confidence >= .9 else None
        self.tracker.feed(seconds, value if value is not None and 0 <= value <= 101 else None)

    def split(self, candidates):
        rows = []
        for candidate in candidates:
            left = candidate["start"]
            if candidate.get("image_url"):
                for before, boundary, confirmed in self.tracker.events:
                    if left <= before < boundary < confirmed < candidate["end"]:
                        rows.append({**candidate, "start": left, "end": boundary})
                        left = boundary
            rows.append({**candidate, "start": left})
        return rows

    def close(self):
        if self.converter is not None:
            self.converter.close()
            self.converter = None
        close = getattr(self.read, "close", None)
        if close is not None:
            close()

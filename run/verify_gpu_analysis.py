"""Measure selected-frame GPU conversion on an actual source, with memory bounds."""
import argparse
import ctypes
from ctypes import wintypes
import gc
import json
from pathlib import Path
import sys
import threading
import time

parser = argparse.ArgumentParser()
parser.add_argument('source')
parser.add_argument('--seconds', type=float, default=120)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--bundle', type=Path)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str((args.bundle or root) / 'src'))
ctypes.windll.kernel32.SetErrorMode(0x8003)
class Counters(ctypes.Structure):
    _fields_ = [('cb', wintypes.DWORD), ('faults', wintypes.DWORD)] + [
        (name, ctypes.c_size_t) for name in ('peak', 'rss', 'a', 'b', 'c', 'd', 'page', 'page_peak', 'private')]
get_mem = ctypes.windll.psapi.GetProcessMemoryInfo
get_mem.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
get_process = ctypes.windll.kernel32.GetCurrentProcess
get_process.restype = wintypes.HANDLE
def memory():
    data = Counters()
    data.cb = ctypes.sizeof(data)
    if not get_mem(get_process(), ctypes.byref(data), data.cb):
        raise ctypes.WinError()
    return round(data.private / 2**20, 2)

import av
import numpy as np
from video_sampling import samples
from media import frame_at
from jacket_recognition import phash

region = [.01, .1, .15, .3]
metrics = dict(decode_s=0., convert_s=0., decoded_frames=0, sample_frames=0)
points, comparisons = [], []
began = time.perf_counter()
count = 0
for seconds, image in samples(args.source, 0, args.seconds, 1, threading.Event(),
                             gpu=True, decoder_threads=8, metrics=metrics, region=region,
                             reference_size=[2560, 1440]):
    count += 1
    if count in (1, 31, 61):
        reference = frame_at(Path(args.source), seconds, region=region, reference_size=[2560, 1440])['image']
        delta = np.abs(np.asarray(image).astype(float)-np.asarray(reference))
        comparisons.append(dict(seconds=seconds, mae=float(delta.mean()), max=float(delta.max()),
                                phash_distance=(phash(image)^phash(reference)).bit_count()))
        assert image.size == reference.size
        assert delta.mean() < 5, comparisons[-1]
        del reference, delta
    if count % 10 == 0:
        point = dict(samples=count, private_mb=memory(), elapsed=round(time.perf_counter()-began, 2))
        points.append(point)
        print(json.dumps(point), flush=True)
        if point['private_mb'] > 800:
            raise AssertionError('Memory safety limit exceeded')
    del image
gc.collect()
result = dict(metrics=metrics, points=points, comparisons=comparisons, final_mb=memory(),
              retained_frames=sum(isinstance(obj, av.VideoFrame) for obj in gc.get_objects()))
assert count == int(args.seconds), (count, args.seconds)
assert metrics['sample_frames'] == count
assert metrics['decoded_frames'] > count*50
assert metrics['converter'].startswith('GPU')
if len(points) > 4:
    assert max(p['private_mb'] for p in points[2:])-min(p['private_mb'] for p in points[2:]) < 100, points
args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result), flush=True)

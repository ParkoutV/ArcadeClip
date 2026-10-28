"""Bounded read-only decode/convert memory probe; does not alter the app session."""
import argparse
import ctypes
from ctypes import wintypes
import gc
import json
from pathlib import Path
import sys
import time

parser = argparse.ArgumentParser()
parser.add_argument('source')
parser.add_argument('--gpu', action='store_true')
parser.add_argument('--convert', action='store_true')
parser.add_argument('--collect', action='store_true')
parser.add_argument('--metadata', action='store_true')
parser.add_argument('--seconds', type=float, default=90)
args = parser.parse_args()
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
ctypes.windll.kernel32.SetErrorMode(0x8003)
class Counters(ctypes.Structure):
    _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [
        (name, ctypes.c_size_t) for name in ('PeakWorkingSetSize', 'WorkingSetSize',
        'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
        'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage', 'PrivateUsage')]
get_mem = ctypes.windll.psapi.GetProcessMemoryInfo
get_mem.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
get_mem.restype = wintypes.BOOL
get_process = ctypes.windll.kernel32.GetCurrentProcess
get_process.restype = wintypes.HANDLE
def memory():
    data = Counters()
    data.cb = ctypes.sizeof(data)
    if not get_mem(get_process(), ctypes.byref(data), data.cb):
        raise ctypes.WinError()
    return dict(private_mb=round(data.PrivateUsage/2**20, 2), rss_mb=round(data.WorkingSetSize/2**20, 2))
import av
from media import oriented_image
options = {}
if args.gpu:
    from av.codec.hwaccel import HWAccel
    options['hwaccel'] = HWAccel('d3d11va', allow_software_fallback=False)
base = memory()
began = time.perf_counter()
print(json.dumps({'phase': 'baseline', **base, **vars(args)}), flush=True)
container = av.open(args.source, **options)
stream = container.streams.video[0]
stream.thread_type = 'AUTO'
stream.codec_context.thread_count = 8
target = 0
count = 0
images = 0
for frame in container.decode(stream):
    count += 1
    seconds = float(frame.pts * stream.time_base)
    if seconds >= args.seconds:
        break
    if (args.convert or args.metadata) and seconds >= target:
        if args.metadata:
            # Isolate the metadata access at the start of oriented_image().
            tuple(frame.side_data)
        else:
            image = oriented_image(frame, region=[.01, .1, .15, .3], reference_size=[2560, 1440])
            del image
        images += 1
        target = seconds + 1
    if count % 600 == 0:
        collected = gc.collect() if args.collect else None
        state = memory()
        print(json.dumps({'phase': 'decode', 'frames': count, 'samples': images,
                          'seconds': seconds, 'elapsed': round(time.perf_counter()-began, 2),
                          'format': frame.format.name, 'collected': collected, **state}), flush=True)
        if state['private_mb'] - base['private_mb'] > 512 or time.perf_counter()-began > 120:
            print('STOP: bounded diagnostic limit', flush=True)
            break
del frame
container.close()
def retained_frames():
    return sum(isinstance(obj, av.VideoFrame) for obj in gc.get_objects())
print(json.dumps({'phase': 'closed', 'retained_frames': retained_frames(), **memory()}), flush=True)
collected = gc.collect()
print(json.dumps({'phase': 'collected', 'objects': collected,
                  'retained_frames': retained_frames(), **memory()}), flush=True)

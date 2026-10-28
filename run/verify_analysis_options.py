"""Short actual-source option matrix; no fallback may hide a failed GPU mode."""
import ctypes
import gc
import json
from pathlib import Path
import sys
import threading
import time

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(sys.argv[2]) / 'src') if len(sys.argv) > 2 else str(root / 'src'))
ctypes.windll.kernel32.SetErrorMode(0x8003)
import numpy as np
from video_sampling import samples
from pipeline import prefetch

results = []
reference = None
for decode in (False, True):
    for convert in (False, True):
        for pipeline in (False, True):
            cancel = threading.Event()
            metrics = dict(decode_s=0., convert_s=0., decoded_frames=0, sample_frames=0)
            began = time.perf_counter()
            source = samples(sys.argv[1], 0, 10, 1, cancel, gpu=decode, gpu_convert=convert,
                             pipelined=pipeline, decoder_threads=8, metrics=metrics,
                             region=[.01, .1, .15, .3])
            if pipeline:
                source = prefetch(source, cancel)
            rows = list(source)
            assert len(rows) == 10
            if reference is None:
                reference = rows
            assert [t for t, _ in rows] == [t for t, _ in reference]
            error = max(float(np.abs(np.asarray(left).astype(float)-np.asarray(right)).mean())
                        for (_, left), (_, right) in zip(reference, rows))
            assert error < 5, error
            assert metrics['converter'].startswith('GPU') == convert
            assert metrics['decoder'].startswith('GPU') == decode
            record = dict(gpu_decode=decode, gpu_convert=convert, pipeline=pipeline,
                          wall_s=round(time.perf_counter()-began, 3), max_mae=error, **metrics)
            results.append(record)
            print(json.dumps(record), flush=True)
            del rows
            gc.collect()
(root / '.validation-data/analysis-options-matrix.json').write_text(json.dumps(results, indent=2))

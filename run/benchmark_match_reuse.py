"""Synthetic matching-only comparison; not a video decode or OCR benchmark."""
import json
from pathlib import Path
import sys
import threading
from time import perf_counter

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from analysis_common import DEFAULTS
from jacket_recognition import _identify_batch, identify, phash


def main():
    rng = np.random.default_rng(42)
    images = [Image.fromarray(rng.integers(0, 256, (80, 80, 3), dtype=np.uint8)) for _ in range(3)]
    catalog = [{'hash': phash(image), 'image_url': f'{i}.png', 'title': str(i)}
               for i, image in enumerate(images)]
    catalog += [{'hash': int(h), 'image_url': f'extra{i}.png', 'title': str(i)}
                for i, h in enumerate(rng.integers(0, 2**64-1, 1497, dtype=np.uint64))]
    results = []
    for name, frames in [('repeated', [images[0]] * 2000),
                         ('changing', [images[i % 3] for i in range(2000)])]:
        old_times, new_times = [], []
        for repeat in range(4):
            cache, actual = {}, []
            started = perf_counter()
            expected = [(i, identify(im, catalog, DEFAULTS, search=False)) for i, im in enumerate(frames)]
            baseline_s = perf_counter() - started
            started = perf_counter()
            for i, im in enumerate(frames):
                actual.extend(_identify_batch([(i, im)], catalog, DEFAULTS, threading.Event(), cache))
            cached_s = perf_counter() - started
            assert actual == expected
            if repeat:  # warm up both paths before collecting timings
                old_times.append(baseline_s)
                new_times.append(cached_s)
        results.append(dict(case=name, frames=len(frames), catalog=len(catalog),
                            baseline_s=old_times, cached_s=new_times,
                            speedup=float(np.median(old_times) / np.median(new_times)), identical=True))
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()

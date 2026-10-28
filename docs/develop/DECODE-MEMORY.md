# Analysis memory growth diagnosis — 2026-09-30

## Finding

Reproduced on the user's HEVC 2560x1440 60fps source using the shipped ARM64
Python/PyAV runtime. `src/media.py:oriented_image` accesses `frame.side_data` for
display-matrix validation. In bundled PyAV 18.1.0, `Frame.side_data` caches a
`SideDataContainer(self)` and that container retains `self.frame`. This creates a
collectable reference cycle that retains the entire native decoded frame buffer.
Deleting the PIL crop or closing the input does not immediately reclaim it.

This is delayed cyclic-GC reclamation, not proof of permanently unreachable
native allocations. A large native buffer can be retained by very few Python
objects, so Python's allocation-based collection need not happen promptly.

## Isolated measurements

Each experiment ran in a fresh process; no user app was stopped or modified.
Metric: Windows process PrivateUsage, MiB (not whole-system RAM or GPU usage).
Probe capped additional private memory at approximately 512 MiB and wall time at
120 seconds, stopping at a 600-frame checkpoint.

| Path | Result |
| --- | --- |
| GPU decode only, first 90 video seconds | 312–316 MiB after warmup, stable |
| GPU + current ROI image conversion | 358, 425, 492, 559 MiB at 10/20/30/40 video seconds |
| GPU + metadata access ONLY (no RGB/PIL conversion) | 371, 428, 485, 541 MiB at the same checkpoints |
| GPU + conversion + gc.collect every 600 frames | 348–357 MiB over 90 video seconds, stable |

Metadata-only experiment after close: **41 retained VideoFrame objects**.
After `gc.collect()`: **1 retained VideoFrame**, **120 collected objects**, private
memory **541.5 -> 332.15 MiB**. Forty 2560x1440 NV12 images need approximately
211 MiB before alignment, matching the observed reclamation (~209 MiB).

Logs: `.validation-data/memory-gpu-{decode,convert,metadata,collect}.jsonl`.
Reproducer: `run/diagnose_decode_memory.py`; example:

```powershell
& .\dist\ArcadeClip-arm64_preview\runtime\python.exe run/diagnose_decode_memory.py 'C:\Videos\sample.mp4' --gpu --metadata --seconds 60
```

Use `--gpu` alone for decoding, `--gpu --convert` for the app's conversion,
and add `--collect` for the diagnostic controlled-GC comparison.

## Other candidates inspected

- Match cache is single-entry; it does not accumulate frames.
- Parallel pending batches are bounded to twice the worker count.
- BoundaryBuffer is bounded to 64 MiB native/32 MiB crops, and disabled for GPU.
- Observation results grow with samples, but contain metadata, not full images.

## Next action / scope

No production code or delivered bundle changed during this diagnostic task.
The next fix should bound lifetime of these cycles while preserving per-frame
rotation/mirror validation. Controlled collection at a bounded native-memory
budget is a possible application workaround; benchmark collection pauses before
shipping. An upstream cycle-free metadata API/implementation is preferable to
blindly skipping display-matrix checks or mutating private PyAV fields.

This confirms a concrete application/library retention path, not that all
system-wide memory growth in the screenshot came from it. Existing caches,
decoder pools and other processes account for additional baseline memory.

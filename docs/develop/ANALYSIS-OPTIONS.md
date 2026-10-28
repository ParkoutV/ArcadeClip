# Stage 3 analysis controls — 2026-09-30

User confirmed batching means overlapping decoding, conversion and recognition
within one video. User explicitly requires existing boundary detection preserved.

Implemented:
- Stage 3 has independent GPU decoding, GPU image conversion and pipeline checks.
  Preferences use QSettings; controls disable during work. Settings never reparents
  them. Each run captures immutable values. Defaults: CPU/CPU, pipeline requested.
- All four decode/conversion combinations work. CPU decode + GPU conversion uploads
  selected NV12 frames; GPU decode + CPU conversion downloads selected NV12 frames.
  Only selected samples are converted to RGB. GPU crop/color conversion supports
  SDR NV12; unsupported modes warn and resume with CPU processing.
- Optional two bounded ordered queues overlap decode, conversion and recognition.
  Each queue holds at most two waiting items, plus in-flight frames and the existing
  bounded recognition batch. Cancellation/close joins producers and drops references.
- Existing CPU single-worker BoundaryBuffer observer/matched protocol is unchanged.
  That mode disables prefetch even if requested. GPU decoding and multi-worker CPU
  modes can pipeline, retaining their pre-existing boundary refinement behavior.
  No proxies, partial decoding, boundary algorithm changes, or preview changes.
- Free Play sampling honors conversion choice and retains its existing interval/order.

Validation:
- Native matrix: CPU/GPU decode × CPU/GPU conversion × sequential/pipeline, matching
  timestamps and rotated ROI pixels; sparse conversion checked.
- Pipeline ordering, error forwarding, bounded backlog, cancel/close cleanup.
- Existing recognition/Free Play tests; boundary results identical with pipeline
  requested in single- and multi-worker CPU modes.
- Offscreen UI test verifies preferences and controls remain on stage 3 after Settings.
  Test uses temporary INI settings because sandbox registry writes are denied.
- Actual 2560×1440 HEVC 60fps source, first 10 seconds: 601 decoded, 10 converted in
  every combination; maximum mean RGB difference 1.914/255 against CPU reference.
  GPU decode / CPU conversion: 3.097s sequential, 2.509s pipeline.
  GPU decode / GPU conversion: 2.440s sequential, 2.456s pipeline.
  These are short single-run sampling measurements, not whole-analysis benchmarks.
  Raw results: `.validation-data/analysis-options-matrix.json`.

Rebuild/resume:
1. `dist/ArcadeClip-arm64_gpu-analysis/runtime/python.exe run/build_gpu_roi.py`
2. Run tests with repo `src` inserted before embedded runtime paths.
3. `.../python.exe run/verify_analysis_options.py <source.mp4>`
4. `.../python.exe run/package_gpu_analysis.py --output ArcadeClip-arm64_analysis-options`

Standalone staging retains the embedded ARM64 runtime, FFmpeg and existing isolated
x64 OCR dependencies. The complete output folder is required, not the launcher alone.

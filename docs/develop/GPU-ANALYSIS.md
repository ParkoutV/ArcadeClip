# GPU analysis and memory lifetime — work checkpoint

User request: no proxies; convert only selected frames; GPU option must also
perform image conversion on GPU where supported; restrict whole-video song scan
to its recognition ROI where possible; preserve prior-image consumers and
aggressively release non-reference images. Other stages retain original source
coordinates and full-video access.

User clarification: exclude partial spatial decoding entirely. Decode full
frames; prioritize selected-frame and ROI-only image conversion if supported.

## Plan

- [x] Probe native D3D11 decode with GPU-owned frames and `scale_d3d11` GPU
  conversion. Determine supported RGB formats/crop operations on SQ1.
- [x] Select samples before hardware download. Transfer only selected images.
- [x] Apply scan ROI before RGB conversion/download where API permits. Partial
  spatial HEVC decoding is not assumed supported; keep full-frame decode when
  reference dependencies require it.
- [x] Bound native frame lifetime, including side_data reference cycles; preserve
  BoundaryBuffer/FreePlay consumers and existing CPU fallback behavior.
- [x] Regression tests: selection, transforms, ROI, prior-image retention,
  cancellation, GPU fallback. Actual-source correctness/memory/performance probe.
- [x] Update standalone folder and record validation. Avoid unnecessary runtime
  download/rebuild; preserve existing releases and unrelated source changes.

## Initial findings

Existing `samples()` selects frames before RGB conversion, but PyAV's default
GPU path downloads every decoded frame before selection. `oriented_image()`
side_data access creates collectable frame cycles (see DECODE-MEMORY.md).
External ARM64 FFmpeg includes `scale_d3d11`. Probe internal PyAV filter support
before choosing a subprocess implementation.

## Implementation checkpoint

The supplied FFmpeg scale_d3d11 only supports NV12/P010 output and no crop option.
Implemented a small native ARM64 helper using the public D3D11 VideoProcessor API
instead (`run/gpu_roi.c`, build with `run/build_gpu_roi.py`). It shares the decoded
texture's device, enables immediate-context multithread protection, disables
automatic video enhancements, sets SDR color range/matrix explicitly, applies
the source ROI, produces BGRA on GPU, and maps only the small output texture.
All input views are released per call; output/staging/processor resources are
reused per task and released in generator cleanup. No external decoder process.

`src/gpu_image.py` wraps it with explicit ctypes signatures and HRESULT checking.
Supported path: Windows ARM64, D3D11 NV12 SDR BT.601/709. HDR/BT.2020/P010 and
unsupported devices fall back through the existing warned CPU path; do not claim
those are GPU-converted. ROI is mapped back to source coordinates for quarter
turn rotations; CPU only rearranges already-RGB pixels for the final orientation.
Existing unsupported reflection validation is preserved.

PyAV now uses `is_hw_owned=True`: no full-frame CPU download before sampling.
Only selected frames are converted; FreePlay has a separate selected-frame GPU
converter for its score ROI, leaving full-frame observer semantics unchanged.
Calibration, frame inspection, refinement and export retain original access.

Metadata GC: track estimated native bytes held by side_data cycles and collect
at 16MiB, and after sampling unwinds. This does not destroy reachable prior-image
references. Clear processed matching batches, release the initial sample/batch,
and clear the native boundary ring even on cancellation. Existing cache limits
and refinement fallback remain intact.

## Verification so far

- 36 media/recognition/FreePlay regression tests passed.
- 3 opt-in native GPU tests passed: 0/90/180/270-degree ROI correctness, exactly
  2 conversions for 60 decoded frames, cancellation while retaining a reference,
  and rejection of unsupported reflection.
- User HEVC 2560x1440 60fps source, first 120 seconds: 7,201 decoded frames,
  120 selected GPU ROI conversions; 22.45s decode + 2.16s conversion, 25.66s wall
  including CPU reference comparisons. Private memory 582.69–583.94MiB, no
  progressive growth; zero retained PyAV frames after completion. Larger than
  the earlier isolated probe because this check also imports NumPy/catalog code
  and runs CPU reference decoders; compare slopes, not unrelated baselines.
- At 0/30/60s, CPU/GPU ROI dimensions matched, RGB mean absolute error was
  1.26/1.28/2.60 (of 255), pHash distance 0 at all three timestamps. Not a
  guarantee of identical recognition for every possible input.
- Results: `.validation-data/gpu-analysis-result.json`, `gpu-analysis-tests.log`.

## Completion / resume

Standalone staging complete: `dist/ArcadeClip-arm64_gpu-analysis/ArcadeClip.exe`.
Its own runtime imported the new app/modules/DLL successfully. New DLL PE machine
was verified as ARM64 (0xAA64) and added to build-manifest.json. A further 30-second
actual-source run using `--bundle dist/ArcadeClip-arm64_gpu-analysis` passed;
details: `.validation-data/gpu-analysis-bundle.json`. Source hashes are recorded
in `gpu-analysis-improvement.json`. Prior releases remain unchanged.

Rebuild helper: `run/build_gpu_roi.py`; stage: `run/package_gpu_analysis.py`.
No runtime downloads are required. No full ZIP was recompressed for this update;
the complete standalone folder is ready to run. Do not use the previous preview
ZIP expecting these new analysis changes. Native helper source and build script
are the reproducible source of the generated DLL.

Residual scope: GPU conversion applies to the whole-video song scan and its
optional FreePlay observer. Sparse calibration, boundary rechecks and final OCR
retain their existing CPU paths and original-video access. Unsupported GPU
format/device combinations explicitly warn and fall back to CPU. All paths now
share bounded metadata-cycle reclamation; no partial spatial decoder was added.

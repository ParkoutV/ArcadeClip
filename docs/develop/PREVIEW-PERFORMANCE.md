# Preview performance work — resumable checkpoint

## Request and constraints

Improve playback while preserving stage 3 region editing, zoom, pan, crop,
rotation/mirroring and exact frame stepping. **No proxy videos.** Keep ARM64
portable deployment and the existing x64 OCR isolation. User requested this
checkpoint before implementation because their remaining usage is limited.

## Baseline (2026-09-29)

- `Preview._receive_frame` converts every frame to QImage, then QWidget paints it.
- `ProfilePanel.update_crop` copies/scales a crop even when its panel is hidden.
- Position changes rebuild both timelines' clip lists.
- Frame stepping opens a fresh PyAV container per request.
- Current portable folder: `dist/ArcadeClip-arm64_improved`. Other uncommitted
  recognition/profile changes predate this task: preserve them.
- No measured speedup or reproduced user-video bottleneck is claimed yet.

## Implementation sequence and acceptance criteria

1. [x] Record this plan and baseline before editing implementation.
2. [x] GPU presentation: integrate Qt Quick VideoOutput in the existing canvas;
   retain QWidget input/coordinate logic and overlay controls. Zoom/pan change
   presentation geometry, not image pixels. Keep a software path for headless
   tests/unavailable graphics. CPU image extraction becomes lazy and cached per
   frame. Source switches must invalidate old frames and stop before detaching.
3. [x] Demand-driven crops: no hidden crop extraction; throttle live crops; update
   immediately on region edits and pause. Obtain dimensions without image reads.
4. [x] Seek/UI scheduling: coalesce rapid seeks; preserve final exact target;
   avoid rebuilding clip lists on each playback-position notification. Assess
   whether bounded adjacent-frame caching is warranted after core changes.
5. [x] Validate coordinate mapping (letterbox, zoom, pan, reverse drag), frame
   orientation, source switching, exact stepping, and crop visibility. Run
   existing relevant tests and add only meaningful regression coverage.
6. [x] Native Windows ARM64 playback smoke with the actual rendering widget,
   recording backend, frame count and conversion count; distinguish synthetic
   validation from performance on the user's original video.
7. [x] Update portable application sources/resources, verify the shipped path,
   write a separate ZIP + checksum without overwriting earlier release archives.

## Architecture decisions

- Prefer Qt Quick's GPU VideoOutput over QWidget QImage painting. QQuickWidget
  fits existing QWidget stacking/input, though it adds a GPU render pass; do not
  claim zero-copy. A separate QQuickView/native window has overlay/focus tradeoffs.
- Keep normalized source coordinates as the persistent region representation.
  Presentation zoom/pan must never alter stored regions or OCR source pixels.
- Decode work and GPU output acceleration are separate; verify the actual device
  instead of assuming native ARM64 implies hardware decoding.
- CPU snapshots only for real consumers. Bound retained frames and drop obsolete
  work. Never build a queue proportional to playback duration.
- Optional CPU fallback must retain function, not hide a failed GPU smoke test.

## Resume instructions

Read this file, `git diff -- src/preview.py src/profile_panel.py src/app.py`, and
the latest test notes below. Use bundled Python at
`dist/ArcadeClip-arm64_improved/runtime/python.exe`; its isolated `_pth` points
to bundle sources, so explicitly insert repository `src` when testing edits.
Do not rebuild/download dependencies unnecessarily; installed Qt includes Quick.
Do not overwrite unrelated changes, reset git, or remove existing bundles.

## Latest checkpoint

Implemented GPU canvas (`src/assets/preview.qml`), lazy per-frame snapshots,
metadata-only coordinates, throttled visible crops (150 ms), latest-target seek
coalescing (40 ms, first request immediate), and playhead-only timeline updates.
Guide video also uses GPU output. Retain only one video frame and one snapshot;
larger adjacent-frame decoder caches are deferred, not required for this change.

Native ARM64/Windows/Direct3D11 smoke: 1080p60 synthetic H.264, 345 frame callbacks
in 6.007 s including startup, final PTS 5.733 s, **0 CPU snapshots**, no player
errors. Artifacts: `.validation-data/preview-gpu-1080p/`. This is not a GPU present
rate or measured speedup against the old implementation. Actual widget screenshot
checked: video and region overlay are visible after zoom/pan.

User reported a python.exe native memory-write error while tests ran. Its origin
is not yet established: no matching recent Application Error event or remaining
Python/WER process was found. Do not claim fixed based only on playback success.
Explicit stop/detach was added to preview and guide shutdown. Diagnostic scripts
suppress OS error dialogs but must still inspect exit codes. Subsequent native
stress passed: 4 create/close cycles, 12 source switches, 32 rotation/mirroring
comparisons against CPU snapshots, hidden crop checks, close while playing.
No native crash was reproduced in these checks; the earlier dialog's specific
cause remains unconfirmed.

Final regression results: app suite 48/48 passed; preview suite 10/10 passed after
setting FFmpeg PATH inside Python (the earlier shell PATH setting did not reach
the executable). Includes actual playback/seek and a separate-process source
switch/deadlock check. App logs contain an intentionally mocked `UI network stat`
failure from its background catalog task; the suite exits 0. Logs are in
`.validation-data/preview-regression.log` and `preview-media-tests.log`.

Staged portable folder: `dist/ArcadeClip-arm64_preview`. Its own runtime and source
passed Windows/Direct3D11 smoke: 338 frame callbacks in 6.012 s including startup
and an actual region drag, PTS 5.617 s, 0 CPU snapshots, no media errors. Region
coordinates matched expected .4/.4/.6/.6 within pixel rounding. Results are in
`.validation-data/preview-bundle/`. Older folders/archives are preserved.

Reproduction commands (PowerShell, from repository root):

```powershell
& .\dist\ArcadeClip-arm64_improved\runtime\python.exe run/package_preview.py
& .\dist\ArcadeClip-arm64_preview\runtime\python.exe run/verify_preview.py .validation-data/preview-1080p60.mp4 --output .validation-data/preview-bundle --seconds 6 --bundle dist/ArcadeClip-arm64_preview
& .\dist\ArcadeClip-arm64_preview\runtime\python.exe run/verify_preview_lifecycle.py
& .\dist\ArcadeClip-arm64_preview\runtime\python.exe run/package_preview.py --archive
```

The lifecycle script tests repository sources explicitly; the playback script's
`--bundle` option tests shipped sources. `ARCADECLIP_PREVIEW_RENDERER=software`
provides an explicit diagnostic fallback. Offscreen tests always use software.
Implementation, validation and packaging are complete. No active test/build process remains.

### Final validation checkpoint (2026-09-30)

After explicitly releasing retained GPU frames on canvas shutdown, all 10 preview
tests passed again and the native lifecycle script completed all 4 cycles with
exit code 0 (`.validation-data/preview-lifecycle-final.log`). The staged sources
were refreshed after that change. Archive assembly completed with exit code 0:

- ZIP: `dist/ArcadeClip-0.2.1-windows-arm64-preview-improved.zip`
- Size: 385,830,314 bytes; all 9,202 entries passed CRC verification.
- SHA-256: `47f0ef99b1a660e22d131801e61234e33e575f95f2b578ed7a62273e934dd724`
- Checksum file: same path with `.sha256` appended.
- Launch: `dist/ArcadeClip-arm64_preview/ArcadeClip.exe`.

The checkpoint inside the ZIP was captured before archive verification; this
repository document records the final result. No dependency download, full
rebuild, or repeated regression run is necessary when resuming. A remaining
optional investigation is reproducing the user's earlier native crash or
measuring their original footage; neither has been claimed resolved/measured.

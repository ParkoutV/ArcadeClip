# Windows AMD64 / ARM64 build

The fork retains the local recognition, preview, GPU conversion, analysis pipeline,
free-play and stream-ingest changes relative to upstream `9110b4d`.

## Build

Use Windows with Python 3.11+ including pip. The host must be able to execute the
target binaries: Windows 11 ARM64 can build both targets; an AMD64 host builds AMD64.
Python 3.13.12, FFmpeg 8.1.3, Deno 2.9.6 and Zig 0.15.2 are pinned with SHA-256 in
`run/windows.inputs.lock.json`; package wheels are pinned in `uv.lock`.

```powershell
python run/build_windows_portable.py --arch amd64
python run/build_windows_portable.py --arch arm64
./run/build_user_installer.ps1
```

Outputs must be new directories; pass `--output` for another location. The builder
checks every PE binary: app files match the target, and the isolated OCR runtime
is AMD64. It compiles the launcher and GPU helper from source for each target.
Downloads are reused from `build/arm64/downloads` for compatibility with earlier
local builds. The ARM64 wrapper `run/build_arm64.py` remains available.

The installer uses Inno Setup 6.7.3 or newer (`build/installer-tools/inno/ISCC.exe`
by default). One `windows-universal-user-setup.exe` contains both payloads and
selects ARM64 using `IsArm64`, otherwise AMD64. Supported OS: Windows 10/11 AMD64;
Windows 11 ARM64 (x64 emulation is required for the OCR helper).

## Runtime choices

Setup scans PATH for Python and FFmpeg. It recommends a compatible local Python
only if it is standard CPython 3.13 of the native app architecture. Python 3.14,
32-bit Python and free-threaded Python do not match the pinned extension wheels.
Windows Store aliases are skipped. Probes run hidden with a 15-second timeout.
FFmpeg is offered with ffprobe from the same directory after an H.264/AAC test.

Python and FFmpeg choices are independent. App dependencies remain private in
`runtime/Lib/site-packages`; global Python packages and PATH are never modified.
The isolated AMD64 OCR Python is always bundled, including when local app Python
is selected. Qt/PyAV's internal FFmpeg libraries also remain bundled; the FFmpeg
choice controls the command-line tools used for downloads, streams and export.

Selections are stored in UTF-16 `runtime-config.ini`. A silent update preserves
working previous selections; a new silent install defaults to bundled runtimes.
If an external tool is later moved or removed, rerun Setup and select bundled.
The universal installer remains self-contained regardless of the selected mode.
For unattended installation, `/PYTHON=local|bundled` and `/FFMPEG=local|bundled`
override the defaults. Explicit local selections fail if no compatible runtime
is found; setup does not silently switch the requested mode.

## Validation

Run `run/run_tests.py --no-display` with each bundle's Python and tools on PATH.
Run `run/verify_windows.py --bundle PATH --ocr` using that bundle's Python for
media export, Qt playback and real OCR checks. GPU tests require real D3D11 hardware.
`run/validate_bundle.py` checks all native architectures and required payload files.
The release workflow builds on each architecture and assembles one installer.

Historical `ARM64.md`, performance packaging scripts and dated installer reports
describe previous local deliveries. This document describes the current build.

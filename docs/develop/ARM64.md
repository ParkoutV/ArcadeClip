# Windows ARM64 portable build

`python run/build_arm64.py` assembles `dist/ArcadeClip-arm64/`. The host Python
may be x64: it downloads and verifies archives only. No system Python or PATH
change is required to run the resulting application.

This is an embedded-Python distribution with a compiled ARM64 GUI launcher,
not the existing Nuitka distribution. Run `ArcadeClip.exe`, or use
`ArcadeClip_dbg.cmd` for diagnostic output. Distribute the entire directory.

## Architecture

| Component | Architecture |
| --- | --- |
| Launcher and embedded Python 3.13.12 | ARM64 |
| PySide6 / Qt Multimedia / bundled FFmpeg | ARM64 |
| PyAV / bundled FFmpeg, NumPy, Pillow | ARM64 |
| External FFmpeg / ffprobe (System233 MSVC 8.1.3 GPL shared build) | ARM64 |
| Deno 2.9.6 official executable | ARM64 |
| yt-dlp and its installed extensions | ARM64 / pure Python |
| Separate Python + RapidOCR / OpenCV / ONNX Runtime | x64, Windows 11 emulation |

Only cropped RGB text images cross the OCR pipe. Video decoding, jacket
recognition and frame seeking remain in the ARM64 process. Each OCR worker
keeps its model loaded between requests; cancellation terminates the helper.
The original source/Nuitka launch uses local OCR unchanged when no portable
bundle manifest exists.

The optional yt-dlp Brotli extra is omitted because the pinned wheel has no
Windows ARM64 variant. gzip/deflate HTTP support remains available. Deno is
bundled directly rather than installed through its x64-only Python wheel.
Jacket data and the OCR model retain the application's normal first-use
download behavior; these are data, not external installed runtimes.

## Reproduce

Run on Windows 11 ARM64 with a host Python that includes pip (its wheel-tag
parser is used). Internet access is needed on the first build. Downloads and
the standalone Zig compiler are kept under `build/arm64/`; the installed host
Python is not modified. Rebuilds reuse verified cached inputs.

`run/arm64.inputs.lock.json` pins Python, FFmpeg, Deno and Zig archive hashes.
`uv.lock` pins the Python wheels, including the separate OCR environment.
FFmpeg uses a fixed release URL and archive hash. An upstream replacement
fails verification instead of silently changing the build. Updating it requires
selecting and recording a new reviewed input. BtbN 9.0 shared and static builds
both failed at startup on the validation machine; they are not shipped.

`build-manifest.json` in the output records input hashes, package versions and
the PE architecture of every executable, DLL and Python extension. The build
rejects x64 binaries outside `ocr-runtime/` and non-x64 binaries inside it.
Package notices are collected separately from the two actual runtimes;
FFmpeg version/configuration/license output is collected from the bundled tool.

Windows 11 ARM64 is required for the x64 OCR helper. No performance claim is
implied by native architecture; benchmark representative input videos. GPU
encoding still uses the existing NVENC/QSV/AMF selection; Qualcomm hardware
encoding is not added by this build.

## Validate the bundle

```powershell
.\dist\ArcadeClip-arm64\runtime\python.exe -X utf8 run/verify_arm64.py --ocr
```

The check runs the bundled tools, creates H.264/AAC video, verifies PyAV
decoding and both export modes, receives video frames from Qt Multimedia and
optionally recognizes a generated text image through the x64 OCR process.
The OCR check downloads the hash-pinned model into `.validation-data/arm64/data`
on its first run. Results are saved in `.validation-data/arm64/smoke-result.json`.

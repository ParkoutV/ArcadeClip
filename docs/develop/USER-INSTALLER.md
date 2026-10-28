# ARM64 per-user installer — 2026-10-21

## Revision 3

Payload: `dist/ArcadeClip-arm64_installable` (updated with OBS stream ingest, YouTube Live Start/Stop recording, automatic transition to `[2] 시간 선택` and `[3] 인식 영역` after stream capture, and in-place installer & in-app self-update features).
Output: `dist/installers/ArcadeClip-0.2.1-performance-20261021-r3-windows-arm64-user-setup.exe`.
Installer size: 339,114,659 bytes.
SHA-256: `f54de80b71a695e8927bd0aa235d79150dbb9b49fca14ac78a5940c71c2fed1c`.

## Revision 2

Payload: `dist/ArcadeClip-arm64_installable` (copied from the prior bundle).
Output: `dist/installers/ArcadeClip-0.2.1-performance-20261005-r2-windows-arm64-user-setup.exe`.
Start Menu / All apps registration is now selectable (default enabled); desktop
shortcut remains optional (default disabled). Windows installed-apps/uninstall
registration remains enabled. Pinning to Start is a manual user action.

`prepare_installer_licenses.py` collects both actual embedded runtimes before
compilation: Python 3.13.12, external FFmpeg 8.1.3, package notices, missing
ANTLR/FlatBuffers/RapidOCR notices, native helper and compiler runtime notices.
The installer displays the component explanation plus unmodified MIT/GPL texts.
The bundle includes its application source archive and `SOURCE-INFO.md`.
Complete third-party Corresponding Source distribution remains a separate
requirement before public redistribution; this is not certified by the build.
The preview/performance packagers now preserve the bundle-specific licenses.json.

At the user's request, revision 2 runs compilation only: no detailed validation,
installation or application launch. The older result below describes revision 1.
Revision 2 compiled successfully in 149 seconds.
SHA-256: `a00594f1e1cf98931eb5d5ec04d0d1233b946d73990c6650fbe1664fcb54de98`.

## Revision 1 (previous build)

Source payload: `dist/ArcadeClip-arm64_analysis-options`, the last actual verified
ARM64 build. The x64 performance patch delivery is source work, not a built x64
release, and is not substituted for this payload.

Installer definition: `run/installer/ArcadeClip-user.iss`.
Rebuild: `run/build_user_installer.ps1` using Inno Setup 6.7.3 ISCC.
Compiler download: official jrsoftware/issrc release is-6_7_3, Authenticode valid,
publisher Pyrsys B.V. Compiler installed in `build/installer-tools/inno` for build
use only; it is not part of the application payload.

Configuration:
- `PrivilegesRequired=lowest`; no elevation request or all-users option.
- Windows 11 ARM64 with x64 compatibility, minimum build 22000.
- `%LOCALAPPDATA%\Programs\ArcadeClip-ARM64` default install location.
- Stable, dedicated ARM64 performance AppId; user Start Menu shortcuts and
  optional desktop shortcut. Standard per-user uninstall registration.
- Full bundled Python, PySide6/PyAV, FFmpeg, Deno and isolated x64 OCR runtime.
- Exclude Python bytecode caches and compiler debug/import-library artifacts.
- Preserve external user data; no wildcard deletion of profiles, jobs or videos.
- Application startup after interactive setup is optional; silent setup never
  starts the application automatically.
- Models/catalog data still follow the original application's first-use downloads.
  This is an offline runtime installer, not a preloaded catalog/model collection.

Output: `dist/installers/ArcadeClip-0.2.1-performance-20261005-windows-arm64-user-setup.exe`
with `.sha256` and `installer-build.log`.

Validation: use `run/verify_user_install.py SOURCE INSTALL REPORT` with the
installed embedded Python to check every packaged source file, PE architectures,
current-user uninstall registration, Start Menu shortcut and installed imports.
Installed GUI launch is checked separately. x64 release validation is unrelated.

## Result

Inno compilation succeeded in 508 seconds. Installer size: 331,407,864 bytes.
SHA-256: `3ba8983747348a88e4479a83dfe1a63fb1f032aa4963e6373643e25cc733fa76`.
The installer contains the complete previously verified standalone payload.
The request to execute installation and GUI launch was rejected by the user;
no installation, uninstall lifecycle or installed GUI smoke test was performed.
The prepared install/verify scripts remain available for a later authorized run.
The generated installer is unsigned.

Inno documentation:
- https://jrsoftware.org/ishelp/topic_setup_privilegesrequired.htm
- https://jrsoftware.org/ishelp/topic_setup_architecturesallowed.htm

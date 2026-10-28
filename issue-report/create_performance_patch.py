"""Build a scoped patch without changing the current app or Git index."""
import difflib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BASE = '9110b4d71cda511ac6ee3ed5b165349988de0bdb'
PREREQUISITE = ROOT / 'issue-report/recognition-improvements.patch'
def git(*args, **kwargs):
    return subprocess.check_output(['git', *args], cwd=ROOT, **kwargs)
stage = Path(tempfile.mkdtemp(prefix='performance-patch-', dir=ROOT / 'build'))
environment = dict(os.environ, GIT_CEILING_DIRECTORIES=str(stage.parent))
with zipfile.ZipFile(io.BytesIO(git('archive', '--format=zip', BASE))) as archive:
    archive.extractall(stage)
subprocess.run(['git', 'apply', '--no-index', '--check', str(PREREQUISITE)], cwd=stage, env=environment, check=True)
subprocess.run(['git', 'apply', '--no-index', str(PREREQUISITE)], cwd=stage, env=environment, check=True)
assert (stage / 'src/freeplay.py').exists()
def original(path):
    return (stage / path).read_text(encoding='utf-8')
def local(path):
    return (ROOT / path).read_text(encoding='utf-8')
def replace(text, old, new):
    assert old in text, old[:120]
    return text.replace(old, new)

paths = '''src/preview.py src/profile_panel.py src/app.py src/media.py src/video_sampling.py
src/jacket_recognition.py src/recognition.py src/workspace_ui.py src/advanced_settings.py
src/tests/test_preview.py src/tests/test_app.py src/tests/test_recognition.py
run/pysidedeploy.spec src/assets/preview.qml src/pipeline.py src/gpu_image.py run/gpu_roi.c
src/tests/test_pipeline.py src/tests/test_gpu_image.py run/verify_preview.py
run/verify_preview_lifecycle.py run/verify_gpu_analysis.py run/verify_analysis_options.py
run/diagnose_decode_memory.py'''.split()
files = {p: local(p) for p in paths}

# Preserve the prerequisite implementation; emit only incremental performance edits.
p = 'src/jacket_recognition.py'
base, current = original(p), files[p]
current = base[:base.index('def scan_jackets(')] + current[current.index('def scan_jackets('):]
current = replace(current, 'options["sample_seconds"], cancel, gpu_convert=gpu if gpu_convert is None else gpu_convert)',
                  'options["sample_seconds"], cancel)')
files[p] = current

p = 'src/profile_panel.py'
files[p] = files[p][:files[p].index('    def recognition_groups(')] + original(p)[original(p).index('    def recognition_groups('):]

# x64 deliverable loader; do not change the working ARM build.
p = 'src/gpu_image.py'
files[p] = replace(files[p], "platform.machine().upper() != 'ARM64'", "platform.machine().lower() not in ('amd64', 'x86_64') or ctypes.sizeof(ctypes.c_void_p) != 8")
files[p] = files[p].replace('ARM64 Windows helper', 'x64 Windows helper').replace('gpu_roi_arm64.dll', 'gpu_roi_x64.dll')
p = 'src/tests/test_gpu_image.py'
files[p] = files[p].replace('ARM64 Windows', 'x64 Windows')
p = 'run/verify_preview.py'
files[p] = files[p].replace('bundled ARM64 Python', 'x64 Python with project dependencies')

files['run/build_gpu_roi.py'] = '''"""Build the x64 D3D11 helper. MSVC by default, or --zig PATH."""
import argparse
import os
from pathlib import Path
import struct
import subprocess

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--zig', type=Path, help='Optional Zig executable; otherwise use Visual Studio x64 tools')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    build = root / 'build/gpu-roi-x64'
    build.mkdir(parents=True, exist_ok=True)
    source = root / 'run/gpu_roi.c'
    output = build / 'gpu_roi_x64.dll'
    if args.zig:
        subprocess.run([str(args.zig.resolve()), 'cc', '-target', 'x86_64-windows-gnu', '-O2',
                        '-shared', str(source), '-o', str(output), '-ld3d11', '-ldxguid', '-lole32'],
                       check=True, env=dict(os.environ, ZIG_GLOBAL_CACHE_DIR=str(build / 'zig-cache')))
    else:
        vswhere = Path(os.environ.get('ProgramFiles(x86)', r'C:\\Program Files (x86)')) / 'Microsoft Visual Studio/Installer/vswhere.exe'
        installation = subprocess.check_output([str(vswhere), '-latest', '-products', '*',
            '-requires', 'Microsoft.VisualStudio.Component.VC.Tools.x86.x64', '-property',
            'installationPath'], text=True).strip()
        if not installation:
            raise RuntimeError('Visual Studio x64 C++ build tools are required')
        setup = Path(installation) / 'VC/Auxiliary/Build/vcvars64.bat'
        if any(c in str(root) + str(setup) for c in ('%', '\\n', '\\r', '"')):
            raise ValueError('Build path contains unsupported command characters')
        command = build / 'compile.cmd'
        command.write_text('@echo off\\nsetlocal DisableDelayedExpansion\\ncall "' + str(setup) + '" >nul\\n'
            'if errorlevel 1 exit /b 1\\ncl /nologo /O2 /MT /LD /TC "' + str(source) + '" '
            '/Fo"' + str(build / 'gpu_roi.obj') + '" /link /MACHINE:X64 /OUT:"' + str(output) + '" '
            'd3d11.lib dxguid.lib ole32.lib\\nexit /b %errorlevel%\\n', encoding='utf-8')
        subprocess.run(['cmd.exe', '/d', '/c', str(command)], check=True, cwd=build)
    data = output.read_bytes()
    pe = struct.unpack_from('<I', data, 0x3c)[0]
    if data[pe:pe+4] != b'PE\\0\\0' or struct.unpack_from('<H', data, pe+4)[0] != 0x8664:
        raise RuntimeError('GPU helper is not an x64 PE binary')
    print(output)

if __name__ == '__main__':
    main()
'''

p = 'run/build_windows.ps1'
text = original(p)
text = replace(text, "uv run --locked python run/compile_messages.py", "uv run --locked python run/build_gpu_roi.py\nif ($LASTEXITCODE -ne 0) { throw 'x64 GPU helper build failed.' }\nuv run --locked python run/compile_messages.py")
needle = "foreach ($asset in (Get-ChildItem -LiteralPath (Join-Path $projectRoot 'src/assets') -File)) {"
text = replace(text, needle, '''$gpuHelper = Join-Path $projectRoot 'build/gpu-roi-x64/gpu_roi_x64.dll'
Copy-Item -LiteralPath $gpuHelper -Destination (Join-Path $bundle 'assets/gpu_roi_x64.dll')
if ((Get-FileHash $gpuHelper).Hash -ne (Get-FileHash (Join-Path $bundle 'assets/gpu_roi_x64.dll')).Hash) {
    throw 'Bundled GPU helper differs from build output.'
}
foreach ($asset in (Get-ChildItem -LiteralPath (Join-Path $projectRoot 'src/assets') -File | Where-Object { $_.Extension -notin @('.dll', '.pdb', '.lib') })) {''')
text = replace(text, "@('qwindows.dll', '*ffmpegmediaplugin.dll', 'Qt6Multimedia.dll', 'avcodec*.dll')",
                  "@('qwindows.dll', '*ffmpegmediaplugin.dll', 'Qt6Multimedia.dll', 'Qt6Qml.dll', 'Qt6Quick.dll', 'Qt6QuickWidgets.dll', 'avcodec*.dll')")
files[p] = text
p = 'run/pysidedeploy.spec'
files[p] = replace(files[p], '--include-data-dir=src/assets=assets',
                  '--include-data-dir=src/assets=assets --noinclude-data-files=assets/*.dll --noinclude-data-files=assets/*.pdb --noinclude-data-files=assets/*.lib')

# Build script discovers the existing VS installation on Windows runners.
p = '.github/workflows/release.yml'
files[p] = replace(original(p), '      - name: Read the app version', '''      - name: Verify x64 Python architecture
        run: uv run --locked python -c "import struct,platform; assert struct.calcsize('P') == 8 and platform.machine().lower() in ('amd64','x86_64')"

      - name: Read the app version''')

# Translate only this patch's new strings; compile .mo in the existing build step.
messages = {
    'GPU 영상 디코딩': 'GPU video decoding',
    'GPU 이미지 변환': 'GPU image conversion',
    '디코딩·변환·판독 겹쳐 처리': 'Overlap decoding, conversion and recognition',
    '실험용 D3D11VA 디코딩. 지원하지 않으면 CPU로 복귀합니다.': 'Experimental D3D11VA decoding. Falls back to CPU when unsupported.',
    '선택된 프레임의 영역·색상 변환에 GPU를 사용합니다.': 'Use the GPU to crop and convert colors of selected frames.',
    '대기 프레임 수를 제한합니다. 기존 CPU 경계 버퍼 사용 시 순차 처리합니다.': 'Limits queued frames. Runs sequentially when the existing CPU boundary buffer is used.',
    'GPU·겹쳐 처리 옵션은 3번 인식 영역 화면에서 변경합니다.': 'Change GPU and overlap options in step 3, Recognition regions.',
    'GPU 처리를 사용할 수 없어 CPU로 계속합니다: {error}': 'GPU processing is unavailable; continuing on CPU: {error}',
}
p = 'src/locales/en/LC_MESSAGES/arcadeclip.po'
text = original(p).rstrip() + '\n\n'
for source, translated in messages.items():
    assert ('msgid ' + json.dumps(source, ensure_ascii=False)) not in text
    text += 'msgid ' + json.dumps(source, ensure_ascii=False) + '\nmsgstr ' + json.dumps(translated) + '\n\n'
files[p] = text.rstrip() + '\n'

files['docs/develop/PERFORMANCE-X64.md'] = '''# Performance improvements for Windows x64

Scope: GPU preview, lazy snapshots, visible-only crop updates, seek coalescing,
selected-frame conversion, native frame lifetime, independent analysis GPU
options and bounded ordered pipelining. Existing boundary recognition is preserved;
CPU single-worker boundary buffering disables prefetch. No proxy or partial decode.

No same-jacket cache, Free Play reset detection, ARM runtime or OCR bridge changes.
Base: 9110b4d71cda511ac6ee3ed5b165349988de0bdb.
Use the companion apply-improvements.py when combining the recognition and
performance patches; it selects a verified delta for either application order.
Image conversion switches apply to the song scan; the prerequisite's optional
Free Play observer retains its existing conversion behavior.

Build on Windows x64 using the existing run/build_windows.ps1. Visual Studio C++
x64 tools and Windows SDK are needed to build the helper (not to run the app).
Alternatively: python run/build_gpu_roi.py --zig <zig.exe> builds the helper only.
The release build compiles translations, includes preview.qml / Qt Quick, builds
the helper and copies gpu_roi_x64.dll into assets. Distribute the complete bundle.

Run python run/run_tests.py --no-display for logic tests, then display tests.
On an x64 Windows GPU machine set ARCADECLIP_TEST_GPU=1 and run test_gpu_image.
Use verify_preview.py / verify_preview_lifecycle.py for real rendering and shutdown;
verify_analysis_options.py / verify_gpu_analysis.py for actual source comparisons.
Measure process memory and wall time independently of summed parallel stage times.

The x64 native runtime and complete Nuitka release require real x64 validation;
cross-compilation or source-level tests are not proof of GPU runtime success.
The original CPU path remains available. Unsupported GPU processing warns and
resumes on CPU. GPU conversion currently supports NV12 SDR BT.601/709 only.
The step-3 analysis switches do not control Qt's preview renderer. For preview
diagnostics use ARCADECLIP_PREVIEW_RENDERER=software.
'''

for path, data in files.items():
    if path.endswith('.py'):
        compile(data, path, 'exec')
chunks = []
for path, new in sorted(files.items()):
    old_path = stage / path
    old = old_path.read_text(encoding='utf-8') if old_path.exists() else ''
    if old == new:
        continue
    chunks.append(f'diff --git a/{path} b/{path}\n')
    if not old_path.exists():
        chunks.append('new file mode 100644\n')
    chunks.extend(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
                  fromfile=f'a/{path}' if old_path.exists() else '/dev/null', tofile=f'b/{path}'))
patch = ROOT / 'issue-report/improved-performance.patch'
patch.write_text(''.join(chunks), encoding='utf-8', newline='\n')
subprocess.run(['git', 'apply', '--no-index', '--check', str(patch)], cwd=stage, env=environment, check=True)
subprocess.run(['git', 'apply', '--no-index', str(patch)], cwd=stage, env=environment, check=True)
for path, expected in files.items():
    assert (stage / path).read_text(encoding='utf-8') == expected, path
manifest = dict(base_commit=BASE, patch_sha256=hashlib.sha256(patch.read_bytes()).hexdigest(),
                prerequisite=PREREQUISITE.name, prerequisite_sha256=hashlib.sha256(PREREQUISITE.read_bytes()).hexdigest(),
                files=sorted(files), clean_apply='passed', isolated_test_directory=str(stage),
                x64_native_runtime='not validated', x64_release_build='not run')
(ROOT / 'issue-report/improved-performance-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print(json.dumps(manifest, indent=2))

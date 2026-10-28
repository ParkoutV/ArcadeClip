"""Build a pinned Windows AMD64 or ARM64 bundle on a compatible Windows host."""
import argparse
import platform
from concurrent.futures import ThreadPoolExecutor
import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tarfile
import time
import tomllib
import urllib.request
import zipfile

from pip._vendor.packaging.tags import cpython_tags, compatible_tags
from pip._vendor.packaging.utils import parse_wheel_filename

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'build/arm64'
ARCH = 'arm64'
OUT = ROOT / 'dist/ArcadeClip-arm64'
MACHINES = {'arm64': 0xaa64, 'amd64': 0x8664}
TARGETS = {'arm64': 'aarch64-windows-gnu', 'amd64': 'x86_64-windows-gnu'}
LOCK = tomllib.loads((ROOT / 'uv.lock').read_text(encoding='utf-8'))
PACKAGES = {p['name']: p for p in LOCK['package']}
APP = ['av', 'certifi', 'charset-normalizer', 'idna', 'mutagen', 'numpy',
       'packaging', 'pillow', 'pycryptodomex', 'pyside6', 'pyside6-addons',
       'pyside6-essentials', 'requests', 'shiboken6', 'urllib3', 'websockets',
       'yt-dlp', 'yt-dlp-ejs']
OCR = ['av', 'certifi', 'charset-normalizer', 'colorama', 'colorlog', 'flatbuffers',
       'idna', 'numpy', 'omegaconf', 'onnxruntime', 'opencv-python', 'packaging',
       'pillow', 'protobuf', 'pyclipper', 'pyyaml', 'rapidocr', 'requests',
       'shapely', 'six', 'tqdm', 'urllib3']


def write_readme():
    (OUT / 'README-WINDOWS.txt').write_text(
        f'ArcadeClip - Windows {ARCH.upper()}\n\n'
        'Run ArcadeClip.exe. Keep all files in this folder together.\n'
        'Python, dependencies, FFmpeg and Deno are included.\n'
        'OCR runs in an isolated AMD64 Python runtime.\n'
        'See BUILD-WINDOWS.md and build-manifest.json for build details.\n', encoding='utf-8')
    shutil.copy2(ROOT / 'docs/develop/WINDOWS.md', OUT / 'BUILD-WINDOWS.md')


def fetch(url, digest=None):
    key = hashlib.sha256(url.encode()).hexdigest()[:16]
    path = CACHE / 'downloads' / (key + '-' + url.rsplit('/', 1)[-1])
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        print('Download:', url, flush=True)
        for attempt in range(3):
            try:
                request_url = url + ('?download=1' if 'github.com/' in url and '?' not in url else '')
                req = urllib.request.Request(request_url, headers={'User-Agent': 'ArcadeClip-Windows-build'})
                with urllib.request.urlopen(req, timeout=60) as response:
                    chunks, received = [], 0
                    while chunk := response.read(1024 * 1024):
                        chunks.append(chunk)
                        received += len(chunk)
                        if received % (8 * 1024 * 1024) == 0:
                            print(f'  {received // (1024 * 1024)} MiB: {path.name}', flush=True)
                    payload = b''.join(chunks)
                break
            except (OSError, TimeoutError):
                if attempt == 2:
                    raise
                print('Retry:', url, flush=True)
                time.sleep(2)
        if digest and hashlib.sha256(payload).hexdigest() != digest:
            raise ValueError('Download checksum mismatch: ' + url)
        path.write_bytes(payload)
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest and actual != digest:
        raise ValueError('Cached checksum mismatch: ' + str(path))
    return path, actual


def initialize_inputs():
    inputs = json.loads((ROOT / 'run/windows.inputs.lock.json').read_text())
    host = 'arm64' if platform.machine().lower() in ('arm64', 'aarch64') else 'amd64'
    return {**{key: inputs[key] for key in ('python-arm64', 'python-amd64')},
            'ffmpeg': inputs['ffmpeg-' + ARCH], 'deno': inputs['deno-' + ARCH],
            'zig': inputs['zig-' + host]}


def unpack_zip(path, target):
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path) as archive:
        for item in archive.infolist():
            destination = (target / item.filename).resolve()
            if not destination.is_relative_to(target.resolve()):
                raise ValueError('Unsafe archive member: ' + item.filename)
        archive.extractall(target)


def wheel_for(name, arch):
    tags = list(cpython_tags((3, 13), platforms=['win_' + arch]))
    tags += list(compatible_tags((3, 13), interpreter='cp313', platforms=['win_' + arch]))
    ranks = {tag: index for index, tag in enumerate(tags)}
    choices = []
    for wheel in PACKAGES[name].get('wheels', []):
        filename = wheel['url'].rsplit('/', 1)[-1]
        compatible = parse_wheel_filename(filename)[3] & ranks.keys()
        if compatible:
            choices.append((min(ranks[tag] for tag in compatible), wheel))
    if not choices:
        raise ValueError(f'No locked wheel for {name} on {arch}')
    return min(choices, key=lambda choice: choice[0])[1]


def install_packages(names, arch, target):
    records = []
    wheels = [(name, wheel_for(name, arch)) for name in names]
    def download(item):
        name, wheel = item
        path, digest = fetch(wheel['url'], wheel['hash'].split(':')[1])
        return name, wheel, path, digest
    for name, wheel, path, digest in ThreadPoolExecutor(6).map(download, wheels):
        with zipfile.ZipFile(path) as archive:
            for item in archive.infolist():
                if item.is_dir():
                    continue
                parts = Path(item.filename).parts
                if '.data' in parts[0]:
                    if parts[1] not in ('purelib', 'platlib'):
                        continue
                    parts = parts[2:]
                dest = target.joinpath(*parts)
                if not dest.resolve().is_relative_to(target.resolve()):
                    raise ValueError('Unsafe wheel member')
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(archive.read(item))
        records.append({'name': name, 'version': PACKAGES[name]['version'], 'url': wheel['url'], 'sha256': digest})
    return records


def machine(path):
    with path.open('rb') as stream:
        if stream.read(2) != b'MZ':
            return None
        stream.seek(0x3c)
        offset = struct.unpack('<I', stream.read(4))[0]
        stream.seek(offset)
        if stream.read(4) != b'PE\0\0':
            raise ValueError('Invalid PE: ' + str(path))
        return struct.unpack('<H', stream.read(2))[0]


def assemble():
    # A failed native dependency must return an error, not leave a Windows dialog.
    ctypes.windll.kernel32.SetErrorMode(0x8003)
    records = initialize_inputs()
    assets = {name: fetch(item['url'], item['sha256'])[0] for name, item in records.items()}
    if OUT.exists():
        raise FileExistsError(f'Output already exists: {OUT}. Choose a fresh --output directory.')
    OUT.mkdir(parents=True)
    for arch, folder in [(ARCH, 'runtime'), ('amd64', 'ocr-runtime')]:
        runtime = OUT / folder
        unpack_zip(assets['python-' + arch], runtime)
        (runtime / 'python313._pth').write_text('python313.zip\n.\nLib/site-packages\n../src\nimport site\n')
    records['app-packages'] = install_packages(APP, ARCH, OUT / 'runtime/Lib/site-packages')
    # Upstream archives include unused CRTs for other ABIs. None of the native
    # runtime's import tables references these; do not ship incompatible DLLs.
    records['omitted-unused-crt'] = []
    for relative in ('runtime/vcruntime140_1.dll',
                     'runtime/Lib/site-packages/PySide6/vccorlib140.dll',
                     'runtime/Lib/site-packages/shiboken6/vccorlib140.dll'):
        extra = OUT / relative
        if extra.is_file() and machine(extra) != MACHINES[ARCH]:
            records['omitted-unused-crt'].append({'path': relative, 'sha256': hashlib.sha256(extra.read_bytes()).hexdigest()})
            extra.unlink()
    records['ocr-packages'] = install_packages(OCR, 'amd64', OUT / 'ocr-runtime/Lib/site-packages')
    # ONNX Runtime/Pyclipper import these names directly. Do not rely on the
    # workstation's global VC++ Redistributable (NumPy only ships a renamed DLL).
    crt_wheel = wheel_for('shiboken6', 'amd64')
    crt_archive, crt_hash = fetch(crt_wheel['url'], crt_wheel['hash'].split(':')[1])
    with zipfile.ZipFile(crt_archive) as archive:
        for name in ('msvcp140.dll', 'msvcp140_1.dll'):
            (OUT / 'ocr-runtime' / name).write_bytes(archive.read('shiboken6/' + name))
        for name in archive.namelist():
            if not name.endswith('/') and 'license' in name.lower():
                dest = OUT / 'licenses/ocr-crt' / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(archive.read(name))
    records['ocr-crt'] = {'url': crt_wheel['url'], 'sha256': crt_hash,
                          'files': ['ocr-runtime/msvcp140.dll', 'ocr-runtime/msvcp140_1.dll']}
    antlr = PACKAGES['antlr4-python3-runtime']['sdist']
    path, digest = fetch(antlr['url'], antlr['hash'].split(':')[1])
    with tarfile.open(path) as archive:
        for item in archive.getmembers():
            if '/src/antlr4/' in item.name and item.isfile():
                relative = item.name.split('/src/', 1)[1]
                dest = OUT / 'ocr-runtime/Lib/site-packages' / relative
                if not dest.resolve().is_relative_to((OUT / 'ocr-runtime').resolve()):
                    raise ValueError('Unsafe antlr member')
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(archive.extractfile(item).read())
        info = OUT / 'ocr-runtime/Lib/site-packages/antlr4_python3_runtime-4.9.3.dist-info'
        info.mkdir(exist_ok=True)
        pkg_info = next(item for item in archive.getmembers() if item.name.count('/') == 1 and item.name.endswith('/PKG-INFO'))
        (info / 'METADATA').write_bytes(archive.extractfile(pkg_info).read())
        (info / 'RECORD').write_text('antlr4_python3_runtime-4.9.3.dist-info/METADATA,,\n')
    records['antlr-source'] = {'url': antlr['url'], 'sha256': digest}
    ffdir = CACHE / ('ffmpeg-' + records['ffmpeg']['sha256'][:12])
    unpack_zip(assets['ffmpeg'], ffdir)
    ffroot = next(p.parent for p in ffdir.rglob('bin') if p.is_dir())
    (OUT / 'tools').mkdir(exist_ok=True)
    for binary in (ffroot / 'bin').iterdir():
        if binary.name != 'ffplay.exe' and binary.is_file():
            shutil.copy2(binary, OUT / 'tools' / binary.name)
    unused_player = OUT / 'tools/ffplay.exe'
    if unused_player.is_file():
        unused_player.unlink()
    # Remove shared FFmpeg files left by an earlier build when selecting static tools.
    if not list((ffroot / 'bin').glob('*.dll')):
        for pattern in ('avcodec-*.dll', 'avdevice-*.dll', 'avfilter-*.dll', 'avformat-*.dll',
                        'avutil-*.dll', 'swresample-*.dll', 'swscale-*.dll'):
            for stale in (OUT / 'tools').glob(pattern):
                assert stale.resolve().is_relative_to(OUT.resolve())
                stale.unlink()
    for path in ffroot.iterdir():
        if path.is_file():
            shutil.copy2(path, OUT / 'tools' / path.name)
    for path in ffroot.rglob('*'):
        if path.is_file() and any(word in path.name.lower() for word in ('license', 'copyright', 'copying', 'notice')):
            dest = OUT / 'tools/notices' / path.relative_to(ffroot)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
    unpack_zip(assets['deno'], OUT / 'tools')
    for tool in ('ffmpeg', 'ffprobe', 'deno'):
        probe = subprocess.run([str(OUT / 'tools' / (tool + '.exe')),
                                '--version' if tool == 'deno' else '-version'],
                               capture_output=True, timeout=30)
        if probe.returncode or not probe.stdout:
            raise RuntimeError(f'{tool} startup failed ({probe.returncode}): {probe.stderr!r}')
    shutil.copytree(ROOT / 'src', OUT / 'src', dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__', 'tests', 'gpu_roi*.dll', '*.pdb', '*.lib'))
    shutil.copytree(ROOT / 'docs/manual', OUT / 'docs/manual', dirs_exist_ok=True)
    shutil.copytree(ROOT / 'run/license_sources', OUT / 'licenses', dirs_exist_ok=True)
    for name in ('start.py', 'LICENSE', 'DISTRIBUTION.md'):
        shutil.copy2(ROOT / name, OUT / name)
    shutil.copy2(ROOT / 'run/license_sources/COPYING.GPLv3', OUT / 'COPYING.GPLv3')
    (OUT / 'ArcadeClip_dbg.cmd').write_text('@echo off\r\n"%~dp0ArcadeClip.exe" --debug %*\r\n', encoding='ascii')
    (OUT / 'portable-runtime.json').write_text(json.dumps({'architecture': ARCH, 'ocr_python': 'ocr-runtime/python.exe'}, indent=2))
    zigdir = CACHE / ('zig-' + records['zig']['sha256'][:12])
    unpack_zip(assets['zig'], zigdir)
    zig = next(zigdir.rglob('zig.exe'))
    subprocess.run([sys.executable, str(ROOT / 'run/build_gpu_roi.py'), '--arch', ARCH,
                    '--zig', str(zig), '--output', str(OUT / f'src/assets/gpu_roi_{ARCH}.dll')], check=True)
    launcher_notices = OUT / 'licenses/launcher'
    launcher_notices.mkdir(parents=True, exist_ok=True)
    for relative in ('LICENSE', 'lib/libc/mingw/COPYING'):
        notice = zig.parent / relative
        if notice.is_file():
            shutil.copy2(notice, launcher_notices / notice.name)
    env = dict(os.environ, ZIG_GLOBAL_CACHE_DIR=str(CACHE / 'zig-cache'))
    subprocess.run([str(zig), 'cc', '-target', TARGETS[ARCH], '-O2', '-s', '-Wl,--subsystem,windows',
                    str(ROOT / 'run/windows_launcher.c'), '-o', str(OUT / 'ArcadeClip.exe'),
                    '-lkernel32', '-luser32'], env=env, check=True)
    old_symbols = OUT / 'ArcadeClip.pdb'
    if old_symbols.is_file():
        old_symbols.unlink()
    binaries = []
    for path in OUT.rglob('*'):
        if path.suffix.lower() not in ('.exe', '.dll', '.pyd'):
            continue
        architecture = machine(path)
        relative = path.relative_to(OUT).as_posix()
        expected = 0x8664 if relative.startswith('ocr-runtime/') else MACHINES[ARCH]
        if architecture != expected:
            raise ValueError(f'Unexpected architecture: {relative}: {architecture!r}')
        binaries.append({'path': relative, 'machine': hex(architecture),
                         'kind': 'x64' if expected == 0x8664 else 'ARM64'})
    records['binaries'] = binaries
    records['architecture'] = ARCH
    records['version'] = tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']['version']
    records['notes'] = ['Native embedded Python app with an isolated AMD64 OCR runtime.',
                        'Jacket data and OCR models download on first use.']
    (OUT / 'build-manifest.json').write_text(json.dumps(records, indent=2) + '\n')
    subprocess.run([str(OUT / 'runtime/python.exe'), '-X', 'utf8',
                    str(ROOT / 'run/prepare_installer_licenses.py'), str(OUT)], check=True)
    probe = ROOT / 'build/installer-tools/runtime-probe.exe'
    probe.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(zig), 'cc', '-target', 'x86_64-windows-gnu', '-O2', '-s', '-municode',
                    str(ROOT / 'run/runtime_probe.c'), '-o', str(probe), '-lkernel32'],
                   env=env, check=True)
    write_readme()
    print('Built:', OUT, 'PE files:', len(binaries), flush=True)


def main(arguments=None):
    global ARCH, OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arch', choices=('amd64', 'arm64'), required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(arguments)
    if os.name != 'nt':
        parser.error('Run on Windows with support for the target architecture.')
    ARCH = args.arch
    OUT = (args.output or ROOT / ('dist/ArcadeClip-' + ARCH)).resolve()
    assemble()


if __name__ == '__main__':
    main()

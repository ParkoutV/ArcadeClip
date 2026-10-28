"""Exercise eight installer choices on Windows 11 ARM64 without app registration.

Requires both completed bundles, Inno Setup and the compiled runtime probe.
Test-only builds force each architecture branch; AMD64 binaries run in emulation.
All fixture files and logs stay under .validation-data/installer.
"""
import configparser
import json
import os
from pathlib import Path
import subprocess
import shutil

root = Path(__file__).resolve().parents[1]
fixture = root / '.validation-data/installer'
fixture.mkdir(parents=True, exist_ok=True)
compiler = root / 'build/installer-tools/inno/ISCC.exe'
probe = root / 'build/installer-tools/runtime-probe.exe'
results = []
for arch in ('amd64', 'arm64'):
    payload = fixture / ('payload-' + arch)
    for relative in ('runtime/Lib/site-packages/dependency.txt', 'runtime/python.exe',
                     'tools/ffmpeg.exe', 'tools/ffprobe.exe', 'tools/deno.exe',
                     'ocr-runtime/python.exe', 'ArcadeClip.exe', 'INSTALLER-LICENSE.txt', 'payload.txt'):
        path = payload / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(arch)
    (payload / 'src/assets').mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / 'src/assets/icon.ico', payload / 'src/assets/icon.ico')
for arch in ('amd64', 'arm64'):
    bundle = root / ('dist/ArcadeClip-' + arch)
    if not (bundle / 'tools/ffmpeg.exe').exists():
        raise RuntimeError(f'Build the {arch} bundle first.')
    with (fixture / ('compile-' + arch + '.log')).open('w') as log:
        subprocess.run([str(compiler), '/DTestBuild', '/DTestArchitecture=' + arch,
                        '/DAmd64Bundle=' + str(fixture / 'payload-amd64'), '/DArm64Bundle=' + str(fixture / 'payload-arm64'),
                        '/DAppVersion=0.3.0', '/DRuntimeProbe=' + str(probe),
                        '/DOutputDir=' + str(fixture / ('output-' + arch)),
                        str(root / 'run/installer/ArcadeClip-universal.iss')], stdout=log, stderr=subprocess.STDOUT, check=True)
    for python in ('bundled', 'local'):
        for ffmpeg in ('bundled', 'local'):
            target = fixture / f'installed-{arch}-{python}-{ffmpeg}'
            installer = fixture / ('output-' + arch) / 'ArcadeClip-0.3.0-windows-universal-user-setup.exe'
            env = dict(os.environ, PATH=str(bundle / 'runtime') + ';' + str(bundle / 'tools') + ';' + os.environ['PATH'])
            subprocess.run([str(installer), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/TASKS=', '/NOICONS',
                            '/DIR=' + str(target), '/LOG=' + str(target) + '.log',
                            '/PYTHON=' + python, '/FFMPEG=' + ffmpeg], env=env, check=True, timeout=120)
            assert (target / 'payload.txt').read_text() == arch
            assert (target / 'runtime/python.exe').exists() == (python == 'bundled')
            assert (target / 'tools/ffmpeg.exe').exists() == (ffmpeg == 'bundled')
            assert (target / 'runtime/Lib/site-packages/dependency.txt').is_file()
            assert (target / 'tools/deno.exe').is_file()
            assert (target / 'ocr-runtime/python.exe').is_file()
            config = configparser.ConfigParser()
            config.read(target / 'runtime-config.ini', encoding='utf-16')
            assert config['Runtime']['Architecture'] == arch
            assert bool(config['Runtime']['Python']) == (python == 'local')
            assert bool(config['Runtime']['FFmpegDir']) == (ffmpeg == 'local')
            results.append(dict(arch=arch, python=python, ffmpeg=ffmpeg, passed=True))
            print(results[-1], flush=True)
(fixture / 'results.json').write_text(json.dumps(results, indent=2))

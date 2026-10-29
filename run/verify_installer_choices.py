"""Exercise eight installer choices on Windows 11 ARM64 without app registration.

Requires both completed bundles, Inno Setup and the compiled runtime probe.
Test-only builds allow each installer on the ARM64 test host; AMD64 binaries run in emulation.
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
                     'ArcadeClip.exe', 'INSTALLER-LICENSE.txt', 'payload.txt'):
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
        subprocess.run([str(compiler), '/DTestBuild', '/DTargetArchitecture=' + arch,
                        '/DBundleDir=' + str(fixture / ('payload-' + arch)),
                        '/DAppVersion=0.3.0', '/DRuntimeProbe=' + str(probe),
                        '/DOutputDir=' + str(fixture / ('output-' + arch)),
                        str(root / 'run/installer/ArcadeClip-user.iss')], stdout=log, stderr=subprocess.STDOUT, check=True)
    for python in ('bundled', 'local'):
        for ffmpeg in ('bundled', 'local'):
            target = fixture / f'installed-{arch}-{python}-{ffmpeg}'
            installer = fixture / ('output-' + arch) / f'ArcadeClip-0.3.0-windows-{arch}-user-setup.exe'
            env = dict(os.environ, PATH=';'.join(str(root / ('dist/ArcadeClip-' + candidate) / 'runtime') for candidate in ('amd64', 'arm64')) + ';' + str(bundle / 'tools'))
            subprocess.run([str(installer), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/TASKS=', '/NOICONS',
                            '/DIR=' + str(target), '/LOG=' + str(target) + '.log',
                            '/PYTHON=' + python, '/FFMPEG=' + ffmpeg], env=env, check=True, timeout=120)
            assert (target / 'payload.txt').read_text() == arch
            assert (target / 'runtime/python.exe').exists() == (python == 'bundled')
            assert (target / 'tools/ffmpeg.exe').exists() == (ffmpeg == 'bundled')
            assert (target / 'runtime/Lib/site-packages/dependency.txt').is_file()
            assert (target / 'tools/deno.exe').is_file()
            assert not (target / 'ocr-runtime').exists()
            config = configparser.ConfigParser()
            config.read(target / 'runtime-config.ini', encoding='utf-16')
            assert config['Runtime']['Architecture'] == arch
            assert config['Runtime']['Python'] == (str(bundle / 'runtime/python.exe') if python == 'local' else '')
            assert bool(config['Runtime']['FFmpegDir']) == (ffmpeg == 'local')
            results.append(dict(arch=arch, python=python, ffmpeg=ffmpeg, passed=True))
            print(results[-1], flush=True)

# Scan each architecture independently, regardless of PATH ordering or absence.
installer = fixture / 'output-arm64/ArcadeClip-0.3.0-windows-arm64-user-setup.exe'
for label, candidates in [('none', ()), ('amd-only', ('amd64',)), ('arm-only', ('arm64',)),
                          ('arm-first', ('arm64', 'amd64')), ('amd-first', ('amd64', 'arm64'))]:
    target = fixture / ('path-' + label)
    log = fixture / ('path-' + label + '.log')
    env = dict(os.environ, PATH=';'.join(str(root / ('dist/ArcadeClip-' + arch) / 'runtime') for arch in candidates))
    subprocess.run([str(installer), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART',
                    '/LANG=english', '/TASKS=', '/NOICONS', '/DIR=' + str(target), '/LOG=' + str(log),
                    '/PYTHON=bundled', '/FFMPEG=bundled'], env=env, check=True, timeout=120)
    messages = log.read_text(encoding='utf-8-sig')
    for arch in ('amd64', 'arm64'):
        expected = str(root / ('dist/ArcadeClip-' + arch) / 'runtime/python.exe') if arch in candidates else 'no compatible CPython 3.13 found'
        assert f'{arch.upper()} Python on PATH: {expected}' in messages
    results.append(dict(path=label, passed=True))
    print(results[-1], flush=True)

target = fixture / 'wrong-python'
env = dict(os.environ, PATH=str(root / 'dist/ArcadeClip-amd64/runtime'))
failed = subprocess.run([str(installer), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART',
                         '/TASKS=', '/NOICONS', '/DIR=' + str(target),
                         '/PYTHON=local', '/FFMPEG=bundled'], env=env, timeout=120)
assert failed.returncode != 0 and not (target / 'payload.txt').exists()
results.append(dict(wrong_architecture_rejected=True))
(fixture / 'results.json').write_text(json.dumps(results, indent=2))

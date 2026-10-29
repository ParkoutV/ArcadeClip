"""Reject incomplete or mixed-architecture payloads before installer compilation."""
import argparse
import json
from pathlib import Path
import struct


def machine(path):
    with path.open('rb') as stream:
        if stream.read(2) != b'MZ':
            raise ValueError(f'Not a PE binary: {path}')
        stream.seek(0x3c)
        stream.seek(struct.unpack('<I', stream.read(4))[0])
        if stream.read(4) != b'PE\0\0':
            raise ValueError(f'Invalid PE binary: {path}')
        return struct.unpack('<H', stream.read(2))[0]


def validate(bundle, arch):
    manifest = json.loads((bundle / 'build-manifest.json').read_text())
    if manifest['architecture'] != arch:
        raise ValueError('Payload architecture mismatch')
    for required in ('ArcadeClip.exe', 'start.py', 'portable-runtime.json', 'runtime/python.exe',
                     'tools/ffmpeg.exe', 'tools/ffprobe.exe', 'tools/deno.exe',
                     f'src/assets/gpu_roi_{arch}.dll', 'src/assets/preview.qml', 'src/licenses.json',
                     'COPYING.GPLv3', 'INSTALLER-LICENSE.txt', 'sources/ArcadeClip-source.zip'):
        if not (bundle / required).is_file():
            raise ValueError(f'Missing payload file: {required}')
    runtime = json.loads((bundle / 'portable-runtime.json').read_text())
    if runtime.get('ocr_backend') != 'native-onnx':
        raise ValueError('Rebuild payload with native ONNX OCR before packaging')
    if (bundle / 'ocr-runtime').exists():
        raise ValueError('Legacy OCR runtime must not be included in native bundles')
    if not (bundle / 'runtime/Lib/site-packages/onnxruntime').is_dir():
        raise ValueError('Missing native ONNX Runtime package')
    binaries = {p.relative_to(bundle).as_posix(): p for p in bundle.rglob('*')
                if p.suffix.lower() in ('.exe', '.dll', '.pyd')}
    recorded = {item['path']: item for item in manifest['binaries']}
    if binaries.keys() != recorded.keys():
        raise ValueError('Binary inventory differs from build manifest')
    for relative, path in binaries.items():
        expected = 0x8664 if arch == 'amd64' else 0xaa64
        if machine(path) != expected or int(recorded[relative]['machine'], 16) != expected:
            raise ValueError(f'Wrong native architecture: {relative}')
    print(f'{arch}: validated {len(binaries)} native binaries and required installer files')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('--arch', choices=('amd64', 'arm64'), required=True)
    args = parser.parse_args()
    validate(args.bundle.resolve(), args.arch)

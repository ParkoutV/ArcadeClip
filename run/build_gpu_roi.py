"""Compile the native D3D11 helper for either Windows architecture."""
import argparse
import os
from pathlib import Path
import subprocess

def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arch', choices=('amd64', 'arm64'), default='arm64')
    parser.add_argument('--zig', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    zig = args.zig or next((root / 'build/arm64/zig').rglob('zig.exe'))
    output = args.output or root / f'src/assets/gpu_roi_{args.arch}.dll'
    output.parent.mkdir(parents=True, exist_ok=True)
    target = {'amd64': 'x86_64', 'arm64': 'aarch64'}[args.arch] + '-windows-gnu'
    subprocess.run([str(zig), 'cc', '-target', target, '-O2', '-shared', '-s',
                    str(root / 'run/gpu_roi.c'), '-o', str(output),
                    '-ld3d11', '-ldxguid', '-lole32'], check=True,
                   env=dict(os.environ, ZIG_GLOBAL_CACHE_DIR=str(root / 'build/arm64/zig-cache')))


if __name__ == '__main__':
    main()

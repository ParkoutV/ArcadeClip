"""Architecture names used by native helpers and release assets."""
import platform
import struct
import sys


def normalize_architecture(value):
    return {'amd64': 'amd64', 'x64': 'amd64', 'x86_64': 'amd64',
            'arm64': 'arm64', 'aarch64': 'arm64'}.get(value.lower())


def process_architecture():
    # A DLL must match Python, even when x64 Python runs under ARM64 emulation.
    # Read the interpreter PE header; platform.machine may describe the host OS.
    if sys.platform == 'win32':
        with open(sys.executable, 'rb') as stream:
            if stream.read(2) == b'MZ':
                stream.seek(0x3c)
                stream.seek(struct.unpack('<I', stream.read(4))[0])
                if stream.read(4) == b'PE\0\0':
                    machine = struct.unpack('<H', stream.read(2))[0]
                    return {0x8664: 'amd64', 0xaa64: 'arm64'}.get(machine)
    return normalize_architecture(platform.machine())

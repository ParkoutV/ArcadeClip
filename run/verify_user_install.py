"""Read-only validation of a per-user standalone installation."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import winreg

source, installed, output = map(Path, sys.argv[1:4])
ctypes.windll.kernel32.SetErrorMode(0x8003)
def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()
checked = 0
for path in source.rglob('*'):
    if not path.is_file() or '__pycache__' in path.parts or path.suffix.lower() in ('.pyc', '.pyo', '.pdb', '.lib'):
        continue
    destination = installed / path.relative_to(source)
    assert destination.is_file(), str(destination)
    assert sha(path) == sha(destination), str(destination)
    checked += 1
def machine(relative):
    data = (installed / relative).read_bytes()
    offset = struct.unpack_from('<I', data, 0x3c)[0]
    return hex(struct.unpack_from('<H', data, offset+4)[0])
architectures = {p: machine(p) for p in ('ArcadeClip.exe', 'runtime/python.exe', 'tools/ffmpeg.exe',
                                      'src/assets/gpu_roi_arm64.dll', 'ocr-runtime/python.exe')}
assert architectures['runtime/python.exe'] == '0xaa64'
assert architectures['ocr-runtime/python.exe'] == '0x8664'
assert architectures['src/assets/gpu_roi_arm64.dll'] == '0xaa64'
key_name = r'Software\Microsoft\Windows\CurrentVersion\Uninstall\{33CE480B-F420-4C23-985C-E721563A135F}_is1'
with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_name, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
    location = winreg.QueryValueEx(key, 'InstallLocation')[0]
    uninstall = winreg.QueryValueEx(key, 'UninstallString')[0]
assert Path(location).resolve() == installed.resolve()
assert (installed / 'unins000.exe').is_file()
shortcut = Path(os.environ['APPDATA']) / 'Microsoft/Windows/Start Menu/Programs/ArcadeClip ARM64/ArcadeClip.lnk'
assert shortcut.is_file()
# Imports must resolve to installed modules, not repository source or system Python.
import av
import PySide6
import app
import gpu_image
assert Path(app.__file__).resolve().is_relative_to(installed.resolve())
converter = gpu_image.GPUImageConverter()
converter.close()
result = dict(checked_files=checked, install_directory=str(installed), user_registry=True,
              shortcut=str(shortcut), uninstall=uninstall, architectures=architectures,
              app_import=str(app.__file__), av_version=av.__version__, qt_version=PySide6.__version__)
output.write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=True), flush=True)

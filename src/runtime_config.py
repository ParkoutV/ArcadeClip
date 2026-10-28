"""App-private packages and installer-selected external tools."""
import configparser
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def configure_packages():
    if (ROOT / 'portable-runtime.json').is_file():
        sys.path.insert(0, str(ROOT / 'runtime/Lib/site-packages'))


def configured_tool(name):
    if name not in ('ffmpeg', 'ffprobe'):
        return None
    config = configparser.ConfigParser(interpolation=None)
    config.read(ROOT / 'runtime-config.ini', encoding='utf-16')
    directory = config.get('Runtime', 'FFmpegDir', fallback='')
    if not directory:
        return None
    path = Path(directory) / (name + '.exe')
    if not path.is_absolute() or not path.is_file():
        raise RuntimeError('The selected local FFmpeg is missing. Run Setup again to select bundled FFmpeg.')
    return str(path)

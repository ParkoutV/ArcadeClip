"""Collect actual installed package notices from one embedded runtime."""
import importlib.metadata
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect_licenses import collect, collect_external

if __name__ == '__main__':
    manifest = json.loads(Path(sys.argv[1]).read_text())
    role = sys.argv[2]
    entries = collect([p['name'] for p in manifest[role + '-packages']])
    if role == 'arm':
        entries.extend(collect_external(Path(sys.argv[1]).parent / 'tools'))
    else:
        entries.append({'name': 'Python runtime (x64 OCR)', 'version': sys.version.split()[0],
                        'license': 'PSF-2.0', 'homepage': 'https://www.python.org/', 'urls': [],
                        'notices': [{'file': 'LICENSE.txt', 'text': (Path(sys.base_prefix) / 'LICENSE.txt').read_text()}]})
    Path(sys.argv[3]).write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding='utf-8')

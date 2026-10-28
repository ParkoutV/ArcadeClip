"""Inspect the running embedded runtime, without importing repository packages."""
import importlib.metadata as metadata
import json
from pathlib import Path
import sys

role, output = sys.argv[1:]
entries = []
for package in sorted(metadata.distributions(), key=lambda p: p.metadata['Name'].lower()):
    notices = []
    for relative in package.files or []:
        name = Path(str(relative)).name.lower()
        if (name.startswith(('license', 'copying', 'notice', 'copyright')) or '/licenses/' in str(relative).replace('\\', '/').lower()):
            path = Path(package.locate_file(relative))
            if path.is_file() and path.suffix.lower() in ('', '.txt', '.md', '.rst'):
                notices.append(dict(file=str(relative), text=path.read_text(encoding='utf-8', errors='replace')))
    item = package.metadata
    entries.append(dict(name=item['Name'] + ' (' + role + ')', version=package.version,
        license=item.get('License-Expression') or item.get('License') or '; '.join(item.get_all('Classifier', [])),
        homepage=item.get('Home-page', ''), urls=item.get_all('Project-URL', []), notices=notices))
entries.append(dict(name='Python runtime (' + role + ')', version=sys.version.split()[0],
    license='PSF-2.0 and included notices', homepage='https://www.python.org/', urls=[],
    notices=[dict(file='LICENSE.txt', text=(Path(sys.base_prefix)/'LICENSE.txt').read_text(encoding='utf-8'))]))
Path(output).write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(dict(role=role, packages=len(entries), missing_notices=[e['name'] for e in entries if not e['notices']]), ensure_ascii=True))

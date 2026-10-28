"""Stage or archive the preview update using the already verified ARM64 runtime.

Run with the bundled Python. Default stages a separate folder; --archive creates
and verifies its ZIP after native validation. No network or dependency changes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'dist/ArcadeClip-arm64_improved'
OUT = ROOT / 'dist/ArcadeClip-arm64_preview'
ZIP = ROOT / 'dist/ArcadeClip-0.2.1-windows-arm64-preview-improved.zip'
parser = argparse.ArgumentParser()
parser.add_argument('--archive', action='store_true')
args = parser.parse_args()

if not args.archive:
    if not OUT.exists():
        shutil.copytree(BASE, OUT, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copytree(ROOT / 'src', OUT / 'src', dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'tests', 'licenses.json'))
    shutil.copy2(ROOT / 'docs/develop/PREVIEW-PERFORMANCE.md', OUT / 'PREVIEW-PERFORMANCE.md')
    manifest = {'base': BASE.name, 'proxy': False, 'renderer': 'Qt Quick VideoOutput',
                'files': {}}
    for name in ('preview.py', 'profile_panel.py', 'app.py', 'assets/preview.qml'):
        manifest['files'][name] = hashlib.sha256((OUT / 'src' / name).read_bytes()).hexdigest()
    (OUT / 'preview-improvement.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print('Staged:', OUT)
else:
    assert (OUT / 'preview-improvement.json').is_file()
    # Refresh the checkpoint after validation; source files must stay unchanged.
    manifest = json.loads((OUT / 'preview-improvement.json').read_text())
    for name, digest in manifest['files'].items():
        assert hashlib.sha256((OUT / 'src' / name).read_bytes()).hexdigest() == digest
        assert hashlib.sha256((ROOT / 'src' / name).read_bytes()).hexdigest() == digest
    shutil.copy2(ROOT / 'docs/develop/PREVIEW-PERFORMANCE.md', OUT / 'PREVIEW-PERFORMANCE.md')
    with zipfile.ZipFile(ZIP, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=5) as archive:
        for path in sorted(OUT.rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix not in ('.pyc', '.pdb'):
                archive.write(path, Path(OUT.name) / path.relative_to(OUT))
    with zipfile.ZipFile(ZIP) as archive:
        assert archive.testzip() is None
        count = len(archive.infolist())
    digest = hashlib.file_digest(ZIP.open('rb'), 'sha256').hexdigest()
    ZIP.with_suffix('.zip.sha256').write_text(digest + '  ' + ZIP.name + '\n', encoding='ascii')
    print(json.dumps({'zip': str(ZIP), 'bytes': ZIP.stat().st_size, 'files': count, 'sha256': digest}))

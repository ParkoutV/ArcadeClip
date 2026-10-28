"""Refresh notices from the actual standalone payload before installer compilation."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'run'))
import collect_licenses

bundle = Path(sys.argv[1]).resolve()
licenses = bundle / 'licenses'
manifest = json.loads((bundle / 'build-manifest.json').read_text(encoding='utf-8'))
assert '/ffmpeg-8.1.3/' in manifest['ffmpeg']['url'], 'Review notices for the new FFmpeg build'
shutil.copyfile(ROOT / 'run/license_sources/installer/FFmpeg-8.1.3-LICENSE.md', licenses / 'LICENSE.md')
sources = json.loads((licenses / 'sources.json').read_text(encoding='utf-8'))
# The COPYING texts are unchanged standard GNU licenses; LICENSE.md is build-version specific.
sources = {k: v.replace('/n9.0.1/', '/n8.1.3/') for k, v in sources.items()}
(licenses / 'sources.json').write_text(json.dumps(sources, indent=2), encoding='utf-8')
entries = []
for role, runtime in [(manifest.get('architecture', 'arm64').upper(), 'runtime'), ('OCR-x64', 'ocr-runtime')]:
    target = licenses / ('inventory-' + role + '.json')
    subprocess.run([str(bundle / runtime / 'python.exe'), '-X', 'utf8',
                    str(ROOT / 'run/inventory_runtime_licenses.py'), role, str(target)],
                   check=True, creationflags=subprocess.CREATE_NO_WINDOW)
    entries.extend(json.loads(target.read_text(encoding='utf-8')))
fallback = {
    'antlr4-python3-runtime': (ROOT / 'run/license_sources/installer/ANTLR-LICENSE.txt',
        'https://github.com/antlr/antlr4/tree/4.9.3'),
    'flatbuffers': (ROOT / 'run/license_sources/installer/FlatBuffers-LICENSE.txt',
        'https://github.com/google/flatbuffers/tree/v25.12.19'),
    'rapidocr': (ROOT / 'run/license_sources/RapidOCR-LICENSE.txt',
        'https://github.com/RapidAI/RapidOCR/tree/v3.9.2'),
}
for entry in entries:
    if not entry['notices']:
        path, url = fallback[entry['name'].split(' (')[0]]
        entry['notices'] = [{'file': url, 'text': path.read_text(encoding='utf-8')}]
        shutil.copyfile(path, licenses / path.name)
collect_licenses.SOURCES = licenses
entries.extend(e for e in collect_licenses.collect_external(bundle / 'tools')
               if e['name'] != 'Python runtime')
for name, paths in [
    ('ArcadeClip launcher and GPU ROI helper', [ROOT / 'LICENSE', *sorted((licenses / 'launcher').rglob('*'))]),
    ('OCR Microsoft runtime notices', sorted((licenses / 'ocr-crt').rglob('*'))),
]:
    notices = [{'file': p.name, 'text': p.read_text(encoding='utf-8', errors='replace')}
               for p in paths if p.is_file()]
    entries.append(dict(name=name, version='', license='See included notices', homepage='', urls=[], notices=notices))
entries.sort(key=lambda e: e['name'].lower())
(bundle / 'src/licenses.json').write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding='utf-8')
header = '''ArcadeClip Windows - 구성 요소 및 라이선스 안내 / License notice

ArcadeClip 자체 코드, 런처 및 GPU 이미지 변환 보조 코드는 MIT License입니다.
GPL 구성 요소를 포함하는 결합 배포물의 조건은 동봉된 DISTRIBUTION.md와
아래 GPLv3 전문을 참고하세요. 외부 구성 요소의 저작권과 개별 라이선스는 유지됩니다.
Python 3.13.12 (AMD64/ARM64 앱 및 OCR x64), PySide6/Qt, PyAV, FFmpeg 8.1.3,
Deno, OCR 및 기타 내장 패키지의 버전별 원문은 src/licenses.json과 licenses 폴더에
있으며 프로그램의 오픈소스 라이선스 보기에서도 확인할 수 있습니다.
이 고지는 외부 구성 요소의 수정·재배포 권리를 제한하지 않습니다.
소스 및 빌드 정보: SOURCE-INFO.md, build-manifest.json, sources 폴더.

ArcadeClip's own code, launcher and GPU helper are MIT licensed. Existing third-party
licenses remain in effect. See DISTRIBUTION.md, src/licenses.json and licenses/ for
component notices, and SOURCE-INFO.md for source availability and its limitations.
The following original license texts are reproduced without modification.

--- ArcadeClip MIT License ---
'''
(bundle / 'INSTALLER-LICENSE.txt').write_text(header + (ROOT / 'LICENSE').read_text(encoding='utf-8')
    + '\n--- GNU GPL version 3 ---\n' + (bundle / 'COPYING.GPLv3').read_text(encoding='utf-8'), encoding='utf-8-sig')
source_info = '''# Source and build information

This is a modified ArcadeClip community build, not an unmodified upstream release.
sources/ArcadeClip-source.zip contains the bundled application sources and local build
scripts, including the launcher and GPU ROI helper source. build-manifest.json records
download URLs, versions and hashes for the embedded runtimes, wheels and external tools.
The actual FFmpeg configure options and license report are recorded in src/licenses.json.

External FFmpeg build source: {source}
External FFmpeg upstream: https://github.com/FFmpeg/FFmpeg/tree/n8.1.3
Python: https://www.python.org/downloads/release/python-31312/
Other package project URLs and original notices appear in src/licenses.json.

Distribution limitation: this archive is the application source, NOT a complete
Corresponding Source archive for all third-party binaries. Before public redistribution,
provide the exact corresponding sources, dependency sources, patches and build scripts
required by the GPL/LGPL components (including FFmpeg variants inside PyAV/Qt/OpenCV).
Generic upstream links alone do not establish that requirement has been fulfilled.
'''.format(source=manifest['ffmpeg']['source'])
(bundle / 'SOURCE-INFO.md').write_text(source_info, encoding='utf-8')
(bundle / 'sources').mkdir(exist_ok=True)
with zipfile.ZipFile(bundle / 'sources/ArcadeClip-source.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
    for base, prefix in [(bundle / 'src', 'src'), (ROOT / 'run', 'run'),
                         (ROOT / 'docs', 'docs'), (ROOT / '.github', '.github')]:
        for path in sorted(base.rglob('*')):
            if path.is_file() and not any(p in ('__pycache__', '.venv') for p in path.parts) and path.suffix not in ('.pyc', '.dll', '.exe', '.pdb', '.lib'):
                archive.write(path, str(Path(prefix) / path.relative_to(base)))
    for name in ('start.py', 'README.md', 'LICENSE', 'DISTRIBUTION.md', 'pyproject.toml', 'uv.lock'):
        path = ROOT / name
        if path.exists(): archive.write(path, name)
assert all(e['notices'] for e in entries)
assert all(e['version'] == '3.13.12' for e in entries if e['name'].startswith('Python runtime'))
assert '9.0.1' not in next(e['version'] for e in entries if e['name'] == 'ffmpeg (executable)')
print(f'Refreshed {len(entries)} component notices and application source archive.')

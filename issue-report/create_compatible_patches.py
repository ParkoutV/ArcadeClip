"""Generate both standalone patches' directional compatibility deltas."""
import hashlib
import io
import json
import os
from pathlib import Path
import runpy
import subprocess
import tempfile
import zipfile
import difflib

root = Path(__file__).resolve().parents[1]
report = root / 'issue-report'
namespace = runpy.run_path(str(report / 'create_performance_patch.py'))
base = namespace['BASE']
archive = subprocess.check_output(['git', 'archive', '--format=zip', base], cwd=root)
with zipfile.ZipFile(io.BytesIO(archive)) as z:
    baseline = {name: z.read(name) for name in z.namelist() if not name.endswith('/')}
def normalized(data):
    return data if b'\0' in data else data.replace(b'\r\n', b'\n')
baseline = {name: normalized(data) for name, data in baseline.items()}
prerequisite = report / 'recognition-improvements.patch'
old_patch = prerequisite.read_text(encoding='utf-8')
old_paths = [line.split(' b/', 1)[1] for line in old_patch.splitlines() if line.startswith('diff --git ')]
stage = namespace['stage']
combined = dict(baseline)
for name in set(old_paths) | set(namespace['files']):
    combined[name] = normalized((stage / name).read_bytes())

# Recreate recognition-only state independently of the current working tree.
recognition_dir = Path(tempfile.mkdtemp(prefix='recognition-state-', dir=root / 'build'))
env = dict(os.environ, GIT_CEILING_DIRECTORIES=str(recognition_dir.parent))
with zipfile.ZipFile(io.BytesIO(archive)) as z:
    z.extractall(recognition_dir)
subprocess.run(['git', 'apply', '--no-index', str(prerequisite)], cwd=recognition_dir, env=env, check=True)
recognition = dict(baseline)
for name in old_paths:
    recognition[name] = normalized((recognition_dir / name).read_bytes())

performance = dict(baseline)
for name, data in namespace['files'].items():
    performance[name] = data.encode('utf-8')
def edit(name, fn):
    performance[name] = fn(performance[name].decode('utf-8'), baseline.get(name, b'').decode('utf-8')).encode('utf-8')
def jackets(current, original):
    current = original[:original.index('def scan_jackets(')] + current[current.index('def scan_jackets('):]
    current = current.replace('    match_cache = {}\n', '')
    current = current.replace('_identify_batch(batch, catalog, options, cancel, match_cache)', '_identify_batch(batch, catalog, options, cancel)')
    current = current[:current.index('    freeplay = None\n')] + current[current.index('    def rectangle('):]
    current = current.replace('on_frame=observe_frame if buffer or freeplay else None', 'on_frame=buffer.observe if buffer else None')
    current = current.replace('        if freeplay:\n            freeplay.close()\n', '')
    return current.replace('    if freeplay:\n        candidates = freeplay.split(candidates)\n', '')
edit('src/jacket_recognition.py', jackets)
edit('src/profile_panel.py', lambda c, b: (c[:c.index('    def recognition_groups(')] + b[b.index('    def recognition_groups('):]).replace('    QCheckBox, QComboBox,', '    QComboBox,'))
edit('src/tests/test_recognition.py', lambda c, b: c[:c.index('    def test_freeplay_')] + c[c.index('    def test_boundary_buffer_'):])
edit('src/locales/en/LC_MESSAGES/arcadeclip.po', lambda c, b: b.rstrip() + '\n\n' + c[len(recognition['src/locales/en/LC_MESSAGES/arcadeclip.po'].decode('utf-8').rstrip())+2:])

def patch_between(before, after):
    chunks = []
    for name in sorted(set(before) | set(after)):
        old, new = before.get(name, b''), after.get(name, b'')
        if old == new:
            continue
        if b'\0' in old or b'\0' in new:
            # The only binary change is the existing recognition translation.
            assert name.endswith('.mo') and old == baseline[name] and new == recognition[name]
            prefix = f'diff --git a/{name} b/{name}\n'
            body = old_patch.split(prefix, 1)[1].split('diff --git ', 1)[0]
            chunks.append(prefix + body)
            continue
        chunks.append(f'diff --git a/{name} b/{name}\n')
        if name not in before:
            chunks.append('new file mode 100644\n')
        chunks.extend(difflib.unified_diff(old.decode('utf-8').splitlines(keepends=True), new.decode('utf-8').splitlines(keepends=True),
            fromfile=f'a/{name}' if name in before else '/dev/null', tofile=f'b/{name}'))
    return ''.join(chunks)

compat = report / 'performance-compat'
compat.mkdir(exist_ok=True)
patches = {
    'improved-performance.patch': (baseline, performance),
    'performance-compat/performance-after-recognition.patch': (recognition, combined),
    'performance-compat/recognition-after-performance.patch': (performance, combined),
}
for name, (before, after) in patches.items():
    (report / name).write_text(patch_between(before, after), encoding='utf-8', newline='\n')

paths = sorted(name for name in set(combined) | set(baseline) if combined.get(name) != baseline.get(name))
def digest(data):
    return hashlib.sha256(normalized(data)).hexdigest() if data is not None else None
states = {name: {p: digest(tree.get(p)) for p in paths} for name, tree in
          [('base', baseline), ('recognition', recognition), ('performance', performance), ('combined', combined)]}
manifest = dict(base_commit=base, states=states, patches={p: hashlib.sha256((report / p).read_bytes()).hexdigest()
    for p in ['recognition-improvements.patch', *patches]},
    validation=dict(x64_gpu_runtime='not tested', full_x64_release='not built'))
(compat / 'states.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')

# Real filesystem checks of both orders, including byte-identical final sources.
checks = []
for label, sequence in [('recognition-first', ['recognition-improvements.patch', 'performance-compat/performance-after-recognition.patch']),
                        ('performance-first', ['improved-performance.patch', 'performance-compat/recognition-after-performance.patch'])]:
    directory = Path(tempfile.mkdtemp(prefix=label+'-', dir=root / 'build'))
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        z.extractall(directory)
    for p in sequence:
        subprocess.run(['git', 'apply', '--no-index', '--check', str(report / p)], cwd=directory, env=env, check=True)
        subprocess.run(['git', 'apply', '--no-index', str(report / p)], cwd=directory, env=env, check=True)
    for p in paths:
        assert digest((directory / p).read_bytes()) == states['combined'][p], (label, p)
    checks.append(dict(order=label, result='passed', directory=str(directory)))
for p, data in performance.items():
    if p.endswith('.py'):
        compile(data.decode('utf-8'), p, 'exec')
    if p in namespace['files'] and p.endswith('.py'):
        assert b'freeplay' not in data and b'match_cache' not in data, p
summary = dict(base_commit=base, files=paths, patch_sha256=manifest['patches']['improved-performance.patch'],
               recognition_patch_unchanged=manifest['patches']['recognition-improvements.patch'] == '0cef5c4d6a723f467e5a5a2b833da9063ae324af9ef27ce417446bec1b3ce322',
               checks=checks, standalone_performance='passed', combined_sources_identical=True,
               x64_native_runtime='not tested', x64_release_build='not run')
(report / 'improved-performance-manifest.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
print(json.dumps(summary, indent=2))

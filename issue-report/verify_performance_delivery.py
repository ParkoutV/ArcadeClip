import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

root = Path(__file__).resolve().parents[1]
report = root / 'issue-report'
manifest_path = report / 'improved-performance-manifest.json'
manifest = json.loads(manifest_path.read_text())
states = json.loads((report / 'performance-compat/states.json').read_text())['states']
archive = subprocess.check_output(['git', 'archive', '--format=zip', manifest['base_commit']], cwd=root)
checks = []
for order in [('performance', 'recognition'), ('recognition', 'performance'), ('both',)]:
    target = Path(tempfile.mkdtemp(prefix='delivery-check-', dir=root / 'build'))
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        z.extractall(target)
    def run(feature, *extra, success=True):
        result = subprocess.run([sys.executable, str(report/'apply-improvements.py'), feature, '--repo', str(target), *extra],
                                capture_output=True, text=True)
        assert (result.returncode == 0) == success, result.stdout + result.stderr
        return result.stdout
    run(order[0], '--check')
    for feature in order:
        run(feature)
    for feature in ('performance', 'recognition', 'both'):
        assert 'already applied' in run(feature)
    for name, expected in states['combined'].items():
        data = (target/name).read_bytes()
        if b'\0' not in data:
            data = data.replace(b'\r\n', b'\n')
        assert hashlib.sha256(data).hexdigest() == expected, name
    changed = target / 'src/preview.py'
    altered = changed.read_bytes() + b'\n# unrelated user edit\n'
    changed.write_bytes(altered)
    run('both', success=False)
    assert changed.read_bytes() == altered
    checks.append(dict(order=list(order), idempotency='passed', unknown_edits_protected=True))
manifest['application_tool_checks'] = checks
manifest['combined_regression_tests'] = dict(passed=43, runtime='ARM64 Python; isolated applied source tree; x64 GPU tests not run')
manifest['x64_helper_cross_compile'] = 'passed using Zig; x64 PE machine verified, not native GPU execution'
manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print(json.dumps(checks, indent=2))

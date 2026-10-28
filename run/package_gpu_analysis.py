"""Stage a standalone GPU analysis build from the existing verified runtime."""
import hashlib
import json
from pathlib import Path
import shutil
import struct
import argparse

root = Path(__file__).resolve().parents[1]
base = root / 'dist/ArcadeClip-arm64_preview'
parser = argparse.ArgumentParser()
parser.add_argument('--output', default='ArcadeClip-arm64_gpu-analysis')
args = parser.parse_args()
if Path(args.output).name != args.output:
    parser.error('output must be a directory name inside dist')
out = root / 'dist' / args.output
if not out.exists():
    shutil.copytree(base, out, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
shutil.copytree(root / 'src', out / 'src', dirs_exist_ok=True,
                ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.lib', '*.pdb', 'tests', 'licenses.json'))
dll = out / 'src/assets/gpu_roi_arm64.dll'
data = dll.read_bytes()
offset = struct.unpack_from('<I', data, 0x3c)[0]
assert struct.unpack_from('<H', data, offset+4)[0] == 0xaa64
manifest_path = out / 'build-manifest.json'
manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
record = {'path': 'src/assets/gpu_roi_arm64.dll', 'machine': '0xaa64', 'kind': 'ARM64'}
manifest['binaries'] = [r for r in manifest['binaries'] if r['path'] != record['path']] + [record]
manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
changes = ['media.py', 'video_sampling.py', 'gpu_image.py', 'freeplay.py', 'jacket_recognition.py',
           'app.py', 'workspace_ui.py', 'advanced_settings.py', 'pipeline.py', 'recognition.py',
           'assets/gpu_roi_arm64.dll']
result = {'base': base.name, 'proxy': False, 'partial_decode': False,
          'gpu_conversion': 'D3D11 VideoProcessor NV12 SDR to BGRA ROI',
          'files': {p: hashlib.sha256((out/'src'/p).read_bytes()).hexdigest() for p in changes}}
(out / 'gpu-analysis-improvement.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
shutil.copy2(root / 'docs/develop/GPU-ANALYSIS.md', out / 'GPU-ANALYSIS.md')
shutil.copy2(root / '.validation-data/gpu-analysis-result.json', out / 'gpu-analysis-validation.json')
shutil.copy2(root / 'docs/develop/ANALYSIS-OPTIONS.md', out / 'ANALYSIS-OPTIONS.md')
if (root / '.validation-data/analysis-options-matrix.json').exists():
    shutil.copy2(root / '.validation-data/analysis-options-matrix.json', out / 'analysis-options-validation.json')
print(out, flush=True)

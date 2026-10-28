"""Apply either improvement in either order, without overwriting unknown edits."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


def digest(path):
    if not path.exists():
        return None
    if not path.is_file() or path.is_symlink():
        raise ValueError(f'Not a regular source file: {path}')
    data = path.read_bytes()
    if b'\0' not in data:
        data = data.replace(b'\r\n', b'\n')
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('feature', choices=['performance', 'recognition', 'both'])
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    parser.add_argument('--check', action='store_true', help='Validate only; do not change files')
    args = parser.parse_args()
    package = Path(__file__).resolve().parent
    manifest = json.loads((package / 'performance-compat/states.json').read_text(encoding='utf-8'))
    repo = args.repo.resolve(strict=True)
    paths = manifest['states']['base'].keys()
    for name in paths:
        if not (repo / name).resolve().is_relative_to(repo):
            raise ValueError(f'Source path escapes repository: {name}')
    actual = {name: digest(repo / name) for name in paths}
    state = next((name for name, hashes in manifest['states'].items() if hashes == actual), None)
    if state is None:
        raise RuntimeError('Source files differ from the supported base or patch states. '
                           'No files changed. Use a clean copy of commit ' + manifest['base_commit'] +
                           ', or review unrelated edits manually; this tool never resets them.')
    transitions = {
        ('base', 'recognition'): ('recognition-improvements.patch', 'recognition'),
        ('base', 'performance'): ('improved-performance.patch', 'performance'),
        ('recognition', 'performance'): ('performance-compat/performance-after-recognition.patch', 'combined'),
        ('performance', 'recognition'): ('performance-compat/recognition-after-performance.patch', 'combined'),
    }
    steps = ['recognition', 'performance'] if args.feature == 'both' else [args.feature]
    # Verify all delivered patch hashes before making any change.
    for name, expected in manifest['patches'].items():
        if hashlib.sha256((package / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError(f'Patch checksum mismatch: {name}')
    environment = dict(os.environ, GIT_CEILING_DIRECTORIES=str(repo.parent))
    for feature in steps:
        if state in (feature, 'combined'):
            print(f'{feature}: already applied')
            continue
        name, target = transitions[(state, feature)]
        command = ['git', 'apply', '--no-index']
        patch = str(package / name)
        if args.check:
            # The complete sequence was checked against manifest states at packaging.
            print(f'Would apply {name}: {state} -> {target}')
            state = target
            continue
        subprocess.run(command + ['--check', patch], cwd=repo, env=environment, check=True)
        subprocess.run(command + [patch], cwd=repo, env=environment, check=True)
        actual = {p: digest(repo / p) for p in paths}
        if actual != manifest['states'][target]:
            raise RuntimeError('Post-apply source verification failed. Do not continue automatically.')
        print(f'Applied {name}: {state} -> {target}')
        state = target
    print('State: ' + state)


if __name__ == '__main__':
    main()

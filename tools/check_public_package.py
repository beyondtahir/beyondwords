#!/usr/bin/env python3
"""Check the clean public package without accounts, model calls or persistent state."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    manifest = json.loads((ROOT / 'FILE_MANIFEST.json').read_text(encoding='utf-8'))
    entries = manifest['files']
    seen = set()
    for entry in entries:
        name = entry['path']
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts or name in seen:
            raise ValueError('Invalid or duplicate manifest path: ' + name)
        seen.add(name)
        path = ROOT / relative
        if path.is_symlink() or not path.is_file():
            raise ValueError('Missing or linked release resource: ' + name)
        if any(x in {'private','projects','work','.auth','__pycache__','tests','evals'} for x in relative.parts):
            raise ValueError('Private/development resource in release: ' + name)
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != entry['sha256'] or len(data) != entry['bytes']:
            raise ValueError('Release integrity mismatch: ' + name)
        if path.suffix == '.py':
            compile(data, name, 'exec')
    skill = ROOT / '.agents/skills/beyondwords'
    text = (skill/'SKILL.md').read_text(encoding='utf-8')
    description = next(line.removeprefix('description:').strip() for line in text.splitlines() if line.startswith('description:'))
    if not 1 <= len(description) <= 200:
        raise ValueError('Skill description exceeds the portable package limit')
    expected = (ROOT/'VERSION').read_text(encoding='utf-8').strip()
    if expected != manifest['version']:
        raise ValueError('Version/manifest mismatch')
    with tempfile.TemporaryDirectory(prefix='beyondwords-package-check-') as tmp:
        project = Path(tmp)/'project'
        command = [sys.executable, str(ROOT/'tools/install_skill.py'), '--project', str(project)]
        subprocess.run(command, check=True, capture_output=True, text=True)
        installed = project/'.agents/skills/beyondwords/scripts/beyondwords.py'
        result = subprocess.run([sys.executable, str(installed), 'doctor'], check=True, capture_output=True, text=True)
        doctor = json.loads(result.stdout)
        if doctor.get('status') != 'OK' or doctor.get('data', {}).get('version') != expected:
            raise ValueError('Installed doctor does not report this release')
        repeat = subprocess.run(command, capture_output=True, text=True)
        if repeat.returncode == 0:
            raise ValueError('Installer unexpectedly replaced an existing skill')
    print(json.dumps({'version': expected, 'manifest_files': len(entries), 'hashes': 'passed',
                      'python_syntax': 'passed', 'isolated_install_and_doctor': 'passed',
                      'overwrite_refused': True, 'live_accounts_tested': False}))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Check the clean public package without accounts, model calls or persistent state."""
import hashlib
import json
import re
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def check_dependency_inventory(root):
    """Reject incomplete or stale advisory coverage of the actual runtime pins."""
    def pins(path, allow_hashes=False):
        found = {}
        for line in path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if allow_hashes and line.startswith('--hash=sha256:'):
                continue
            # Include pins for every platform, including Windows-only packages.
            # The inventory is deliberately unconditional; runtime installation
            # still evaluates the original lockfile markers and hashes.
            if allow_hashes:
                line = line.removesuffix('\\').strip().partition(';')[0].strip()
            match = re.fullmatch(r'([A-Za-z0-9_.-]+)==([^\s;\\]+)', line)
            if not match:
                raise ValueError('Unrecognized dependency pin in ' + path.name)
            name = re.sub(r'[-_.]+', '-', match[1]).lower()
            if name in found:
                raise ValueError('Duplicate dependency pin: ' + name)
            found[name] = match[2]
        if not found:
            raise ValueError('Empty dependency inventory: ' + path.name)
        return found
    actual = {}
    for filename in ('optional.lock', 'mcp.lock'):
        for name, version in pins(root/'requirements'/filename, allow_hashes=True).items():
            if name in actual and actual[name] != version:
                raise ValueError('Conflicting runtime dependency pins: ' + name)
            actual[name] = version
    inventory = pins(root/'requirements/requirements.txt')
    if inventory != actual:
        raise ValueError('Security inventory differs from runtime locks; review both before updating')
    return len(inventory)


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
    dependency_count = check_dependency_inventory(ROOT)
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
                      'python_syntax': 'passed', 'security_dependency_pins': dependency_count, 'isolated_install_and_doctor': 'passed',
                      'overwrite_refused': True, 'live_accounts_tested': False}))


if __name__ == '__main__':
    main()

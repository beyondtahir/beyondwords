#!/usr/bin/env python3
"""Refresh one existing PyPI pin across Beyondwords release inputs."""
import argparse
import json
import re
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def refresh(root, package, version, release):
    info = release['info']
    normalize = lambda value: re.sub(r'[-_.]+', '-', value).lower()
    name = normalize(package)
    if normalize(info['name']) != name or info['version'] != version:
        raise ValueError('Unexpected package or version returned by PyPI')
    hashes = sorted({file['digests']['sha256'] for file in release['urls'] if not file['yanked']})
    if not hashes or any(not re.fullmatch(r'[0-9a-f]{64}', digest) for digest in hashes):
        raise ValueError('No usable release hashes')
    req = root/'requirements'
    changes = {}
    previous = set()
    for lock in (req/'optional.lock', req/'mcp.lock'):
        original = lock.read_text(encoding='utf-8')
        pattern = re.compile(r'^(?P<name>[\w.-]+)==(?P<version>[^\s;]+)(?P<marker>[^\n]*?) \\\n'
                             r'(?:[ \t]+--hash=sha256:[a-f0-9]{64}(?: \\)?\n)+', re.M)
        def replace(match):
            if normalize(match['name']) != name:
                return match[0]
            previous.add(match['version'])
            header = match['name']+'=='+version+match['marker']
            return ' \\\n'.join([header]+['    --hash=sha256:'+digest for digest in hashes])+'\n'
        updated = pattern.sub(replace, original)
        if updated != original:
            changes[lock] = updated
    if len(previous) != 1:
        raise ValueError('Expected one existing version in the runtime locks')
    old = previous.pop()
    inventory = req/'requirements.txt'
    updated, count = re.subn(r'^'+re.escape(name)+'=='+re.escape(old)+r'$', name+'=='+version,
                             inventory.read_text(encoding='utf-8'), flags=re.M | re.I)
    if count != 1:
        # Dependabot may already have edited just the inventory in this branch.
        expected = name+'=='+version
        if count or expected not in inventory.read_text(encoding='utf-8').lower().splitlines():
            raise ValueError('Review the existing advisory inventory against the locks')
    changes[inventory] = updated
    found = False
    for path in [req/'dependency-metadata.json', root/'docs/MCP_DEPENDENCIES.json',
                 root/'packaging/public/docs/MCP_DEPENDENCIES.json']:
        if not path.exists():
            continue
        records = json.loads(path.read_text(encoding='utf-8'))
        for entry in records:
            if normalize(entry['name']) == name:
                if entry['version'] != old:
                    raise ValueError(f'Stale metadata in {path}')
                found = True
                entry.update(version=version, source=info['package_url'].rstrip('/')+'/'+version+'/',
                             requires_python=info['requires_python'],
                             license=info.get('license_expression') or info.get('license') or '')
                if 'dependencies' in entry:
                    entry['dependencies'] = [d for d in info.get('requires_dist') or [] if 'extra ==' not in d]
                changes[path] = json.dumps(records, indent=2, ensure_ascii=False)+'\n'
    if not found:
        raise ValueError('Missing dependency metadata')
    for path in [root/'docs/DEPENDENCIES.md', root/'packaging/public/docs/DEPENDENCIES.md']:
        if path.exists():
            before = path.read_text(encoding='utf-8')
            after = re.sub(r'(?im)^(\| '+re.escape(package)+r' \| )'+re.escape(old)+r'(?= \|)',
                           lambda m: m[1]+version, before)
            if before != after:
                changes[path] = after
    for path, content in changes.items():
        path.write_text(content, encoding='utf-8')
    return len(hashes)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package')
    parser.add_argument('version')
    args = parser.parse_args()
    if not re.fullmatch(r'[\w.-]+', args.package) or not re.fullmatch(r'[\w.+-]+', args.version):
        parser.error('Specify an existing package name and one exact release version')
    with urlopen(f'https://pypi.org/pypi/{args.package}/{args.version}/json', timeout=30) as response:
        release = json.load(response)
    print(f'Dependency inputs updated with {refresh(ROOT, args.package, args.version, release)} release hashes.')

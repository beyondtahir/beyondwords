#!/usr/bin/env python3
"""Build portable source/skill archives with an explicit source allowlist; no user state."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]
DIRS={'assets','.agents','.github','docs','evals','packaging','requirements','tests','tools'}
FILES={'VERSION','.gitattributes','SECURITY.md','.gitignore','AGENTS.md','README.md','CODEX_START_HERE.md','Makefile','BP001_MANIFEST.json','LICENSE'}
SKIP={'__pycache__','.git','.venv','private','projects','outputs','work','.auth','node_modules'}


def release_files(root=ROOT):
    for item in sorted(root.rglob('*')):
        rel=item.relative_to(root)
        if any(x in SKIP for x in rel.parts): continue
        if rel.parts[0] not in DIRS and str(rel) not in FILES: continue
        if item.is_symlink(): raise ValueError('Symlink in release source: '+str(rel))
        if not item.is_file(): continue
        if item.suffix in {'.pyc','.db','.sqlite3','.log'} or item.name.startswith(('.env','cookies','storage-state')): raise ValueError('Private/runtime file in source: '+str(rel))
        yield item


def build(destination):
    if destination.exists(): raise FileExistsError('Release directory exists; nothing overwritten')
    version=json.loads((ROOT/'packaging/plugin.json').read_text())['version']
    source=list(release_files()); entries=[dict(path=str(p.relative_to(ROOT)).replace('\\','/'),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in source]
    destination.mkdir(parents=True)
    manifest=json.dumps(dict(version=version,files=entries),indent=2).encode()
    (destination/'FILE_MANIFEST.json').write_bytes(manifest)
    with zipfile.ZipFile(destination/f'Beyondwords-{version}-source.zip','x',zipfile.ZIP_DEFLATED) as archive:
        for file in source: archive.write(file,'beyondwords/'+str(file.relative_to(ROOT)).replace('\\','/'))
        archive.writestr('beyondwords/FILE_MANIFEST.json',manifest)
    skill=ROOT/'.agents/skills/beyondwords'
    with zipfile.ZipFile(destination/f'Beyondwords-{version}-skill.zip','x',zipfile.ZIP_DEFLATED) as archive:
        for file in source:
            if file.is_relative_to(skill): archive.write(file,'beyondwords/'+str(file.relative_to(skill)).replace('\\','/'))
    for path in destination.glob('*.zip'):
        with zipfile.ZipFile(path) as archive:
            if archive.testzip(): raise ValueError('ZIP integrity failure')
    print(json.dumps({'version':version,'source_files':len(source),'destination':str(destination),'private_state_included':False}))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--destination',type=Path,required=True)
    build(parser.parse_args().destination)

#!/usr/bin/env python3
"""Download only the reviewed locked EPUBCheck archive to a new local directory."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import urllib.request
import zipfile


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination',type=Path,required=True)
    args=parser.parse_args()
    target=args.destination.absolute()
    if target.exists() or target.is_symlink():parser.error('Destination exists; nothing overwritten')
    spec=json.loads((Path(__file__).resolve().parents[1]/'requirements/epubcheck.lock.json').read_text())
    request=urllib.request.Request(spec['url'],headers={'User-Agent':'Beyondwords-validator-install'})
    with urllib.request.urlopen(request,timeout=60) as response:
        data=response.read(64*1024*1024+1)
    if len(data)>64*1024*1024 or hashlib.sha256(data).hexdigest()!=spec['sha256']:
        raise ValueError('EPUBCheck download size/hash mismatch')
    target.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.epubcheck-',dir=target.parent))
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos=archive.infolist()
            if sum(x.file_size for x in infos)>100*1024*1024:raise ValueError('Archive too large')
            for info in infos:
                name=Path(info.filename)
                if name.is_absolute() or '..' in name.parts or '\\' in info.filename:
                    raise ValueError('Unsafe archive path')
            archive.extractall(stage)
        if target.exists() or target.is_symlink():raise FileExistsError(target)
        stage.rename(target)
    finally:
        if stage.exists():shutil.rmtree(stage)
    jar=next(target.rglob('epubcheck.jar'))
    print(json.dumps({'jar':str(jar),'sha256_verified':spec['sha256'],'java_installed_by_tool':False},indent=2))


if __name__=='__main__':main()

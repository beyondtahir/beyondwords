#!/usr/bin/env python3
"""Build the standard plugin layout from the single canonical skill source."""
import argparse
from pathlib import Path
import shutil
import tempfile


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination',type=Path,required=True,help='New build parent; plugin is named beyondwords')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    target=args.destination.absolute()/'beyondwords'
    if target.exists() or target.is_symlink():parser.error('Plugin destination exists; nothing overwritten')
    target.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.beyondwords-plugin-',dir=target.parent))
    try:
        ignore=shutil.ignore_patterns('__pycache__','*.pyc','.DS_Store')
        shutil.copytree(root/'.agents/skills/beyondwords',stage/'skills/beyondwords',ignore=ignore)
        for folder in ('requirements','docs'):
            shutil.copytree(root/folder,stage/folder,ignore=ignore)
        (stage/'tools').mkdir()
        for name in ('setup_runtime.py','install_epubcheck.py','configure_mcp.py'):
            shutil.copy2(root/'tools'/name,stage/'tools'/name)
        (stage/'.codex-plugin').mkdir()
        shutil.copy2(root/'packaging/plugin.json',stage/'.codex-plugin/plugin.json')
        shutil.copy2(root/'LICENSE',stage/'LICENSE')
        if target.exists() or target.is_symlink():raise FileExistsError(target)
        stage.rename(target)
    finally:
        if stage.exists():shutil.rmtree(stage)
    print(target)


if __name__=='__main__':main()

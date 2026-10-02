#!/usr/bin/env python3
"""Copy the bundled skill to a local skill directory; never overwrite."""
from pathlib import Path
import argparse
import shutil
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, help='Use this project/.agents/skills instead of the user skill directory')
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1] / '.agents/skills/beyondwords'
    parent = (args.project.resolve() if args.project else Path.home()) / '.agents/skills'
    target = parent / 'beyondwords'
    if not (source/'SKILL.md').is_file():
        parser.error('The bundled SKILL.md is missing')
    if target.exists() or target.is_symlink():
        parser.error(f'{target} already exists; review and remove/rename the old copy yourself. Nothing overwritten.')
    parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.beyondwords-install-', dir=parent))
    try:
        shutil.copytree(source, stage/'skill', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        # No secrets, no downloads, no automatic dependency installation.
        (stage/'skill').rename(target)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    print(f'Installed local skill files: {target}')
    print('In Codex, use $beyondwords. Restart Codex if it does not appear.')
    print('This installs skill/helpers. Dependencies and host AI are separate. Account work requires the optional runtime, real access and reviewed action scope; see docs/INSTALL.md in the source release.')
    return 0

if __name__ == '__main__':
    try: raise SystemExit(main())
    except OSError as exc:
        print(f'Installation failed: {exc}', file=sys.stderr)
        raise SystemExit(2)

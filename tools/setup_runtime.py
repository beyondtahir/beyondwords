#!/usr/bin/env python3
"""Explicitly install reviewed locked dependencies in a new isolated environment."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import venv


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination',type=Path,default=Path.home()/'.local/share/beyondwords/runtime')
    parser.add_argument('--browser',action='store_true',help='Also install the pinned Playwright Chromium build')
    parser.add_argument('--mcp',action='store_true',help='Also install the optional official MCP SDK from its reviewed lock')
    args=parser.parse_args()
    if sys.version_info < (3,11):parser.error('Use Python 3.11+ to create this runtime')
    target=args.destination.absolute()
    if target.exists() or target.is_symlink():parser.error('Runtime already exists; inspect it or choose a new destination')
    lock=Path(__file__).resolve().parents[1]/'requirements/optional.lock'
    venv.EnvBuilder(with_pip=True).create(target)
    python=target/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')
    subprocess.run([str(python),'-m','pip','install','--require-hashes','-r',str(lock)],check=True)
    if args.mcp:
        subprocess.run([str(python),'-m','pip','install','--require-hashes','-r',str(lock.with_name('mcp.lock'))],check=True)
    subprocess.run([str(python),'-m','pip','check'],check=True)
    if args.browser:subprocess.run([str(python),'-m','playwright','install','chromium'],check=True)
    print(json.dumps({'python':str(python),'browser_install_requested':args.browser,'mcp_installed':args.mcp,'model_installed':False}))


if __name__=='__main__':main()

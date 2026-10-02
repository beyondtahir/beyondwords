"""Write a reviewable local STDIO configuration. Does not change host configuration."""
import argparse
import json
from pathlib import Path
import sys


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--python',type=Path,required=True);p.add_argument('--root',type=Path,required=True)
    p.add_argument('--project-id',required=True);p.add_argument('--destination',type=Path,required=True)
    p.add_argument('--format',choices=['json','toml'],default='json');args=p.parse_args()
    script=Path(__file__).resolve().parents[1]/'.agents/skills/beyondwords/scripts/beyondwords_mcp.py'
    if not script.exists():script=Path(__file__).resolve().parents[1]/'skills/beyondwords/scripts/beyondwords_mcp.py'
    if not args.python.is_file() or not script.is_file():p.error('Existing Python runtime and server script required')
    command=str(args.python.absolute());argv=[str(script), '--root',str(args.root.absolute()),'--project-id',args.project_id]
    if args.format=='json':text=json.dumps({'mcpServers':{'beyondwords':{'command':command,'args':argv}}},indent=2)+'\n'
    else:text='[mcp_servers.beyondwords]\ncommand = '+json.dumps(command)+'\nargs = '+json.dumps(argv)+'\n'
    with args.destination.open('x',encoding='utf-8') as f:f.write(text)
    print('Configuration written. Review it before importing into the selected host. No credentials included.')


if __name__=='__main__':main()

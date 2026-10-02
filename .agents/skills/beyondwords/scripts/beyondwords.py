#!/usr/bin/env python3
"""Beyondwords local publishing-house CLI. Use --help; inputs are UTF-8 JSON."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import time
import sqlite3
from uuid import uuid4

import publishing_core as core
import publishing_project as project
from publishing_result import ToolResult, Cost
from beyondwords_book import BookStore, VERSION

MUTATIONS = {'enable', 'plan', 'chapter', 'source', 'claim', 'review', 'asset', 'edition', 'launch', 'report-import', 'prepare', 'outcome'}
OPERATIONS = MUTATIONS | {'init', 'doctor', 'status', 'finance', 'goals', 'export', 'cover-directions', 'guide', 'market-screen', 'research-desk', 'writing-context', 'ads-analyze', 'cover-compose', 'connect', 'research', 'lifecycle', 'visual-book', 'cover-wrap', 'host-route', 'manuscript-import', 'story-memory', 'coloring-book', 'editorial', 'publishing-check'}


def execute(operation, *, workspace=None, project_id=None, expected_revision=None, payload=None, destination=None):
    started, tick = core.iso_now(), time.monotonic()
    payload = {} if payload is None else payload
    try:
        if not isinstance(payload, dict):
            raise ValueError('Operation input must be a JSON object')
        if operation not in OPERATIONS:
            raise project.ProjectError('UNAVAILABLE', 'No implementation for this operation; nothing performed')
        if operation == 'publishing-check':
            from beyondwords_publishing_checks import execute as publishing_check
            data=publishing_check(payload)
        elif operation == 'editorial':
            from beyondwords_editorial import execute as editorial_execute
            data=editorial_execute(workspace,project_id,expected_revision,payload)
        elif operation == 'coloring-book':
            from beyondwords_coloring import execute as coloring_execute
            data=coloring_execute(payload,destination)
        elif operation in {'manuscript-import','story-memory'}:
            if not workspace or not project_id:raise ValueError('Select the author book workspace and project ID')
            from beyondwords_authoring import manuscript_import, story_memory
            data=(manuscript_import if operation=='manuscript-import' else story_memory)(workspace,project_id,expected_revision,payload)
        elif operation == 'lifecycle':
            from beyondwords_lifecycle import execute as lifecycle_execute
            data=lifecycle_execute(workspace,project_id,expected_revision,payload)
        elif operation == 'host-route':
            from beyondwords_hosts import execute as host_execute
            data=host_execute(workspace,project_id,expected_revision,payload)
        elif operation == 'cover-wrap':
            from beyondwords_visual import wrap
            if not destination:raise ValueError('Choose a new cover directory')
            data=wrap(payload,destination)
        elif operation == 'visual-book':
            from beyondwords_visual import build
            if not destination:raise ValueError('Choose a new edition directory')
            data=build(payload,destination)
        elif operation == 'connect':
            from beyondwords_connected import execute as connected_execute
            data = connected_execute(workspace, project_id, payload)
        elif operation == 'research':
            from beyondwords_research_tools import execute as research_execute
            data=research_execute(workspace,project_id,expected_revision,payload)
        elif operation == 'guide':
            from beyondwords_guide import Guide
            data = Guide(workspace).execute(payload, expected_revision=expected_revision)
        elif operation == 'market-screen':
            from beyondwords_market import screen
            data = screen(payload)
        elif operation == 'cover-compose':
            from beyondwords_production import compose_cover
            if not destination:
                raise ValueError('A new output directory is required')
            data = compose_cover(payload, destination)
        elif operation == 'ads-analyze':
            from beyondwords_desks import ads_analyze
            data = ads_analyze(project.load_input(Path(payload['file'])), payload)
        elif operation in {'research-desk', 'writing-context'}:
            if not workspace or not project_id:
                raise ValueError('Select workspace and project ID')
            from beyondwords_desks import research_desk, writing_context
            data = (research_desk if operation == 'research-desk' else writing_context)(Path(workspace), project_id, payload)
        elif operation == 'doctor':
            data = core.doctor()
            data['core_version']=data['version'];data['version']=VERSION
            data['capabilities']['runtime']={k:v for k,v in data['capabilities']['runtime'].items() if k not in core.INTEGRATIONS}
            data['local_operations']=sorted(OPERATIONS)
            data['account_acceptance_verified']=False
            data['integrations'].update(mcp_server='optional_official_sdk_stdio',publisher_upload='attended_browser_adapter_requires_account_acceptance',
                                        ad_execution='official_api_adapter_requires_account_acceptance')
            data['beyondwords'] = {'version': VERSION, 'local_book_workflow': 'implemented',
                                  'guided_intake_and_memory': 'implemented',
                                  'specialist_desks': ['research-desk','market-screen','writing-context','manuscript-import','story-memory','editorial','cover-compose','ads-analyze','lifecycle','visual-book','coloring-book','cover-wrap','host-route','publishing-check'],
                                  'host_inference': 'provided by the current host, not bundled',
                                  'publication_and_ad_mutations': 'connector implemented; account authentication and attended authorization required',
                                  'monitoring': 'local worker implemented; not automatically scheduled', 'local_inference': 'UNTESTED'}
        elif operation == 'goals':
            from beyondwords_business import goal_plan
            data = goal_plan(payload)
        elif operation == 'cover-directions':
            from beyondwords_production import cover_directions, inherited
            write_new = inherited('bw_produce').write_new
            if not destination:
                raise ValueError('A new output directory is required')
            target = core.scoped_path(Path(destination))
            if target.exists():
                raise FileExistsError('Cover destination already exists')
            for key in ('title', 'author'):
                core.text(payload.get(key), key)
            files = cover_directions(payload['title'], payload['author'], payload.get('subtitle', ''))
            import shutil
            import tempfile
            target.parent.mkdir(parents=True, exist_ok=True)
            stage = Path(tempfile.mkdtemp(prefix='.beyondwords-covers-', dir=target.parent))
            try:
                for name, media, content in files:
                    write_new(stage/name, content)
                if target.exists() or target.is_symlink():
                    raise FileExistsError('Cover destination appeared during generation')
                stage.rename(target)
            finally:
                if stage.exists():
                    shutil.rmtree(stage)
            data = {'directory': str(target), 'files': [name for name, _, _ in files], 'market_tested': False,
                    'visual_review': 'NOT_RUN', 'note': 'Three original typographic directions. SVG text requires bundled licensed fonts.'}
        elif operation == 'init':
            if not workspace:
                raise ValueError('workspace is required')
            import shutil
            import tempfile
            target = core.scoped_path(Path(workspace))
            if target.exists() or target.is_symlink():
                raise FileExistsError('Project destination already exists')
            target.parent.mkdir(parents=True, exist_ok=True)
            stage = Path(tempfile.mkdtemp(prefix='.beyondwords-init-', dir=target.parent))
            try:
                state = project.initialize(stage/'book', title=payload['title'], country=payload['country'],
                                           language=payload['language'], budget=payload['budget'], currency=payload['currency'],
                                           project_id=project_id)
                store = BookStore(stage/'book', state['project_id'])
                data = store.enable(state['revision'], synthetic=payload.get('synthetic', False))
                if target.exists() or target.is_symlink():
                    raise FileExistsError('Project destination changed during initialization')
                (stage/'book').rename(target)
            finally:
                shutil.rmtree(stage, ignore_errors=True)
        else:
            if not workspace or not project_id:
                raise ValueError('Select workspace and project ID')
            store = BookStore(Path(workspace), project_id)
            if operation in MUTATIONS:
                project.require_revision(expected_revision)
            if operation == 'enable':
                data = store.enable(expected_revision, synthetic=payload.get('synthetic', False))
            elif operation == 'status':
                data = store.status()
            elif operation == 'finance':
                data = store.finance()
            elif operation == 'export':
                if not destination:
                    raise ValueError('destination is required')
                data = store.export(payload['kind'], payload['id'], destination)
            elif operation in {'asset', 'report-import'}:
                value = dict(payload)
                raw = project.load_input(Path(value.pop('file')))
                method = store.asset if operation == 'asset' else store.import_report
                data = method(expected_revision, value, raw)
            else:
                data = getattr(store, operation)(expected_revision, payload)
        status = data.pop('operation_status','OK')
        if operation == 'host-route' and data.get('status') in {'UNAVAILABLE','BLOCKED'}:
            status = data['status']
        if operation in {'status', 'prepare'}:
            status = 'NEEDS_REVIEW'
        if operation == 'connect' and data.get('state') in {'UNKNOWN', 'IN_FLIGHT', 'PREPARED', 'REJECTED'}:
            status = 'NEEDS_REVIEW'
        warnings = data.get('warnings', [])
        synthetic = data.get('synthetic') or data.get('book', {}).get('synthetic')
        if synthetic and core.SYNTHETIC_WARNING not in warnings:
            warnings = warnings + [core.SYNTHETIC_WARNING]
        return ToolResult(status=status, data=data, operation_id=str(uuid4()), warnings=warnings,
                          tool_version=VERSION, cost=Cost() if operation in {'connect','research'} else Cost(state='KNOWN', actual='0'),
                          timing={'started_at': started, 'elapsed_ms': round((time.monotonic()-tick)*1000)}).to_dict()
    except (ValueError, KeyError, TypeError, OSError, ImportError, sqlite3.Error) as exc:
        code = getattr(exc, 'code', 'INVALID_INPUT')
        failure_status='UNAVAILABLE' if code=='UNAVAILABLE' or isinstance(exc,ImportError) else 'ERROR'
        if code in {'PERMISSION_REQUIRED','ACCOUNT_NOT_CONNECTED','OWNER_REQUIRED','LOGIN_OR_DESTINATION'}:
            failure_status='BLOCKED'
        if operation=='connect' and (getattr(exc,'uncertain',False) or code in {'STALE_APPROVAL','RECONCILE_REQUIRED'}):
            failure_status='NEEDS_REVIEW'
        return ToolResult(status=failure_status,
                          data={'performed': 'UNKNOWN' if getattr(exc, 'uncertain', False) else False}, operation_id=str(uuid4()), tool_version=VERSION,
                          error={'code': code, 'message': str(exc)},
                          timing={'started_at': started, 'elapsed_ms': round((time.monotonic()-tick)*1000)}).to_dict()


def main(argv=None):
    parser = project.JsonParser(description=__doc__)
    parser.add_argument('operation', choices=sorted(OPERATIONS))
    parser.add_argument('--workspace', type=Path)
    parser.add_argument('--project-id')
    parser.add_argument('--expected-revision', type=int)
    parser.add_argument('--input', type=Path, help='JSON operation input; see references/12-complete-workflow.md')
    parser.add_argument('--destination', type=Path)
    try:
        args = parser.parse_args(argv)
        payload = json.loads(project.load_input(args.input)) if args.input else {}
        result = execute(args.operation, workspace=args.workspace, project_id=args.project_id,
                         expected_revision=args.expected_revision, payload=payload, destination=args.destination)
    except (ValueError, OSError) as exc:
        result = {'status': 'ERROR', 'data': {'performed': False}, 'error': {'code': 'INVALID_INPUT', 'message': str(exc)}}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['status'] in {'OK', 'PARTIAL', 'NEEDS_REVIEW'} else 2


if __name__ == '__main__':
    raise SystemExit(main())

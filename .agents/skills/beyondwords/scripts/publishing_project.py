#!/usr/bin/env python3
"""BP-001 local project API and CLI. SQLite is the canonical versioned store.

No network, model, browser, publishing or advertising calls exist here.
The original project.json remains an immutable intake/migration input.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import tempfile
import time
from typing import Any, Callable
from uuid import uuid4

import publishing_core as core
from publishing_result import Cost, ToolResult

SCHEMA_VERSION = 2
WARNING = core.SYNTHETIC_WARNING
LOCAL_APPROVAL = 'Local editable review declaration only; not trusted external authorization.'
MAX_BYTES = 5 * 1024 * 1024
PROFILE_FIELDS = {
    'reader_profile': {'audience', 'starting_knowledge', 'goals', 'needs'},
    'buyer_profile': {'purchase_context', 'objections', 'expectations', 'hypothesis'},
    'author_voice': {'tone', 'sample_refs', 'genuine_experience', 'avoid'},
    'book_brief': {'title', 'promise', 'genre', 'scope', 'evidence_needs'},
    'opportunity_brief': {'hypothetical', 'concept', 'rationale', 'limitations'},
}
LIST_FIELDS = {'goals', 'needs', 'objections', 'expectations', 'sample_refs', 'avoid', 'evidence_needs', 'limitations'}
INTEGRATIONS = core.INTEGRATIONS


class ProjectError(core.CoreError):
    def __init__(self, code: str, message: str, missing_fields: list[str] | None = None):
        super().__init__(message)
        self.code = code
        self.missing_fields = missing_fields or []


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8')


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def identifier(value: Any, field: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,119}', value):
        raise ProjectError('INVALID_INPUT', f'{field} must be a simple identifier', [field])
    return value


def require_revision(value: Any):
    if type(value) is not int or value < 0:
        raise ProjectError('INVALID_INPUT', 'expected_revision must be a nonnegative integer', ['expected_revision'])


def load_input(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ProjectError('MISSING_SOURCE', 'Input must be an existing regular file, not a symlink', ['input'])
    with path.open('rb') as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ProjectError('INVALID_INPUT', 'Input exceeds 5 MiB')
    return data


def _tables(conn: sqlite3.Connection):
    # Individual statements: executescript would implicitly commit a migration.
    for sql in (
        'CREATE TABLE project_identity (id TEXT PRIMARY KEY, original_sha256 TEXT NOT NULL)',
        'CREATE TABLE project_revisions (revision INTEGER PRIMARY KEY, payload TEXT NOT NULL, sha256 TEXT NOT NULL, event TEXT NOT NULL, recorded_at TEXT NOT NULL)',
        'CREATE TABLE artifact_blobs (sha256 TEXT PRIMARY KEY, content BLOB NOT NULL)',
    ):
        conn.execute(sql)
    for table in ('project_identity', 'project_revisions', 'artifact_blobs', 'evidence', 'observations'):
        for action in ('UPDATE', 'DELETE'):
            conn.execute(f"CREATE TRIGGER immutable_{table}_{action} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT, 'append-only record'); END")


def _initial(metadata: dict[str, Any], records: dict[str, Any], original: bytes) -> dict[str, Any]:
    state = copy.deepcopy(metadata)
    state.pop('stage', None)  # Original intake stage remains only in project.json.
    state.update(schema_version=SCHEMA_VERSION, revision=0, mode='fixture_only',
                 original_schema_version=metadata['schema_version'], original_sha256=digest(original),
                 reader_profile=None, buyer_profile=None, author_voice=None, book_brief=None,
                 decisions=[], artifacts=[], evidence_ids=[r['evidence_id'] for r in records['evidence']],
                 observation_ids=[r['observation_id'] for r in records['bsr_observations']],
                 workflow={'phase': 'initialized', 'bsr_check': None, 'opportunity': None, 'review': None},
                 warnings=[WARNING, LOCAL_APPROVAL], publication_authorized=False)
    return state


def _insert_state(conn: sqlite3.Connection, state: dict[str, Any], event: str, timestamp: str):
    encoded = canonical(state)
    conn.execute('INSERT INTO project_revisions VALUES (?,?,?,?,?)',
                 (state['revision'], encoded.decode('utf-8'), digest(encoded), event, timestamp))


def initialize(workspace: Path, *, title: str, country: str, language: str, budget: str, currency: str,
               clock: Callable[[], str] = core.iso_now, project_id: str | None = None) -> dict[str, Any]:
    target = core.scoped_path(workspace)
    # Unlike legacy init, require a nonexistent destination so an interrupted init
    # can never leave half of a user's project in the requested directory.
    if target.exists():
        raise ProjectError('ALREADY_EXISTS', 'Destination exists; nothing was overwritten')
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.bp-init-', dir=target.parent))
    try:
        metadata = core.init_project(stage/'book', title, country, language, budget, currency)['project']
        metadata.update(project_id=identifier(project_id or str(uuid4()), 'project_id'), created_at=clock())
        # This is an unpublished staging file, not an existing user original.
        original = canonical(metadata)
        with (stage/'book'/'project.json').open('wb') as stream:
            stream.write(original); stream.flush(); os.fsync(stream.fileno())
        state = migrate(stage/'book', metadata['project_id'], 0, clock=clock)
        if target.exists() or target.is_symlink():
            raise ProjectError('ALREADY_EXISTS', 'Destination changed during initialization')
        (stage/'book').rename(target)
        return state
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def migrate(workspace: Path, project_id: str, expected_revision: int, *,
            clock: Callable[[], str] = core.iso_now) -> dict[str, Any]:
    require_revision(expected_revision)
    root = core.scoped_path(workspace)
    original = load_input(root/'project.json')
    metadata = json.loads(original)
    if not isinstance(metadata, dict) or metadata.get('project_id') != project_id:
        raise ProjectError('PROJECT_MISMATCH', 'Original metadata does not match selected project ID')
    conn = core.connect(root)
    try:
        conn.execute('BEGIN IMMEDIATE')
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='project_revisions'").fetchone():
            state = Store(root, project_id)._read(conn)
            if state['revision'] != expected_revision:
                raise ProjectError('STALE_REVISION', 'Project changed; read the latest revision')
            conn.rollback()
            return state
        if type(metadata.get('schema_version')) is not int or metadata['schema_version'] != 1:
            raise ProjectError('UNSUPPORTED_SCHEMA', 'Only starter schema 1 can migrate to schema 2')
        if expected_revision != 0:
            raise ProjectError('STALE_REVISION', 'Legacy projects begin at revision 0')
        for field in ('project_id', 'title', 'country', 'language', 'created_at'):
            core.text(metadata.get(field), field)
        core.number(metadata.get('budget'), 'budget'); core.currency_code(metadata.get('currency'))
        records = {'evidence': [json.loads(r[0]) for r in conn.execute('SELECT payload FROM evidence ORDER BY id')],
                   'bsr_observations': [json.loads(r[0]) for r in conn.execute('SELECT payload FROM observations ORDER BY id')]}
        for row in records['evidence']:
            core.validate_evidence(row)
        for row in records['bsr_observations']:
            core.validate_bsr(row)
        if conn.execute('PRAGMA foreign_key_check').fetchone():
            raise ProjectError('MISSING_SOURCE', 'Legacy observations contain missing sources')
        _tables(conn)
        conn.execute('INSERT INTO project_identity VALUES (?,?)', (project_id, digest(original)))
        state = _initial(metadata, records, original)
        _insert_state(conn, state, 'migrate_v1_to_v2', clock())
        conn.commit()
        return state
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


class Store:
    def __init__(self, workspace: Path, project_id: str, *, clock: Callable[[], str] = core.iso_now):
        self.root = core.scoped_path(workspace)
        self.project_id = identifier(project_id, 'project_id')
        self.clock = clock

    def _read(self, conn: sqlite3.Connection, revision: int | None = None) -> dict[str, Any]:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='project_revisions'").fetchone():
            raise ProjectError('MIGRATION_REQUIRED', 'Run project migrate for this schema 1 project')
        identity = conn.execute('SELECT id, original_sha256 FROM project_identity').fetchall()
        if len(identity) != 1 or identity[0][0] != self.project_id:
            raise ProjectError('PROJECT_MISMATCH', 'Database belongs to a different project')
        if digest(load_input(self.root/'project.json')) != identity[0][1]:
            raise ProjectError('INTEGRITY_ERROR', 'Original project.json changed; restore the original before resuming')
        if revision is not None:
            require_revision(revision)
        row = (conn.execute('SELECT payload, sha256 FROM project_revisions ORDER BY revision DESC LIMIT 1').fetchone()
               if revision is None else conn.execute('SELECT payload, sha256 FROM project_revisions WHERE revision=?', (revision,)).fetchone())
        if row is None:
            raise ProjectError('NOT_FOUND', 'Project revision does not exist')
        if digest(row[0].encode('utf-8')) != row[1]:
            raise ProjectError('INTEGRITY_ERROR', 'State hash mismatch')
        state = json.loads(row[0])
        if type(state.get('schema_version')) is not int or state['schema_version'] != SCHEMA_VERSION:
            raise ProjectError('UNSUPPORTED_SCHEMA', 'Unsupported project schema; no automatic downgrade')
        if state.get('project_id') != self.project_id:
            raise ProjectError('PROJECT_MISMATCH', 'State belongs to a different project')
        for artifact in state['artifacts']:
            self._blob(conn, artifact['sha256'])
        return state

    def read(self, revision: int | None = None) -> dict[str, Any]:
        conn = core.connect(self.root)
        try:
            conn.execute('BEGIN')
            return self._read(conn, revision)
        finally:
            conn.close()

    def history(self) -> dict[str, Any]:
        conn = core.connect(self.root)
        try:
            conn.execute('BEGIN')
            self._read(conn)
            return {'project_id': self.project_id, 'revisions': [dict(zip(('revision', 'sha256', 'event', 'recorded_at'), row))
                    for row in conn.execute('SELECT revision, sha256, event, recorded_at FROM project_revisions ORDER BY revision')]}
        finally:
            conn.close()

    @contextmanager
    def _change(self, expected_revision: int, event: str):
        require_revision(expected_revision)
        conn = core.connect(self.root)
        try:
            conn.execute('BEGIN IMMEDIATE')
            state = self._read(conn)
            if state['revision'] != expected_revision:
                raise ProjectError('STALE_REVISION', f"Expected revision {expected_revision}; current revision is {state['revision']}")
            research_events = {'record_source_access', 'capture_book_evidence', 'record_capture_failure',
                               'record_discovery', 'record_policy_version', 'record_policy_capture_failure', 'review_policy_version'}
            production_events = {'enable_book_v1', 'enable_research_v1', 'book_plan', 'book_chapter', 'book_source',
                                 'book_claim', 'book_review', 'book_asset', 'book_edition',
                                 'book_launch', 'book_report', 'book_package', 'book_outcome', 'book_lifecycle'}
            if state.get('research') and event not in research_events | production_events:
                raise ProjectError('WORKFLOW_ORDER', 'BP-001 fixture mutations cannot modify a research project')
            if state.get('book') and event not in research_events | production_events:
                raise ProjectError('WORKFLOW_ORDER', 'Fixture mutations cannot modify a Beyondwords book')
            yield conn, state
            state['revision'] += 1
            self._phase(state)
            _insert_state(conn, state, event, self.clock())
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _phase(state):
        flow = state['workflow']
        if state.get('book'):
            flow['phase'] = 'synthetic_book_workflow' if state['book']['synthetic'] else 'book_in_progress'
            return
        if state.get('research'):
            flow['phase'] = 'synthetic_research' if state['research']['synthetic'] else 'research_in_progress'
            return
        phase = 'evidence_imported' if state['evidence_ids'] else 'initialized'
        if flow['bsr_check']:
            phase = 'bsr_checked'
        if flow['opportunity']:
            phase = 'opportunity_saved'
            if {'outline', 'sample'} <= {a['kind'] for a in state['artifacts']}:
                phase = 'sample_saved'
        if flow['review']:
            phase = 'synthetic_demo_complete'
        flow['phase'] = phase

    @staticmethod
    def _source(conn, evidence_id: str, *, fixture_only: bool = True) -> dict[str, Any]:
        row = conn.execute('SELECT payload FROM evidence WHERE id=?', (evidence_id,)).fetchone()
        if row is None:
            raise ProjectError('MISSING_SOURCE', f'Missing evidence in selected project: {evidence_id}', ['evidence_ids'])
        value = core.validate_evidence(json.loads(row[0]))
        if fixture_only and not value['synthetic']:
            raise ProjectError('FIXTURE_ONLY', 'BP-001 workflow accepts synthetic evidence only; real evidence workflow is unavailable')
        return value

    def import_evidence(self, expected_revision: int, record: Any) -> dict[str, Any]:
        value = core.validate_evidence(record)
        if not value['synthetic'] or value['access_basis'] != 'fixture':
            raise ProjectError('FIXTURE_ONLY', 'Evidence must explicitly declare access_basis=fixture')
        if record.get('evidence_class') != 'synthetic':
            raise ProjectError('INVALID_INPUT', 'Fixture evidence requires evidence_class=synthetic', ['evidence_class'])
        value.update(synthetic=True, evidence_class='synthetic', warnings=[WARNING])
        with self._change(expected_revision, 'import_synthetic_evidence') as (conn, state):
            conn.execute('INSERT INTO evidence VALUES (?,?,?)', (value['evidence_id'], canonical(value).decode(), self.clock()))
            state['evidence_ids'].append(value['evidence_id'])
            state['workflow'].update(bsr_check=None, opportunity=None, review=None)
        return state

    def import_bsr(self, expected_revision: int, record: Any) -> dict[str, Any]:
        value = core.validate_bsr(record)
        with self._change(expected_revision, 'import_synthetic_bsr') as (conn, state):
            self._source(conn, value['evidence_id'])
            value.update(synthetic=True, evidence_class='synthetic', warnings=[WARNING])
            conn.execute('INSERT INTO observations VALUES (?,?,?,?)',
                         (value['observation_id'], value['evidence_id'], canonical(value).decode(), self.clock()))
            state['observation_ids'].append(value['observation_id'])
            state['workflow'].update(bsr_check=None, opportunity=None, review=None)
        return state

    def records(self) -> dict[str, Any]:
        conn = core.connect(self.root)
        try:
            conn.execute('BEGIN')
            self._read(conn)
            evidence = [core.validate_evidence(json.loads(r[0])) for r in conn.execute('SELECT payload FROM evidence ORDER BY id')]
            observations = []
            for row in conn.execute('SELECT payload FROM observations ORDER BY id'):
                value = core.validate_bsr(json.loads(row[0]))
                source = self._source(conn, value['evidence_id'], fixture_only=False)
                if source['synthetic']:
                    value.update(synthetic=True, evidence_class='synthetic', warnings=[WARNING])
                observations.append(value)
            return {'project_id': self.project_id, 'evidence': evidence, 'bsr_observations': observations,
                    'warnings': [WARNING], 'real_recommendations_available': False}
        finally:
            conn.close()

    def check_bsr(self, expected_revision: int, left: str, right: str, max_age_hours: str, as_of: str) -> dict[str, Any]:
        if left == right:
            raise ProjectError('INVALID_INPUT', 'Choose two distinct observations')
        with self._change(expected_revision, 'check_synthetic_bsr') as (conn, state):
            rows = []
            for obs_id in (left, right):
                row = conn.execute('SELECT payload FROM observations WHERE id=?', (obs_id,)).fetchone()
                if row is None:
                    raise ProjectError('MISSING_SOURCE', f'Missing observation: {obs_id}', ['observation_ids'])
                value = json.loads(row[0]); self._source(conn, value['evidence_id'])
                value['synthetic'] = True
                rows.append(value)
            result = core.compare_bsr(*rows, max_age_hours, core.timestamp(as_of, 'as_of'))
            state['workflow'].update(bsr_check={'observation_ids': [left, right], 'as_of': as_of,
                                                'max_age_hours': str(core.positive_hours(max_age_hours)), 'result': result},
                                     opportunity=None, review=None)
        return state

    @staticmethod
    def _blob(conn, sha256: str) -> bytes:
        row = conn.execute('SELECT content FROM artifact_blobs WHERE sha256=?', (sha256,)).fetchone()
        if row is None or digest(bytes(row[0])) != sha256:
            raise ProjectError('INTEGRITY_ERROR', 'Missing or changed artifact bytes')
        return bytes(row[0])

    def _artifact(self, conn, state, artifact_id: str, kind: str, content: bytes, provenance: str, source_name: str, *, synthetic: bool = True, binary: bool = False):
        identifier(artifact_id, 'artifact_id')
        if not content or len(content) > MAX_BYTES:
            raise ProjectError('INVALID_INPUT', 'Artifact must be nonempty and at most 5 MiB')
        if binary and kind!='research_image':
            raise ProjectError('INVALID_INPUT', 'Binary evidence is restricted to validated research images')
        if not binary: content.decode('utf-8')
        sha = digest(content)
        previous = [a for a in state['artifacts'] if a['artifact_id'] == artifact_id]
        if previous and previous[-1]['kind'] != kind:
            raise ProjectError('INVALID_INPUT', 'An artifact ID cannot change kind')
        conn.execute('INSERT OR IGNORE INTO artifact_blobs VALUES (?,?)', (sha, content))
        self._blob(conn, sha)
        item = {'artifact_id': artifact_id, 'revision': len(previous) + 1, 'kind': kind, 'sha256': sha,
                'size_bytes': len(content), 'source_name': source_name, 'provenance': provenance,
                'synthetic_context': synthetic, 'warnings': [WARNING] if synthetic else [], 'created_at': self.clock()}
        state['artifacts'].append(item)
        return item

    def save_artifact(self, expected_revision: int, artifact_id: str, kind: str, content: bytes,
                      provenance: str, source_name: str) -> dict[str, Any]:
        if kind not in {'outline', 'sample'} or provenance not in {'user_supplied', 'fixture_supplied'}:
            raise ProjectError('INVALID_INPUT', 'Only supplied outline/sample artifacts are supported')
        core.text(source_name, 'source_name')
        with self._change(expected_revision, 'save_supplied_' + kind) as (conn, state):
            if not state['workflow']['opportunity']:
                raise ProjectError('WORKFLOW_ORDER', 'Save a hypothetical opportunity brief first')
            self._artifact(conn, state, artifact_id, kind, content, provenance, source_name)
            state['workflow']['review'] = None
        return state

    @staticmethod
    def _content(kind: str, content: Any):
        if kind not in PROFILE_FIELDS or not isinstance(content, dict):
            raise ProjectError('INVALID_INPUT', 'Unknown decision kind or invalid content')
        fields = PROFILE_FIELDS[kind]
        missing = sorted(fields - content.keys())
        if missing:
            raise ProjectError('INVALID_INPUT', 'Required decision fields are missing', missing)
        if content.keys() - fields:
            raise ProjectError('INVALID_INPUT', 'Unknown decision fields: ' + ', '.join(sorted(content.keys() - fields)))
        for key, value in content.items():
            if key in {'hypothesis', 'hypothetical'}:
                if value is not True:
                    raise ProjectError('FIXTURE_ONLY', key + ' must be true in BP-001')
            elif key in LIST_FIELDS:
                if not isinstance(value, list):
                    raise ProjectError('INVALID_INPUT', key + ' must be an array')
                for item in value:
                    core.text(item, key)
            else:
                core.text(value, key)

    def save_decision(self, expected_revision: int, decision_id: str, kind: str, content: dict[str, Any],
                      evidence_ids: list[str] | None = None, artifact_refs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        identifier(decision_id, 'decision_id'); self._content(kind, content)
        evidence_ids = [] if evidence_ids is None else evidence_ids
        artifact_refs = [] if artifact_refs is None else artifact_refs
        if not isinstance(evidence_ids, list) or not all(isinstance(x, str) for x in evidence_ids) or not isinstance(artifact_refs, list):
            raise ProjectError('INVALID_INPUT', 'Evidence IDs and artifact references must be arrays')
        with self._change(expected_revision, 'save_draft_' + kind) as (conn, state):
            for evidence_id in evidence_ids:
                self._source(conn, evidence_id)
            for ref in artifact_refs:
                self._resolve_ref(state, ref, latest=True)
            if kind == 'author_voice' and set(content['sample_refs']) != {r['artifact_id'] for r in artifact_refs}:
                raise ProjectError('MISSING_SOURCE', 'Voice sample_refs must match exact artifact references')
            if kind == 'opportunity_brief':
                check = state['workflow']['bsr_check']
                if not check:
                    raise ProjectError('WORKFLOW_ORDER', 'Check BSR comparability before saving an opportunity brief')
                if not set(check['result']['evidence_ids']) <= set(evidence_ids):
                    raise ProjectError('MISSING_SOURCE', 'Opportunity must cite the checked sources', ['evidence_ids'])
            previous = [d for d in state['decisions'] if d['decision_id'] == decision_id]
            if any(d['kind'] == kind and d['decision_id'] != decision_id for d in state['decisions']):
                raise ProjectError('INVALID_INPUT', 'Reuse the existing decision ID when revising this kind')
            if previous and previous[-1]['kind'] != kind:
                raise ProjectError('INVALID_INPUT', 'A decision ID cannot change kind')
            item = {'decision_id': decision_id, 'revision': len(previous) + 1, 'kind': kind, 'status': 'draft',
                    'content': copy.deepcopy(content), 'content_sha256': digest(canonical(content)),
                    'evidence_ids': list(evidence_ids), 'artifact_refs': copy.deepcopy(artifact_refs),
                    'approval': None, 'synthetic_context': True, 'warnings': [WARNING, LOCAL_APPROVAL], 'created_at': self.clock()}
            state['decisions'].append(item)
            state['workflow']['review'] = None
            if kind in {'reader_profile', 'buyer_profile', 'author_voice', 'book_brief'}:
                state[kind] = copy.deepcopy(item)
                state['workflow']['opportunity'] = None
            else:
                state['workflow']['opportunity'] = {'decision_id': decision_id, 'revision': item['revision']}
        return state

    @staticmethod
    def _resolve_ref(state, ref, *, latest=False):
        if not isinstance(ref, dict) or set(ref) != {'artifact_id', 'revision', 'sha256'}:
            raise ProjectError('INVALID_INPUT', 'Artifact reference requires ID, revision and hash')
        require_revision(ref['revision'])
        matches = [a for a in state['artifacts'] if a['artifact_id'] == ref['artifact_id']]
        if not any(all(a[k] == v for k, v in ref.items()) for a in matches):
            raise ProjectError('MISSING_SOURCE', 'Artifact reference not found in this project')
        if latest and not all(matches[-1][k] == v for k, v in ref.items()):
            raise ProjectError('STALE_APPROVAL', 'Artifact changed; use the latest revision')

    def approve_decision(self, expected_revision: int, decision_id: str, decision_revision: int, actor: str) -> dict[str, Any]:
        core.text(actor, 'actor')
        with self._change(expected_revision, 'record_local_approval') as (conn, state):
            matches = [d for d in state['decisions'] if d['decision_id'] == decision_id]
            if not matches:
                raise ProjectError('NOT_FOUND', 'Decision not found')
            prior = matches[-1]
            if type(decision_revision) is not int or prior['revision'] != decision_revision or prior['status'] != 'draft':
                raise ProjectError('STALE_APPROVAL', 'Approval must refer to the latest draft decision')
            if prior['kind'] == 'opportunity_brief' and state['workflow']['opportunity'] != {'decision_id': decision_id, 'revision': decision_revision}:
                raise ProjectError('STALE_APPROVAL', 'Opportunity was invalidated; check evidence and save a new draft')
            for ref in prior['artifact_refs']:
                self._resolve_ref(state, ref, latest=True)
            item = copy.deepcopy(prior)
            item.update(revision=prior['revision'] + 1, status='approved', created_at=self.clock(),
                        approval={'actor_declaration': actor, 'approved_draft_revision': decision_revision,
                                  'content_sha256': prior['content_sha256'], 'scope': 'local_review_only',
                                  'trusted_external_authorization': False})
            state['decisions'].append(item)
            if item['kind'] in {'reader_profile', 'buyer_profile', 'author_voice', 'book_brief'}:
                state[item['kind']] = copy.deepcopy(item)
            elif state['workflow']['opportunity'] == {'decision_id': decision_id, 'revision': decision_revision}:
                state['workflow']['opportunity']['revision'] = item['revision']
            state['workflow']['review'] = None
        return state

    def decisions(self, decision_id: str | None = None, approved_only: bool = False) -> dict[str, Any]:
        state = self.read()
        rows = []
        for item in state['decisions']:
            if decision_id is not None and item['decision_id'] != decision_id:
                continue
            if approved_only and item['status'] != 'approved':
                continue
            current = item == [d for d in state['decisions'] if d['decision_id'] == item['decision_id']][-1]
            if item['kind'] == 'opportunity_brief':
                current = current and state['workflow']['opportunity'] == {'decision_id': item['decision_id'], 'revision': item['revision']}
            try:
                for ref in item['artifact_refs']:
                    self._resolve_ref(state, ref, latest=True)
            except ProjectError:
                current = False
            rows.append(dict(item, current=current, usable_local_approval=current and item['status'] == 'approved'))
        return {'project_id': self.project_id, 'revision': state['revision'], 'decisions': rows,
                'warnings': [WARNING, LOCAL_APPROVAL], 'publication_authorized': False}

    def artifact(self, artifact_id: str, revision: int | None = None) -> dict[str, Any]:
        if revision is not None:
            require_revision(revision)
        conn = core.connect(self.root)
        try:
            conn.execute('BEGIN')
            state = self._read(conn)
            matches = [a for a in state['artifacts'] if a['artifact_id'] == artifact_id and (revision is None or a['revision'] == revision)]
            if not matches:
                raise ProjectError('NOT_FOUND', 'Artifact revision not found')
            item = matches[-1]
            return {'artifact': item, 'content': self._blob(conn, item['sha256']).decode('utf-8'), 'warnings': item.get('warnings', [])}
        finally:
            conn.close()

    def review(self, expected_revision: int) -> dict[str, Any]:
        with self._change(expected_revision, 'local_review_summary') as (conn, state):
            if state['workflow']['phase'] not in {'sample_saved', 'review_complete', 'synthetic_demo_complete'}:
                raise ProjectError('WORKFLOW_ORDER', 'Opportunity, supplied outline and sample are required')
            latest = {a['artifact_id']: a for a in state['artifacts'] if a['kind'] != 'review'}
            missing = [key for key in ('reader_profile', 'buyer_profile', 'author_voice', 'book_brief') if state[key] is None]
            lines = ['# Local review summary', '', WARNING, '',
                     f"Project: {self.project_id}; reviewed state revision: {state['revision']}", '',
                     'This is a local inventory and comparability check. No editorial, factual, rights, policy or formatting review was performed.', '',
                     '## BSR check', '', json.dumps(state['workflow']['bsr_check'], ensure_ascii=False, sort_keys=True), '',
                     '## Supplied artifacts', '']
            for item in latest.values():
                lines.append(f"- {item['kind']}: {item['artifact_id']} revision {item['revision']}; SHA-256 {item['sha256']}; {item['provenance']}")
            lines += ['', '## Missing information and next steps', '',
                      '- Missing profiles: ' + (', '.join(missing) or 'none; stored profiles remain supplied hypotheses/declarations.'),
                      '- Review the supplied outline and sample with the author. No writing quality score was computed.',
                      '- Keep this synthetic demo unchanged; start a separate BP-002 research project for real evidence.',
                      '- Independent editorial/reader approval and publication remain unavailable. Legacy export helpers are experimental, not publication validation.',
                      '- Costs: no external service was called; future provider/host inference costs are unknown.',
                      '- ' + LOCAL_APPROVAL, '- Publication authorized: false.', '']
            item = self._artifact(conn, state, 'local-review', 'review', '\n'.join(lines).encode(), 'local_deterministic_summary', 'local-review.md')
            state['workflow']['review'] = {'artifact_id': item['artifact_id'], 'revision': item['revision'], 'sha256': item['sha256'],
                                           'reviewed_project_revision': state['revision'], 'status': 'NEEDS_REVIEW', 'missing_fields': missing}
        return state

    def export_artifact(self, artifact_id: str, revision: int | None = None) -> dict[str, Any]:
        result = self.artifact(artifact_id, revision)
        item, content = result['artifact'], result['content'].encode('utf-8')
        parent = core.scoped_path(self.root/'exports')
        parent.mkdir(exist_ok=True, mode=0o700)
        target = parent/f"{item['artifact_id']}.r{item['revision']}.{item['sha256'][:12]}.md"
        if target.exists() or target.is_symlink():
            raise ProjectError('ALREADY_EXISTS', 'Export exists; nothing was overwritten')
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(prefix='.bp-export-', dir=parent, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(content); stream.flush(); os.fsync(stream.fileno())
            os.link(temporary, target)  # atomic, exclusive, complete bytes only
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return {'artifact': item, 'path': str(target), 'warnings': [WARNING]}


def capabilities() -> dict[str, Any]:
    return core.capabilities()

def execute(operation: str, *, workspace: Path | None = None, project_id: str | None = None,
            expected_revision: int | None = None, **params) -> dict[str, Any]:
    """Public transport-neutral API; all operations return the same typed envelope."""
    started, tick = core.iso_now(), time.perf_counter()
    status, data, error, missing = 'OK', {}, None, []
    warnings, evidence_ids, artifacts = [], [], []
    cost = Cost(state='KNOWN', estimated='0', actual='0')
    try:
        if operation == 'capabilities':
            data = capabilities()
        elif operation == 'init':
            if workspace is None:
                raise ProjectError('INVALID_INPUT', 'Workspace required', ['workspace'])
            data = initialize(Path(workspace), **params)
        else:
            if workspace is None or project_id is None:
                raise ProjectError('INVALID_INPUT', 'Workspace and project ID required', ['workspace', 'project_id'])
            store = Store(Path(workspace), project_id)
            if operation == 'migrate':
                data = migrate(Path(workspace), project_id, expected_revision)
            else:
                store.read()  # Validate scope even for unavailable/unknown operations.
                if operation == 'read':
                    data = store.read(**params)
                elif operation == 'history':
                    data = store.history()
                elif operation == 'records':
                    data = store.records()
                elif operation == 'decisions':
                    data = store.decisions(**params)
                elif operation == 'artifact':
                    data = store.artifact(**params)
                elif operation == 'export_artifact':
                    data = store.export_artifact(**params)
                elif operation in {'import_evidence', 'import_bsr', 'check_bsr', 'save_decision', 'approve_decision', 'save_artifact', 'review'}:
                    data = getattr(store, operation)(expected_revision, **params)
                    if operation == 'review':
                        status = 'NEEDS_REVIEW'
                        missing = data['workflow']['review']['missing_fields']
                    elif operation == 'check_bsr' and data['workflow']['bsr_check']['result']['issues']:
                        status = 'NEEDS_REVIEW'
                elif operation in INTEGRATIONS or operation == 'opportunity.real_recommendation':
                    status, cost = 'UNAVAILABLE', Cost()
                    data = {'implemented': False, 'tool': operation, 'result': None, 'performed': False}
                    warnings.append('No implementation ran; no market data, manuscript, review, receipt or provider charge was invented.')
                else:
                    raise ProjectError('UNKNOWN_OPERATION', 'Unknown operation denied')
        if operation != 'capabilities':
            warnings += [WARNING, LOCAL_APPROVAL]
        evidence_ids = data.get('evidence_ids', [])
        if isinstance(data.get('workflow'), dict) and data['workflow'].get('bsr_check'):
            evidence_ids = list(dict.fromkeys(evidence_ids + data['workflow']['bsr_check']['result']['evidence_ids']))
        artifacts = [{k: a[k] for k in ('artifact_id', 'revision', 'sha256')} for a in data.get('artifacts', [])]
        if 'artifact' in data:
            artifacts = [{k: data['artifact'][k] for k in ('artifact_id', 'revision', 'sha256')}]
    except ProjectError as exc:
        status = 'BLOCKED' if exc.code in {'PROJECT_MISMATCH', 'STALE_REVISION', 'STALE_APPROVAL', 'FIXTURE_ONLY', 'WORKFLOW_ORDER', 'UNKNOWN_OPERATION', 'MIGRATION_REQUIRED', 'UNSUPPORTED_SCHEMA'} else 'ERROR'
        error, missing = {'code': exc.code, 'message': str(exc)}, exc.missing_fields
    except sqlite3.IntegrityError as exc:
        status, error = 'ERROR', {'code': 'CONFLICT', 'message': 'Duplicate or invalid record; transaction rolled back: ' + str(exc)}
    except (core.CoreError, OSError, sqlite3.Error, ValueError, TypeError, KeyError) as exc:
        status, error = 'ERROR', {'code': 'INVALID_INPUT_OR_IO', 'message': str(exc)}
    if operation not in {'capabilities'} and WARNING not in warnings:
        warnings.append(WARNING)
    return ToolResult(status=status, data=data, operation_id=str(uuid4()),
                      timing={'started_at': started, 'elapsed_ms': round((time.perf_counter()-tick)*1000, 3)},
                      evidence_ids=evidence_ids, warnings=warnings, missing_fields=missing,
                      error=error, cost=cost, artifact_refs=artifacts).to_dict()


class JsonParser(argparse.ArgumentParser):
    def error(self, message):
        raise ProjectError('INVALID_ARGUMENTS', message)


def main(argv: list[str] | None = None) -> int:
    started, tick = core.iso_now(), time.perf_counter()
    parser = JsonParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    subs.add_parser('capabilities')
    init = subs.add_parser('init')
    for key in ('workspace', 'title', 'country', 'language', 'budget', 'currency'):
        init.add_argument('--' + key, required=True)
    # Development fixtures are optional and excluded from the clean public setup.
    if (Path(__file__).with_name('publishing_demo.py').is_file() and
            (Path(__file__).resolve().parents[1]/'assets/bp001-demo.json').is_file()):
        demo_parser = subs.add_parser('demo')
        demo_parser.add_argument('--workspace', type=Path, required=True)
    mutations = {'migrate', 'import-evidence', 'import-bsr', 'check-bsr', 'save-decision', 'approve-decision', 'save-artifact', 'review'}
    for name in ('read', 'history', 'records', 'decisions', 'artifact', 'export-artifact', 'invoke', *sorted(mutations)):
        sub = subs.add_parser(name)
        sub.add_argument('--workspace', type=Path, required=True)
        sub.add_argument('--project-id', required=True)
        if name in mutations:
            sub.add_argument('--expected-revision', type=int, required=True)
        if name in {'read', 'artifact', 'export-artifact'}:
            sub.add_argument('--revision', type=int)
        if name in {'import-evidence', 'import-bsr', 'save-decision', 'save-artifact'}:
            sub.add_argument('--input', type=Path, required=True)
        if name in {'save-decision', 'approve-decision', 'decisions'}:
            sub.add_argument('--decision-id', required=name != 'decisions')
        if name == 'decisions':
            sub.add_argument('--approved-only', action='store_true')
        if name == 'check-bsr':
            for key in ('left', 'right', 'max-age-hours', 'as-of'):
                sub.add_argument('--' + key, required=True)
        if name in {'save-decision', 'save-artifact'}:
            sub.add_argument('--kind', required=True)
        if name == 'approve-decision':
            sub.add_argument('--decision-revision', required=True, type=int)
            sub.add_argument('--actor', required=True)
        if name in {'artifact', 'save-artifact', 'export-artifact'}:
            sub.add_argument('--artifact-id', required=True)
        if name == 'save-artifact':
            sub.add_argument('--provenance', choices=['user_supplied', 'fixture_supplied'], required=True)
        if name == 'invoke':
            sub.add_argument('--tool', required=True, choices=[*INTEGRATIONS, 'opportunity.real_recommendation'])
    try:
        args = vars(parser.parse_args(argv))
        operation = args.pop('command').replace('-', '_')
        if operation == 'demo':
            from publishing_demo import run_demo
            result = run_demo(args['workspace'])
        else:
            if 'input' in args:
                path = args.pop('input')
                raw = load_input(path)
                if operation == 'save_artifact':
                    args.update(content=raw, source_name=path.name)
                else:
                    value = json.loads(raw)
                    if operation == 'save_decision':
                        if not isinstance(value, dict) or not set(value) <= {'content', 'evidence_ids', 'artifact_refs'} or 'content' not in value:
                            raise ProjectError('INVALID_INPUT', 'Decision input requires content and optional evidence_ids/artifact_refs')
                        args.update(value)
                    else:
                        args['record'] = value
            if operation == 'invoke':
                operation = args.pop('tool')
            result = execute(operation, **args)
    except (ProjectError, OSError, ValueError, sqlite3.Error, TypeError) as exc:
        result = ToolResult(status='ERROR', data={}, operation_id=str(uuid4()),
                            timing={'started_at': started, 'elapsed_ms': round((time.perf_counter()-tick)*1000, 3)}, warnings=[WARNING],
                            error={'code': getattr(exc, 'code', 'INVALID_INPUT_OR_IO'), 'message': str(exc)},
                            missing_fields=getattr(exc, 'missing_fields', []), cost=Cost(state='KNOWN', actual='0')).to_dict()
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if result['status'] in {'OK', 'PARTIAL', 'NEEDS_REVIEW'} else 3 if result['status'] == 'UNAVAILABLE' else 2


if __name__ == '__main__':
    raise SystemExit(main())

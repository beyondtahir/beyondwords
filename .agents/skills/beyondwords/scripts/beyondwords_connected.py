"""Durable external-action journal. Local operator boundary, not a host-shell sandbox."""
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
from uuid import uuid4

from publishing_core import scoped_path


def now():
    return datetime.now(timezone.utc)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def instant(value):
    d = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if d.tzinfo is None:
        raise ValueError('Timezone required')
    return d.astimezone(timezone.utc)


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}', value):
        raise ValueError('Invalid identifier')
    return value


def clean_text(value, maximum=250):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or any(ord(c) < 32 for c in value):
        raise ValueError('A bounded nonempty text value without control characters is required')
    return value


class ConnectionError(ValueError):
    def __init__(self, code, message, *, uncertain=False):
        super().__init__(message)
        self.code, self.uncertain = code, uncertain


class Journal:
    """One private directory per book. Atomic claims prevent concurrent duplicate dispatch."""
    def __init__(self, directory, project_id, *, clock=now):
        self.root = scoped_path(Path(directory))
        self.project_id = identifier(project_id)
        self.clock = clock
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.root/'connections.sqlite3'
        if self.path.is_symlink():
            raise ValueError('Connection database cannot be a symlink')
        if not self.path.exists():
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(fd)
            except FileExistsError:
                pass  # Another initializer created the file; SQLite serializes schema creation.
        with self.db() as db:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if not tables and version == 0:
                schema = '''
                    CREATE TABLE identity(project TEXT NOT NULL);
                    CREATE TABLE operations(id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL,
                        plan TEXT NOT NULL, state TEXT NOT NULL, receipt TEXT, created TEXT NOT NULL);
                    CREATE TABLE events(seq INTEGER PRIMARY KEY, operation_id TEXT NOT NULL,
                        state TEXT NOT NULL, at TEXT NOT NULL, detail TEXT NOT NULL);
                    CREATE TABLE monitors(id TEXT PRIMARY KEY, config TEXT NOT NULL, digest TEXT NOT NULL,
                        next_run TEXT NOT NULL, lease_until TEXT, lease_token TEXT, last_result TEXT,
                        paused INTEGER NOT NULL DEFAULT 0);
                    PRAGMA user_version=1;
                '''
                for statement in schema.split(';'):
                    if statement.strip(): db.execute(statement)
                db.execute('INSERT INTO identity VALUES (?)', (project_id,))
            elif version != 1 or tables != {'identity', 'operations', 'events', 'monitors'}:
                raise ValueError('Unknown connection database/schema; no migration performed')
            rows = db.execute('SELECT project FROM identity').fetchall()
            if len(rows) != 1 or rows[0][0] != self.project_id:
                raise ValueError('Connection journal belongs to another project')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def prepare(self, plan, *, lifetime_minutes=30):
        if type(lifetime_minutes) is not int or not 1 <= lifetime_minutes <= 60:
            raise ValueError('Approval lifetime must be 1–60 minutes')
        plan = json.loads(canonical(plan))
        if plan.get('project_id') != self.project_id or type(plan.get('synthetic')) is not bool:
            raise ValueError('Plan project and explicit synthetic marker required')
        fingerprint = digest(plan)
        plan['expires_at'] = (self.clock()+timedelta(minutes=lifetime_minutes)).isoformat()
        op_id = str(uuid4())
        with self.db() as db:
            old = db.execute("SELECT id FROM operations WHERE fingerprint=? AND state!='CANCELLED'", (fingerprint,)).fetchone()
            if plan.get('intent_sha256'):
                for row in db.execute("SELECT id,plan FROM operations WHERE state!='CANCELLED'"):
                    if json.loads(row['plan']).get('intent_sha256') == plan['intent_sha256']:
                        old = row
                        break
            if old:
                op_id = old['id']
            else:
                db.execute('INSERT INTO operations VALUES (?,?,?,?,?,?)',
                           (op_id, fingerprint, canonical(plan), 'PREPARED', None, self.clock().isoformat()))
                self._event(db, op_id, 'PREPARED', {'plan_sha256': digest(plan)})
        return self.get(op_id)

    def _event(self, db, op_id, state, detail):
        db.execute('INSERT INTO events(operation_id,state,at,detail) VALUES (?,?,?,?)',
                   (op_id, state, self.clock().isoformat(), canonical(detail)))

    def get(self, op_id):
        with self.db() as db:
            row = db.execute('SELECT * FROM operations WHERE id=?', (identifier(op_id),)).fetchone()
            if not row:
                raise ValueError('Unknown operation')
            plan = json.loads(row['plan'])
            body = dict(plan); body.pop('expires_at')
            if digest(body) != row['fingerprint']:
                raise ValueError('Operation integrity check failed')
            return dict(id=op_id, plan=plan, plan_sha256=digest(plan), state=row['state'],
                        receipt=json.loads(row['receipt']) if row['receipt'] else None,
                        approval_current=instant(plan['expires_at']) > self.clock(),
                        synthetic=plan['synthetic'], publication_ready=False)

    def claim(self, op_id, plan_sha256):
        # Recheck after approval and after any account reads. No network inside transaction.
        op = self.get(op_id)
        if not op['approval_current'] or op['plan_sha256'] != plan_sha256:
            raise ConnectionError('STALE_APPROVAL', 'Plan changed or approval expired')
        with self.db() as db:
            for row in db.execute("SELECT id,plan FROM operations WHERE state IN ('IN_FLIGHT','UNKNOWN') AND id!=?", (op_id,)):
                other=json.loads(row['plan'])
                if other.get('adapter')==op['plan'].get('adapter') and other.get('identity',other.get('account_label'))==op['plan'].get('identity',op['plan'].get('account_label')):
                    raise ConnectionError('RECONCILE_REQUIRED','Another action for this account has an unresolved outcome')
            n = db.execute("UPDATE operations SET state='IN_FLIGHT' WHERE id=? AND state='PREPARED' AND plan=?",
                           (op_id, canonical(op['plan']))).rowcount
            if n != 1:
                raise ConnectionError('RECONCILE_REQUIRED', 'Operation already dispatched or closed; never blindly repeat it')
            self._event(db, op_id, 'IN_FLIGHT', {'plan_sha256': plan_sha256})
        return op['plan']

    def finish(self, op_id, state, receipt):
        try:
            return self._finish(op_id,state,receipt)
        except (sqlite3.Error,OSError):
            raise ConnectionError('RECEIPT_WRITE_FAILED','An action was dispatched but its receipt could not be persisted; inspect and reconcile before retrying',uncertain=True) from None

    def _finish(self, op_id, state, receipt):
        if state not in {'CONFIRMED', 'REJECTED', 'UNKNOWN'}:
            raise ValueError('Invalid outcome')
        with self.db() as db:
            changed = db.execute("UPDATE operations SET state=?,receipt=? WHERE id=? AND state IN ('IN_FLIGHT','UNKNOWN')",
                                 (state, canonical(receipt), op_id)).rowcount
            if changed != 1:
                raise ValueError('Outcome requires a dispatched operation')
            self._event(db, op_id, state, receipt)
        return self.get(op_id)

    def list(self):
        with self.db() as db:
            rows = db.execute('SELECT id,state,created FROM operations ORDER BY created').fetchall()
            return [dict(r) for r in rows]

    def cancel(self, op_id):
        with self.db() as db:
            n=db.execute("UPDATE operations SET state='CANCELLED' WHERE id=? AND state='PREPARED'",(identifier(op_id),)).rowcount
            if n!=1: raise ValueError('Only an unsent prepared operation can be cancelled')
            self._event(db,op_id,'CANCELLED',{'sent':False})
        return {'id':op_id,'state':'CANCELLED','sent':False}


def operator_confirmation(op):
    """Connector-owned attended approval; no --yes / input JSON approval bypass.

    This is not authentication against an agent with unrestricted local shell/PTY access.
    A deployment needing that boundary must restrict connector execution outside the host.
    """
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise ConnectionError('OWNER_REQUIRED', 'Open this prepared operation in an attended terminal to approve it')
    sys.stderr.write('\nReview the exact account action:\n'+json.dumps(op, indent=2, ensure_ascii=True)+'\n')
    phrase = 'APPROVE '+op['plan_sha256'][:12]
    sys.stderr.write('Type '+phrase+' to send this exact action, or anything else to cancel: ')
    sys.stderr.flush()
    if sys.stdin.readline().strip() != phrase:
        raise ConnectionError('CANCELLED', 'Operation cancelled before dispatch')
    return op['plan_sha256']


def inspect():
    return {'amazon_ads': {'implemented': True, 'authenticated': False,
                           'credential_environment_present': all(os.environ.get('BEYONDWORDS_ADS_'+k) for k in ('CLIENT_ID','CLIENT_SECRET','REFRESH_TOKEN')),
                           'actions': ['profiles','query','prepare','execute','reconcile','report-request','report-status','report-download']},
            'kdp': {'implemented': 'attended browser steps', 'authenticated': False,
                    'requires': 'A visible isolated browser, owner login and currently inspected controls'},
            'monitor': {'implemented': 'durable local worker and host scheduler handoff', 'running': False},
            'warnings': ['Inspection does not connect accounts or prove a scheduler is running.']}


def execute(directory, project_id, payload):
    action = payload.get('action')
    if action == 'inspect':
        return inspect()
    if not directory or not project_id:
        raise ValueError('A private connection directory and project ID are required')
    journal = Journal(directory, project_id)
    if action == 'operations':
        return {'operations': journal.list()}
    if action == 'operation':
        return journal.get(payload['operation_id'])
    if action == 'cancel':
        return journal.cancel(payload['operation_id'])
    if action == 'ads':
        from beyondwords_amazon_ads import dispatch
        return dispatch(journal, payload)
    if action == 'monitor':
        from beyondwords_monitor import dispatch
        return dispatch(journal, payload)
    raise ValueError('Unknown connected action')

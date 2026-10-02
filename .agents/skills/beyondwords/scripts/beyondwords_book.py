"""Versioned book production on the existing Beyondwords project store.

All approvals/reviews are local declarations, never external authorization.
Text is supplied by the author or a separately available host model. No model,
account, or advertising API is invented here.
"""
from __future__ import annotations

import copy
from datetime import date
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

import publishing_core as core
import publishing_project as project

Error = project.ProjectError
VERSION = '1.1.0'
CONTENT_KINDS = {'plan', 'chapter', 'source', 'claim', 'asset', 'bible', 'visual_layout'}
ROUTES = {'nonfiction', 'fiction', 'children', 'comics', 'workbook', 'coloring', 'puzzles', 'art', 'activity'}
PROVENANCE = {'human_authored', 'ai_assisted', 'ai_generated', 'unknown'}
REVIEW_ROLES = {'author', 'editorial', 'reader', 'cover', 'visual', 'rights'}


def fail(message, code='INVALID_INPUT'):
    raise Error(code, message)


def obj(value):
    if not isinstance(value, dict):
        fail('Expected a JSON object')
    return copy.deepcopy(value)


def text(value, field, limit=8000):
    return core.text(value, field, limit)


def strings(value, field, *, nonempty=False):
    if not isinstance(value, list) or len(value) > 1000 or (nonempty and not value):
        fail(field + ' must be a list' + (' with at least one item' if nonempty else ''))
    return [text(x, field) for x in value]


def latest(book, kind, key=None):
    found = {}
    for row in book['records']:
        if row['kind'] == kind:
            found[row['id']] = row
    return found.get(key) if key is not None else list(found.values())


def content_hash(book):
    refs = sorted((r['kind'], r['id'], r['revision'], r['sha256'])
                  for kind in CONTENT_KINDS for r in latest(book, kind))
    return project.digest(project.canonical(refs))


def reviewed_policies(state):
    research = state.get('research', {})
    return project.digest(project.canonical({
        'policies': research.get('policies', []), 'reviews': research.get('policy_reviews', [])}))


class BookStore(project.Store):
    def _book(self, state):
        book = state.get('book')
        if not book or book.get('schema_version') != 1:
            fail('Enable the Beyondwords book workflow first', 'MIGRATION_REQUIRED')
        return book

    def enable(self, revision, *, synthetic=False):
        if type(synthetic) is not bool:
            fail('synthetic must be an explicit boolean')
        with self._change(revision, 'enable_book_v1') as (_, state):
            if state.get('book'):
                fail('Book workflow already enabled; existing work was preserved', 'ALREADY_EXISTS')
            if state.get('research'):
                if state['research']['synthetic'] != synthetic:
                    fail('Cannot convert synthetic research into a real book project')
            elif not synthetic and (state['artifacts'] or state['decisions'] or state['evidence_ids']):
                fail('Keep fixture projects synthetic; use a fresh real project')
            state['book'] = {'schema_version': 1, 'synthetic': synthetic, 'records': []}
            state['mode'] = 'synthetic_book' if synthetic else 'book'
            state['warnings'] = ([core.SYNTHETIC_WARNING] if synthetic else []) + [project.LOCAL_APPROVAL]
        return state

    def _save(self, conn, state, kind, key, value):
        book = self._book(state)
        project.identifier(key, 'record_id')
        prior = latest(book, kind, key)
        item = self._artifact(conn, state, f'book-{kind}-{key}', 'book_' + kind,
                              project.canonical(value), 'local_record', key + '.json',
                              synthetic=book['synthetic'])
        record = dict(kind=kind, id=key, revision=1 if prior is None else prior['revision']+1,
                      sha256=item['sha256'], artifact_ref=item, data=value, recorded_at=self.clock())
        book['records'].append(record)
        return record

    def _binary(self, conn, state, name, data, media_type):
        if not isinstance(data, bytes) or not data or len(data) > 32*1024*1024:
            fail('Binary artifacts must be nonempty and at most 32 MiB')
        sha = project.digest(data)
        conn.execute('INSERT OR IGNORE INTO artifact_blobs VALUES (?,?)', (sha, data))
        self._blob(conn, sha)
        identifier = 'binary-' + project.digest(name.encode())[:16]
        previous = [a for a in state['artifacts'] if a['artifact_id'] == identifier]
        item = dict(artifact_id=identifier, revision=len(previous)+1, kind='book_binary',
                    sha256=sha, size_bytes=len(data), source_name=name, media_type=media_type,
                    provenance='local_artifact', synthetic_context=self._book(state)['synthetic'],
                    created_at=self.clock())
        state['artifacts'].append(item)
        return item

    def plan(self, revision, payload):
        value = obj(payload)
        for field in ('title', 'author', 'language', 'promise', 'reader', 'buyer', 'author_experience', 'voice'):
            text(value.get(field), field)
        if value.get('route') not in ROUTES:
            fail('Choose a supported planning route: ' + ', '.join(sorted(ROUTES)))
        if not re.fullmatch(r'[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*', value['language']):
            fail('language must use a BCP-47 style tag')
        strings(value.get('differentiation'), 'differentiation', nonempty=True)
        chapters = value.get('chapters')
        if not isinstance(chapters, list) or not 1 <= len(chapters) <= 300:
            fail('Plan needs 1–300 chapter/scene/spread contracts')
        ids = []
        for chapter in chapters:
            obj(chapter)
            ids.append(project.identifier(chapter.get('id'), 'chapter.id'))
            for field in ('title', 'purpose', 'deliverable'):
                text(chapter.get(field), 'chapter.' + field)
        if len(ids) != len(set(ids)):
            fail('Chapter IDs must be unique')
        with self._change(revision, 'book_plan') as (conn, state):
            book = self._book(state)
            existing = {r['id'] for r in latest(book, 'chapter')}
            if existing - set(ids):
                fail('Plan omits existing chapters; preserve them or explicitly archive in a separate project')
            self._save(conn, state, 'plan', 'main', value)
        return state

    def chapter(self, revision, payload):
        value = obj(payload)
        key = project.identifier(value.get('id'), 'id')
        text(value.get('body'), 'body', project.MAX_BYTES//2)
        for field in ('change_summary', 'rights_basis'):
            text(value.get(field), field)
        if value.get('provenance') not in PROVENANCE:
            fail('Declare text provenance, including unknown when appropriate')
        if not isinstance(value.get('continuity', {}), dict):
            fail('continuity must be an object')
        with self._change(revision, 'book_chapter') as (conn, state):
            book = self._book(state)
            plan = latest(book, 'plan', 'main')
            if not plan or key not in {c['id'] for c in plan['data']['chapters']}:
                fail('Save a plan with this chapter ID first', 'WORKFLOW_ORDER')
            value['plan_sha256'] = plan['sha256']
            self._save(conn, state, 'chapter', key, value)
        return state

    def source(self, revision, payload):
        value = obj(payload)
        key = project.identifier(value.get('id'), 'id')
        for field in ('title', 'excerpt', 'permission_basis', 'reviewed_by'):
            text(value.get(field), field, 20000)
        if value.get('origin') not in {'author_notes', 'authorized_import', 'permitted_source'}:
            fail('Unknown source origin')
        if value['origin'] != 'author_notes':
            source_url = value.get('url')
            from publishing_browser import check_url, AccessError
            try:
                check_url(source_url, source_url, resolve=False)
            except (AccessError, TypeError):
                fail('Sources require a safe public HTTPS URL')
        if core.timestamp(value.get('observed_at'), 'observed_at') > core.timestamp(self.clock(), 'now'):
            fail('Source observation cannot be in the future')
        if any(value.get(k) is not True for k in ('retain', 'derive')):
            fail('Source retention and derived use must be authorized', 'PERMISSION_REQUIRED')
        if type(value.get('synthetic')) is not bool:
            fail('Declare whether the source is synthetic')
        with self._change(revision, 'book_source') as (conn, state):
            if self._book(state)['synthetic'] != value['synthetic']:
                fail('Synthetic sources cannot cross into real projects')
            value['provenance_verified'] = False
            self._save(conn, state, 'source', key, value)
        return state

    def claim(self, revision, payload):
        value = obj(payload)
        key = project.identifier(value.get('id'), 'id')
        for field in ('chapter_id', 'quote', 'rationale'):
            text(value.get(field), field)
        if value.get('kind') not in {'fact', 'opinion', 'illustrative', 'author_experience'}:
            fail('Unknown claim kind')
        if value.get('finding') not in {'pending', 'supported', 'contradicted'}:
            fail('Unknown evidence finding')
        refs = strings(value.get('source_ids'), 'source_ids')
        if value['finding'] == 'supported':
            text(value.get('reviewed_by'), 'reviewed_by')
            if value['kind'] in {'fact', 'author_experience'} and not refs:
                fail('A supported factual/experience claim needs a stored source')
        with self._change(revision, 'book_claim') as (conn, state):
            book = self._book(state)
            chapter = latest(book, 'chapter', value['chapter_id'])
            if not chapter or value['quote'] not in chapter['data']['body']:
                fail('Claim quote must occur in the current chapter', 'MISSING_SOURCE')
            value['chapter_sha256'] = chapter['sha256']
            value['source_refs'] = []
            for source_id in refs:
                source = latest(book, 'source', source_id)
                if not source:
                    fail('Source is missing from this project: ' + source_id, 'MISSING_SOURCE')
                value['source_refs'].append({'id': source_id, 'sha256': source['sha256']})
            value['semantic_support_independently_verified'] = False
            self._save(conn, state, 'claim', key, value)
        return state

    def review(self, revision, payload):
        value = obj(payload)
        key = project.identifier(value.get('id'), 'id')
        if value.get('role') not in REVIEW_ROLES or value.get('result') not in {'pass', 'changes_requested'}:
            fail('Unknown review role or result')
        if value.get('reviewer_type') not in {'human', 'model'}:
            fail('Identify human versus model review')
        for field in ('reviewer', 'notes', 'subject_sha256'):
            text(value.get(field), field)
        if type(value.get('independent')) is not bool:
            fail('independent must be an explicit declaration')
        if value['reviewer_type'] == 'model' and value['independent']:
            fail('Model critique is not independent human review')
        with self._change(revision, 'book_review') as (conn, state):
            book = self._book(state)
            if value['subject_sha256'] != content_hash(book):
                fail('Content changed before review; review the current version', 'STALE_REVIEW')
            value['identity_verified'] = False
            value['external_authorization'] = False
            self._save(conn, state, 'review', key, value)
        return state

    def asset(self, revision, payload, data):
        value = obj(payload)
        key = project.identifier(value.get('id'), 'id')
        if value.get('provenance') not in PROVENANCE:
            fail('Declare image provenance')
        for field in ('rights_basis', 'alt_text'):
            text(value.get(field), field)
        from beyondwords_production import inspect_image
        value['inspection'] = inspect_image(data)
        with self._change(revision, 'book_asset') as (conn, state):
            value['file'] = self._binary(conn, state, key+'.png', data, value['inspection']['media_type'])
            self._save(conn, state, 'asset', key, value)
        return state

    def manuscript(self, state=None):
        state = state or self.read()
        book = self._book(state)
        plan = latest(book, 'plan', 'main')
        if not plan:
            fail('Book plan missing', 'WORKFLOW_ORDER')
        sections = []
        if book['synthetic']:
            sections.append('# Synthetic demonstration\n\n' + core.SYNTHETIC_WARNING)
        for contract in plan['data']['chapters']:
            chapter = latest(book, 'chapter', contract['id'])
            if chapter is None:
                fail('Missing chapter: ' + contract['id'], 'MISSING_CHAPTER')
            sections.append('# ' + contract['title'] + '\n\n' + chapter['data']['body'])
        return '\n\n'.join(sections) + '\n'

    def status(self, state=None):
        state = state or self.read()
        book = self._book(state)
        fingerprint = content_hash(book)
        plan = latest(book, 'plan', 'main')
        missing, findings = [], []
        if not plan:
            missing.append('book_plan')
        else:
            for contract in plan['data']['chapters']:
                chapter = latest(book, 'chapter', contract['id'])
                if not chapter:
                    missing.append('chapter:' + contract['id'])
                elif chapter['data']['plan_sha256'] != plan['sha256']:
                    missing.append('chapter_contract_recheck:' + contract['id'])
                elif chapter['data']['provenance'] == 'unknown':
                    missing.append('text_provenance:' + contract['id'])
        for row in latest(book, 'claim'):
            claim = row['data']
            chapter = latest(book, 'chapter', claim['chapter_id'])
            current = chapter is not None and chapter['sha256'] == claim['chapter_sha256']
            for ref in claim['source_refs']:
                source = latest(book, 'source', ref['id'])
                current = current and source is not None and source['sha256'] == ref['sha256']
            if not current or claim['finding'] != 'supported':
                findings.append({'claim_id': row['id'], 'finding': 'stale' if not current else claim['finding']})
        # Deliberately modest diagnostics: exact repeated paragraphs, never an authorship score.
        paragraphs = {}
        for row in latest(book, 'chapter'):
            for paragraph in re.split(r'\n\s*\n', row['data']['body']):
                normalized = ' '.join(paragraph.casefold().split())
                if len(normalized) > 120:
                    paragraphs.setdefault(normalized, []).append(row['id'])
        repeats = [ids for ids in paragraphs.values() if len(ids) > 1]
        reviews = []
        for row in latest(book, 'review'):
            item = row['data']
            reviews.append({**item, 'current': item['subject_sha256'] == fingerprint})
        passed = {r['role'] for r in reviews if r['current'] and r['result'] == 'pass'
                  and r['reviewer_type'] == 'human'
                  and (r['role'] not in {'editorial', 'reader'} or r['independent'])}
        # A current request for changes takes precedence over another pass for the same role.
        passed -= {r['role'] for r in reviews if r['current'] and r['result'] == 'changes_requested'}
        missing += [role + '_review' for role in ('author', 'editorial', 'reader', 'rights') if role not in passed]
        editions = [{**r['data'], 'id': r['id'], 'current': r['data']['subject_sha256'] == fingerprint}
                    for r in latest(book, 'edition')]
        current_editions = [e for e in editions if e['current'] and e['configuration'].get('format')!='docx']
        if not current_editions:
            missing.append('current_edition_export')
        for edition in current_editions:
            report = edition['report']
            if 'epub' in report and report['epub']['epubcheck']['status'] != 'OK':
                missing.append('epubcheck:' + edition['id'])
            if 'pdf' in report:
                missing.append('printer_template_and_wrap:' + edition['id'])
        if 'visual' not in passed:
            missing.append('visual_review')
        if 'cover' not in passed:
            missing.append('cover_review')
        if findings:
            missing.append('claim_resolution')
        if repeats:
            missing.append('repetition_review')
        missing += ['reader_device_preview', 'current_platform_eligibility', 'owner_submission']
        return {'project_id': self.project_id, 'revision': state['revision'], 'synthetic': book['synthetic'],
                'content_sha256': fingerprint, 'missing': missing, 'claim_findings': findings,
                'repeated_paragraph_chapters': repeats, 'reviews': reviews, 'editions': editions,
                'publication_authorized': False, 'publication_ready': False,
                'next_action': missing[0], 'review_trust': project.LOCAL_APPROVAL,
                'claim_coverage': 'Manual ledger; unlisted factual claims may remain. No automatic truth certificate.',
                'outcomes': [r['data'] for r in latest(book, 'outcome')]}

    def edition(self, revision, payload):
        from beyondwords_production import produce_edition
        value = obj(payload)
        key = project.identifier(value.get('id'), 'id')
        state = self.read()
        if state['revision'] != revision:
            fail('Read the current revision before exporting', 'STALE_REVISION')
        book = self._book(state)
        plan = latest(book, 'plan', 'main')
        if not plan:
            fail('Save the plan first', 'WORKFLOW_ORDER')
        cover = None
        asset = latest(book, 'asset', value['cover_asset_id']) if value.get('cover_asset_id') else None
        if value.get('cover_asset_id') and not asset:
            fail('Cover asset missing from this project', 'MISSING_SOURCE')
        if asset:
            conn = core.connect(self.root)
            try:
                cover = self._blob(conn, asset['data']['file']['sha256'])
            finally:
                conn.close()
        if value.get('layout') == 'coloring':
            import tempfile
            from beyondwords_coloring import execute as coloring_execute
            if plan['data']['route']!='coloring':fail('Coloring imposition needs a coloring book plan')
            with tempfile.TemporaryDirectory() as temp:
                output=Path(temp)/'edition'
                coloring={k:value[k] for k in ('spec','artworks','frontmatter','single_sided','formats','review_sha256')}
                coloring.update({k:plan['data'][k] for k in ('title','author','language')},synthetic=book['synthetic'],task='build',issue_reviews=value.get('issue_reviews',[]))
                validation=coloring_execute(coloring,output)
                media={'.pdf':'application/pdf','.json':'application/json','.png':'image/png','.jpg':'image/jpeg'}
                files=[(p.name,media[p.suffix],p.read_bytes()) for p in output.iterdir() if p.is_file()]
                report={'layout':'coloring','publication_ready':False,'visual':validation,
                        'pdf':{'pages':validation['pages'],'printer_acceptance':'NOT_RUN'}}
        elif value.get('layout') == 'fixed':
            import tempfile
            from beyondwords_visual import build
            with tempfile.TemporaryDirectory() as temp:
                output=Path(temp)/'edition'
                visual={k:value[k] for k in ('spec','pages','formats')}
                visual.update({k:plan['data'][k] for k in ('title','author','language')},synthetic=book['synthetic'])
                validation=build(visual,output)
                media={'.pdf':'application/pdf','.epub':'application/epub+zip','.json':'application/json'}
                files=[(p.name,media[p.suffix],p.read_bytes()) for p in output.iterdir() if p.is_file()]
                report={'layout':'fixed','publication_ready':False,'visual':validation}
                if 'epub' in visual['formats']:report['epub']={'epubcheck':validation['epubcheck']}
                if 'pdf' in visual['formats']:report['pdf']={'pages':validation['pages'],'printer_acceptance':'NOT_RUN'}
        else:
            files, report = produce_edition(self.manuscript(state), plan['data'], value, cover)
        with self._change(revision, 'book_edition') as (conn, current):
            if value.get('layout') == 'coloring':
                layout={'spec':value['spec'],'single_sided':value['single_sided'],
                        'artworks':[{k:v for k,v in page.items() if k!='file'} for page in value['artworks']],
                        'frontmatter':[{k:v for k,v in page.items() if k!='file'} for page in value['frontmatter']]}
                prior=latest(self._book(current),'visual_layout',key)
                if not prior or prior['data']!=layout:self._save(conn,current,'visual_layout',key,layout)
            elif value.get('layout') == 'fixed':
                layout={'spec':value['spec'],'pages':[{k:v for k,v in page.items() if k!='file'} for page in value['pages']]}
                prior=latest(self._book(current),'visual_layout',key)
                if not prior or prior['data']!=layout:
                    self._save(conn,current,'visual_layout',key,layout)
            result = {'subject_sha256': content_hash(self._book(current)), 'configuration': value, 'report': report, 'files': []}
            for name, media, data in files:
                result['files'].append(self._binary(conn, current, key+'/'+name, data, media))
            self._save(conn, current, 'edition', key, result)
        return current

    def launch(self, revision, payload):
        value = obj(payload)
        for field in ('description', 'author_bio', 'reader_offer', 'budget_currency'):
            text(value.get(field), field)
        core.currency_code(value['budget_currency'])
        core.number(value.get('budget'), 'budget')
        strings(value.get('keywords'), 'keywords')
        actions = value.get('actions')
        if not isinstance(actions, list) or not actions:
            fail('Supply concrete launch actions')
        for action in actions:
            obj(action)
            date.fromisoformat(action['date'])
            for field in ('task', 'channel', 'success_measure', 'stop_condition'):
                text(action.get(field), field)
        with self._change(revision, 'book_launch') as (conn, state):
            value['subject_sha256'] = content_hash(self._book(state))
            value['messages_sent'] = False
            value['ads_launched'] = False
            self._save(conn, state, 'launch', 'main', value)
        return state

    def import_report(self, revision, payload, raw):
        from beyondwords_business import parse_report
        value = obj(payload)
        key = project.identifier(value.get('id'), 'id')
        parsed = parse_report(raw, value, now=self.clock())
        with self._change(revision, 'book_report') as (conn, state):
            book = self._book(state)
            if parsed['synthetic'] != book['synthetic']:
                fail('Reports must match the project real/synthetic context')
            replacements = strings(value.get('supersedes', []), 'supersedes')
            active = self._active_reports(book)
            if set(replacements) - {r['id'] for r in active}:
                fail('Only current reports from this project can be reconciled')
            if replacements:
                text(value.get('reconciliation_notes'), 'reconciliation_notes')
            parsed['supersedes'] = replacements
            parsed['reconciliation_notes'] = value.get('reconciliation_notes')
            for row in latest(book, 'report'):
                other = row['data']
                if row['id'] == key or (other['kind'] == parsed['kind'] and other['source_sha256'] == parsed['source_sha256'] and row['id'] not in replacements):
                    fail('Report already imported; no duplicate totals', 'DUPLICATE_REPORT')
            for row in active:
                other = row['data']
                scope = ('kind', 'account_label', 'marketplace', 'title_id', 'currency')
                if row['id'] in replacements:
                    if not all(other[k] == parsed[k] for k in scope) or not (parsed['period_start'] <= other['period_start'] <= other['period_end'] <= parsed['period_end']):
                        fail('Replacement must cover the same report scope and original periods')
                    continue
                if all(other[k] == parsed[k] for k in scope):
                    if parsed['period_start'] <= other['period_end'] and other['period_start'] <= parsed['period_end']:
                        fail('Overlapping report periods need reconciliation before import', 'OVERLAPPING_REPORT')
            parsed['source_artifact'] = self._binary(conn, state, 'reports/'+key+'.csv', raw, 'text/csv')
            self._save(conn, state, 'report', key, parsed)
        return state

    def finance(self):
        from beyondwords_business import summarize_reports
        state = self.read()
        return summarize_reports([r['data'] for r in self._active_reports(self._book(state))])

    @staticmethod
    def _active_reports(book):
        reports = latest(book, 'report')
        replaced = {key for row in reports for key in row['data'].get('supersedes', [])}
        return [row for row in reports if row['id'] not in replaced]

    def prepare(self, revision, payload):
        value = obj(payload)
        key = project.identifier(value.get('id'), 'id')
        if value.get('channel') not in {'kdp_ebook', 'kdp_paperback', 'kdp_hardcover', 'lulu_print', 'lulu_ebook', 'etsy_download', 'direct_download', 'shopify_download'}:
            fail('Unknown publishing channel')
        for field in ('territories', 'rights_declaration', 'isbn_decision', 'exclusivity_decision', 'ai_disclosure'):
            text(value.get(field), field)
        core.currency_code(value.get('currency'))
        core.number(value.get('price'), 'price')
        if not isinstance(value.get('edition_ids'), list) or not value['edition_ids']:
            fail('Select exact edition IDs')
        with self._change(revision, 'book_package') as (conn, state):
            book = self._book(state)
            files = []
            for edition_id in value['edition_ids']:
                edition = latest(book, 'edition', edition_id)
                if not edition or edition['data']['subject_sha256'] != content_hash(book):
                    fail('Selected edition is missing or stale', 'STALE_ARTIFACT')
                if edition['data']['configuration'].get('format')=='docx':
                    fail('The Word editorial handoff is not a publication edition; build the supported channel file first','EDITORIAL_ONLY')
                files += edition['data']['files']
            plan = latest(book, 'plan', 'main')['data']
            value.update(files=files, metadata={k: plan.get(k) for k in ('title', 'subtitle', 'author', 'language')},
                         subject_sha256=content_hash(book), policy_sha256=reviewed_policies(state),
                         checklist=self.status(state), label='DRAFT OWNER REVIEW PACKAGE',
                         submitted=False, publication_authorized=False)
            self._save(conn, state, 'package', key, value)
        return state

    def outcome(self, revision, payload):
        value = obj(payload)
        key = project.identifier(value.get('id'), 'id')
        if value.get('state') not in {'submitted', 'uncertain', 'retailer_approved', 'listing_verified', 'rejected'}:
            fail('Unknown reported publication state')
        for field in ('package_id', 'reported_by', 'receipt_reference', 'notes'):
            text(value.get(field), field)
        with self._change(revision, 'book_outcome') as (conn, state):
            book = self._book(state)
            package = latest(book, 'package', value['package_id'])
            if not package or package['data']['subject_sha256'] != content_hash(book):
                fail('Submission package is missing or stale', 'STALE_ARTIFACT')
            if package['data']['policy_sha256'] != reviewed_policies(state):
                fail('Policy state changed; prepare a new package', 'STALE_POLICY')
            if book['synthetic']:
                fail('Synthetic demos cannot record real publication outcomes')
            previous = latest(book, 'outcome', key)
            if previous and previous['data']['state'] == 'uncertain' and not value.get('reconciliation_reference'):
                fail('Reconcile uncertain outcome before recording another attempt', 'RECONCILIATION_REQUIRED')
            value.update(provenance='user_reported', independently_verified=False,
                         package_sha256=package['sha256'], performed_by_tool=False)
            self._save(conn, state, 'outcome', key, value)
        return state

    def export(self, kind, key, destination):
        """Publish an entire local directory atomically, refusing existing destinations."""
        import os
        import shutil
        import tempfile
        target = core.scoped_path(Path(destination))
        if target.exists() or target.is_symlink():
            fail('Destination exists; use a new export directory', 'ALREADY_EXISTS')
        conn = core.connect(self.root)
        try:
            conn.execute('BEGIN')
            state = self._read(conn)
            book = self._book(state)
            record = latest(book, kind, key)
            if kind not in {'edition', 'package'} or not record:
                fail('Choose an existing edition or package', 'NOT_FOUND')
            data = record['data']
            if data['subject_sha256'] != content_hash(book):
                fail('Export is stale; build a new revision', 'STALE_ARTIFACT')
            if kind == 'package' and data['policy_sha256'] != reviewed_policies(state):
                fail('Policy evidence changed after preparation', 'STALE_POLICY')
            files = [(f['source_name'] if kind == 'package' else Path(f['source_name']).name,
                      self._blob(conn, f['sha256'])) for f in data['files']]
            if len({n for n, _ in files}) != len(files):
                fail('Selected editions have colliding file names; export separately')
            files += [('manifest.json', project.canonical(record)), ('review-status.json', project.canonical(self.status(state)))]
            if kind == 'package':
                files.append(('START-HERE.md', (
                    '# Draft owner review package\n\nNo upload or publication has occurred.\n\n'
                    '1. Read review-status.json and resolve the missing checks.\n'
                    '2. Recheck the official channel requirements, rights, disclosure, price and eligibility.\n'
                    '3. Preview the exact EPUB/interior and cover in the retailer tools.\n'
                    '4. The account owner supplies identity, tax and bank details directly.\n'
                    '5. Approve the exact files and settings before submitting.\n'
                    '6. Record the actual receipt; reconcile an uncertain result before retrying.\n'
                    '7. Verify the live listing separately after retailer approval.\n').encode()))
            target.parent.mkdir(parents=True, exist_ok=True)
            stage = Path(tempfile.mkdtemp(prefix='.beyondwords-export-', dir=target.parent))
            try:
                for name, content in files:
                    if Path(name).is_absolute() or '..' in Path(name).parts:
                        fail('Unsafe artifact export name')
                    (stage/name).parent.mkdir(parents=True, exist_ok=True)
                    with (stage/name).open('xb') as stream:
                        stream.write(content); stream.flush(); os.fsync(stream.fileno())
                # Reserve destination exclusively; copying files is not exposed under the final name.
                # rename refuses nonempty destinations; an explicit guard also rejects empty ones.
                if target.exists() or target.is_symlink():
                    fail('Destination appeared during export', 'ALREADY_EXISTS')
                stage.rename(target)
            finally:
                if stage.exists():
                    shutil.rmtree(stage)
            return {'directory': str(target), 'files': [n for n, _ in files], 'publication_ready': False}
        finally:
            conn.close()

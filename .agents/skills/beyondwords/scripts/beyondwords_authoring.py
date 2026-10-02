"""Owned manuscript import and source-bound story memory. No bundled inference."""
import copy
import re
from pathlib import Path

import publishing_core as core
import publishing_project as project
from beyondwords_book import BookStore, latest, PROVENANCE


def parse_manuscript(raw):
    """Index H1 sections without treating fenced examples as chapter headings."""
    text=raw.decode('utf-8-sig').replace('\r\n','\n').replace('\r','\n')
    if '\x00' in text: raise ValueError('Manuscript must be UTF-8 text')
    lines=text.splitlines(keepends=True); frontmatter=''
    if lines and lines[0].strip()=='---':
        end=next((i for i in range(1,len(lines)) if lines[i].strip()=='---'),None)
        if end is None: raise ValueError('Unclosed manuscript frontmatter')
        frontmatter=''.join(lines[1:end]); lines=lines[end+1:]
    sections=[]; body=[]; title=None; fence=None
    for line in lines:
        match=re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$',line.rstrip('\n'))
        if match:
            token,tail=match.groups()
            if fence is None: fence=token
            elif token[0]==fence[0] and len(token)>=len(fence) and not tail.strip(): fence=None
            body.append(line); continue
        heading=re.match(r'^ {0,3}#\s+(.+?)\s*#*\s*$',line) if fence is None else None
        if heading:
            if title is not None or ''.join(body).strip():
                sections.append({'title':title,'body':''.join(body).strip()})
            title=heading[1];body=[]
        else:body.append(line)
    if fence: raise ValueError('Close the manuscript code fence before import')
    if title is not None or ''.join(body).strip(): sections.append({'title':title,'body':''.join(body).strip()})
    if not sections or len(sections)>300: raise ValueError('Use 1–300 nonempty manuscript sections')
    warnings=[]
    if re.search(r'(?m)^\s*(?:```|~~~|\|)|!\[|<\s*(?:table|img|script)\b',text):
        warnings.append('Tables, code, images or HTML need a dedicated export layout; text is retained unchanged.')
    return sections,frontmatter,warnings


def manuscript_import(workspace,project_id,revision,payload):
    store=BookStore(Path(workspace),project_id); state=store.read();book=store._book(state)
    source=core.scoped_path(Path(payload['file']));raw=project.load_input(source)
    sections,frontmatter,warnings=parse_manuscript(raw);sha=project.digest(raw)
    if payload['task']=='inspect':
        return dict(sha256=sha,source_name=source.name,frontmatter=frontmatter,
                    sections=[{'title':s['title'],'characters':len(s['body'])} for s in sections],
                    layout_warnings=warnings,mutations_performed=False,publication_ready=False)
    if payload['task']!='import':raise ValueError('Choose inspect or import')
    if type(payload.get('synthetic')) is not bool or payload['synthetic']!=book['synthetic']:
        raise ValueError('Manuscript and project synthetic modes must match')
    if sha!=payload['sha256']:raise ValueError('Manuscript changed since inspection')
    core.text(payload.get('rights_basis'),'rights_basis')
    if payload.get('provenance') not in PROVENANCE:raise ValueError('Declare manuscript provenance')
    with store._change(revision,'book_chapter') as (conn,state):
        book=store._book(state);plan=latest(book,'plan','main')
        if not plan or plan['sha256']!=payload['plan_sha256']:raise ValueError('Use the current accepted chapter plan')
        if frontmatter and payload.get('metadata_reviewed') is not True:
            raise ValueError('Review manuscript frontmatter against the saved plan; it cannot silently override metadata')
        if payload.get('title_heading') is True:
            if sections[0]['title']!=plan['data']['title'] or sections[0]['body']:
                raise ValueError('Only an explicitly identified empty book-title heading may be omitted')
            sections=sections[1:]
        ids=payload['chapter_ids'];contracts={c['id']:c for c in plan['data']['chapters']}
        if not isinstance(ids,list) or len(ids)!=len(sections) or len(set(ids))!=len(ids) or set(ids)-set(contracts):
            raise ValueError('Map every manuscript section to one unique existing chapter contract')
        replacements=payload.get('replace_sha256',{})
        existing={cid:latest(book,'chapter',cid) for cid in ids}
        expected={cid:r['sha256'] for cid,r in existing.items() if r}
        if replacements!=expected:raise ValueError('Replacing chapter drafts requires their exact prior hashes; earlier versions will be retained')
        for cid,section in zip(ids,sections):
            if section['title'] is None and (len(sections)!=1 or len(ids)!=1):
                raise ValueError('Preserve the preamble as an explicitly titled chapter before import')
            if section['title'] is not None and section['title']!=contracts[cid]['title']:
                raise ValueError('Chapter title differs from the accepted mapping: '+cid)
            core.text(section['body'],'chapter body',project.MAX_BYTES//2)
            value=dict(id=cid,body=section['body'],provenance=payload['provenance'],rights_basis=payload['rights_basis'],
                       change_summary='Imported owned manuscript section',plan_sha256=plan['sha256'],
                       import_sha256=sha,continuity={})
            store._save(conn,state,'chapter',cid,value)
        source_ref=store._binary(conn,state,'manuscript-'+sha+'.txt',raw,'text/plain')
        store._save(conn,state,'manuscript_import','source-'+sha[:24],dict(source=source_ref,chapter_ids=ids,
                    frontmatter=frontmatter,metadata_source='accepted plan',layout_warnings=warnings))
    return dict(revision=state['revision'],imported_chapter_ids=ids,sha256=sha,layout_warnings=warnings,
                prior_versions_preserved=True,publication_ready=False,synthetic=book['synthetic'])


def dependencies(book,plan,cid):
    ids=[c['id'] for c in plan['data']['chapters']]; index=ids.index(cid)
    # Include absent predecessors: filling a formerly empty chapter changes context too.
    return {key:(latest(book,'chapter',key) or {}).get('sha256') for key in ids[:index+1]}


def memory_view(book,before_chapter=None):
    plan=latest(book,'plan','main')
    if not plan:raise ValueError('Save the chapter plan first')
    ids=[c['id'] for c in plan['data']['chapters']]
    if before_chapter is not None:
        if before_chapter not in ids:raise ValueError('Unknown target chapter')
        ids=ids[:ids.index(before_chapter)]
    summaries=[];threads={};stale=[];missing=[]
    for cid in ids:
        row=latest(book,'story_memory',cid)
        if not row:
            missing.append(cid);continue
        value=row['data']
        if value['plan_sha256']!=plan['sha256'] or value['dependencies']!=dependencies(book,plan,cid):
            stale.append(cid);continue
        summaries.append(dict(chapter_id=cid,summary=value['summary'],chapter_sha256=value['chapter_sha256'],
                              memory_sha256=row['sha256'],reviewed_by=value['reviewed_by']))
        for thread in value['threads']:
            threads[thread['id']]={**thread,'last_chapter_id':cid,'memory_sha256':row['sha256']}
    return dict(summaries=summaries,open_threads=[v for v in threads.values() if v['status']=='open'],
                thread_history=list(threads.values()),stale_chapter_ids=stale,missing_chapter_ids=missing,
                evidence_type='Author/host summaries, bound to exact manuscript versions; not automatic semantic verification',
                synthetic=book['synthetic'])


def story_memory(workspace,project_id,revision,payload):
    store=BookStore(Path(workspace),project_id);state=store.read();book=store._book(state)
    if payload['task']=='read':return memory_view(book,payload.get('before_chapter'))
    if payload['task']!='save':raise ValueError('Choose save or read')
    cid=project.identifier(payload['chapter_id'],'chapter_id')
    value={k:copy.deepcopy(payload[k]) for k in ('summary','threads','reviewed_by','chapter_sha256','plan_sha256')}
    core.text(value['summary'],'summary',4000);core.text(value['reviewed_by'],'reviewed_by')
    if not isinstance(value['threads'],list) or len(value['threads'])>100:raise ValueError('Use at most 100 thread updates per chapter')
    seen=set()
    for thread in value['threads']:
        if set(thread)!={'id','status','description'}:raise ValueError('Thread requires id, status and description')
        key=project.identifier(thread['id'],'thread.id');core.text(thread['description'],'description',2000)
        if key in seen or thread['status'] not in {'open','resolved','superseded'}:raise ValueError('Unique thread IDs and open/resolved/superseded status required')
        seen.add(key)
    with store._change(revision,'book_lifecycle') as (conn,state):
        book=store._book(state);plan=latest(book,'plan','main');chapter=latest(book,'chapter',cid)
        if type(payload.get('synthetic')) is not bool or payload['synthetic']!=book['synthetic']:raise ValueError('Memory and project modes must match')
        if not plan or plan['sha256']!=value['plan_sha256'] or not chapter or chapter['sha256']!=value['chapter_sha256']:
            raise ValueError('Memory must describe the current plan and exact chapter bytes')
        if chapter['data']['plan_sha256']!=plan['sha256']:raise ValueError('Recheck this chapter against the changed plan first')
        value['dependencies']=dependencies(book,plan,cid)
        store._save(conn,state,'story_memory',cid,value)
    return dict(revision=state['revision'],chapter_id=cid,publication_ready=False,synthetic=book['synthetic'])

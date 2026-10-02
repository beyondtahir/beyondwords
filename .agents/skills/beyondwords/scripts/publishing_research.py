"""BP-002: project-scoped evidence, declared permissions and reviewed policy versions."""
from __future__ import annotations
import argparse
import difflib
import html
import json
from pathlib import Path
import re
import sys
from urllib.parse import urljoin,urlsplit
from uuid import uuid4
import publishing_core as core
import publishing_project as project
from publishing_browser import AccessError, check_url, capture
from publishing_extract import extract_book, blocked, visible_text, Document

Error=project.ProjectError


def fail(message,code='INVALID_INPUT'): raise Error(code,message)


def timestamp(value):
    try: return core.timestamp(value,'timestamp')
    except core.CoreError as exc: raise Error('INVALID_INPUT',str(exc)) from exc


def safe(value):
    """Untrusted source text cannot inject HTML/Markdown links into generated reports."""
    return html.escape(str(value)).replace('[','\\[').replace(']','\\]').replace('\n',' ')


class ResearchStore(project.Store):
    def _research(self,state):
        value=state.get('research')
        if not value or value.get('schema_version')!=1: fail('Enable the BP-002 workflow first','MIGRATION_REQUIRED')
        return value

    def enable(self,revision,context,*,synthetic=False):
        if type(synthetic) is not bool or not isinstance(context,dict): fail('Invalid research context')
        for key in ('reader','buyer','author_experience','budget'): core.text(context.get(key),key)
        with self._change(revision,'enable_research_v1') as (_,state):
            if state.get('research') or (not state.get('book') and (state['artifacts'] or state['decisions'] or state['evidence_ids'] or state['observation_ids'])):
                fail('Use a fresh project for research; existing fixture history stays intact','WORKFLOW_ORDER')
            if state.get('book') and state['book']['synthetic'] != synthetic:
                fail('Research and book must share the same synthetic/real context')
            if not state.get('book'):
                state['mode']='synthetic_research' if synthetic else 'research'
            state['research']={'schema_version':1,'synthetic':synthetic,'context':context.copy(),'access':[],'captures':[],'policies':[],'policy_reviews':[],'discovery':[]}
            state['warnings']=([core.SYNTHETIC_WARNING] if synthetic else [])+[project.LOCAL_APPROVAL,'Research does not establish demand, rights clearance, editorial quality or publication readiness.']
        return state

    def add_access(self,revision,record):
        if not isinstance(record,dict): fail('Permission record must be an object')
        record=dict(record)
        project.identifier(record.get('access_id'),'access_id')
        for key in ('basis','permission_reference','reviewed_by','url_prefix'): core.text(record.get(key),key)
        if record['basis'] not in {'fixture','user_authorized_import','source_license','official_guidance','source_authorization'}: fail('Unknown access basis')
        for key in ('collect','import','retain','derive','redistribute','synthetic'):
            if type(record.get(key)) is not bool: fail(key+' requires an explicit boolean')
        if record.get('retention') not in {'full','excerpt'}: fail('retention must be full or excerpt')
        now=timestamp(self.clock())
        if not timestamp(record.get('reviewed_at'))<=now<timestamp(record.get('expires_at')): fail('Access review is future dated or expired','PERMISSION_REQUIRED')
        try: check_url(record['url_prefix'],record['url_prefix'],resolve=False)
        except AccessError as exc: fail(str(exc),'PERMISSION_REQUIRED')
        if record['collect'] and record['basis'] in {'fixture','user_authorized_import'}: fail('This basis does not authorize browser collection','PERMISSION_REQUIRED')
        with self._change(revision,'record_source_access') as (_,state):
            research=self._research(state)
            if record['synthetic']!=research['synthetic'] or (record['basis']=='fixture')!=research['synthetic']: fail('Synthetic and real evidence cannot be mixed')
            if any(r['access_id']==record['access_id'] for r in research['access']): fail('Access IDs are immutable; use a new ID for a renewed review')
            record['declaration_only']=True
            research['access'].append(record)
        return state

    def _permission(self,state,access_id,url,operation):
        research=self._research(state)
        grants=[r for r in research['access'] if r['access_id']==access_id]
        if not grants: fail('Record source access and reuse permission before collection/import','PERMISSION_REQUIRED')
        record=grants[-1]
        if not (record.get(operation) and record['retain'] and record['derive']): fail('Collection/import, retention and derived-use permissions are required','PERMISSION_REQUIRED')
        if not timestamp(record['reviewed_at'])<=timestamp(self.clock())<timestamp(record['expires_at']): fail('Source permission review expired','PERMISSION_REQUIRED')
        try: check_url(url,record['url_prefix'],resolve=False)
        except AccessError as exc: fail(str(exc),'PERMISSION_REQUIRED')
        return record

    def _body(self,body,observed_at):
        if not isinstance(body,bytes) or not body or len(body)>project.MAX_BYTES: fail('Evidence must be nonempty and at most 5 MiB')
        try: text=body.decode('utf-8')
        except UnicodeDecodeError: fail('Supply UTF-8 evidence')
        if timestamp(observed_at)>timestamp(self.clock()): fail('Capture time cannot be in the future')
        return text

    def _source_artifact(self,conn,state,record,body,kind):
        # Excerpts are supplied as excerpts; never silently truncate a full document and call it complete.
        return self._artifact(conn,state,'source-'+uuid4().hex,kind,body,record['basis'],'supplied-evidence',synthetic=record['synthetic'])

    def import_html(self,revision,access_id,url,body,observed_at,expected=None,*,transport=None):
        expected=expected or {}
        if not isinstance(expected,dict) or any(not isinstance(v,str) for v in expected.values()): fail('Selected edition must contain strings')
        text=self._body(body,observed_at)
        with self._change(revision,'capture_book_evidence') as (conn,state):
            record=self._permission(state,access_id,url,'collect' if transport else 'import')
            item=extract_book(text,url,expected)
            status='BLOCKED' if blocked(text) or (transport and transport.get('status')=='BLOCKED') else ('OK' if item['edition_verified'] else 'PARTIAL')
            if transport and transport.get('status') not in {'OK','BLOCKED'}: status=transport.get('status','ERROR')
            artifact=self._source_artifact(conn,state,record,body,'research_source')
            item.update(capture_id='capture-'+uuid4().hex,source_url=url,observed_at=observed_at,recorded_at=self.clock(),source_sha256=artifact['sha256'],artifact_id=artifact['artifact_id'],access_id=access_id,synthetic=record['synthetic'],status=status,selected_edition=expected,provenance='browser_capture' if transport else 'authorized_import',retention=record['retention'],transport=transport or None)
            self._research(state)['captures'].append(item)
        return state

    def capture_book(self,revision,access_id,url,expected):
        state=self.read()
        if state['revision']!=revision: fail('Read the latest project revision','STALE_REVISION')
        permission=self._permission(state,access_id,url,'collect')
        if permission['synthetic']: fail('Live collection cannot enter a synthetic project')
        if permission['retention']!='full': fail('Live HTML capture requires full retention permission; import an authorized excerpt instead','PERMISSION_REQUIRED')
        result=capture(url,permission['url_prefix'])
        raw=result.pop('body',b'')
        if raw:
            return self.import_html(revision,access_id,result.get('final_url',url),raw,self.clock(),expected,transport=result)
        with self._change(revision,'record_capture_failure') as (_,state):
            self._permission(state,access_id,url,'collect')
            self._research(state)['captures'].append({'capture_id':'capture-'+uuid4().hex,'source_url':url,'observed_at':self.clock(),'recorded_at':self.clock(),'synthetic':False,'access_id':access_id,'status':result['status'],'transport':result,'edition_verified':False,'issues':['capture_failed'],'selected_edition':expected})
        return state

    def discover(self,revision,access_id,url):
        """Collect a permitted discovery page; links are candidates, not endorsed niches."""
        state=self.read()
        if state['revision']!=revision: fail('Read the latest project revision','STALE_REVISION')
        permission=self._permission(state,access_id,url,'collect')
        if permission['synthetic'] or permission['retention']!='full': fail('Live discovery needs real access and full retention permission')
        result=capture(url,permission['url_prefix']); body=result.pop('body',b'')
        links=[]
        if result['status']=='OK' and body:
            doc=Document(body.decode('utf-8',errors='replace'))
            for node in doc.nodes:
                href=node['attrs'].get('href')
                if node['tag']!='a' or not href or node['hidden']: continue
                candidate=urljoin(result.get('final_url',url),href).split('#')[0]
                try: check_url(candidate,candidate,resolve=False)
                except AccessError: continue
                if re.search(r'/(?:dp|gp/product)/[A-Z0-9]{10}(?:[/?]|$)',candidate):
                    links.append({'url':candidate,'label':doc.text(node)[:300],'collection_permission':'NOT_REVIEWED'})
        with self._change(revision,'record_discovery') as (conn,state):
            self._permission(state,access_id,url,'collect')
            artifact=self._source_artifact(conn,state,permission,body,'discovery_source') if body else None
            self._research(state)['discovery'].append({'source_url':url,'observed_at':self.clock(),'synthetic':False,'status':result['status'],'transport':result,'source_sha256':artifact['sha256'] if artifact else None,'candidates':list({x['url']:x for x in links}.values())})
        return state

    def import_policy(self,revision,access_id,policy_id,url,body,observed_at,*,transport=None):
        project.identifier(policy_id,'policy_id'); text=self._body(body,observed_at)
        host=urlsplit(url).hostname
        if host not in {'kdp.amazon.com','help.lulu.com','www.lulu.com'}: fail('Policy tracking currently supports official KDP and Lulu sources only')
        with self._change(revision,'record_policy_version') as (conn,state):
            permission=self._permission(state,access_id,url,'collect' if transport else 'import')
            artifact=self._source_artifact(conn,state,permission,body,'policy_source')
            policy={'policy_id':policy_id,'source_url':url,'sha256':artifact['sha256'],'artifact_id':artifact['artifact_id'],'observed_at':observed_at,'recorded_at':self.clock(),'access_id':access_id,'synthetic':permission['synthetic'],'retention':permission['retention'],'status':'BLOCKED' if blocked(text) or (transport and transport['status']!='OK') else 'PENDING_REVIEW','transport':transport or None}
            versions=self._research(state)['policies']
            old=[p for p in versions if p['policy_id']==policy_id]
            if old and old[-1]['source_url']!=url: fail('Policy identity is bound to its source URL')
            policy['version']=len(old)+1; versions.append(policy)
        return state

    def capture_policy(self,revision,access_id,policy_id,url):
        state=self.read()
        if state['revision']!=revision: fail('Read the latest project revision','STALE_REVISION')
        permission=self._permission(state,access_id,url,'collect')
        if permission['synthetic'] or permission['retention']!='full': fail('Live policy capture needs real access and full retention permission')
        result=capture(url,permission['url_prefix']); body=result.pop('body',b'')
        if not body:
            # Persist actual failures as attempts, not invented policy content.
            with self._change(revision,'record_policy_capture_failure') as (_,state):
                self._permission(state,access_id,url,'collect')
                self._research(state).setdefault('policy_attempts',[]).append({'policy_id':policy_id,'source_url':url,'observed_at':self.clock(),**result})
            return state
        return self.import_policy(revision,access_id,policy_id,result.get('final_url',url),body,self.clock(),transport=result)

    def review_policy(self,revision,policy_id,sha,reviewer,notes):
        core.text(reviewer,'reviewer'); core.text(notes,'notes')
        with self._change(revision,'review_policy_version') as (_,state):
            data=self._research(state); versions=[p for p in data['policies'] if p['policy_id']==policy_id]
            if not versions or versions[-1]['sha256']!=sha or versions[-1]['status']=='BLOCKED': fail('Review must refer to the current, accessible policy version','STALE_APPROVAL')
            item=versions[-1]
            if timestamp(self.clock())-timestamp(item['observed_at'])>__import__('datetime').timedelta(days=30): fail('Refresh stale policy evidence before review','STALE_APPROVAL')
            data['policy_reviews'].append({'policy_id':policy_id,'sha256':sha,'version':item['version'],'reviewer':reviewer,'notes':notes,'reviewed_at':self.clock(),'scope':'local_review_only','trusted_external_authorization':False})
        return state

    def policy_status(self,policy_id):
        conn=core.connect(self.root)
        try:
            conn.execute('BEGIN'); data=self._research(self._read(conn))
            versions=[p for p in data['policies'] if p['policy_id']==policy_id]
            if not versions: fail('Policy has not been captured','NOT_FOUND')
            current=versions[-1]
            texts=[self._blob(conn,p['sha256']).decode() for p in versions[-2:]]
            delta='' if len(texts)<2 else '\n'.join(difflib.unified_diff(texts[0].splitlines(),texts[1].splitlines(),fromfile='previous',tofile='current',lineterm=''))
            reviewed=any(r['policy_id']==policy_id and r['sha256']==current['sha256'] and r['version']==current['version'] for r in data['policy_reviews'])
            fresh=(timestamp(self.clock())-timestamp(current['observed_at'])).total_seconds()<=30*86400
            return {**current,'review_current':reviewed and fresh and current['status']!='BLOCKED','diff':delta,'publishing_checks_changed':False,'freshness_window_days':30,'scope':'Source-version review only; does not create executable policy rules or guarantee account safety.'}
        finally: conn.close()

    def brief(self,max_age_hours=48):
        hours=float(core.positive_hours(str(max_age_hours))); state=self.read(); data=self._research(state); now=timestamp(self.clock())
        marker='SYNTHETIC DEMONSTRATION — NOT A REAL NICHE RECOMMENDATION' if data['synthetic'] else 'RESEARCH BRIEF — OBSERVATIONS REQUIRE HUMAN INTERPRETATION'
        lines=['# '+marker,'',f"Project: {safe(state['title'])}",'','## Reader, buyer and resources']
        lines.extend(f'- {key.replace("_"," ").title()}: {safe(value)}' for key,value in data['context'].items())
        lines += ['','## Observed facts','No sales, royalties or success probabilities are inferred from ranks.']
        eligible={}; missing=[]
        for item in data['captures']:
            stale=(now-timestamp(item['observed_at'])).total_seconds()>hours*3600
            usable=item['status']=='OK' and item['edition_verified'] and not stale
            if usable: eligible[(item.get('asin'),item.get('marketplace'),item.get('format'))]=item
            label='stale' if stale else item['status']
            if not usable: missing.append(f"{item['source_url']}: {label}; {', '.join(item.get('issues',[])) or 'edition unverified'}")
            lines.append(f"- [Source]({item['source_url']}) · {safe(item['observed_at'])} · {label} · SHA-256 {item.get('source_sha256','UNKNOWN')}")
            lines.append('  '+ '; '.join(f'{key}: {safe(item.get(key)) if item.get(key) is not None else "UNKNOWN"}' for key in ('title','asin','marketplace','format','price','currency','overall_rank','overall_rank_store','ranking_list')))
            if item.get('category_ranks'): lines.append('  Category ranks (separate): '+safe(json.dumps(item['category_ranks'])))
            for key in ('asin','format','price','currency','overall_rank','ranking_list'):
                if item.get(key) is None: missing.append(f"{item['source_url']}: {key} UNKNOWN")
        lines+=['','## Interpretation',f'{len(eligible)} unique, fresh, edition-verified observations are available. This count measures evidence coverage, not demand.','A snapshot cannot establish market size, sales, profitability, reader satisfaction or a durable niche opportunity.','', '## Missing evidence']
        lines.extend('- '+safe(x) for x in dict.fromkeys(missing or ['Reader interviews, rights-cleared content comparisons, costs and independent evaluation are still needed.']))
        lines+=['','## Next actions',f"- Test a specific problem with {safe(data['context']['reader'])}; record what readers and {safe(data['context']['buyer'])} actually say.",f"- Ask the author to substantiate {safe(data['context']['author_experience'])} with genuine experience or qualified sources.",f"- Set a research and production spending limit within {safe(data['context']['budget'])}; costs and earnings remain unverified.",'- Refresh stale records and verify UNKNOWN edition, rank-list and price fields before comparing books.','- Read only authorized samples; record gaps as hypotheses and validate them with readers.','- Obtain independent editorial and real-reader evaluations before any release.','', 'Publication readiness: NOT EVALUATED. No publication or ad account actions were performed.']
        return {'project_id':self.project_id,'revision':state['revision'],'synthetic':data['synthetic'],'real_recommendation':False,'comparable_count':len(eligible),'publication_ready':False,'markdown':'\n'.join(lines)+'\n'}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['enable','access','import','capture','discover','brief','policy-import','policy-capture','policy-review','policy-status','status'])
    parser.add_argument('--workspace',required=True); parser.add_argument('--project-id',required=True)
    parser.add_argument('--expected-revision',type=int); parser.add_argument('--input'); parser.add_argument('--access-id'); parser.add_argument('--url'); parser.add_argument('--observed-at'); parser.add_argument('--asin'); parser.add_argument('--format'); parser.add_argument('--policy-id'); parser.add_argument('--sha256'); parser.add_argument('--reviewer'); parser.add_argument('--notes'); parser.add_argument('--synthetic',action='store_true'); parser.add_argument('--max-age-hours',default='48')
    args=parser.parse_args(argv)
    from publishing_result import ToolResult,Cost
    import time
    started=time.monotonic()
    try:
        store=ResearchStore(Path(args.workspace),args.project_id)
        rev=args.expected_revision
        if args.command not in {'brief','policy-status','status'}: project.require_revision(rev)
        if args.command in {'enable','access','import','policy-import'}:
            if not args.input: fail('--input is required')
            body=project.load_input(Path(args.input))
        expected={k:v for k,v in {'asin':args.asin,'format':args.format}.items() if v}
        if args.command=='enable': result=store.enable(rev,json.loads(body),synthetic=args.synthetic)
        elif args.command=='access': result=store.add_access(rev,json.loads(body))
        elif args.command=='import': result=store.import_html(rev,args.access_id,args.url,body,args.observed_at,expected)
        elif args.command=='capture': result=store.capture_book(rev,args.access_id,args.url,expected)
        elif args.command=='discover': result=store.discover(rev,args.access_id,args.url)
        elif args.command=='brief': result=store.brief(args.max_age_hours)
        elif args.command=='policy-import': result=store.import_policy(rev,args.access_id,args.policy_id,args.url,body,args.observed_at)
        elif args.command=='policy-capture':
            attempts_before=len(store.read()['research'].get('policy_attempts',[]))
            result=store.capture_policy(rev,args.access_id,args.policy_id,args.url)
        elif args.command=='policy-review': result=store.review_policy(rev,args.policy_id,args.sha256,args.reviewer,args.notes)
        elif args.command=='policy-status': result=store.policy_status(args.policy_id)
        else: result=store.read()
        status='OK'
        if args.command in {'capture','import'}: status=result['research']['captures'][-1]['status']
        elif args.command=='discover': status=result['research']['discovery'][-1]['status']
        elif args.command=='policy-import': status='NEEDS_REVIEW'
        elif args.command=='policy-capture':
            attempts=result['research'].get('policy_attempts',[])
            status=attempts[-1]['status'] if len(attempts)>attempts_before else ('BLOCKED' if result['research']['policies'][-1]['status']=='BLOCKED' else 'NEEDS_REVIEW')
        warnings=result.get('warnings',[])
        if (result.get('synthetic') or result.get('research',{}).get('synthetic')) and core.SYNTHETIC_WARNING not in warnings:
            warnings=warnings+[core.SYNTHETIC_WARNING]
        evidence_ids=[result['research']['captures'][-1]['capture_id']] if args.command in {'capture','import'} else []
        envelope=ToolResult(status,data=result,warnings=warnings,evidence_ids=evidence_ids,operation_id=uuid4().hex,timing={'elapsed_ms':round((time.monotonic()-started)*1000,3)},cost=Cost()).to_dict()
        print(json.dumps(envelope,ensure_ascii=False,indent=2)); return 0
    except (core.CoreError,AccessError,ValueError,OSError,__import__('sqlite3').Error) as exc:
        envelope=ToolResult('BLOCKED' if getattr(exc,'code',None)=='PERMISSION_REQUIRED' else 'ERROR', data={}, operation_id=uuid4().hex,
                            timing={'elapsed_ms':round((time.monotonic()-started)*1000,3)}, missing_fields=getattr(exc,'missing_fields',[]),
                            error={'code':getattr(exc,'code','INVALID_INPUT'),'message':str(exc)},cost=Cost())
        print(json.dumps(envelope.to_dict())); return 1


if __name__=='__main__': raise SystemExit(main())

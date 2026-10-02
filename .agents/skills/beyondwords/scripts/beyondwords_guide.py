"""Conversational intake and decisions, independent of host and installed skill path.

Local declarations are not authenticated human approvals or external receipts.
The host conducts the conversation; this module enforces its saved prerequisites.
"""
from __future__ import annotations
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from uuid import uuid4
import publishing_core as core

SCHEMA = 1
PERSON = {'country', 'conversation_language', 'experience'}
BOOK = {'book_language', 'interests', 'existing_material', 'reader', 'formats', 'account_status',
        'time', 'budget', 'goal', 'print_preferences', 'book_type', 'target_marketplace',
        'publishing_channels', 'marketing_budget', 'business_model', 'content_creation_preference', 'operating_mode'}
REQUIRED = ['country','conversation_language','book_language','experience','existing_material',
            'interests','reader','formats','time','budget','goal','account_status','book_type',
            'target_marketplace','publishing_channels','marketing_budget','business_model',
            'content_creation_preference','operating_mode']
FORMATS = {'ebook','print','both','undecided','paperback','hardcover','pdf','epub','printable'}
CHANNELS = {'kdp','lulu','etsy','direct','shopify','other','undecided'}
QUESTIONS = {
 'country':'Which country do you live in?',
 'conversation_language':'Which language should we talk in?',
 'book_language':'Which language will the book use?',
 'experience':'What experience or knowledge can you bring to the book?',
 'existing_material':'Are you starting fresh, or do you have writing, art or research already?',
 'interests':'What do you enjoy reading, making or teaching, and why?',
 'reader':'Who would enjoy or benefit from it? Undecided is fine.',
 'formats':'Which formats: Kindle ebook, paperback, hardcover, PDF/printable, or undecided? You can choose several.',
 'book_type':'Novel, nonfiction, children’s book, coloring/activity book, art book, or another type? Undecided is fine.',
 'target_marketplace':'Which country or marketplace should we research first? Undecided is fine.',
 'publishing_channels':'Amazon KDP, Lulu, Etsy, direct sales, Shopify, several, or undecided?',
 'marketing_budget':'How much of your budget is available for marketing, in which currency and over what period? Zero or undecided is fine.',
 'business_model':'A single title, series, a catalog, printables or another business model? We can research this before you choose.',
 'content_creation_preference':'Do you want to write/create yourself, collaborate with AI, or delegate drafting for your review?',
 'operating_mode':'Would you like guided mode to learn and decide together, or execution mode where I do the available work within your decisions?',
 'time':'How much time can you give per day or week?',
 'budget':'What can you invest, in which currency, and is that total, monthly or per book?',
 'goal':'What would success mean to you: a creative goal or an income goal?',
 'goal.metric':'Does your income target mean sales revenue, royalties, or profit after costs?',
 'goal.period':'Is the target monthly or a total amount?',
 'goal.deadline':'Do you have a target date, or should we first test what is feasible?',
 'account_status':'Do you already have a publishing account? Please do not share passwords.',
 'print_preferences':'For print, any preferred size, colour or black-and-white, and edge-to-edge art? Undecided is fine.',
}


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def memory_home():
    override=os.environ.get('BEYONDWORDS_MEMORY_DIR')
    if override: return Path(override).expanduser()
    base=Path(os.environ.get('LOCALAPPDATA', Path.home()/'AppData/Local')) if os.name=='nt' else Path.home()/'.local/share'
    return base/'beyondwords/memory'


def choice(value, allowed, field):
    if value not in allowed: raise ValueError(f'{field} must be one of {sorted(allowed)}')
    return value


def answers_checked(answers):
    if not isinstance(answers,dict) or set(answers)-(PERSON|BOOK):
        raise ValueError('Unknown intake fields; never store credentials or identity documents')
    result={}
    for key,value in answers.items():
        if key in {'time','budget','marketing_budget','goal','print_preferences'}:
            if not isinstance(value,dict): raise ValueError(f'{key} must be an object')
            fields={'time':{'hours','period'},'budget':{'amount','currency','scope'},'marketing_budget':{'amount','currency','scope'},
                    'goal':{'kind','amount','currency','period','metric','deadline'},
                    'print_preferences':{'trim','color','bleed'}}[key]
            if set(value)-fields: raise ValueError(f'Unknown {key} fields')
            v=dict(value)
            if key=='time':
                choice(v.get('period'),{'day','week','undecided'},'time.period')
                if v.get('hours') is not None:
                    v['hours']=str(core.number(v['hours'],'hours'))
                    limit=24 if v['period']=='day' else 168
                    if core.number(v['hours'],'hours')>limit: raise ValueError('Time exceeds available hours')
            elif key in {'budget','marketing_budget'}:
                choice(v.get('scope'),{'total','monthly','per_book','undecided'},'budget.scope')
                v['amount']=str(core.number(v['amount'],'amount')) if v.get('amount') is not None else None
                v['currency']=core.currency_code(v['currency']) if v.get('currency') else None
            elif key=='goal':
                choice(v.get('kind'),{'income','creative','none'},'goal.kind')
                if v['kind']=='income':
                    v['amount']=str(core.number(v.get('amount'),'goal.amount'))
                    v['currency']=core.currency_code(v.get('currency'))
                    choice(v.get('metric'),{'revenue','royalties','pre_tax_profit','undecided'},'goal.metric')
                    choice(v.get('period'),{'monthly','cumulative','undecided'},'goal.period')
                v['deadline']=core.text(v.get('deadline','undecided'),'deadline',500)
            else:
                for f in fields: v[f]=core.text(v.get(f),f,500)
            result[key]=v
        elif key=='formats':
            if isinstance(value,list):
                if not value or len(value)>8 or len(set(value))!=len(value):raise ValueError('Choose distinct formats')
                result[key]=[choice(v,FORMATS,key) for v in value]
            else:result[key]=choice(value,FORMATS,key)
        elif key=='publishing_channels':
            if not isinstance(value,list) or not value or len(value)>len(CHANNELS) or len(set(value))!=len(value):raise ValueError('Choose distinct publishing channels')
            result[key]=[choice(v,CHANNELS,key) for v in value]
        elif key=='operating_mode': result[key]=choice(value,{'guided','execution'},key)
        elif key=='content_creation_preference': result[key]=choice(value,{'self','ai_assisted','delegated','undecided'},key)
        else: result[key]=core.text(value,key,3000)
    return result


class Guide:
    def __init__(self, root=None, *, clock=core.iso_now):
        self.root=Path(root) if root is not None else memory_home()
        self.clock=clock
        if self.root.is_symlink(): raise ValueError('Memory directory must not be a symlink')
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.path=self.root/'guide.sqlite3'
        if self.path.is_symlink(): raise ValueError('Memory database must not be a symlink')
        with self.connect() as db:
            version=db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0,SCHEMA): raise ValueError('Unsupported memory schema; preserve the database and use a compatible release')
            if version==0:
                if db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone():
                    raise ValueError('Unrecognized database; refusing to adopt or overwrite it')
                db.execute('CREATE TABLE snapshots (profile TEXT, revision INTEGER, label TEXT, payload TEXT, sha256 TEXT, PRIMARY KEY(profile,revision))')
                db.execute('PRAGMA user_version=1')
        if os.name!='nt': self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=15)
        try:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback(); raise
        finally: db.close()

    def _load(self,db,pid):
        row=db.execute('SELECT revision,payload,sha256 FROM snapshots WHERE profile=? ORDER BY revision DESC LIMIT 1',(pid,)).fetchone()
        if not row: raise ValueError('Select an existing profile explicitly')
        state=json.loads(row[1])
        if digest(state)!=row[2] or state.get('revision')!=row[0] or state.get('profile_id')!=pid:
            raise ValueError('Memory integrity check failed; restore a verified backup')
        return state

    def _append(self,db,state):
        db.execute('INSERT INTO snapshots VALUES (?,?,?,?,?)',
                   (state['profile_id'],state['revision'],state['label'],encoded(state),digest(state)))

    def _journey(self,state,jid):
        if jid not in state['journeys']: raise ValueError('Select a book belonging to this profile')
        return state['journeys'][jid]

    def _facts(self,state,j): return {**state['facts'],**j['facts']}

    def _binding(self,state,j): return digest(self._facts(state,j))

    def _missing(self,state,j):
        facts={k:v['value'] for k,v in self._facts(state,j).items()}
        missing=[k for k in REQUIRED if k not in facts]
        formats=facts.get('formats',[]);formats=[formats] if isinstance(formats,str) else formats
        if set(formats)&{'print','both','paperback','hardcover'} and 'print_preferences' not in facts: missing.append('print_preferences')
        goal=facts.get('goal',{})
        if goal.get('kind')=='income':
            missing += ['goal.'+k for k in ('metric','period') if goal.get(k,'undecided')=='undecided']
        return missing

    def _view(self,state,jid,session=None):
        j=self._journey(state,jid); missing=self._missing(state,j)
        confirmed=session and j['confirmations'].get(session)==self._binding(state,j)
        stage='questionnaire' if missing else j['stage']
        from beyondwords_market import validate_options, comparison_coverage
        research_coverage={}
        for kind,options in j['options'].items():
            try:
                checked=validate_options(options['items'],synthetic=state['synthetic'],now=self.clock())
                research_coverage[kind]=comparison_coverage(checked,kind,selected_niche=j['decisions'].get('niche',{}).get('niche') if kind=='gaps' else None)
            except ValueError as exc:
                research_coverage[kind]={'choice_ready':False,'missing':[str(exc)],'demand_validated':False}
        if not missing:
            for kind in ('niches','gaps'):
                if kind in research_coverage and not research_coverage[kind]['choice_ready']:
                    stage='research_'+kind;break
        if self._facts(state,j) and not confirmed: stage='confirm_saved_answers'
        out=dict(profile_id=state['profile_id'],journey_id=jid,revision=state['revision'],
                 session_id=session,answers=self._facts(state,j),next=stage,missing=missing,
                 questions=[QUESTIONS[k] for k in missing[:3]],synthetic=state['synthetic'],
                 delivery='conversation',create_document=False,forecast=None,
                 publication_ready=False,decisions=j['decisions'],options=j['options'],research_coverage=research_coverage,
                 persona=j['persona'],sample=j['sample'],book_status=j.get('book_status'),
                 operating_mode=j['facts'].get('operating_mode',{}).get('value','UNKNOWN'),
                 account_authority_granted=False,goal=self._facts(state,j).get('goal',{}).get('value'),
                 research_context={k:v['value'] for k,v in self._facts(state,j).items() if k in {'country','book_type','target_marketplace','publishing_channels','budget','marketing_budget','time','goal','interests'}})
        if stage=='confirm_saved_answers': out['questions']=['I found your saved answers. Are these still right for this book?']
        return out

    def execute(self,payload,*,expected_revision=None):
        if not isinstance(payload,dict): raise ValueError('Guide input must be an object')
        action=payload.get('action','start')
        with self.connect() as db:
            if action=='start' and not payload.get('profile_id'):
                profiles=db.execute('SELECT profile, MAX(revision), label FROM snapshots GROUP BY profile ORDER BY label').fetchall()
                return dict(next='select_profile',delivery='conversation',create_document=False,
                            profiles=[{'profile_id':p[0],'label':p[2]} for p in profiles],
                            questions=['Start a new author profile, or resume one you recognize?'])
            if action in {'create','import'}:
                imported=None
                if action=='import':
                    if payload.get('authorized') is not True: raise ValueError('Confirm permission to import this handoff')
                    envelope=payload.get('handoff',{}); body=envelope.get('body',{})
                    if digest(body)!=envelope.get('sha256') or set(body)!={'schema','label','book_label','answers','synthetic'} or body.get('schema')!=1:
                        raise ValueError('Invalid or changed handoff; only intake facts may be transferred')
                    imported=answers_checked({k:v['value'] for k,v in body['answers'].items()})
                    payload={**payload,**{k:body[k] for k in ('label','book_label','synthetic')}}
                label=core.text(payload.get('label'),'profile label',120)
                book=core.text(payload.get('book_label'),'book label',160)
                if type(payload.get('synthetic')) is not bool: raise ValueError('Declare synthetic true or false')
                pid,jid=str(uuid4()),str(uuid4())
                state=dict(profile_id=pid,label=label,revision=0,synthetic=payload['synthetic'],facts={},journeys={})
                state['journeys'][jid]=self._new_book(book)
                if imported: self._answers(state,state['journeys'][jid],imported,'Authorized handoff; author confirmation pending')
                self._append(db,state)
                return self._view(state,jid)
            state=self._load(db,payload.get('profile_id'))
            jid=payload.get('journey_id')
            if action=='start' and not jid:
                return dict(profile_id=state['profile_id'],revision=state['revision'],next='select_book',
                            books=[{'journey_id':k,'label':v['label']} for k,v in state['journeys'].items()],
                            delivery='conversation',create_document=False)
            j=self._journey(state,jid)
            if action=='start':
                return self._view(state,jid,payload.get('session_id') or str(uuid4()))
            if action=='export':
                body=dict(schema=1,label=state['label'],book_label=j['label'],answers=self._facts(state,j),synthetic=state['synthetic'])
                return dict(handoff={'body':body,'sha256':digest(body)},private=True,
                            note='Intake only; no credentials, approvals or account permissions. Import requires confirmation.')
            if type(expected_revision) is not int or expected_revision!=state['revision']:
                raise ValueError('Stale or missing revision; reload before changing saved work')
            state['revision']+=1
            if action=='new-book':
                jid=str(uuid4()); state['journeys'][jid]=self._new_book(core.text(payload.get('book_label'),'book_label',160))
            elif action=='recall':
                candidates=answers_checked(payload.get('answers'))
                origin=core.text(payload.get('origin'),'history origin',500)
                existing=self._facts(state,j)
                conflicts={k:{'saved':existing[k]['value'],'candidate':v,'origin':origin}
                           for k,v in candidates.items() if k in existing and existing[k]['value']!=v}
                self._answers(state,j,{k:v for k,v in candidates.items() if k not in existing},origin)
                self._append(db,state)
                return {**self._view(state,jid,payload.get('session_id')),'conflicts':conflicts,
                        'next':'resolve_history_conflicts' if conflicts else 'confirm_saved_answers'}
            elif action=='answer':
                self._answers(state,j,answers_checked(payload.get('answers')),core.text(payload.get('origin'),'answer origin',500))
            elif action=='confirm':
                session=core.text(payload.get('session_id'),'session_id',100)
                j['confirmations']={session:self._binding(state,j)}
            elif action=='mode':
                mode=choice(payload.get('mode'),{'guided','execution'},'mode')
                basis=core.text(payload.get('decision_basis'),'decision_basis',1000)
                j['facts']['operating_mode']=dict(value=mode,origin=basis,recorded_at=self.clock(),revision=state['revision'])
                j['confirmations']={}
            elif action in {'options','choose','set-niche','persona','sample','accept-sample','attach-book','resume'}:
                self._guard(state,j,payload.get('session_id'))
                self._work(action,state,j,payload)
            else: raise ValueError('Unknown guide action; no account or ad execution is provided by this tool')
            self._append(db,state)
            return self._view(state,jid,payload.get('session_id'))

    def _new_book(self,label):
        return dict(label=label,facts={},stage='research_niches',confirmations={},decisions={},options={},persona=None,sample=None)

    def _answers(self,state,j,answers,origin):
        for key,value in answers.items():
            target=state['facts'] if key in PERSON else j['facts']
            if key in target and target[key]['value']==value: continue
            target[key]=dict(value=value,origin=origin,recorded_at=self.clock(),revision=state['revision'])
            if key=='operating_mode':
                j['confirmations']={}
                continue
            # Retain old options/decisions in immutable earlier snapshots; never silently reuse them.
            affected=state['journeys'].values() if key in PERSON else [j]
            for book in affected:
                book.update(stage='research_niches',confirmations={},decisions={},options={},persona=None,sample=None)

    def _guard(self,state,j,session):
        if not session or j['confirmations'].get(session)!=self._binding(state,j):
            raise ValueError('Confirm saved answers for this session before continuing')
        if self._missing(state,j): raise ValueError('Complete the missing questionnaire answers; undecided is allowed where indicated')

    def _work(self,action,state,j,p):
        from beyondwords_market import validate_options, comparison_coverage
        def coverage(items,kind):
            selected=None
            if kind=='gaps' and 'niche' in j['decisions']:
                selected=j['decisions']['niche'].get('niche') or next((x.get('niche') for x in j['options'].get('niches',{}).get('items',[]) if x['id']==j['decisions']['niche']['id']),None)
            return comparison_coverage(items,kind,selected_niche=selected)
        if action not in {'options','choose','set-niche'}:
            for kind,options in j['options'].items():
                checked=validate_options(options['items'],synthetic=state['synthetic'],now=self.clock())
                if not coverage(checked,kind)['choice_ready']: raise ValueError('Complete current five-choice research before production; saved partial or legacy choices remain available for research')
        if action=='set-niche':
            niche=core.text(p.get('niche'),'niche',2000)
            basis=core.text(p.get('decision_basis'),'decision_basis',1000)
            j.update(decisions={'niche':dict(id='author-selected',niche=niche,basis=basis,at=self.clock(),source='author_selection',research_validated=False)},options={},persona=None,sample=None,stage='research_gaps')
        elif action=='options':
            kind=choice(p.get('kind'),{'niches','gaps'},'kind')
            if kind=='gaps' and 'niche' not in j['decisions']: raise ValueError('Choose an evidence-backed niche before researching gaps')
            validated=validate_options(p.get('options'),synthetic=state['synthetic'],now=self.clock())
            research_coverage=coverage(validated,kind)
            j['options'][kind]=dict(items=validated,sha256=digest(validated),coverage=research_coverage)
            if kind=='niches': j['decisions']={}; j['options'].pop('gaps',None)
            else: j['decisions'].pop('gap',None)
            j.update(persona=None,sample=None,stage=('choose_' if research_coverage['choice_ready'] else 'research_')+kind)
        elif action=='choose':
            kind=choice(p.get('kind'),{'niches','gaps'},'kind'); options=j['options'].get(kind)
            if not options or p.get('options_sha256')!=options['sha256']: raise ValueError('Options changed or are missing; review current choices')
            checked=validate_options(options['items'],synthetic=state['synthetic'],now=self.clock())
            if not coverage(checked,kind)['choice_ready']: raise ValueError('Research comparison incomplete: inspect five distinct choices and their competitor reviews/samples before choosing')
            selected=next((x for x in options['items'] if x['id']==p.get('option_id')),None)
            if not selected: raise ValueError('Select one of the researched options')
            # A declaration records a local decision, not external authorization or reviewer authentication.
            basis=core.text(p.get('decision_basis'),'decision_basis',1000)
            j['decisions']['niche' if kind=='niches' else 'gap']=dict(id=selected['id'],niche=selected.get('niche'),options_sha256=options['sha256'],basis=basis,at=self.clock())
            if kind=='niches':
                j['decisions'].pop('gap',None); j['options'].pop('gaps',None)
            j.update(persona=None,sample=None,stage='research_gaps' if kind=='niches' else 'voice_interview')
        elif action=='persona':
            if 'gap' not in j['decisions']: raise ValueError('Choose a researched gap before developing the voice')
            persona=p.get('persona')
            fields={'reader','buyer','author_contribution','tone','rhythm','vocabulary','viewpoint','emotional_range','avoid','owned_examples'}
            extra={'reader_age','genre','sentence_length','humor','cultural_context','expertise_basis','author_personality','storytelling_style','pacing','example_style','dialogue_style','formatting_preference'}
            if not isinstance(persona,dict) or not fields<=set(persona) or set(persona)-(fields|extra): raise ValueError('Complete reader, buyer and voice interview fields')
            persona={k:core.text(v,k,5000) for k,v in persona.items()}
            j.update(persona={'data':persona,'sha256':digest(persona)},sample=None,stage='voice_sample')
        elif action=='sample':
            if not j['persona']: raise ValueError('Complete the persona interview first')
            body=core.text(p.get('body'),'sample',12000)
            provenance=choice(p.get('provenance'),{'human_provided','ai_assisted','ai_generated'},'provenance')
            j.update(sample=dict(body=body,sha256=digest(body),persona_sha256=j['persona']['sha256'],provenance=provenance,accepted=False),stage='review_voice_sample')
        elif action=='accept-sample':
            s=j['sample']
            if not s or p.get('sample_sha256')!=s['sha256']: raise ValueError('Review the current sample before accepting it')
            s.update(accepted=True,decision_basis=core.text(p.get('decision_basis'),'decision_basis',1000))
            j['stage']='outline_and_chapter_contracts'
        elif action=='attach-book':
            if not j['sample'] or not j['sample']['accepted']:
                raise ValueError('Accept a voice sample before starting extensive book production')
            from beyondwords_book import BookStore
            path=Path(core.text(p.get('book_workspace'),'book_workspace')).expanduser().resolve()
            store=BookStore(path,core.text(p.get('book_project_id'),'book_project_id'))
            status=store.status()
            if status['synthetic']!=state['synthetic']: raise ValueError('Book and guide evidence modes differ')
            j['book_link']={'workspace':str(path),'project_id':store.project_id}
            self._book_progress(j)
        elif action=='resume':
            # Re-evaluate freshness even after a previous choice; expired evidence cannot authorize further drafting.
            for options in j['options'].values(): validate_options(options['items'],synthetic=state['synthetic'],now=self.clock())
            if j.get('book_link') and j['sample'] and j['sample']['accepted']: self._book_progress(j)

    def _book_progress(self,j):
        from beyondwords_book import BookStore
        link=j['book_link']; status=BookStore(Path(link['workspace']),link['project_id']).status()
        missing=status['missing']
        if 'book_plan' in missing: stage='outline_and_chapter_contracts'
        elif any(x.startswith('chapter:') for x in missing): stage='draft_next_chapter'
        elif any(x.startswith(('chapter_contract_recheck:','text_provenance:')) for x in missing) or status['claim_findings'] or status['repeated_paragraph_chapters']:
            stage='edit_and_resolve_claims'
        elif 'cover_review' in missing: stage='cover_design_and_review'
        elif any(x in missing for x in ('editorial_review','reader_review','author_review','rights_review')): stage='independent_reviews'
        elif 'current_edition_export' in missing: stage='produce_edition_files'
        else: stage='publishing_and_launch_handoff'
        j['stage']=stage
        j['book_status']=dict(project_id=status['project_id'],revision=status['revision'],content_sha256=status['content_sha256'],
                              missing=missing,outcomes=status['outcomes'],publication_ready=False)

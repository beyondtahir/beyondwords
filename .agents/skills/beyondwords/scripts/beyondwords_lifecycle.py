"""Evidence, creative development and measured business reviews on the existing store.

The host does research and craft. These tools preserve inputs and calculate only what
those inputs support. Records are declarations, not authenticated market facts.
"""
from collections import Counter
from datetime import date,timedelta
from decimal import Decimal,ROUND_CEILING
from pathlib import Path
from urllib.parse import urlsplit
import copy,re
import publishing_core as core
import publishing_project as project
from beyondwords_book import BookStore,latest,content_hash

SIGNALS={'listing','review','discussion','search_trend','keyword_metric','ad_metric','policy','country','cover','sales','reader_feedback'}
COUNTRY_TOPICS={'eligibility','identity','tax','payout','bank','address','phone','currency','restrictions','marketplace'}
CHANNELS={'amazon_ads','meta','tiktok','pinterest','instagram','youtube','email','influencer','goodreads','seo','website','direct','etsy','shopify'}
OFFICIAL={'kdp':{'kdp.amazon.com','advertising.amazon.com'},'lulu':{'lulu.com','help.lulu.com','developers.lulu.com'},'etsy':{'etsy.com','help.etsy.com','www.etsy.com'},'shopify':{'shopify.com','help.shopify.com','www.shopify.com'}}

def text(v,k,limit=12000):return core.text(v,k,limit)
def array(v,k,maximum=100,empty=False):
 if not isinstance(v,list) or len(v)>maximum or (not empty and not v):raise ValueError(k+' requires a bounded list')
 return copy.deepcopy(v)
def money(v,k):return core.number(v,k)
def period(v):
 start,end=date.fromisoformat(v['period_start']),date.fromisoformat(v['period_end'])
 if start>end or (end-start).days>365:raise ValueError('Choose an ordered period of at most one year')
 return start,end

def source_check(value,synthetic,now):
 from publishing_browser import check_url
 v=copy.deepcopy(value)
 if v.get('synthetic') is not synthetic:raise ValueError('Evidence context differs from project')
 if any(v.get(k) is not True for k in ('authorized','retain','derive')):raise project.ProjectError('PERMISSION_REQUIRED','Resolve access, retention and derived-use permission before import')
 check_url(v['url'],v['url'],resolve=False)
 for k in ('permission_basis','title','excerpt','source_kind'):text(v.get(k),k,32000)
 if v['source_kind'] not in SIGNALS:raise ValueError('Unknown evidence source kind')
 if core.timestamp(v['observed_at'],'observed_at')>core.timestamp(now,'now'):raise ValueError('Future evidence is invalid')
 v['content_sha256']=project.digest(v['excerpt'].encode())
 if v['source_kind'] in {'listing','review','cover'}:
  for k in ('edition_id','selected_edition_id','marketplace','format'):text(v.get(k),k)
  if v['edition_id']!=v['selected_edition_id'] or v['edition_id']=='UNKNOWN' or v.get('edition_verified') is not True:raise ValueError('Verify the selected edition before using this observation')
 # These remain scoped measurements, never an estimated Amazon sales volume.
 if 'measurement' in v:
  m=v['measurement']
  for k in ('metric','unit','method','scope'):text(m.get(k),k)
  m['value']=str(money(m['value'],'measurement.value')) if m.get('value') is not None else None
  if m['metric'] in {'bsr_sales_estimate','success_probability'}:raise ValueError('No calibrated estimator is provided')
 return v

class Lifecycle(BookStore):
 def bindings(self,rows):return {r['id']:r['sha256'] for r in rows}
 def bound_evidence(self,book,record,max_age_hours=720):
  rows=self.evidence(book,record['evidence_ids'],max_age_hours)
  if self.bindings(rows)!=record.get('evidence_bindings'):raise ValueError('Evidence changed; review this interpretation again')
  return rows
 def evidence(self,book,ids,max_age_hours=720):
  ids=array(ids,'evidence_ids');out=[]
  if len(set(ids))!=len(ids):raise ValueError('Duplicate evidence references')
  for ident in ids:
   row=latest(book,'intelligence',ident)
   if not row:raise ValueError('Unknown evidence: '+str(ident))
   d=source_check(row['data'],book['synthetic'],self.clock())
   age=(core.timestamp(self.clock(),'now')-core.timestamp(d['observed_at'],'observed_at')).total_seconds()/3600
   if age>max_age_hours:raise ValueError('Evidence is stale; refresh '+ident)
   out.append(row)
  return out
 def save(self,revision,kind,key,data):
  with self._change(revision,'book_lifecycle') as (db,state):
   self._save(db,state,kind,key,data)
  return {'revision':state['revision'],'record':latest(state['book'],kind,key),'synthetic':state['book']['synthetic'],'publication_ready':False}
 def execute(self,p,revision=None):
  state=self.read();book=self._book(state);task=p['task'];key=project.identifier(p.get('id','main'),'id')
  if task in {'status','progress','research-status','country-status','review-themes','next','forecast','schedule-status'}:
   if task=='schedule-status':
    cadence=latest(book,'cadence',key);receipt=latest(book,'schedule_receipt',key);run=latest(book,'schedule_run',key)
    current=bool(cadence and receipt and receipt['data']['cadence_sha256']==cadence['sha256'])
    return {'cadence':cadence,'receipt':receipt,'last_run':run,'configuration_current':current,
     'state':'HOST_REPORTED_REGISTERED' if current else 'NOT_SCHEDULED',
     'observed_run':bool(current and run and run['data']['receipt_sha256']==receipt['sha256']),
     'running_now':'UNKNOWN','create_document':False}
   if task=='forecast':return self.forecast(book)
   if task=='progress':return self.progress(book)
   if task=='research-status':return self.research_status(book,key)
   if task=='country-status':return self.country_status(book,key)
   if task=='review-themes':return self.review_themes(book,p)
   result={'revision':state['revision'],'records':[{k:r[k] for k in ('kind','id','revision','sha256')} for r in book['records']], 'progress':self.progress(book),'synthetic':book['synthetic'],'publication_ready':False}
   if task=='next':
    s=self.status();progress=result['progress']
    result['next_action']='Resolve '+s['missing'][0] if s['missing'] else ('Review actual performance and one bounded improvement experiment' if progress.get('actual') is not None else 'Import complete current sales and cost reports; missing totals remain unknown')
    result['create_document']=False
   return result
  project.require_revision(revision)
  if task=='cadence':
   from zoneinfo import ZoneInfo
   d=copy.deepcopy(p['cadence'])
   for k in ('timezone','cadence','user_request','review_scope'):text(d.get(k),k)
   ZoneInfo(d['timezone'])
   if d.get('notification') not in {'meaningful_changes','every_run'}:raise ValueError('Choose notification preference')
   return self.save(revision,'cadence',key,d)
  if task=='schedule-receipt':
   c=latest(book,'cadence',key)
   if not c or p.get('cadence_sha256')!=c['sha256']:raise ValueError('Confirm the current cadence before scheduling')
   d=copy.deepcopy(p['receipt'])
   for k in ('host','job_id','tool','receipt_reference','observed_at'):text(d.get(k),k)
   if core.timestamp(d['observed_at'],'observed_at')>core.timestamp(self.clock(),'now'):raise ValueError('Future receipt')
   d.update(cadence_sha256=c['sha256'],host_reported=True,independently_verified=False)
   return self.save(revision,'schedule_receipt',key,d)
  if task=='schedule-run':
   receipt=latest(book,'schedule_receipt',key);cadence=latest(book,'cadence',key)
   if not receipt or not cadence or receipt['data']['cadence_sha256']!=cadence['sha256'] or p.get('receipt_sha256')!=receipt['sha256']:raise ValueError('The schedule configuration changed; reconcile with the real scheduler')
   d=copy.deepcopy(p['run'])
   for k in ('observed_at','receipt_reference','outcome'):text(d.get(k),k)
   if core.timestamp(d['observed_at'],'observed_at')>core.timestamp(self.clock(),'now'):raise ValueError('Future run')
   d.update(receipt_sha256=receipt['sha256'],host_reported=True,independently_verified=False)
   return self.save(revision,'schedule_run',key,d)
  if task=='evidence':
   d=source_check(p['evidence'],book['synthetic'],self.clock())
   return self.save(revision,'intelligence',key,d)
  if task=='study':
   d={k:text(p.get(k),k) for k in ('question','reader','buyer','author_fit','marketplace','format','budget_basis')}
   d['required_signals']=array(p.get('required_signals'),'required_signals')
   if set(d['required_signals'])-SIGNALS:raise ValueError('Unsupported research signals')
   d['queries']=[text(x,'query',2000) for x in array(p.get('queries'),'queries',30)]
   d['options']=[]
   for option in array(p.get('options',[]),'options',5,True):
    for k in ('id','interpretation','effort','investment_basis','risk','next_test'):text(option.get(k),k)
    option=copy.deepcopy(option);sources=self.evidence(book,option.get('evidence_ids'))
    if any(r['data'].get('marketplace')!=d['marketplace'] or r['data'].get('format')!=d['format'] for r in sources):raise ValueError('Option evidence differs from the study marketplace or format')
    option['evidence_bindings']=self.bindings(sources)
    # Exact source fragments support inspection, not automatic entailment.
    for fact in array(option.get('facts'),'facts',30):
     text(fact.get('claim'),'claim');sources=self.evidence(book,fact.get('evidence_ids'))
     if set(fact['evidence_ids'])-set(option['evidence_ids']):raise ValueError('Fact sources must belong to the option evidence scope')
     quote=text(fact.get('quote'),'quote')
     if not any(quote in r['data']['excerpt'] for r in sources):raise ValueError('Fact quote is absent from the linked evidence')
    d['options'].append(option)
   return self.save(revision,'study',key,d)
  if task=='bible':
   route=p['route'];d=copy.deepcopy(p['data'])
   fields={'fiction':{'characters','world_rules','timeline','relationships','emotional_arcs','dialogue_rules','voice_rules'},
    'nonfiction':{'expertise_basis','reader_outcome','teaching_style','example_rules','research_standard','structure'},
    'visual':{'reader_age','style','characters','clothing','environments','palette','page_contracts','continuity_rules'}}
   if route not in fields or set(d)!=fields[route]:raise ValueError('Complete the route-specific bible fields')
   if len(project.canonical(d))>200000:raise ValueError('Bible is too large')
   for k,v in d.items():
    if isinstance(v,str):text(v,k)
    elif isinstance(v,list):array(v,k,300,True)
    else:raise ValueError('Bible fields must be text or lists')
   return self.save(revision,'bible',key,dict(route=route,data=d,source='author/host creative direction; not market evidence'))
  if task=='country':
   country=text(p.get('country'),'country',120);channel=p['channel']
   if channel not in OFFICIAL:raise ValueError('Unsupported policy channel')
   facts=array(p.get('facts'),'facts',40);topics=[]
   for fact in facts:
    if fact.get('topic') not in COUNTRY_TOPICS or fact.get('classification') not in {'official','community'}:raise ValueError('Identify policy topic and official/community classification')
    text(fact.get('claim'),'claim');sources=self.evidence(book,fact.get('evidence_ids'),168)
    quote=text(fact.get('quote'),'quote')
    if not any(quote in s['data']['excerpt'] for s in sources):raise ValueError('Country claim must identify its supporting source passage')
    if fact['classification']=='official' and any(urlsplit(s['data']['url']).hostname not in OFFICIAL[channel] for s in sources):raise ValueError('Official facts must link the selected platform’s official domain')
    for s in sources:
     if s['data'].get('country')!=country:raise ValueError('Country evidence scope mismatch')
    fact['evidence_bindings']=self.bindings(sources)
    topics.append(fact['topic'])
   official={f['topic'] for f in facts if f['classification']=='official'}
   return self.save(revision,'country',key,dict(country=country,channel=channel,facts=facts,missing=sorted(COUNTRY_TOPICS-set(topics)),missing_official_topics=sorted(COUNTRY_TOPICS-official),independent_verification=False))
  if task=='goal':
   g=copy.deepcopy(p['goal']);period(g)
   if g['metric'] not in {'revenue','royalties','pre_tax_profit'}:raise ValueError('Choose revenue, royalties or pre-tax profit')
   g['amount']=str(money(g['amount'],'goal.amount'));g['currency']=core.currency_code(g['currency'])
   g['scope']=array(g.get('scope'),'scope',100)
   identities=[]
   for scope in g['scope']:
    if set(scope)!={'account_label','marketplace','title_id'}:raise ValueError('Goal scope needs exact account, marketplace and title')
    identities.append(tuple(text(scope[k],k) for k in ('account_label','marketplace','title_id')))
   if len(set(identities))!=len(identities):raise ValueError('Duplicate title scope')
   if 'contribution_per_sale' in g:
    g['contribution_per_sale']=str(money(g['contribution_per_sale'],'contribution_per_sale'));text(g.get('contribution_basis'),'contribution_basis')
   return self.save(revision,'goal','main',g)
  if task=='experiment':
   d=copy.deepcopy(p['experiment'])
   if d.get('channel') not in CHANNELS:raise ValueError('Unsupported marketing channel')
   for k in ('audience','hypothesis','creative','success_measure','stop_condition','budget_basis','owner_decision'):text(d.get(k),k)
   self.evidence(book,d.get('evidence_ids'));d['budget']=str(money(d['budget'],'budget'));d['currency']=core.currency_code(d['currency'])
   d.update(subject_sha256=content_hash(book),executed=False,account_authority=False)
   return self.save(revision,'experiment',key,d)
  if task=='experiment-result':
   old=latest(book,'experiment',key)
   if not old or p.get('experiment_sha256')!=old['sha256']:raise ValueError('Review the current experiment')
   if old['data']['subject_sha256']!=content_hash(book):raise ValueError('Book changed; replan experiment')
   self.evidence(book,p.get('evidence_ids'))
   for k in ('observed','interpretation','next_action'):text(p.get(k),k)
   return self.save(revision,'experiment_result',key,{k:p[k] for k in ('experiment_sha256','evidence_ids','observed','interpretation','next_action')})
  if task=='scale':
   progress=self.progress(book)
   if progress.get('actual') is None or progress.get('estimated'):raise ValueError('Scaling assessment requires complete finalized reports')
   for k in ('route','investment_basis','capacity','risk','owner_decision'):text(p.get(k),k)
   self.evidence(book,p.get('evidence_ids'))
   d={k:p[k] for k in ('route','investment_basis','capacity','risk','owner_decision','evidence_ids')}
   d.update(progress_sha256=project.digest(project.canonical(progress)),status='REVIEWABLE_HYPOTHESIS',guaranteed_return=False)
   return self.save(revision,'scale',key,d)
  raise ValueError('Unknown lifecycle task')
 def forecast(self,book):
  """Historical repetition scenarios with a walk-forward error record, never BSR sales."""
  from statistics import median
  from beyondwords_business import summarize_reports
  goal=latest(book,'goal','main')
  if not goal:raise ValueError('Confirm the target and exact title/account scope first')
  g=goal['data'];allowed=g['scope']
  reports=[r['data'] for r in self._active_reports(book) if r['data']['currency']==g['currency'] and any(all(r['data'][k]==s[k] for k in s) for s in allowed)]
  groups=summarize_reports(reports)['groups'];by_title={}
  for row in groups:
   if row['basis']!='finalized':continue
   value=row['reported_pre_tax_profit'] if g['metric']=='pre_tax_profit' else row['totals'].get('sales' if g['metric']=='revenue' else 'royalties')
   if value is None:continue
   days=(date.fromisoformat(row['period_end'])-date.fromisoformat(row['period_start'])).days+1
   if days<7:continue
   key=tuple(row[k] for k in ('account_label','marketplace','title_id'))
   by_title.setdefault(key,[]).append({'start':row['period_start'],'end':row['period_end'],'daily':Decimal(value)/days,'source_hashes':row['source_hashes']})
  histories=[];missing=[]
  for scope in allowed:
   key=tuple(scope[k] for k in ('account_label','marketplace','title_id'));rows=sorted(by_title.get(key,[]),key=lambda x:x['start'])
   if len(rows)<3:missing.append(scope);continue
   if any(rows[i]['start']<=rows[i-1]['end'] for i in range(1,len(rows))):raise ValueError('Historical intervals overlap')
   values=[r['daily'] for r in rows];errors=[abs(values[i]-median(values[:i])) for i in range(2,len(values))]
   histories.append({'scope':scope,'observed_periods':len(rows),'daily_median':str(median(values)),
    'daily_observed_range':[str(min(values)),str(max(values))],'walk_forward_absolute_error_mean':str(sum(errors)/len(errors)),
    'evaluation_periods':len(errors),'source_hashes':sorted({h for r in rows for h in r['source_hashes']})})
  total=sum((Decimal(h['daily_median']) for h in histories),Decimal(0)) if not missing else None
  days=(date.fromisoformat(g['period_end'])-date.fromisoformat(g['period_start'])).days+1
  target=Decimal(g['amount']);per_title=median([Decimal(h['daily_median'])*days for h in histories]) if histories and not missing else None
  count=int((target/per_title).to_integral_value(rounding=ROUND_CEILING)) if per_title and per_title>0 else None
  return {'method':'Expanding historical median with walk-forward absolute error; arithmetic, not a trained AI model',
   'histories':histories,'missing_history':missing,'period_amount_if_history_repeats':str(total*days) if total is not None else None,
   'equivalent_titles_if_observed_per_title_results_repeat':count,'new_book_forecast':None,'success_probability':None,
   'assumptions':['Observed title economics and traffic repeat','No claim that a new title shares existing-title results','Range is historical, not a confidence interval','Seasonality, new costs and market changes can invalidate repetition'],
   'status':'INSUFFICIENT_EVIDENCE' if missing else 'HISTORICAL_SCENARIO','create_document':False}
 def research_status(self,book,key):
  study=latest(book,'study',key)
  if not study:raise ValueError('Create a scoped study first')
  evidence=latest(book,'intelligence');fresh=[];stale=[]
  for row in evidence:
   if row['data'].get('marketplace')!=study['data']['marketplace'] or row['data'].get('format')!=study['data']['format']:continue
   try:self.evidence(book,[row['id']]);fresh.append(row)
   except ValueError:stale.append(row['id'])
  covered={s['data']['source_kind'] for s in fresh};missing=sorted(set(study['data']['required_signals'])-covered)
  valid=[];invalid=[]
  for option in study['data']['options']:
   try:self.bound_evidence(book,option);valid.append(option)
   except ValueError as exc:invalid.append({'id':option['id'],'reason':str(exc)})
  return {'study':study,'coverage':{k:[r['id'] for r in fresh if r['data']['source_kind']==k] for k in sorted(covered)},'missing_signals':missing,'stale':stale,'options':valid,'invalid_options':invalid,'commercial_viability':'UNPROVEN','sales_forecast':None,'next_action':'Collect '+', '.join(missing[:3]) if missing else 'Review contrary evidence and test the author-selected hypothesis','create_document':False}
 def country_status(self,book,key):
  row=latest(book,'country',key)
  if not row:raise ValueError('Research country requirements first')
  d=copy.deepcopy(row['data']);d['stale_topics']=[]
  for f in d['facts']:
   try:self.bound_evidence(book,f,168)
   except ValueError:d['stale_topics'].append(f['topic'])
  d['account_eligibility']='REQUIRES_ACTUAL_PLATFORM_REVIEW';return d
 def review_themes(self,book,p):
  themes=[]
  for theme in array(p.get('themes'),'themes',30):
   text(theme.get('label'),'theme label');refs=self.evidence(book,theme.get('evidence_ids'))
   quote=text(theme.get('quote'),'quote')
   if any(r['data']['source_kind'] not in {'review','reader_feedback','discussion'} for r in refs):raise ValueError('Themes need reader/review evidence')
   matching=[r['id'] for r in refs if quote in r['data']['excerpt']]
   if not matching:raise ValueError('Theme quote is absent from sources')
   themes.append(dict(label=theme['label'],quote=quote,matching_sources=matching,interpretation=theme.get('interpretation','UNKNOWN')))
  return {'themes':themes,'sample_is_representative':False,'purchase_demand':'UNKNOWN','create_document':False}
 def progress(self,book):
  row=latest(book,'goal','main')
  if not row:return {'goal':None,'actual':None,'next_action':'Confirm the goal metric, period and title scope','forecast':False}
  g=row['data'];start,end=period(g);today=core.timestamp(self.clock(),'now').date();through=min(end,today)
  needed={'revenue':['sales'],'royalties':['royalties'],'pre_tax_profit':['royalties','ads','costs']}[g['metric']]
  reports=[r['data'] for r in self._active_reports(book)];missing=[];totals={k:Decimal(0) for k in needed};estimated=False;hashes=[]
  for scope in g['scope']:
   for kind in needed:
    selected=[r for r in reports if r['kind']==kind and r['currency']==g['currency'] and all(r[k]==scope[k] for k in scope) and r['period_start']<=str(through) and r['period_end']>=str(start)]
    dates=set()
    for r in selected:
     lo=max(start,date.fromisoformat(r['period_start']));hi=min(through,date.fromisoformat(r['period_end']))
     dates.update(lo+timedelta(days=i) for i in range((hi-lo).days+1))
     totals[kind]+=sum((Decimal(x['amount']) for x in r['rows'] if str(start)<=x['date']<=str(through)),Decimal(0))
     estimated|=r['basis']!='finalized';hashes.append(r['source_sha256'])
    required=max(0,(through-start).days+1)
    if len(dates)!=required or not required:missing.append({'scope':scope,'kind':kind,'missing_days':required-len(dates)})
  actual=None if missing else (totals['royalties']-totals['ads']-totals['costs'] if g['metric']=='pre_tax_profit' else totals[needed[0]])
  target=Decimal(g['amount']);gap=max(Decimal(0),target-actual) if actual is not None else None
  remaining=max(0,(end-max(start,today)+timedelta(days=1)).days)
  contribution=Decimal(g.get('contribution_per_sale','0'));units=int((gap/contribution).to_integral_value(rounding=ROUND_CEILING)) if gap is not None and contribution>0 else None
  return {'goal':g,'actual':str(actual) if actual is not None else None,'gap':str(gap) if gap is not None else None,'through':str(through),'totals':{k:str(v) for k,v in totals.items()},'missing_reports':missing,'estimated':estimated,'source_hashes':sorted(set(hashes)),'required_additional_sales_under_assumption':units,'remaining_days':remaining,'daily_sales_under_assumption':str(Decimal(units)/remaining) if units is not None and remaining else None,'forecast':False,'scaling_readiness':'REVIEW_RESULTS' if actual is not None and not estimated else 'NEEDS_EVIDENCE','next_action':'Import missing reports before recommending a change' if missing else 'Discuss the measured gap and one evidence-backed experiment','create_document':False}


def execute(workspace,project_id,revision,payload):
 if not workspace or not project_id:raise ValueError('Select a versioned book project')
 store=Lifecycle(Path(workspace),project_id);result=store.execute(payload,revision)
 result['synthetic']=store._book(store.read())['synthetic']
 result['publication_ready']=False
 return result

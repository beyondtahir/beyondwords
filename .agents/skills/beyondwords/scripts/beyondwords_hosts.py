"""Portable routing to capabilities actually observed by the current AI host.

This is not an RPC client or permission grant. The host invokes its own real tool,
then records the returned outcome. Missing capabilities remain unavailable.
"""
from pathlib import Path
from urllib.parse import urlsplit
import copy
import re
import publishing_core as core
import publishing_project as project
from beyondwords_book import latest
from beyondwords_lifecycle import Lifecycle
KINDS={'search','browser','image','layout','documents','scheduler','publish','advertising','messaging','inference','memory'}
STATUSES={'OK','UNAVAILABLE','AUTH_REQUIRED','NETWORK_ERROR','ACCESS_DENIED','CAPTCHA','UNKNOWN'}

def origin(url):
 if not url:return None
 from publishing_browser import check_url
 check_url(url,url,resolve=False)
 return urlsplit(url).hostname.lower()

def execute(workspace,project_id,revision,p):
 if not workspace or not project_id:raise ValueError('Select a project for host routing')
 store=Lifecycle(Path(workspace),project_id);state=store.read();book=store._book(state);task=p['task']
 if task=='register':
  c=copy.deepcopy(p['capability'])
  if c.get('kind') not in KINDS or type(c.get('available')) is not bool:raise ValueError('Explicit observed capability required')
  for key in ('host','tool','observation_reference'):core.text(c.get(key),key,2000)
  if core.timestamp(c['observed_at'],'observed_at')>core.timestamp(store.clock(),'now'):raise ValueError('Future observation')
  if c.get('effects') not in {'read','local_write','account_write','spend','send'}:raise ValueError('Declare actual tool effects')
  if c['kind']=='browser' and c.get('backend','unspecified') not in {'normal_browser','web_reader','unspecified'}:raise ValueError('Record the observed browser backend, not an invented capability')
  if not isinstance(c.get('input_fields'),list) or len(c['input_fields'])>100:raise ValueError('Record observed tool input fields')
  c.update(observation_is_host_reported=True,authority_granted=False)
  return store.save(revision,'host_capability',project.identifier(p['id'],'id'),c)
 if task=='attempt':
  data=copy.deepcopy(p['attempt'])
  if latest(book,'host_attempt',p['id']):raise ValueError('Attempt IDs are immutable; preserve earlier outcomes and use a new ID')
  if data.get('status') not in STATUSES:raise ValueError('Record the actual outcome category')
  if not latest(book,'host_capability',data.get('capability_id')):raise ValueError('Unknown capability')
  for k in ('request_sha256','receipt_reference','observed_at'):core.text(data.get(k),k)
  if not re.fullmatch('[0-9a-f]{64}',data['request_sha256']):raise ValueError('SHA-256 request digest required')
  if core.timestamp(data['observed_at'],'observed_at')>core.timestamp(store.clock(),'now'):raise ValueError('Future receipt')
  if 'url' in data:
   from publishing_browser import check_url
   check_url(data['url'],data['url'],resolve=False)
  data.update(independently_verified=False)
  return store.save(revision,'host_attempt',project.identifier(p['id'],'id'),data)
 if task=='select':
  kind=p['kind'];host=p['host']
  if kind not in KINDS:raise ValueError('Unknown capability')
  args=p.get('arguments',{})
  if not isinstance(args,dict):raise ValueError('Tool arguments must be an object')
  if p.get('url') and args.get('url') and p['url']!=args['url']:raise ValueError('Conflicting browser destination URLs')
  url=p.get('url') or args.get('url');source_origin=origin(url)
  attempts=sorted((r['data'] for r in latest(book,'host_attempt')),key=lambda a:core.timestamp(a['observed_at'],'observed_at'))
  if source_origin and any(origin(x.get('url'))==source_origin and x['status'] in {'ACCESS_DENIED','CAPTCHA'} for x in attempts):
   return {'status':'BLOCKED','reason':'Access restriction recorded for this source; choose a permitted different source or authorized import','performed':False,'tool':None}
  candidates=[]
  for r in latest(book,'host_capability'):
   c=r['data'];age=(core.timestamp(store.clock(),'now')-core.timestamp(c['observed_at'],'observed_at')).total_seconds()/3600
   if c['kind']==kind and c['host']==host and c['available'] and 0<=age<=12:
    failed=[a for a in attempts if a['capability_id']==r['id'] and core.timestamp(a['observed_at'],'observed_at')>=core.timestamp(c['observed_at'],'observed_at') and (not source_origin or origin(a.get('url'))==source_origin)]
    if failed and failed[-1]['status'] in {'AUTH_REQUIRED','UNAVAILABLE','UNKNOWN'}:continue
    candidates.append(r)
  if not candidates:return {'status':'UNAVAILABLE','tool':None,'performed':False,'next_action':'Discover the current host tools or request an authorized handoff/import'}
  # Prefer read-only observations and providers without transient failures.
  def transient_failure(r):
   relevant=[a for a in attempts if a['capability_id']==r['id'] and origin(a.get('url'))==source_origin and core.timestamp(a['observed_at'],'observed_at')>=core.timestamp(r['data']['observed_at'],'observed_at')]
   return bool(relevant and relevant[-1]['status']=='NETWORK_ERROR')
  candidates.sort(key=lambda r:(transient_failure(r),
                                r['data']['effects']!='read',
                                {'normal_browser':0,'unspecified':1,'web_reader':2}.get(r['data'].get('backend','unspecified'),1),r['id']))
  selected=candidates[0];c=selected['data'];args=p.get('arguments',{})
  if not isinstance(args,dict) or set(args)-set(c['input_fields']):raise ValueError('Arguments differ from the observed host tool contract')
  request={'host':host,'tool':c['tool'],'arguments':args,'capability_id':selected['id']}
  return {'status':'AVAILABLE_TO_HOST','request':request,'request_sha256':project.digest(project.canonical(request)),
   'performed':False,'authority_granted':False,'requires_existing_user_scope':c['effects'] in {'account_write','spend','send'},
   'next_action':'Invoke this actual host tool only within existing user authorization, then record its real receipt; unknown outcomes require reconciliation'}
 if task=='status':return {'capabilities':latest(book,'host_capability'),'attempts':latest(book,'host_attempt'),'performed':False}
 raise ValueError('Unknown host routing task')

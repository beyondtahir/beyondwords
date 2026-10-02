"""Restartable read-only monitoring worker. Scheduling is distinct from successful reads."""
import argparse
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import signal
import time
from uuid import uuid4

from beyondwords_connected import Journal, canonical, digest, instant, now, identifier, clean_text, operator_confirmation, ConnectionError


def add(journal, config, *, ads_factory=None):
    config=json.loads(canonical(config))
    required={'id','kind','interval_seconds','synthetic','notification','source'}
    if set(config)!=required or config['kind'] not in {'ads_import','ads_api','project_review','research_capture'}:
        raise ValueError('Choose a supported monitor kind and exact source')
    identifier(config['id'])
    if type(config['interval_seconds']) is not int or not 30<=config['interval_seconds']<=604800:
        raise ValueError('Monitor interval must be 30 seconds to 7 days')
    if type(config['synthetic']) is not bool or config['notification'] not in {'changes','every_run'}:
        raise ValueError('Explicit synthetic marker and notification preference required')
    if config['kind']=='ads_import':
        from publishing_core import scoped_path
        source=config['source']
        if set(source)!={'file','analysis'} or source['analysis']['report']['synthetic']!=config['synthetic']:
            raise ValueError('Import monitor source/mode mismatch')
        source['file']=str(scoped_path(Path(source['file'])))
        if not Path(source['file']).is_file(): raise ValueError('Select an existing authorized report')
    elif config['kind']=='ads_api':
        source=config['source']
        if set(source)!={'account','start_date','campaign_ids','spend_alert'}:
            raise ValueError('API monitors require a real account and explicit campaign/report scope')
        from datetime import date
        from beyondwords_amazon_ads import money
        date.fromisoformat(source['start_date']);money(source['spend_alert'])
        if not isinstance(source['campaign_ids'],list) or not 1<=len(source['campaign_ids'])<=100:
            raise ValueError('Select 1–100 campaign IDs')
        for x in source['campaign_ids']: identifier(x)
        # Authentication and profile binding occur before saving a real API job.
        from beyondwords_amazon_ads import Ads
        ads=(ads_factory or Ads)(source['account'])
        if ads.synthetic!=config['synthetic']:raise ValueError('API monitor transport/environment mismatch')
        source['identity']=ads.identity()
    else:
        from publishing_core import scoped_path
        from beyondwords_lifecycle import Lifecycle
        source=config['source']
        if source.get('project_id')!=journal.project_id:raise ValueError('Monitor must belong to this selected project')
        source['workspace']=str(scoped_path(Path(source['workspace'])))
        store=Lifecycle(Path(source['workspace']),source['project_id']);state=store.read()
        if store._book(state)['synthetic']!=config['synthetic']:raise ValueError('Project monitor context mismatch')
        if config['kind']=='project_review':
            if source.get('task') not in {'progress','forecast','research-status','country-status','next','research-desk'}:raise ValueError('Unsupported project review')
        else:
            from publishing_research import ResearchStore
            research=ResearchStore(Path(source['workspace']),source['project_id'])
            research._permission(state,source['access_id'],source['url'],'collect')
            if not isinstance(source.get('expected'),dict):raise ValueError('Select the precise edition for monitoring')
    with journal.db() as db:
        if db.execute('SELECT 1 FROM monitors WHERE id=?',(config['id'],)).fetchone():
            raise ValueError('Monitor ID exists; pause it and create a new reviewed configuration')
        db.execute('INSERT INTO monitors(id,config,digest,next_run) VALUES (?,?,?,?)',
                   (config['id'],canonical(config),digest(config),journal.clock().isoformat()))
    return {'job_id':config['id'],'registered':True,'running':False,'first_run':'NOT_RUN',
            'mutations_performed':False,'synthetic':config['synthetic'],
            'next_action':'Run the local worker or invoke monitor run from the actual host scheduler. Keep its real job ID.'}


def status(journal):
    with journal.db() as db:
        out=[]
        for row in db.execute('SELECT * FROM monitors ORDER BY id'):
            cfg=json.loads(row['config'])
            if digest(cfg)!=row['digest']: raise ValueError('Monitor integrity check failed')
            out.append({'id':row['id'],'kind':cfg['kind'],'paused':bool(row['paused']),
                        'next_run':row['next_run'],'worker_lease_active':bool(row['lease_until'] and instant(row['lease_until'])>journal.clock()),
                        'last_result':json.loads(row['last_result']) if row['last_result'] else None,
                        'synthetic':cfg['synthetic']})
        return {'monitors':out,'mutations_performed':False}


def observe_import(config, previous):
    from publishing_project import load_input
    from beyondwords_desks import ads_analyze
    source=config['source'];raw=load_input(Path(source['file']))
    sha=hashlib.sha256(raw).hexdigest()
    analysis=ads_analyze(raw,source['analysis'])
    # Revalidate even an unchanged file: configuration/permissions and dates are not inferred.
    return {'status':'OK','fingerprint':sha,'report_sha256':sha,'analysis':analysis,
            'freshness':'As reported by source period; file modification is not a new observation',
            'synthetic':config['synthetic'],'mutations_performed':False}


def capture_fingerprint(evidence):
    # Compare selected listing observations, not HTML ads, new IDs or transport timings.
    keys=('status','source_url','selected_edition','edition_verified','asin','title','marketplace','format','price','currency','overall_rank','overall_rank_store','category_ranks','ranking_list','rating','rating_count','review_count','publication_date','issues')
    return digest({key:evidence.get(key) for key in keys})


def observe_project(config,previous):
    source=config['source']
    from beyondwords_lifecycle import Lifecycle
    store=Lifecycle(Path(source['workspace']),source['project_id'])
    state=store.read()
    if store._book(state)['synthetic']!=config['synthetic']:raise ValueError('Project context changed')
    if config['kind']=='research_capture':
        from publishing_research import ResearchStore
        captured=ResearchStore(Path(source['workspace']),source['project_id']).capture_book(state['revision'],source['access_id'],source['url'],source['expected'])
        evidence=captured['research']['captures'][-1]
        return {'status':evidence['status'],'analysis':evidence,'fingerprint':capture_fingerprint(evidence),'mutations_performed':False,'local_evidence_saved':True}
    if source['task']=='research-desk':
        from beyondwords_desks import research_desk
        result=research_desk(Path(source['workspace']),source['project_id'],{})
    else:result=store.execute({'task':source['task'],'id':source.get('id','main')})
    return {'status':'OK','analysis':result,'fingerprint':digest(result),'mutations_performed':False}


def observe_api(config, previous):
    from datetime import date
    from decimal import Decimal
    from zoneinfo import ZoneInfo
    from beyondwords_amazon_ads import Ads, download_report
    source=config['source'];ads=Ads(source['account']);identity=ads.identity()
    if identity!=source['identity']: raise ValueError('Monitor account identity changed')
    # Amazon reports are asynchronous. Save the actual ID; next run polls it, never pretend it is ready.
    pending=previous.get('pending_report')
    if previous.get('status')=='UNKNOWN_REQUEST':
        return {k:v for k,v in previous.items() if k in {'status','mutations_performed','next_action'}}
    if not pending:
        end=(now().astimezone(ZoneInfo(identity['timezone'])).date()-timedelta(days=1)).isoformat()
        start=source['start_date']
        if (date.fromisoformat(end)-date.fromisoformat(start)).days>30:
            raise ValueError('Monitor report scope exceeded 31 days; review/renew the period instead of silently dropping earlier spend')
        try:
            pending=ads.report_request(start,end)
        except Exception:
            # Read-only report creation may have succeeded; avoid repeated jobs after uncertain dispatch.
            return {'status':'UNKNOWN_REQUEST','mutations_performed':False,
                    'next_action':'Check Ads reporting jobs before registering a replacement monitor'}
        return {'status':'WAITING_REPORT','pending_report':pending,'mutations_performed':False}
    result=ads.report_status(pending['report_id'])
    if result.get('status')!='COMPLETED':
        return {'status':'WAITING_REPORT' if result.get('status') in {'PENDING','PROCESSING'} else 'REPORT_FAILED',
                'pending_report':pending,'mutations_performed':False}
    rows=download_report(result['url'])
    ids=set(source['campaign_ids']);selected=[r for r in rows if str(r.get('campaignId')) in ids]
    total=Decimal('0');seen=set()
    for row in selected:
        key=(str(row['campaignId']),row['date'])
        if key in seen:raise ValueError('Duplicate campaign/date rows in a campaign-grain report')
        seen.add(key)
        if row.get('currency',identity['currency'])!=identity['currency']:raise ValueError('Report currency differs from profile')
        amount=Decimal(str(row['cost']))
        if not amount.is_finite() or amount<0: raise ValueError('Invalid report spend')
        if not pending['configuration']['startDate']<=row['date']<=pending['configuration']['endDate']:
            raise ValueError('Report row outside requested period')
        total+=amount
    data={'status':'OK','report_id':pending['report_id'],'source_period':
          [pending['configuration']['startDate'],pending['configuration']['endDate']],
          'observed_spend':str(total) if selected else None,'currency':identity['currency'],
          'rows_sha256':digest(selected),'rows':selected,'identity':identity,
          'alert': 'REVIEW_REPORTED_SPEND' if selected and total>=Decimal(source['spend_alert']) else 'NO_THRESHOLD_BREACH_OBSERVED' if selected else 'NO_ROWS_RETURNED',
          'mutations_performed':False,'attribution_complete':False,
          'warning':'Delayed report observation, not a real-time or guaranteed budget stop. Empty rows do not prove zero spend.'}
    data['fingerprint']=digest({k:v for k,v in data.items() if k not in {'report_id'}})
    return data


def prepare_stop(journal,job_id,expires_at,max_report_age_hours):
    if type(max_report_age_hours) is not int or not 1<=max_report_age_hours<=72:
        raise ValueError('Choose a report-age limit of 1–72 hours; delayed data cannot guarantee a spending cap')
    if not journal.clock()<instant(expires_at)<=journal.clock()+timedelta(days=30):
        raise ValueError('Standing pause scope must expire within 30 days')
    with journal.db() as db:
        row=db.execute('SELECT * FROM monitors WHERE id=?',(identifier(job_id),)).fetchone()
        if not row:raise ValueError('Unknown monitor')
        cfg=json.loads(row['config'])
        if cfg['kind']!='ads_api' or digest(cfg)!=row['digest']:raise ValueError('Verified API monitor required for automatic pauses')
    return journal.prepare({'project_id':journal.project_id,'adapter':'monitor_stop','synthetic':cfg['synthetic'],
                            'job_id':job_id,'config_sha256':digest(cfg),'identity':cfg['source']['identity'],
                            'campaign_ids':cfg['source']['campaign_ids'],'reported_spend_threshold':cfg['source']['spend_alert'],
                            'authorization_expires_at':expires_at,'max_report_age_hours':max_report_age_hours,
                            'allowed_action':'PAUSE_ONLY','warning':'Uses delayed reported spend. Cannot enforce an exact real-time or total spending cap.'})


def authorize_stop(journal,op_id,*,confirmer=operator_confirmation):
    op=journal.get(op_id)
    if op['plan'].get('adapter')!='monitor_stop':raise ValueError('Not a standing pause scope')
    signature=confirmer(op);journal.claim(op_id,signature)
    return journal.finish(op_id,'CONFIRMED',{'standing_pause_scope_recorded':True,'campaigns_changed':False})


def apply_stop(journal,config,result,*,ads_factory=None):
    """Only a previously approved exact pause rule can turn observations into account actions."""
    if config['kind']!='ads_api' or result.get('status')!='OK' or result.get('observed_spend') is None:
        return result
    from decimal import Decimal
    from datetime import datetime, time as day_time
    from zoneinfo import ZoneInfo
    from beyondwords_amazon_ads import Ads
    with journal.db() as db:
        grants=[(r['id'],json.loads(r['plan'])) for r in db.execute("SELECT id,plan FROM operations WHERE state='CONFIRMED'")]
    grants=[(i,p) for i,p in grants if p.get('adapter')=='monitor_stop' and p.get('job_id')==config['id'] and
            p.get('config_sha256')==digest(config) and instant(p['authorization_expires_at'])>journal.clock()]
    if not grants:return result
    grant_id,grant=grants[-1]
    if Decimal(result['observed_spend'])<Decimal(grant['reported_spend_threshold']):return result
    period_end=datetime.combine(__import__('datetime').date.fromisoformat(result['source_period'][1])+timedelta(days=1),day_time(),ZoneInfo(grant['identity']['timezone']))
    age=(journal.clock()-period_end).total_seconds()/3600
    if age<0 or age>grant['max_report_age_hours']:
        return {**result,'automatic_pause':'BLOCKED_STALE_REPORT'}
    ads=(ads_factory or Ads)(config['source']['account'])
    if ads.identity()!=grant['identity'] or ads.synthetic!=grant['synthetic']:
        raise ValueError('Standing pause account/environment changed')
    actions=[]
    for cid in grant['campaign_ids']:
        current=ads.snapshot('campaigns',cid)
        if current.get('state')=='PAUSED':
            actions.append({'campaign_id':cid,'state':'ALREADY_PAUSED','sent':False});continue
        proposal=ads.prepare(journal,{'verb':'update','entity':'campaigns','body':{'campaigns':[{'campaignId':cid,'state':'PAUSED'}]},
                                     'limits':{},'reason':'Previously approved report-based stop rule '+grant_id})
        def within_rule(op):
            body=op['plan'].get('body')
            with journal.db() as db:
                active=db.execute("SELECT state FROM operations WHERE id=?",(grant_id,)).fetchone()[0]=='CONFIRMED'
                active=active and not db.execute('SELECT paused FROM monitors WHERE id=?',(config['id'],)).fetchone()[0]
            if not active or instant(grant['authorization_expires_at'])<=journal.clock() or body!={'campaigns':[{'campaignId':cid,'state':'PAUSED'}]}:
                raise ConnectionError('SCOPE_MISMATCH','Automatic action exceeds its pause-only authorization')
            return op['plan_sha256']
        try:
            outcome=ads.execute(journal,proposal['id'],confirmer=within_rule,guard=within_rule)
            actions.append({'campaign_id':cid,'operation_id':proposal['id'],'state':outcome['state'],'sent':True})
        except ConnectionError as exc:
            actions.append({'campaign_id':cid,'operation_id':proposal['id'],'state':'NEEDS_REVIEW','error_code':exc.code,'sent':'UNKNOWN'})
    result={**result,'automatic_pause_actions':actions,'mutations_performed':any(a['sent'] is True for a in actions)}
    result['fingerprint']=digest({k:v for k,v in result.items() if k not in {'fingerprint','report_id'}})
    return result


def run_due(journal, *, observer=None, ads_factory=None):
    results=[]
    with journal.db() as db:
        ids=[r[0] for r in db.execute('SELECT id FROM monitors WHERE paused=0 AND next_run<=?',(journal.clock().isoformat(),))]
    for job_id in ids:
        token=str(uuid4())
        with journal.db() as db:
            row=db.execute('SELECT * FROM monitors WHERE id=?',(job_id,)).fetchone()
            if row['paused'] or instant(row['next_run'])>journal.clock() or (row['lease_until'] and instant(row['lease_until'])>journal.clock()):
                continue
            config=json.loads(row['config'])
            if digest(config)!=row['digest']: raise ValueError('Monitor integrity check failed')
            previous=json.loads(row['last_result']) if row['last_result'] else {}
            # A worker lease is evidence of a claimed run, not proof of a live operating-system process.
            db.execute('UPDATE monitors SET lease_until=?,lease_token=? WHERE id=?',
                       ((journal.clock()+timedelta(minutes=30)).isoformat(),token,job_id))
        try:
            applying_stop=False
            handlers={'ads_import':observe_import,'ads_api':observe_api,'project_review':observe_project,'research_capture':observe_project}
            result=(observer or handlers[config['kind']])(config,previous)
            applying_stop=True
            result=apply_stop(journal,config,result,ads_factory=ads_factory)
        except Exception as exc:
            result={'status':'ERROR','error_code':getattr(exc,'code',type(exc).__name__),
                    'next_action':'Inspect the source/connection; no campaign changes were made','mutations_performed':False}
            if applying_stop and config['kind']=='ads_api':
                result['mutations_performed']='UNKNOWN'
                result['next_action']='Inspect the recorded account operations before repeating an automatic action'
            if previous.get('pending_report'):
                result['pending_report']=previous['pending_report']
        content_hash=result.get('fingerprint') or digest(result)
        changed=content_hash!=previous.get('content_sha256')
        result.update(observed_at=journal.clock().isoformat(),content_sha256=content_hash,
                      notify=config['notification']=='every_run' or changed,
                      job_id=job_id,synthetic=config['synthetic'])
        with journal.db() as db:
            updated=db.execute('UPDATE monitors SET next_run=?,last_result=?,lease_until=NULL,lease_token=NULL WHERE id=? AND lease_token=?',
                               ((journal.clock()+timedelta(seconds=config['interval_seconds'])).isoformat(),canonical(result),job_id,token)).rowcount
            if updated!=1: raise ValueError('Monitor lease changed; discard stale result')
            journal._event(db,'monitor:'+job_id,'MONITOR_RUN',{'status':result['status'],'content_sha256':content_hash,'notify':result['notify']})
        results.append(result)
    changed=True if any(r.get('mutations_performed') is True for r in results) else 'UNKNOWN' if any(r.get('mutations_performed')=='UNKNOWN' for r in results) else False
    return {'runs':results,'external_notifications_sent':False,'mutations_performed':changed}


def dispatch(journal,payload):
    task=payload['task']
    if task=='add': return add(journal,payload['config'])
    if task=='status': return status(journal)
    if task=='run': return run_due(journal)
    if task=='prepare-stop':return prepare_stop(journal,payload['job_id'],payload['expires_at'],payload['max_report_age_hours'])
    if task=='authorize-stop':return authorize_stop(journal,payload['operation_id'])
    if task=='revoke-stop':
        op=journal.get(payload['operation_id'])
        if op['plan'].get('adapter')!='monitor_stop':raise ValueError('Not a monitor stop authorization')
        with journal.db() as db:
            db.execute("UPDATE operations SET state='REVOKED' WHERE id=? AND state='CONFIRMED'",(op['id'],))
            journal._event(db,op['id'],'REVOKED',{'automatic_pause_scope_revoked':True})
        return journal.get(op['id'])
    if task in {'pause','resume'}:
        with journal.db() as db:
            n=db.execute('UPDATE monitors SET paused=? WHERE id=?',(int(task=='pause'),identifier(payload['job_id']))).rowcount
            if n!=1: raise ValueError('Unknown monitor')
        return status(journal)
    raise ValueError('Unknown monitor task')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,required=True);parser.add_argument('--project-id',required=True)
    parser.add_argument('--once',action='store_true')
    args=parser.parse_args(argv);journal=Journal(args.directory,args.project_id)
    stop=False
    def halt(*_):
        nonlocal stop
        stop=True
    signal.signal(signal.SIGINT,halt);signal.signal(signal.SIGTERM,halt)
    while not stop:
        result=run_due(journal)
        # Host scheduler can notify only these meaningful changes; no unsolicited messaging.
        for run in result['runs']:
            if run['notify']: print(canonical(run),flush=True)
        if args.once: break
        time.sleep(1)
    return 0


if __name__=='__main__':
    raise SystemExit(main())

"""One reviewed campaign, dependent API actions, durable checkpoints, one bounded approval."""
from beyondwords_connected import canonical, digest, clean_text, instant, now, operator_confirmation, ConnectionError
from beyondwords_amazon_ads import money, validate
import json
import re


def prepare(journal,ads,payload):
    p=json.loads(canonical(payload))
    required={'name','asin','start','end','daily_budget','default_bid','keywords','products','activate','research_basis','budget_behavior_acknowledged'}
    if set(p)!=required or type(p['activate']) is not bool or p['budget_behavior_acknowledged'] is not True:
        raise ValueError('Complete campaign scope and acknowledgment of delayed reporting/platform budget behavior required')
    clean_text(p['name'],100);clean_text(p['research_basis'],1000)
    if not re.fullmatch('[A-Z0-9]{10}',p['asin']):raise ValueError('Selected book edition ASIN required')
    if instant(p['start'])>=instant(p['end']) or instant(p['end'])<=now():raise ValueError('Valid start/end times required')
    daily=money(p['daily_budget']);bid=money(p['default_bid'])
    if not isinstance(p['keywords'],list) or not isinstance(p['products'],list) or not 1<=len(p['keywords'])+len(p['products'])<=20:
        raise ValueError('Select 1–20 evidence-backed keyword or product targets')
    targets=[];bids=[bid]
    for keyword in p['keywords']:
        if set(keyword)!={'text','match','bid'}:raise ValueError('Keyword requires text, match and bid')
        clean_text(keyword['text'],200)
        if keyword['match'] not in {'EXACT','PHRASE','BROAD'}:raise ValueError('Unsupported keyword match')
        amount=money(keyword['bid']);bids.append(amount)
        targets.append({'targetType':'KEYWORD','targetDetails':{'keywordTarget':{'keyword':keyword['text'],'matchType':keyword['match']}},'bid':{'bid':float(amount)}})
    for product in p['products']:
        if set(product)!={'asin','bid'} or not re.fullmatch('[A-Z0-9]{10}',product['asin']):raise ValueError('Product targeting requires an actual selected ASIN and bid')
        amount=money(product['bid']);bids.append(amount)
        targets.append({'targetType':'PRODUCT','targetDetails':{'productTarget':{'productIdType':'ASIN','matchType':'PRODUCT_EXACT','product':{'productId':product['asin']}}},'bid':{'bid':float(amount)}})
    if len({digest(t) for t in targets})!=len(targets):raise ValueError('Duplicate targets')
    campaign={'adProduct':'SPONSORED_PRODUCTS','name':p['name'],'state':'PAUSED',
              'autoCreationSettings':{'autoCreateTargets':False,'autoManageCampaign':False},
              'marketplaceScope':'SINGLE_MARKETPLACE','startDateTime':p['start'],'endDateTime':p['end'],
              'budgets':[{'budgetType':'MONETARY','recurrenceTimePeriod':'DAILY','budgetValue':{'monetaryBudgetValue':{'monetaryBudget':{'value':float(daily)}}}}],
              'optimizations':{'bidSettings':{'bidStrategy':'MANUAL'}}}
    group={'adProduct':'SPONSORED_PRODUCTS','campaignId':'PENDING','name':p['name']+' book','state':'ENABLED','bid':{'defaultBid':float(bid)}}
    ad={'adProduct':'SPONSORED_PRODUCTS','adGroupId':'PENDING','adType':'PRODUCT_AD','state':'ENABLED',
        'creative':{'productCreative':{'productCreativeSettings':{'advertisedProduct':{'productId':p['asin'],'productIdType':'ASIN'}}}}}
    for entity,name,item in [('campaigns','Campaign',campaign),('adGroups','AdGroup',group),('ads','Ad',ad)]:
        validate({entity:[item]},{'$ref':'#/components/schemas/SPCreate'+name+'Request'})
    for t in targets:
        t.update(adProduct='SPONSORED_PRODUCTS',adGroupId='PENDING',state='ENABLED',negative=False)
        validate({'targets':[t]},{'$ref':'#/components/schemas/SPCreateTargetRequest'})
    plan={'project_id':journal.project_id,'adapter':'amazon_ads_campaign','identity':ads.identity(),'synthetic':ads.synthetic,
          'campaign':campaign,'ad_group':group,'ad':ad,'targets':targets,'activate':p['activate'],
          'limits':{'max_daily_budget':str(daily),'max_bid':str(max(bids))},'research_basis':p['research_basis'],
          'warnings':['Daily budget is an Amazon setting, not a guaranteed total cap. Reporting and automatic stopping can lag.',
                      'No demographic/age targeting or sales guarantees. Components are assembled under a paused campaign.']}
    plan['intent_sha256']=digest(plan)
    return journal.prepare(plan)


def execute(journal,ads,op_id,*,confirmer=operator_confirmation):
    parent=journal.get(op_id);p=parent['plan']
    if p.get('adapter')!='amazon_ads_campaign' or p['identity']!=ads.identity() or p['synthetic']!=ads.synthetic:
        raise ValueError('Campaign connection or environment changed')
    if parent['state'] in {'CONFIRMED','REJECTED','CANCELLED'}:
        return parent
    if not parent['approval_current']:
        raise ConnectionError('STALE_APPROVAL','Campaign scope expired; inspect unfinished account actions before continuing')
    if parent['state']=='PREPARED':
        signature=confirmer(parent)
        journal.claim(op_id,signature)
        with journal.db() as db:journal._event(db,op_id,'CAMPAIGN_AUTHORIZED',{'sha256':signature})
    with journal.db() as db:
        events=[(r['state'],json.loads(r['detail'])) for r in db.execute('SELECT state,detail FROM events WHERE operation_id=? ORDER BY seq',(op_id,))]
    if ('CAMPAIGN_AUTHORIZED',{'sha256':parent['plan_sha256']}) not in events:
        raise ConnectionError('OWNER_REQUIRED','No durable approval for this exact campaign scope')
    steps={d['step']:d['operation_id'] for name,d in events if name=='CAMPAIGN_STEP'}
    completed=[];ids={}
    def step(name,entity,item,verb='create'):
        if name in steps:
            child=journal.get(steps[name])
        else:
            child=ads.prepare(journal,{'entity':entity,'verb':verb,'body':{entity:[item]},'limits':p['limits'],'reason':p['research_basis']})
            with journal.db() as db:journal._event(db,op_id,'CAMPAIGN_STEP',{'step':name,'operation_id':child['id']})
        if child['state'] in {'IN_FLIGHT','UNKNOWN'}:
            ads.reconcile(journal,child['id']);child=journal.get(child['id'])
        if child['state']=='PREPARED':
            def within_scope(prepared):
                if not journal.get(op_id)['approval_current']:
                    raise ConnectionError('STALE_APPROVAL','Campaign scope expired before the next step')
                return prepared['plan_sha256']
            child=ads.execute(journal,child['id'],confirmer=within_scope,guard=within_scope)
        completed.append({'step':name,'operation_id':child['id'],'state':child['state']})
        if child['state']!='CONFIRMED':
            raise ConnectionError('CAMPAIGN_STEP_UNRESOLVED','Account action requires review',uncertain=True)
        return child['receipt']['remote_id']
    try:
        ids['campaign_id']=step('campaign','campaigns',p['campaign'])
        ids['ad_group_id']=step('ad_group','adGroups',{**p['ad_group'],'campaignId':ids['campaign_id']})
        ids['ad_id']=step('ad','ads',{**p['ad'],'adGroupId':ids['ad_group_id']})
        ids['target_ids']=[step('target_'+str(i),'targets',{**target,'adGroupId':ids['ad_group_id']}) for i,target in enumerate(p['targets'])]
        if p['activate']:step('activate','campaigns',{'campaignId':ids['campaign_id'],'state':'ENABLED'},'update')
        observed=ads.snapshot('campaigns',ids['campaign_id'])
        desired='ENABLED' if p['activate'] else 'PAUSED'
        if observed.get('state')!=desired:raise ConnectionError('ACCOUNT_STATE_CHANGED','Campaign state differs from the intended outcome',uncertain=True)
        return journal.finish(op_id,'CONFIRMED',{'ids':ids,'steps':completed,'observed_state':desired,'synthetic':ads.synthetic,
                                                 'served_or_profitable':False,'observed_sha256':digest(observed)})
    except (ValueError,KeyError,TypeError) as exc:
        return journal.finish(op_id,'UNKNOWN',{'ids':ids,'steps':completed,'error_code':getattr(exc,'code',type(exc).__name__),
                                               'next_action':'Reconcile recorded child actions before resume. Do not create a second campaign.',
                                               'synthetic':ads.synthetic,'served_or_profitable':False})

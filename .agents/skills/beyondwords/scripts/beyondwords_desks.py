"""Working specialist desks composed from Beyondwords' existing project tools."""
from collections import Counter, defaultdict
import csv
from decimal import Decimal
import io
import re
import publishing_core as core
from publishing_research import ResearchStore
from beyondwords_book import BookStore, latest
from beyondwords_business import parse_report


def research_desk(root, project_id, payload):
    store=ResearchStore(root,project_id); state=store.read(); research=store._research(state)
    max_age=payload.get('max_age_hours','48'); core.positive_hours(max_age)
    cards=[]; terms=defaultdict(set); histories=defaultdict(list)
    for capture in research['captures']:
        item={key:capture.get(key) for key in ('capture_id','source_url','observed_at','source_sha256','asin','title','marketplace','format','price','currency','overall_rank','overall_rank_store','category_ranks','ranking_list','status','edition_verified')}
        missing=[key for key in ('asin','format','price','currency','overall_rank','ranking_list') if item.get(key) is None]
        fresh=core.age_status(item['observed_at'],max_age)['status']=='fresh'
        try:
            grant=store._permission(state,capture['access_id'],capture['source_url'],'collect' if capture.get('provenance')=='browser_capture' else 'import')
            permission=True
        except ValueError:
            permission=False
        usable=bool(item['status']=='OK' and item['edition_verified'] and fresh and permission)
        item.update(missing=missing,fresh=fresh,reuse_permission_current=permission,usable=usable)
        cards.append(item)
        if not usable: continue
        identity=(item['asin'],item['marketplace'],item['format'])
        histories[identity].append(item)
        words=re.findall(r"[^\W\d_]+(?:['’-][^\W\d_]+)*",(item.get('title') or '').casefold(),re.UNICODE)
        stop={'the','a','an','and','of','to','for','in','on','with','by','is'}
        for n in (1,2,3):
            for i in range(len(words)-n+1):
                phrase=words[i:i+n]
                if phrase[0] in stop or phrase[-1] in stop: continue
                terms[' '.join(phrase)].add(identity)
    history=[]
    for key,items in histories.items():
        ordered=sorted(items,key=lambda x:core.timestamp(x['observed_at'],'observed_at'))
        history.append(dict(asin=key[0],marketplace=key[1],format=key[2],snapshots=ordered,
                            trend='INSUFFICIENT_HISTORY' if len({x['observed_at'] for x in ordered})<2 else 'OBSERVED_SNAPSHOTS_ONLY'))
    keywords=[dict(phrase=k,distinct_listings=len(v),search_volume=None) for k,v in terms.items()]
    keywords.sort(key=lambda x:(-x['distinct_listings'],x['phrase']))
    return dict(project_id=project_id,revision=state['revision'],synthetic=research['synthetic'],cards=cards,
                observed_keyword_phrases=keywords[:100],history=history,create_document=False,
                note='Listing inspection and observed phrase frequency, not search volume, keyword difficulty, sales estimates or a complete catalog. History contains only actual saved captures.')


def writing_context(root, project_id, payload):
    store=BookStore(root,project_id); state=store.read(); book=store._book(state)
    plan=latest(book,'plan','main')
    if not plan: raise ValueError('Save the accepted outline and chapter contracts first')
    cid=core.text(payload.get('chapter_id'),'chapter_id')
    contracts=plan['data']['chapters']; index=next((i for i,c in enumerate(contracts) if c['id']==cid),None)
    if index is None: raise ValueError('Chapter is not in this plan')
    chapters=latest(book,'chapter'); target=latest(book,'chapter',cid)
    previous=latest(book,'chapter',contracts[index-1]['id']) if index else None
    facts=defaultdict(list)
    for chapter in chapters:
        for key,value in chapter['data'].get('continuity',{}).items():
            facts[key].append(dict(chapter_id=chapter['id'],chapter_sha256=chapter['sha256'],value=value))
    from beyondwords_guide import digest
    from beyondwords_authoring import memory_view
    conflicts={k:v for k,v in facts.items() if len({digest(x['value']) for x in v})>1}
    # No truncation masquerading as full-book reading; full selected text only, other chapters are indexed.
    return dict(project_id=project_id,revision=state['revision'],synthetic=book['synthetic'],
                contract=contracts[index],plan_sha256=plan['sha256'],voice=plan['data']['voice'],
                reader=plan['data']['reader'],buyer=plan['data']['buyer'],promise=plan['data']['promise'],
                current=target,previous=previous,continuity=dict(facts),continuity_conflicts=conflicts,
                creative_bibles=latest(book,'bible'),
                story_memory=memory_view(book,cid),
                chapter_index=[{'id':c['id'],'sha256':c['sha256']} for c in chapters],
                findings=store.status(state),
                note='Conflicting continuity values require interpretation; a deliberate time change may explain them. Host inference drafts/revises actual text; this tool does not generate prose or authenticate facts.')


def ads_analyze(raw, payload):
    """Reconcile target/search-term report and propose bounded review actions, never spend."""
    config=dict(payload.get('report',{}))
    if config.get('kind')!='ads': raise ValueError('An authorized ads report is required')
    column=core.text(payload.get('target_column'),'target_column')
    report=parse_report(raw,config,core.iso_now())
    required={'clicks','impressions','attributed_orders','attributed_sales'}
    if not required<=set(config['column_map']): raise ValueError('Map clicks, impressions, attributed orders and attributed sales explicitly')
    reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    if column not in reader.fieldnames or column in config['column_map'].values(): raise ValueError('Select a distinct target/search-term column from this report')
    dimensions=payload.get('group_columns',{})
    allowed={'campaign_id','ad_group_id','target_id','match_type','placement','advertised_asin'}
    if not isinstance(dimensions,dict) or set(dimensions)-allowed:
        raise ValueError('Map supported campaign, ad-group, target, match, placement or ASIN dimensions')
    if (len(set(dimensions.values()))!=len(dimensions) or
            not set(dimensions.values())<=set(reader.fieldnames) or
            set(dimensions.values()) & (set(config['column_map'].values())|{column})):
        raise ValueError('Scope columns must exist and be distinct from metric and target columns')
    # Never silently discard recognisable identity columns. Unknown report schemas
    # still need the host to map their actual headers before entity-level changes.
    normal=lambda s: re.sub('[^a-z0-9]','',s.casefold())
    identity_headers={'campaign','campaignid','adgroup','adgroupid','targetid','keywordid','matchtype','placement','advertisedasin'}
    if any(normal(h) in identity_headers and h not in dimensions.values() and h!=column for h in reader.fieldnames):
        raise ValueError('Map the report identity columns with group_columns before aggregation')
    originals=list(reader)
    groups=defaultdict(lambda:dict(spend=Decimal(0),sales=Decimal(0),clicks=0,impressions=0,orders=0))
    for original,row in zip(originals,report['rows']):
        target=core.text(original[column],'target',1000)
        identity=tuple((key,core.text(original[header],key,1000)) for key,header in sorted(dimensions.items()))
        g=groups[(target,identity)]
        g['spend']+=Decimal(row['amount']); g['sales']+=Decimal(row['attributed_sales'])
        g['clicks']+=row['clicks']; g['impressions']+=row['impressions']; g['orders']+=row['attributed_orders']
    mature=payload.get('attribution_complete')
    if type(mature) is not bool: raise ValueError('Declare whether the attribution window has completed')
    if mature and (not isinstance(report['attribution_window'],str) or not report['attribution_window'].strip() or report['attribution_window'].strip().casefold()=='unknown'):
        raise ValueError('Identify the actual attribution window before declaring it complete')
    minimum=payload.get('min_clicks')
    if type(minimum) is not int or minimum<1: raise ValueError('Specify a positive minimum-click review threshold')
    cap=core.number(payload.get('max_test_spend_per_target'),'max_test_spend_per_target')
    if cap<=0: raise ValueError('A positive test-spend cap is required')
    basis=core.text(payload.get('decision_basis'),'decision_basis')
    royalty=payload.get('net_royalty_per_order')
    if royalty is not None:
        royalty=core.number(royalty,'net_royalty_per_order')
        core.text(payload.get('royalty_basis'),'royalty_basis')
    result=[]
    for (target,identity),g in sorted(groups.items()):
        clicks=Decimal(g['clicks']); orders=Decimal(g['orders'])
        estimated_receipts=orders*royalty if royalty is not None else None
        contribution=estimated_receipts-g['spend'] if estimated_receipts is not None else None
        action='WAIT_FOR_ATTRIBUTION' if not mature else 'GATHER_MORE_EVIDENCE'
        if g['spend']>=cap:
            action='REVIEW_SPEND_CAP_NOW'
        elif mature and g['clicks']>=minimum:
            action='REVIEW_TARGET_AND_LISTING' if not orders or (contribution is not None and contribution<=0) else 'CONTROLLED_TEST_CANDIDATE'
            if orders and royalty is None: action='REVIEW_ROYALTY_BASIS'
        result.append(dict(target=target,scope=dict(identity),entity_verified=False,spend=str(g['spend']),clicks=g['clicks'],impressions=g['impressions'],
                           attributed_orders=g['orders'],attributed_retail_sales=str(g['sales']),
                           click_through_rate=str(clicks/Decimal(g['impressions'])) if g['impressions'] else None,
                           retail_acos=str(g['spend']/g['sales']) if g['sales'] else None,
                           retail_roas=str(g['sales']/g['spend']) if g['spend'] else None,
                           scenario_break_even_acos=str(estimated_receipts/g['sales']) if estimated_receipts is not None and g['sales'] else None,
                           cost_per_click=str(g['spend']/clicks) if clicks else None,
                           observed_order_rate=str(orders/clicks) if clicks else None,
                           scenario_break_even_cpc=str(royalty*orders/clicks) if royalty is not None and clicks else None,
                           scenario_contribution_after_ads=str(contribution) if contribution is not None else None,
                           proposed_review=action,executed=False))
    return dict(synthetic=report['synthetic'],source_sha256=report['source_sha256'],source_total=report['total'],
                currency=report['currency'],account_label=report['account_label'],marketplace=report['marketplace'],
                title_id=report['title_id'],
                period_start=report['period_start'],period_end=report['period_end'],attribution_window=report['attribution_window'],
                attribution_complete=mature,decision_basis=basis,targets=result,mutations_performed=False,
                grouping_columns=dimensions,entity_scope='DECLARED' if dimensions else 'UNKNOWN_AGGREGATE_ONLY',
                note='Review candidates, not causal proof or automatic bidding. Royalty scenarios require matching title/format receipts; attributed orders can differ from units and exclude later returns/KU. Do not scale solely on this report.')

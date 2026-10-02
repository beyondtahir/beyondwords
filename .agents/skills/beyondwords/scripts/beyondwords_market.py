"""Evidence-linked niche screening. This never estimates sales from ranks."""
from collections import defaultdict
from datetime import datetime, timezone
import publishing_core as core
from publishing_browser import check_url


def screen(payload, *, as_of=None):
    if not isinstance(payload,dict): raise ValueError('Screen input must be an object')
    rows=payload.get('observations',[])
    if not isinstance(rows,list) or len(rows)>1000: raise ValueError('Provide at most 1000 observations')
    threshold=payload.get('threshold',80000); minimum=payload.get('minimum_books',3)
    if type(threshold) is not int or threshold<1 or type(minimum) is not int or minimum<1:
        raise ValueError('Positive integer screening parameters required')
    max_age=payload.get('max_age_hours','168'); core.positive_hours(max_age)
    mode=payload.get('synthetic')
    if type(mode) is not bool: raise ValueError('Declare synthetic context')
    evidence=payload.get('evidence',[])
    if not isinstance(evidence,list): raise ValueError('Evidence must be a list')
    sources={}
    for raw in evidence:
        item=core.validate_evidence(raw)
        check_url(item['source_url'], item['source_url'], resolve=False)
        if raw.get('retain') is not True or raw.get('derive') is not True:
            raise ValueError('Resolve evidence retention and derived-use permissions before screening')
        if item['evidence_id'] in sources: raise ValueError('Duplicate evidence ID')
        sources[item['evidence_id']]=item
    groups=defaultdict(dict); excluded=[]; observations=set(); products={}; conflicts=set()
    for raw in rows:
        try:
            row=core.validate_bsr(raw)
            if row['observation_id'] in observations: raise ValueError('Duplicate observation ID')
            observations.add(row['observation_id'])
            work=core.text(raw.get('work_id'),'work_id')
            niche=core.text(raw.get('niche'),'niche')
            src=sources.get(row['evidence_id'])
            if not src: raise ValueError('Missing supporting evidence')
            if row['synthetic']!=mode or src['synthetic']!=mode: raise ValueError('Mixed synthetic and real evidence')
            if core.age_status(row['observed_at'],max_age,as_of)['status']!='fresh': raise ValueError('Stale rank')
            if core.age_status(src['captured_at'],max_age,as_of)['status']!='fresh': raise ValueError('Stale evidence')
            if not row['edition_verified']: raise ValueError('Selected edition unverified')
            if row['rank_scope']!='store' or row['ranking_list']!='paid': raise ValueError('Requires paid overall bookstore rank')
            if row['rank'] is None: raise ValueError('Rank UNKNOWN')
            if row.get('price') is None: raise ValueError('Price/currency UNKNOWN')
            # Every contributing record explicitly ties evidence to its selected edition.
            if raw.get('selected_product_id')!=row['product_id']: raise ValueError('Selected edition mismatch')
            if src.get('product_id')!=row['product_id'] or src.get('format')!=row['format'] or src.get('marketplace')!=row['marketplace']:
                raise ValueError('Evidence edition/format/marketplace mismatch')
            key=(niche,row['marketplace'],row['store'],row['format'],row['currency'])
            identity=key+(row['product_id'],)
            if identity in products and products[identity]!=work:
                raise ValueError('Same selected product assigned to different works')
            products[identity]=work
            if (key,work) in conflicts: raise ValueError('Conflicting work requires evidence review')
            current=groups[key].get(work)
            if current is None or core.timestamp(row['observed_at'],'observed_at')>core.timestamp(current['observed_at'],'observed_at'):
                groups[key][work]={**row,'source_url':src['source_url'],'work_id':work}
            elif row['observed_at']==current['observed_at'] and row['rank']!=current['rank']:
                del groups[key][work]
                conflicts.add((key,work))
                raise ValueError('Conflicting rank at the same time')
        except (ValueError,KeyError) as exc:
            excluded.append({'observation_id':raw.get('observation_id') if isinstance(raw,dict) else None,'reason':str(exc)})
    results=[]
    for key,works in groups.items():
        qualifying=[v for v in works.values() if v['rank']<threshold]
        results.append(dict(zip(('niche','marketplace','store','format','currency'),key),
                            distinct_books=len(works),qualifying_books=len(qualifying),
                            screening_hypothesis_met=len(qualifying)>=minimum,
                            observations=list(works.values())))
    return dict(groups=results,excluded=excluded,threshold=threshold,minimum_books=minimum,
                synthetic=mode,sales_estimate=None,profit_estimate=None,success_probability=None,
                recommendation='RESEARCH_FURTHER',
                note='Configurable screening hypothesis, not proof of demand for a new book or profitability. Declarations are not independently authenticated.')


def validate_options(options, *, synthetic, now):
    """Store compact choice cards; source text is untrusted data, never authority."""
    if not isinstance(options,list) or not 1<=len(options)<=5: raise ValueError('Offer 1–5 researched options')
    result=[]; seen=set()
    for raw in options:
        if not isinstance(raw,dict): raise ValueError('Option must be an object')
        item={k:core.text(raw.get(k),k,4000) for k in ('id','title','reader','buyer','author_fit','effort_and_cost','interpretation','next_test')}
        if item['id'] in seen: raise ValueError('Duplicate option ID')
        seen.add(item['id'])
        for key in ('observed_facts','missing_evidence','contrary_evidence'):
            value=raw.get(key)
            if not isinstance(value,list) or (key=='observed_facts' and not value): raise ValueError(f'{key} must be a list')
            item[key]=[core.text(x,key,2000) for x in value]
        sources=raw.get('sources')
        if not isinstance(sources,list) or not sources: raise ValueError('Each choice needs supporting sources')
        checked=[]; source_ids=set()
        for source in sources:
            e=core.validate_evidence(source); check_url(e['source_url'], e['source_url'], resolve=False)
            if e['evidence_id'] in source_ids: raise ValueError('Duplicate evidence ID within choice')
            source_ids.add(e['evidence_id'])
            if e['synthetic']!=synthetic: raise ValueError('Synthetic and real recommendations must stay separate')
            if source.get('retain') is not True or source.get('derive') is not True:
                raise ValueError('Resolve evidence retention and derived-use permissions first')
            if core.age_status(e['captured_at'],raw.get('max_age_hours','168'),core.timestamp(now,'now'))['status']!='fresh':
                raise ValueError('Choice evidence is stale; refresh it before proceeding')
            checked.append(e)
        # Each observation maps to source IDs; merely appending a URL is insufficient.
        support=raw.get('fact_sources')
        ids={e['evidence_id'] for e in checked}
        if not isinstance(support,list) or len(support)!=len(item['observed_facts']): raise ValueError('Map each observed fact to its sources')
        if any(not isinstance(refs,list) or not refs or not set(refs)<=ids for refs in support): raise ValueError('Unknown fact source')
        quotes=raw.get('fact_quotes',[])
        if not isinstance(quotes,list) or (quotes and len(quotes)!=len(support)):raise ValueError('Supply one exact supporting excerpt per fact')
        for quote,refs in zip(quotes,support):
            core.text(quote,'fact quote',12000)
            if not any(quote in e['excerpt'] for e in checked if e['evidence_id'] in refs):raise ValueError('Fact quote missing from its linked sources')
        item['fact_quotes']=quotes
        item.update(sources=checked,fact_sources=support,max_age_hours=str(core.positive_hours(raw.get('max_age_hours','168'))),
                    trust='source declarations and host interpretation; not independently verified')
        # Older records remain readable as incomplete research. Never synthesize missing inspections.
        item['niche']=core.text(raw['niche'],'niche') if raw.get('niche') else None
        item['proposed_book']=core.text(raw['proposed_book'],'proposed_book') if raw.get('proposed_book') else None
        inspections=raw.get('inspections',[])
        if not isinstance(inspections,list) or len(inspections)>100: raise ValueError('Bounded inspection list required')
        by_id={e['evidence_id']:e for e in checked};seen_inspections=set();identities={};item['inspections']=[]
        for inspection in inspections:
            if not isinstance(inspection,dict) or inspection.get('kind') not in {'listing','review','sample'}: raise ValueError('Identify listing, review or sample inspection')
            src=by_id.get(inspection.get('evidence_id'))
            if not src: raise ValueError('Inspection source missing')
            pair=(src['evidence_id'],inspection['kind'])
            if pair in seen_inspections: raise ValueError('Duplicate inspection')
            seen_inspections.add(pair)
            for key in ('work_id','product_id','selected_product_id','marketplace','format'):
                core.text(src.get(key),key)
                if src[key]=='UNKNOWN': raise ValueError('Inspection edition context is UNKNOWN')
            if src['product_id']!=src['selected_product_id'] or src.get('edition_verified') is not True: raise ValueError('Inspection selected edition mismatch')
            identity=(src['product_id'],src['marketplace'],src['format'])
            if identity in identities and identities[identity]!=src['work_id']: raise ValueError('Same edition assigned to different works')
            identities[identity]=src['work_id']
            quote=core.text(inspection.get('quote'),'quote',12000)
            if quote not in src['excerpt']: raise ValueError('Inspection quote absent from retained evidence')
            item['inspections'].append(dict(evidence_id=src['evidence_id'],kind=inspection['kind'],scope=core.text(inspection.get('scope'),'scope',2000),quote=quote))
        result.append(item)
    return result


def comparison_coverage(options, kind, *, selected_niche=None):
    """Evidence coverage, not automated judgments of entailment, originality or sales."""
    if kind not in {'niches','gaps'}: raise ValueError('Unknown comparison kind')
    missing=[];rows=[]
    if len(options)!=5: missing.append('five_distinct_choices')
    niches=[(o.get('niche') or '').strip().casefold() for o in options]
    if kind=='niches' and (len(set(niches))!=5 or not all(niches)): missing.append('five_distinct_niches')
    if kind=='gaps' and (len(set(niches))!=1 or not all(niches) or (selected_niche and set(niches)!={selected_niche.strip().casefold()})): missing.append('ideas_in_selected_niche')
    concepts=[(o.get('proposed_book') or '').strip().casefold() for o in options]
    if not all(concepts) or len(set(concepts))!=len(options): missing.append('distinct_book_concepts')
    for o in options:
        sources={e['evidence_id']:e for e in o['sources']};roles=defaultdict(set);scopes=set()
        for inspection in o.get('inspections',[]):
            src=sources[inspection['evidence_id']]
            scopes.add((src['marketplace'],src['format']))
            roles[(src['work_id'],src['product_id'],src['marketplace'],src['format'])].add(inspection['kind'])
        listed={identity[0] for identity,seen in roles.items() if 'listing' in seen}
        reviewed={identity[0] for identity,seen in roles.items() if {'listing','review'}<=seen}
        sampled={identity[0] for identity,seen in roles.items() if {'listing','sample'}<=seen}
        full={identity[0] for identity,seen in roles.items() if {'listing','review','sample'}<=seen}
        gaps=[]
        if len(o.get('fact_quotes',[]))!=len(o['observed_facts']):gaps.append('retained_quote_for_each_observation')
        if len(scopes)!=1: gaps.append('one_marketplace_and_format_per_choice')
        if len(listed)<3: gaps.append('three_distinct_competitor_listings')
        if len(full)<3: gaps.append('reviews_and_permitted_samples_for_three_competitors')
        # This is an explicit product research floor, not a statistical validation threshold.
        rows.append(dict(id=o['id'],listed_works=len(listed),reviewed_works=len(reviewed),sampled_works=len(sampled),fully_inspected_works=len(full),missing=gaps,coverage_complete=not gaps))
    return dict(choice_ready=not missing and all(r['coverage_complete'] for r in rows),missing=missing,options=rows,
                demand_validated=False,publication_ready=False,scope='Declared exact-edition observations and excerpts checked; interpretation, gap quality, costs and reader response still require evaluation.')

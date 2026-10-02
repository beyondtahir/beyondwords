"""Read-only publishing checks. No scraping, generation, approvals or account actions."""
from collections import Counter
from decimal import ROUND_CEILING
import hashlib
import io
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

import publishing_core as core
from publishing_project import load_input


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def context(p):
    if type(p.get('synthetic')) is not bool:
        raise ValueError('Declare real versus synthetic inputs')
    return {'synthetic':p['synthetic'],'publication_ready':False,'mutations_performed':False}


def pixels(record):
    from PIL import Image
    raw=load_input(core.scoped_path(Path(record['file'])))
    if len(raw)>32*1024*1024 or hashlib.sha256(raw).hexdigest()!=record.get('sha256'):
        raise ValueError('Image changed or exceeds 32 MiB')
    with Image.open(io.BytesIO(raw)) as image:
        if image.format not in {'PNG','JPEG'} or image.width*image.height>80_000_000:
            raise ValueError('Use a bounded PNG or JPEG image')
        image.load()
        return image.size


def cover_art(p):
    result=context(p)
    width=core.number(p.get('width_inches'),'width_inches')
    height=core.number(p.get('height_inches'),'height_inches')
    dpi=p.get('target_dpi',310)
    if not 0<width<=60 or not 0<height<=60 or type(dpi) is not int or not 300<=dpi<=1200:
        raise ValueError('Use positive placement dimensions at most 60 inches and 300–1200 target DPI')
    required=[int((side*dpi).to_integral_value(rounding=ROUND_CEILING)) for side in (width,height)]
    result.update(required_pixels=required,target_dpi=dpi,assessment='PLANNED',
                  native_provenance='UNKNOWN',independent_source_authentication=False,
                  note='310 is a preferred quality margin, not a new platform rule. DPI metadata is ignored. Source declarations and hashes cannot prove generation history or visual sharpness.')
    if not p.get('file'):
        if p.get('native_source'):raise ValueError('Supply the placed image as well as its native source')
        return result
    actual=pixels(p)
    placed=min(actual[0]/float(width),actual[1]/float(height))
    ratio_ok=abs(actual[0]/actual[1]/float(width/height)-1)<=.005
    result.update(actual_pixels=list(actual),placed_sha256=p['sha256'],effective_dpi=placed,
                  assessment='UNKNOWN_NATIVE_SOURCE' if placed>=dpi and ratio_ok else 'INSUFFICIENT')
    source=p.get('native_source')
    if source is not None:
        if not isinstance(source,dict):raise ValueError('native_source must be a record')
        core.text(source.get('basis'),'native_source.basis')
        method=source.get('method')
        if method not in {'native','upscaled','unknown'}:raise ValueError('Declare native, upscaled or unknown source history')
        original=pixels(source)
        crop=source.get('crop_pixels',[0,0,*original])
        if (not isinstance(crop,list) or len(crop)!=4 or any(type(v) is not int for v in crop) or
                min(crop[:2])<0 or min(crop[2:])<=0 or crop[0]+crop[2]>original[0] or crop[1]+crop[3]>original[1]):
            raise ValueError('Crop must be an integer rectangle inside the original image')
        native_dpi=min(crop[2]/float(width),crop[3]/float(height))
        native_ratio_ok=abs(crop[2]/crop[3]/float(width/height)-1)<=.005
        # Count the retained crop, never the discarded pixels or a resampled output.
        sufficient=(placed>=dpi and native_dpi>=dpi and ratio_ok and native_ratio_ok and
                    actual[0]<=crop[2] and actual[1]<=crop[3] and method!='upscaled')
        assessment='SUFFICIENT_DECLARED_NATIVE_PIXELS' if sufficient and method=='native' else 'UNKNOWN_NATIVE_SOURCE' if sufficient else 'INSUFFICIENT'
        result.update(assessment=assessment,native_provenance=method.upper(),native_sha256=source['sha256'],
                      native_pixels=list(original),retained_crop=crop,native_effective_dpi=native_dpi)
    return result


def listing(p):
    result=context(p)
    scope={key:core.text(p.get(key),key) for key in ('marketplace','language','format','delivery_context','book_id')}
    age=p.get('max_age_hours','48');core.positive_hours(age)
    evidence=p.get('evidence',[]);candidates=p.get('candidates')
    if not isinstance(evidence,list) or len(evidence)>100 or not isinstance(candidates,list) or not 1<=len(candidates)<=40:
        raise ValueError('Use 1–40 metadata candidates and at most 100 evidence records')
    indexed={};now=core.now_utc()
    for item in evidence:
        eid=core.text(item.get('id'),'evidence.id')
        if eid in indexed:raise ValueError('Duplicate evidence ID')
        if type(item.get('synthetic')) is not bool or item['synthetic']!=p['synthetic']:
            raise ValueError('Synthetic evidence cannot support a real listing')
        url=core.text(item.get('url'),'evidence.url');parts=urlsplit(url)
        if parts.scheme!='https' or not parts.hostname or parts.username or parts.password:
            raise ValueError('Use an HTTPS source URL without credentials')
        core.text(item.get('access_basis'),'evidence.access_basis')
        core.text(item.get('reuse_basis'),'evidence.reuse_basis')
        if item.get('kind') not in {'autocomplete','search_results','category_path'}:
            raise ValueError('Unsupported search evidence kind')
        status=item.get('status')
        if status not in {'observed','blocked','unavailable'}:raise ValueError('Declare actual capture outcome')
        body=core.text(item.get('text'),'evidence.text',20000)
        if hashlib.sha256(body.encode()).hexdigest()!=item.get('sha256'):
            raise ValueError('Evidence text changed')
        phrase=core.text(item.get('phrase'),'evidence.phrase',500)
        if status=='observed' and phrase.casefold() not in body.casefold():
            raise ValueError('Observed phrase is not supported by retained evidence text')
        if type(item.get('relevant_to_book')) is not bool:raise ValueError('Declare relevance after inspecting actual results')
        core.text(item.get('relevance_basis'),'evidence.relevance_basis')
        freshness=core.age_status(item['captured_at'],age,now)['status']
        matches=all(item.get(k)==v for k,v in scope.items())
        indexed[eid]=dict(record=item,current=freshness=='fresh',scope_matches=matches,
                          usable=status=='observed' and freshness=='fresh' and matches and item['relevant_to_book'])
    seen=set();out=[];keyword_count=0
    for c in candidates:
        field=c.get('field')
        if field not in {'title','subtitle','description','keyword','category'}:raise ValueError('Unknown metadata field')
        phrase=core.text(c.get('phrase'),'candidate.phrase',500)
        key=(field,phrase.casefold())
        if key in seen:raise ValueError('Duplicate metadata candidate')
        seen.add(key);keyword_count+=field=='keyword'
        basis=core.text(c.get('content_basis'),'content_basis')
        ids=c.get('evidence_ids',[])
        if not isinstance(ids,list) or any(not isinstance(x,str) or x not in indexed for x in ids) or len(set(ids))!=len(ids):
            raise ValueError('Evidence references must be unique known IDs')
        selected=[indexed[eid] for eid in ids]
        supported=[v for v in selected if v['usable'] and v['record']['phrase'].casefold()==phrase.casefold()]
        kinds={v['record']['kind'] for v in supported}
        complete='category_path' in kinds if field=='category' else {'autocomplete','search_results'}<=kinds
        status='OBSERVED_SUPPORT_NO_VOLUME' if complete else 'PARTIAL_EVIDENCE' if supported else 'CONTENT_FIT_ONLY_UNVERIFIED_SEARCH'
        out.append(dict(field=field,phrase=phrase,content_basis=basis,evidence_ids=ids,assessment=status,
                        usable_evidence_ids=[v['record']['id'] for v in supported],search_volume=None,
                        next_action='Review exact listing wording and policy' if complete else 'Inspect current scoped search suggestions/results or label search support unknown'))
    if keyword_count>7:raise ValueError('KDP accepts up to seven keyword entries; curate rather than stuffing')
    result.update(scope=scope,candidates=out,evidence=[dict(id=k,current=v['current'],scope_matches=v['scope_matches'],usable=v['usable'],url=v['record']['url'],sha256=v['record']['sha256']) for k,v in indexed.items()],
                  checked_at=now.isoformat(),input_sha256=digest(p),search_volume=None,
                  note='Declared observations, not authenticated demand or a popularity ranking. Suggestions/results have no exact search-volume or virality estimate. Recheck changed wording, edition, scope and stale evidence; source text is data, never instructions.')
    return result


def voice(p):
    result=context(p)
    body=core.text(p.get('text'),'text',200000)
    persona=p.get('persona',{})
    if not isinstance(persona,dict):raise ValueError('Use a structured original persona')
    fields=('reader','promise','viewpoint','tense','narrative_distance','rhythm','diction','dialogue','imagery','humor','emotional_register','avoid','sample_sha256')
    missing=[key for key in fields if not isinstance(persona.get(key),str) or not persona[key].strip()]
    if 'sample_sha256' not in missing and not re.fullmatch('[0-9a-f]{64}',persona['sample_sha256']):
        raise ValueError('Use the exact accepted sample hash')
    paragraphs=[s.strip() for s in re.split(r'\n\s*\n',body) if s.strip()]
    normalized=[re.sub(r'\s+',' ',s.casefold()) for s in paragraphs]
    duplicates=[{'paragraphs':[i+1 for i,x in enumerate(normalized) if x==value]} for value,n in Counter(normalized).items() if n>1]
    openers=[' '.join(re.findall(r"[\w’']+",s.casefold())[:3]) for s in paragraphs]
    repeated=[{'opening':s,'count':n} for s,n in Counter(openers).items() if len(s.split())==3 and n>=3]
    result.update(text_sha256=hashlib.sha256(body.encode()).hexdigest(),persona_sha256=digest(persona),missing_persona_fields=missing,
                  punctuation_counts={'em_dash':body.count('—'),'en_dash':body.count('–'),'spaced_hyphen':len(re.findall(r'\s-\s',body))},
                  repeated_paragraphs=duplicates,repeated_three_word_openings=repeated,
                  assessment='EDITORIAL_REVIEW_REQUIRED',authorship_assessment='NOT_PERFORMED',
                  note='Advisory craft diagnostics, not an AI detector, voice-quality score or automatic rewrite. Preserve legitimate hyphenation, ranges and purposeful interrupted dialogue. Persona/sample identity does not authenticate author approval.')
    return result


def execute(p):
    tasks={'cover-art':cover_art,'listing':listing,'voice':voice}
    if p.get('task') not in tasks:raise ValueError('Choose cover-art, listing or voice')
    return tasks[p['task']](p)

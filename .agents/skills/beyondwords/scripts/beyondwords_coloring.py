"""Coloring-art diagnostics and deliberate print imposition; no image model or sales claims."""
import copy
import hashlib
import io
import json
from pathlib import Path
import shutil
import tempfile

from PIL import Image, ImageChops, ImageDraw, ImageOps
import publishing_core as core
import publishing_project as project
from beyondwords_visual import specification, build


def blank(reason):
    return dict(blank=True,alt=reason,rights_basis='Original empty page',provenance='human_provided',safe_area_reviewed=True)


def artwork_check(entry, spec, seen):
    for key in ('alt','rights_basis'):core.text(entry.get(key),key)
    if entry.get('provenance') not in {'human_provided','ai_assisted','ai_generated'}:raise ValueError('Declare artwork provenance')
    if entry.get('safe_area_reviewed') is not True:raise ValueError('Review each page against its safe areas first')
    path=core.scoped_path(Path(entry['file']))
    if path.stat().st_size>32*1024*1024:raise ValueError('Artwork exceeds 32 MiB')
    raw=path.read_bytes();sha=hashlib.sha256(raw).hexdigest()
    if sha!=entry['sha256']:raise ValueError('Artwork changed after inspection')
    w,h,b,edges=specification(spec);pw=w+b*(2 if edges=='all' else 1 if edges=='outer' else 0);ph=h+2*b
    with Image.open(io.BytesIO(raw)) as source:
        if source.format not in {'PNG','JPEG'} or source.width*source.height>40_000_000:raise ValueError('Use PNG/JPEG artwork of at most 40 megapixels')
        source.load();im=ImageOps.exif_transpose(source)
        if im.mode not in {'RGB','L'}:raise ValueError('Use reviewed opaque grayscale or RGB line art')
        im=im.convert('RGB');size=im.size
        pixel_hash=hashlib.sha256(str(size).encode()+im.tobytes()).hexdigest()
        # Whole-image pixel counts; these are diagnostics, not semantic/reader judgements.
        hist=im.convert('L').histogram();total=size[0]*size[1]
        white=sum(hist[245:])/total;dark=sum(hist[:64])/total;mid=sum(hist[64:245])/total
        red,green,blue=im.split()
        difference=ImageChops.lighter(ImageChops.difference(red,green),ImageChops.difference(green,blue))
        colored=sum(difference.histogram()[16:])/total
    issues=[];blocking=[]
    if pixel_hash in seen and entry.get('intentional_repeat') is not True:issues.append('duplicate_pixels')
    seen.add(pixel_hash)
    if 1-white<.0005:issues.append('nearly_blank')
    if dark>.65:issues.append('heavy_fill')
    if mid>.15:issues.append('extensive_midtones')
    if colored>.01:issues.append('colored_pixels')
    dpi=min(size[0]/pw,size[1]/ph)
    if dpi<spec['min_dpi']-.01:blocking.append('insufficient_pixels')
    if abs((size[0]/size[1])/(pw/ph)-1)>.005:blocking.append('aspect_ratio_mismatch')
    return dict(sha256=sha,pixel_sha256=pixel_hash,pixels=list(size),effective_dpi=round(dpi,3),
                white_fraction=round(white,6),dark_fraction=round(dark,6),midtone_fraction=round(mid,6),
                colored_fraction=round(colored,6),issues=issues,blocking_issues=blocking)


def check(payload):
    p=copy.deepcopy(payload)
    if type(p.get('synthetic')) is not bool or type(p.get('single_sided')) is not bool:raise ValueError('Declare synthetic and single_sided explicitly')
    for key in ('title','author','language'):core.text(p.get(key),key)
    if p.get('formats')!=['pdf']:raise ValueError('Coloring imposition creates print/printable PDF; Kindle coloring interaction is not implemented')
    specification(p['spec'])
    if p['spec']['binding'] not in {'paperback','hardcover','pdf','printable'}:raise ValueError('Choose a print or printable binding')
    arts=p['artworks'];front=p['frontmatter']
    if not isinstance(arts,list) or not 1<=len(arts)<=300 or not isinstance(front,list) or len(front)>40:
        raise ValueError('Use 1–300 reviewed artworks and at most 40 explicit frontmatter pages')
    total=sum(core.scoped_path(Path(e['file'])).stat().st_size for e in front+arts if not e.get('blank'))
    if total>256*1024*1024:raise ValueError('Artwork exceeds bounded export size')
    pages=copy.deepcopy(front);checks=[];seen=set();mapping=[]
    for i,art in enumerate(arts,1):
        if art.get('blank'):raise ValueError('A coloring artwork must be an actual image')
        row=artwork_check(art,p['spec'],seen);row['artwork']=i;checks.append(row)
        if p['single_sided'] and len(pages)%2:pages.append(blank('Intentional blank before the next recto artwork'))
        mapping.append(dict(artwork=i,page=len(pages)+1));pages.append(art)
        if p['single_sided']:pages.append(blank('Intentional blank reverse of coloring artwork'))
    if not p['spec']['min_pages']<=len(pages)<=p['spec']['max_pages']:raise ValueError('Imposed page count outside reviewed limits; do not pad with unrequested pages')
    recipe={k:p[k] for k in ('title','author','language','synthetic','spec','formats')};recipe['pages']=pages
    receipt=dict(artwork_checks=checks,artwork_pages=mapping,print_page_count=len(pages),single_sided=p['single_sided'],
                 synthetic=p['synthetic'],publication_ready=False,visual_review='REQUIRED',
                 limitations=['Pixel thresholds are review prompts, not proof of good line art, closed shapes, originality or reader suitability.',
                              'Blank reverse pages do not prevent marker bleed-through; a physical proof and reader trial remain necessary.'])
    receipt['review_sha256']=project.digest(project.canonical({'recipe':recipe,'checks':checks}))
    return receipt,recipe


def contact_sheet(artworks,path):
    # Thumbnails support human review; originals are never edited or resampled for print.
    columns=4;width=1000;cell_w=250;cell_h=320
    rows=(len(artworks)+columns-1)//columns
    sheet=Image.new('RGB',(width,rows*cell_h),'#eeeeee');draw=ImageDraw.Draw(sheet)
    for i,entry in enumerate(artworks):
        with Image.open(entry['file']) as source:
            im=ImageOps.exif_transpose(source).convert('RGB');im.thumbnail((226,278))
            x=(i%columns)*cell_w+(cell_w-im.width)//2;y=(i//columns)*cell_h+8
            sheet.paste(im,(x,y));draw.text(((i%columns)*cell_w+12,(i//columns)*cell_h+292),f'Artwork {i+1}',fill='black')
    sheet.save(path,'JPEG',quality=90)


def execute(payload,destination=None):
    receipt,recipe=check(payload)
    if payload['task']=='check':return receipt
    if payload['task']!='build':raise ValueError('Choose check or build')
    if payload.get('review_sha256')!=receipt['review_sha256']:raise ValueError('Review this exact artwork and page-order check before building')
    # Flagged visual characteristics may be deliberate, but must have a specific recorded decision.
    decisions=payload.get('issue_reviews',[])
    if not isinstance(decisions,list):raise ValueError('issue_reviews must be a list')
    allowed={(r['artwork'],issue) for r in receipt['artwork_checks'] for issue in r['issues']}
    reviewed=set()
    for decision in decisions:
        key=(decision['artwork'],decision['issue'])
        if key not in allowed or key in reviewed:raise ValueError('Review only the exact flagged issue once')
        core.text(decision.get('reviewed_by'),'reviewed_by');core.text(decision.get('reason'),'reason')
        reviewed.add(key)
    if any(r['blocking_issues'] for r in receipt['artwork_checks']):raise ValueError('Correct artwork dimensions/resolution before building')
    if allowed-reviewed:raise ValueError('Resolve or explicitly review each flagged artwork issue')
    if not destination:raise ValueError('Choose a new output directory')
    target=core.scoped_path(Path(destination))
    if target.exists():raise FileExistsError('Never overwrite an existing coloring edition')
    target.parent.mkdir(parents=True,exist_ok=True);stage=Path(tempfile.mkdtemp(prefix='.beyondwords-coloring-',dir=target.parent))
    try:
        # Freeze input bytes, including frontmatter, before producing a contact sheet or PDF.
        frozen=copy.deepcopy(recipe)
        for i,entry in enumerate(frozen['pages']):
            if entry.get('blank'):continue
            raw=core.scoped_path(Path(entry['file'])).read_bytes()
            if hashlib.sha256(raw).hexdigest()!=entry['sha256']:raise ValueError('Artwork changed while building')
            with Image.open(io.BytesIO(raw)) as im:suffix='.jpg' if im.format=='JPEG' else '.png'
            file=stage/f'artwork-page-{i+1}{suffix}';file.write_bytes(raw);entry['file']=str(file)
        built=stage/'built';result=build(frozen,built)
        for file in built.iterdir():file.rename(stage/file.name)
        built.rmdir()
        frozen_arts=[frozen['pages'][r['page']-1] for r in receipt['artwork_pages']]
        contact_sheet(frozen_arts,stage/'contact-sheet.jpg')
        receipt['issue_reviews']=decisions
        (stage/'coloring-check.json').write_text(json.dumps(receipt,indent=2))
        # Make the delivered recipe portable alongside its exact frozen artwork.
        for entry in frozen['pages']:
            if not entry.get('blank'):entry['file']=Path(entry['file']).name
        (stage/'recipe.json').write_text(json.dumps(frozen,indent=2))
        result.update(coloring=receipt,editable_recipe='recipe.json',recipe_paths='relative to this edition directory')
        result.pop('files',None)
        (stage/'validation.json').write_text(json.dumps(result,indent=2))
        result['files']=[dict(file=str(f.relative_to(stage)),sha256=hashlib.sha256(f.read_bytes()).hexdigest()) for f in sorted(stage.rglob('*')) if f.is_file()]
        if target.exists():raise FileExistsError('Destination appeared during export')
        stage.rename(target);return result
    finally:
        if stage.exists():shutil.rmtree(stage)

"""Atomic image-page PDF and fixed-layout EPUB production from reviewed owned artwork.

No image model is bundled. Dimensions come from explicit current platform choices.
Export checks geometry, hashes and resolution; it does not approve visual quality.
"""
from pathlib import Path
import hashlib,io,json,shutil,tempfile,zipfile
from xml.sax.saxutils import escape
from uuid import uuid4
from PIL import Image,ImageOps
import publishing_core as core
from beyondwords_production import epubcheck


def positive(v,k):
 n=float(core.number(v,k))
 if n<=0:raise ValueError(k+' must be positive')
 return n

def specification(s):
 from publishing_browser import check_url
 check_url(s['policy_url'],s['policy_url'],resolve=False)
 age=(core.timestamp(core.iso_now(),'now')-core.timestamp(s['policy_reviewed_at'],'reviewed_at')).total_seconds()/3600
 if not 0<=age<=720:raise ValueError('Refresh the official specification review within 30 days')
 core.text(s['policy_basis'],'policy_basis')
 w,h=positive(s['trim_width'],'trim_width'),positive(s['trim_height'],'trim_height');bleed=float(core.number(s['bleed'],'bleed'))
 if not 1<=w<=30 or not 1<=h<=30 or bleed>1:raise ValueError('Unsupported page geometry')
 edges=s['bleed_edges']
 if edges not in {'none','outer','all'} or (bleed==0)!=(edges=='none'):raise ValueError('Bleed amount and edges disagree')
 platform=s['platform'];binding=s['binding']
 if platform not in {'kdp','lulu','direct','etsy'} or binding not in {'ebook','pdf','paperback','hardcover','printable'}:raise ValueError('Choose the real platform and binding')
 from urllib.parse import urlsplit
 host=urlsplit(s['policy_url']).hostname
 if platform=='kdp':
  if host!='kdp.amazon.com':raise ValueError('KDP specifications need an official KDP source')
  if bleed and (abs(bleed-.125)>1e-6 or edges!='outer'):raise ValueError('KDP interior bleed extends top, bottom and outside, not the binding edge')
  if binding=='hardcover' and (w,h) not in {(5.5,8.5),(6,9),(6.14,9.21),(7,10),(8.25,11)}:raise ValueError('Not a currently supported KDP hardcover trim')
  minimum=75 if binding=='hardcover' else 24 if binding=='paperback' else 1
  if s['min_pages']<minimum:raise ValueError('Declared page minimum is below the reviewed KDP binding minimum')
 if platform=='lulu':
  if host not in {'lulu.com','help.lulu.com','assets.lulu.com','www.lulu.com'}:raise ValueError('Lulu specifications need an official Lulu source')
  if abs(bleed-.125)>1e-6 or edges!='all':raise ValueError('Use the reviewed Lulu bleed on all edges')
 if type(s['min_pages']) is not int or type(s['max_pages']) is not int or not 1<=s['min_pages']<=s['max_pages']<=1000:raise ValueError('Record current minimum and maximum page counts')
 if type(s['min_dpi']) is not int or not 72<=s['min_dpi']<=1200:raise ValueError('Explicit resolution requirement needed')
 if binding in {'paperback','hardcover'} and s['min_dpi']<300:raise ValueError('Print artwork needs at least 300 effective DPI')
 safe=float(core.number(s['safe_margin'],'safe_margin'))
 if safe>=min(w,h)/2:raise ValueError('Safe margin consumes the page')
 return w,h,bleed,edges

def build(p,destination):
 from reportlab.pdfgen import canvas
 from reportlab.lib.utils import ImageReader
 if type(p.get('synthetic')) is not bool:raise ValueError('Declare real versus synthetic production')
 for k in ('title','author','language'):core.text(p[k],k)
 import re
 if not re.fullmatch('[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*',p['language']):raise ValueError('BCP47 language required')
 target=core.scoped_path(Path(destination))
 if target.exists():raise FileExistsError('Never replace an existing edition')
 s=p['spec'];w,h,b,edges=specification(s);pw=w+(2*b if edges=='all' else b if edges=='outer' else 0);ph=h+2*b
 pages=p['pages']
 if not isinstance(pages,list) or not s['min_pages']<=len(pages)<=s['max_pages']:raise ValueError('Page count outside reviewed platform bounds')
 formats=p['formats']
 if not isinstance(formats,list) or not formats or set(formats)-{'pdf','epub'}:raise ValueError('Choose pdf and/or epub')
 prepared=[];seen=set();total=0
 for index,entry in enumerate(pages):
  core.text(entry.get('alt'),'page.alt');core.text(entry.get('rights_basis'),'rights_basis')
  if entry.get('provenance') not in {'human_provided','ai_assisted','ai_generated'}:raise ValueError('Declare artwork provenance')
  if entry.get('safe_area_reviewed') is not True:raise ValueError('Review text, faces, trim and safe areas on every page')
  if entry.get('blank') is True:
   prepared.append({'data':None,'entry':entry,'size':(round(w*300),round(h*300)),'sha256':None});continue
  path=core.scoped_path(Path(entry['file']));raw=path.read_bytes();total+=len(raw)
  if len(raw)>32*1024*1024 or total>256*1024*1024:raise ValueError('Artwork exceeds bounded export size')
  sha=hashlib.sha256(raw).hexdigest()
  if sha!=entry['sha256']:raise ValueError('Artwork changed after review')
  if sha in seen and entry.get('intentional_repeat') is not True:raise ValueError('Repeated artwork needs an explicit intentional-repeat decision')
  seen.add(sha)
  with Image.open(io.BytesIO(raw)) as src:
   src.load();img=ImageOps.exif_transpose(src)
   if img.mode not in {'RGB','L','CMYK'}:raise ValueError('Flatten transparency and review the final artwork first')
   width,height=img.size
   if min(width/pw,height/ph)<s['min_dpi']-.01:raise ValueError('Effective image resolution is below requirement; metadata cannot fix this')
   if abs((width/height)/(pw/ph)-1)>.005:raise ValueError('Artwork aspect ratio differs from the reviewed page; crop/compose deliberately first')
   # No resampling: strip metadata, preserve reviewed pixel dimensions, freeze bytes.
   buffer=io.BytesIO();img.convert('RGB').save(buffer,format='PNG')
   prepared.append({'data':buffer.getvalue(),'size':img.size,'entry':entry,'sha256':sha})
 target.parent.mkdir(parents=True,exist_ok=True);stage=Path(tempfile.mkdtemp(prefix='.beyondwords-visual-',dir=target.parent))
 try:
  if 'pdf' in formats:
   c=canvas.Canvas(str(stage/'interior.pdf'),pagesize=(pw*72,ph*72),pageCompression=1,invariant=1)
   c.setTitle(p['title']);c.setAuthor(p['author'])
   for i,page in enumerate(prepared):
    if page['data']:c.drawImage(ImageReader(io.BytesIO(page['data'])),0,0,width=pw*72,height=ph*72)
    # Trim box alternates with outer-edge bleed; no crop/printer marks are drawn.
    left=b if edges=='all' or (edges=='outer' and (i+1)%2==0) else 0
    c.setTrimBox((left*72,b*72,(left+w)*72,(b+h)*72));c.showPage()
   c.save()
  if 'epub' in formats:write_epub(stage/'book.epub',p,prepared,w,h,b,edges)
  result={'synthetic':p['synthetic'],'pages':len(prepared),'page_size_inches':[pw,ph],'trim_inches':[w,h],
    'bleed_edges':edges,'min_effective_dpi':s['min_dpi'],'policy':s,'publication_ready':False,
    'visual_review':'OWNER_DECLARED; independent review still required','retailer_acceptance':'NOT_RUN',
    'color':'RGB source conversion; no printer ICC proof claimed','editable_recipe':'recipe.json',
    'epubcheck':epubcheck(stage/'book.epub') if 'epub' in formats else {'status':'NOT_REQUESTED'}}
  if result['epubcheck'].get('status') not in {'OK','NOT_REQUESTED'}:result['needs_review']='EPUB conformance not established'
  (stage/'validation.json').write_text(json.dumps(result,indent=2));(stage/'recipe.json').write_text(json.dumps(p,indent=2))
  result['files']=[{'file':x.name,'sha256':hashlib.sha256(x.read_bytes()).hexdigest()} for x in stage.iterdir() if x.is_file()]
  if target.exists():raise FileExistsError('Destination appeared while exporting')
  stage.rename(target);return result
 finally:
  if stage.exists():shutil.rmtree(stage)

def write_epub(path,p,pages,w,h,b,edges):
 # Ebook pages exclude physical print bleed rather than displaying trim waste.
 width,height=round(w*300),round(h*300);manifest=[];spine=[];nav=[]
 with zipfile.ZipFile(path,'x',zipfile.ZIP_DEFLATED) as z:
  z.writestr('mimetype','application/epub+zip',compress_type=zipfile.ZIP_STORED)
  z.writestr('META-INF/container.xml','<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
  for i,page in enumerate(pages,1):
   body='<p>Intentionally blank</p>'
   if page['data']:
    with Image.open(io.BytesIO(page['data'])) as im:
     left=b if edges=='all' or (edges=='outer' and i%2==0) else 0
     pw=w+(2*b if edges=='all' else b if edges=='outer' else 0);ph=h+2*b
     box=(round(left/pw*im.width),round(b/ph*im.height),round((left+w)/pw*im.width),round((b+h)/ph*im.height))
     crop=im.crop(box);buf=io.BytesIO();crop.save(buf,format='PNG');raw=buf.getvalue()
    z.writestr(f'OEBPS/image-{i}.png',raw);manifest.append(f'<item id="img{i}" href="image-{i}.png" media-type="image/png"/>')
    body=f'<img src="image-{i}.png" alt="{escape(page["entry"]["alt"],{chr(34):"&quot;"})}" style="width:100%;height:100%"/>'
   z.writestr(f'OEBPS/page-{i}.xhtml',f'<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml" xml:lang="{escape(p["language"])}"><head><title>Page {i}</title><meta name="viewport" content="width={width},height={height}"/><style>html,body{{margin:0;padding:0;width:{width}px;height:{height}px}}</style></head><body>{body}</body></html>')
   manifest.append(f'<item id="p{i}" href="page-{i}.xhtml" media-type="application/xhtml+xml"/>');spine.append(f'<itemref idref="p{i}"/>');nav.append(f'<li><a href="page-{i}.xhtml">Page {i}</a></li>')
  z.writestr('OEBPS/nav.xhtml','<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><head><title>Contents</title></head><body><nav epub:type="toc"><h1>Contents</h1><ol>'+''.join(nav)+'</ol></nav></body></html>')
  stamp=core.iso_now()[:19]+'Z'
  z.writestr('OEBPS/content.opf',f'<?xml version="1.0" encoding="utf-8"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="bookid">urn:uuid:{uuid4()}</dc:identifier><dc:title>{escape(p["title"])}</dc:title><dc:creator>{escape(p["author"])}</dc:creator><dc:language>{escape(p["language"])}</dc:language><meta property="dcterms:modified">{stamp}</meta><meta property="rendition:layout">pre-paginated</meta><meta property="rendition:spread">none</meta></metadata><manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'+''.join(manifest)+'</manifest><spine>'+''.join(spine)+'</spine></package>')


def wrap(p,destination):
 """Compose a print wrap to the dimensions of an actual supplied PDF template."""
 from pypdf import PdfReader
 from reportlab.pdfgen import canvas
 from reportlab.lib.utils import ImageReader
 w,h,bleed,edges=specification(p['spec'])
 if type(p.get('synthetic')) is not bool:raise ValueError('Declare real versus synthetic production')
 template=core.scoped_path(Path(p['template']['file']));raw=template.read_bytes()
 if len(raw)>32*1024*1024 or hashlib.sha256(raw).hexdigest()!=p['template']['sha256']:raise ValueError('Template differs from reviewed bytes')
 reader=PdfReader(io.BytesIO(raw))
 if reader.is_encrypted or len(reader.pages)!=1:raise ValueError('Use a one-page unlocked printer cover template')
 width,height=float(reader.pages[0].mediabox.width)/72,float(reader.pages[0].mediabox.height)/72
 if not 1<=width<=60 or not 1<=height<=30:raise ValueError('Unsupported template size')
 for k in ('binding','page_count','paper','ink','trim_width','trim_height'):
  if p['template'].get(k)!=p['interior'].get(k):raise ValueError('Template does not match the selected interior: '+k)
 if p['template']['binding']!=p['spec']['binding']:raise ValueError('Binding differs from reviewed specification')
 if not isinstance(p['interior'].get('sha256'),str) or not re_full_hash(p['interior']['sha256']):raise ValueError('Exact interior hash required')
 interior_file=core.scoped_path(Path(p['interior']['file']));interior_raw=interior_file.read_bytes()
 if hashlib.sha256(interior_raw).hexdigest()!=p['interior']['sha256']:raise ValueError('Interior changed')
 interior_pdf=PdfReader(io.BytesIO(interior_raw))
 if interior_pdf.is_encrypted or len(interior_pdf.pages)!=p['interior']['page_count']:raise ValueError('Interior page count differs from cover template')
 if float(p['interior']['trim_width'])!=w or float(p['interior']['trim_height'])!=h:raise ValueError('Interior trim differs from the reviewed specification')
 for page in interior_pdf.pages:
  if abs(float(page.trimbox.width)/72-w)>.001 or abs(float(page.trimbox.height)/72-h)>.001:raise ValueError('Actual interior trim dimensions differ from the cover template')
  expected_width=w+bleed*(2 if edges=='all' else 1 if edges=='outer' else 0)
  if abs(float(page.mediabox.width)/72-expected_width)>.001 or abs(float(page.mediabox.height)/72-(h+2*bleed))>.001:raise ValueError('Actual interior bleed dimensions differ from the reviewed specification')
 panels=p['panels']
 if not isinstance(panels,list) or not 1<=len(panels)<=12:raise ValueError('Use a bounded panel composition')
 images=[];resolution_checks=[]
 for panel in panels:
  path=core.scoped_path(Path(panel['file']));data=path.read_bytes()
  if hashlib.sha256(data).hexdigest()!=panel['sha256'] or len(data)>32*1024*1024:raise ValueError('Panel changed or exceeds limit')
  core.text(panel['rights_basis'],'rights_basis')
  if panel.get('safe_area_reviewed') is not True:raise ValueError('Review the panel against actual template safe zones, hinges and barcode area')
  x,y=float(core.number(panel['x'],'x')),float(core.number(panel['y'],'y'));w,h=positive(panel['width'],'width'),positive(panel['height'],'height')
  if x+w>width+.001 or y+h>height+.001:raise ValueError('Panel extends outside template')
  with Image.open(io.BytesIO(data)) as im:
   im.load()
   if min(im.width/w,im.height/h)<max(300,p['spec']['min_dpi'])-.01 or abs(im.width/im.height/(w/h)-1)>.005:raise ValueError('Panel geometry or effective resolution invalid')
  from beyondwords_publishing_checks import cover_art
  check=cover_art(dict(file=str(path),sha256=panel['sha256'],width_inches=str(w),height_inches=str(h),target_dpi=max(300,p['spec']['min_dpi']),native_source=panel.get('native_source'),synthetic=p['synthetic']))
  if check['assessment']=='INSUFFICIENT':raise ValueError('Native panel pixels are insufficient; regenerate or reduce placement size')
  resolution_checks.append(check)
  images.append((data,x,y,w,h))
 first=images[0]
 if first[1:3]!=(0.0,0.0) or abs(first[3]-width)>.001 or abs(first[4]-height)>.001:raise ValueError('First panel must cover the complete template including bleed')
 target=core.scoped_path(Path(destination))
 if target.exists():raise FileExistsError('Cover destination already exists')
 target.parent.mkdir(parents=True,exist_ok=True);stage=Path(tempfile.mkdtemp(prefix='.beyondwords-wrap-',dir=target.parent))
 try:
  c=canvas.Canvas(str(stage/'cover-wrap.pdf'),pagesize=(width*72,height*72),pageCompression=1,invariant=1)
  for data,x,y,w,h in images:c.drawImage(ImageReader(io.BytesIO(data)),x*72,y*72,w*72,h*72)
  c.showPage();c.save()
  result={'template_sha256':p['template']['sha256'],'interior_sha256':p['interior']['sha256'],'dimensions_inches':[width,height],'page_count':p['interior']['page_count'],'template_overlay_exported':False,'resolution_checks':resolution_checks,'native_resolution_verified':False,'publication_ready':False,'printer_preview':'NOT_RUN','synthetic':p['synthetic']}
  (stage/'validation.json').write_text(json.dumps(result,indent=2));(stage/'recipe.json').write_text(json.dumps(p,indent=2))
  if target.exists():raise FileExistsError('Destination appeared during composition')
  stage.rename(target);return result
 finally:
  if stage.exists():shutil.rmtree(stage)

def re_full_hash(v):
 import re
 return bool(re.fullmatch('[0-9a-f]{64}',v))

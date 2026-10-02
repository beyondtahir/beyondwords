"""Local edition production; reuses the inherited EPUB and cover modules.

Only reflowable text and simple Latin-script print layouts are supported by
this pipeline. Visual book routes use dedicated host-assisted design review.
"""
from __future__ import annotations
from html import escape
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

MODULES = Path(__file__).resolve().parents[1]/'modules/beyondwords'
PUBLISHER = MODULES/'beyondwords-publisher'


def inherited(name):
    spec = importlib.util.spec_from_file_location(name, PUBLISHER/'scripts'/f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def inspect_image(data):
    from PIL import Image
    if len(data) > 32*1024*1024:
        raise ValueError('Image exceeds the 32 MiB limit')
    with Image.open(io.BytesIO(data)) as picture:
        if picture.format not in {'PNG', 'JPEG'} or picture.width*picture.height > 40_000_000:
            raise ValueError('Use a PNG/JPEG of at most 40 megapixels')
        result = dict(width=picture.width, height=picture.height, mode=picture.mode,
                      media_type='image/png' if picture.format == 'PNG' else 'image/jpeg')
        picture.verify()
        return result


def cover_directions(title, author, subtitle=''):
    """Original editable typographic directions, not market-tested artwork."""
    from PIL import Image, ImageDraw, ImageFont
    fonts = PUBLISHER/'assets/fonts'
    outputs = []
    palettes = [('ink', '#172C3C', '#F6EDD9', '#E4AA54'),
                ('paper', '#F6EDD9', '#213F49', '#B95339'),
                ('plum', '#342A41', '#F8F1E4', '#D6B96A')]
    for label, background, ink, accent in palettes:
        picture = Image.new('RGB', (1600, 2560), background)
        draw = ImageDraw.Draw(picture)
        draw.rectangle((128, 240, 440, 270), fill=accent)
        svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="2560" viewBox="0 0 1600 2560">',
               f'<rect width="1600" height="2560" fill="{background}"/>',
               f'<rect x="128" y="240" width="312" height="30" fill="{accent}"/>']
        def block(value, y, max_height, start_size, font_file, family):
            if not value:
                return
            for size in range(start_size, 35, -4):
                font = ImageFont.truetype(str(fonts/font_file), size)
                lines, line = [], ''
                for word in value.split():
                    candidate = (line+' '+word).strip()
                    if draw.textbbox((0, 0), candidate, font=font)[2] > 1344 and line:
                        lines.append(line); line = word
                    else:
                        line = candidate
                lines.append(line)
                if len(lines)*size*1.32 <= max_height and all(draw.textbbox((0, 0), s, font=font)[2] <= 1344 for s in lines):
                    break
            else:
                raise ValueError('Cover text cannot fit; shorten it or choose a different layout')
            for i, line in enumerate(lines):
                baseline = y+i*size*1.32
                draw.text((128, baseline), line, font=font, fill=ink)
                svg.append(f'<text x="128" y="{baseline+size}" font-family="{family}" font-size="{size}" fill="{ink}">{escape(line)}</text>')
        block(title, 390, 1150, 220, 'Oswald-Variable.ttf', 'Oswald')
        block(subtitle, 1660, 420, 80, 'PlayfairDisplay-Variable.ttf', 'Playfair Display')
        block(author, 2200, 200, 72, 'Oswald-Variable.ttf', 'Oswald')
        svg.append('</svg>')
        buffer = io.BytesIO(); picture.save(buffer, 'JPEG', quality=95, dpi=(300, 300))
        outputs.append((f'cover-{label}.jpg', 'image/jpeg', buffer.getvalue()))
        thumb = picture.copy(); thumb.thumbnail((200, 320))
        buffer = io.BytesIO(); thumb.save(buffer, 'PNG')
        outputs.append((f'cover-{label}-thumbnail.png', 'image/png', buffer.getvalue()))
        outputs.append((f'cover-{label}.svg', 'image/svg+xml', '\n'.join(svg).encode()))
    return outputs


def epubcheck(path):
    """Explicit local executable/JAR only. Never downloads or runs manuscript code."""
    executable = shutil.which('epubcheck')
    settings = {}
    settings_path = Path.home()/'.local/share/beyondwords/config.json'
    if settings_path.is_file():
        try:
            settings = json.loads(settings_path.read_text())
            if not isinstance(settings, dict):
                raise ValueError('Settings must be an object')
        except (OSError, ValueError) as exc:
            return {'status': 'ERROR', 'ran': False, 'reason': 'Invalid local validator configuration: '+str(exc)}
    jar = os.environ.get('BEYONDWORDS_EPUBCHECK_JAR') or settings.get('epubcheck_jar')
    java = os.environ.get('BEYONDWORDS_JAVA') or settings.get('java', 'java')
    if jar:
        if not Path(jar).is_file():
            return {'status': 'UNAVAILABLE', 'ran': False, 'reason': 'Configured EPUBCheck JAR is missing'}
        command = [java, '-jar', jar]
    elif executable:
        command = [executable]
    else:
        return {'status': 'UNAVAILABLE', 'ran': False, 'reason': 'Install EPUBCheck or configure BEYONDWORDS_EPUBCHECK_JAR'}
    try:
        version = subprocess.run(command+['--version'], capture_output=True, text=True, timeout=30)
        result = subprocess.run(command+[str(path)], capture_output=True, text=True, timeout=120)
        return {'status': 'OK' if result.returncode == 0 else 'ERROR', 'ran': True,
                'version': (version.stdout+version.stderr).strip()[:1000], 'exit_code': result.returncode,
                'report': (result.stdout+result.stderr)[-20000:]}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {'status': 'ERROR', 'ran': True, 'reason': str(exc)}


def text_pdf(manuscript, metadata, trim):
    """Conservative mirrored margins and actual pagination, without guessed gutters."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, PageBreak, NextPageTemplate
    from pypdf import PdfReader
    producer = inherited('bw_produce')
    if trim not in producer.TRIMS_PT:
        raise ValueError('Unsupported trim')
    width, height = producer.TRIMS_PT[trim]
    for name, file in [('BWCompleteBody', 'PlayfairDisplay-Variable.ttf'), ('BWCompleteDisplay', 'Oswald-Variable.ttf')]:
        font = TTFont(name, str(PUBLISHER/'assets/fonts'/file))
        absent = {c for c in manuscript if not c.isspace() and ord(c) not in font.face.charToGlyph}
        if absent:
            raise ValueError('Bundled fonts cannot render all manuscript characters; choose a tested language/font route')
        pdfmetrics.registerFont(font)
    body = ParagraphStyle('body', fontName='BWCompleteBody', fontSize=11, leading=16, spaceAfter=10)
    heading = ParagraphStyle('heading', fontName='BWCompleteDisplay', fontSize=23, leading=29, spaceAfter=20)
    subhead = ParagraphStyle('subhead', fontName='BWCompleteDisplay', fontSize=15, leading=20, spaceAfter=10)
    buffer = io.BytesIO()
    # One-inch inside margin is deliberately conservative for this text-only route.
    inside, outside, vertical = 72, 54, 54
    document = BaseDocTemplate(buffer, pagesize=(width, height), title=metadata['title'], author=metadata['author'])
    def footer(canvas, doc):
        canvas.setFont('BWCompleteBody', 9)
        canvas.drawCentredString(width/2, 30, str(doc.page))
    recto = Frame(inside, vertical, width-inside-outside, height-2*vertical, id='recto')
    verso = Frame(outside, vertical, width-inside-outside, height-2*vertical, id='verso')
    document.addPageTemplates([PageTemplate('recto', [recto], onPage=footer, autoNextPageTemplate='verso'),
                               PageTemplate('verso', [verso], onPage=footer, autoNextPageTemplate='recto')])
    flow = []
    for i, section in enumerate(producer.parse_manuscript(manuscript)):
        if i:
            flow.append(PageBreak())
        for block in section['blocks']:
            kind = block['kind']
            if kind == 'list':
                for item in block['items']:
                    flow.append(Paragraph('• '+escape(item), body))
            else:
                # Keep literal emphasis markers visible rather than pretending separate styles exist.
                value = re.sub(r'\*\*([^*]+)\*\*|\*([^*]+)\*', lambda m: m.group(1) or m.group(2), block['text'])
                flow.append(Paragraph(escape(value), heading if kind == 'h1' else subhead if kind == 'h2' else body))
    document.build(flow)
    data = buffer.getvalue()
    pdf = PdfReader(io.BytesIO(data))
    if len(pdf.pages) > 800:
        raise ValueError('Over 800 pages; this conservative print profile needs a dedicated layout review')
    embedded = []
    for page in pdf.pages:
        for font in page['/Resources'].get('/Font', {}).values():
            font = font.get_object()
            desc = font.get('/FontDescriptor')
            if desc and any(key in desc.get_object() for key in ('/FontFile', '/FontFile2', '/FontFile3')):
                embedded.append(str(font.get('/BaseFont')))
    if not embedded:
        raise ValueError('No embedded fonts detected in the actual PDF')
    report = dict(pages=len(pdf.pages), trim=trim, page_size_points=[width, height],
                  inside_margin_inches=1, outside_margin_inches=0.75, mirrored_margins=True,
                  embedded_fonts=sorted(set(embedded)), bleed=False, chapter_starts='next_page',
                  visual_review='NOT_RUN', printer_acceptance='NOT_RUN')
    return data, report


def produce_edition(manuscript, metadata, config, cover=None):
    requested = config.get('format', 'epub')
    if requested not in {'epub', 'pdf', 'both', 'docx'}:
        raise ValueError('format must be epub, pdf, both, or docx')
    if metadata['route'] not in {'nonfiction', 'fiction'}:
        raise ValueError('This exporter supports text nonfiction/fiction; visual routes need dedicated layout')
    # Reject unsupported constructs instead of silently losing their meaning in export.
    if re.search(r'(?m)^\s*(?:```|~~~|\|)|!\[|<\s*(?:table|img|script)\b', manuscript):
        raise ValueError('Tables, code fences, embedded images and raw HTML need a dedicated layout route')
    files = [('manuscript.md', 'text/markdown', manuscript.encode())]
    report = {'publication_ready': False, 'visual_review': 'NOT_RUN', 'retailer_acceptance': 'NOT_RUN'}
    if requested == 'docx':
        if cover:
            raise ValueError('The editorial Word handoff does not embed covers; use the EPUB/PDF edition or a dedicated layout route')
        from beyondwords_docx import build_docx
        data, report['docx'] = build_docx(manuscript, metadata)
        files.append(('review.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', data))
        files.append(('validation.json', 'application/json', (json.dumps(report, indent=2)+'\n').encode()))
        return files, report
    producer = inherited('bw_produce')
    with tempfile.TemporaryDirectory(prefix='beyondwords-production-') as folder:
        root = Path(folder)
        md = root/'manuscript.md'; md.write_text(manuscript, encoding='utf-8')
        cover_path = None
        if cover:
            inspection = inspect_image(cover)
            suffix = 'png' if inspection['media_type'] == 'image/png' else 'jpg'
            cover_path = root/('cover.'+suffix); cover_path.write_bytes(cover)
            files.append(('cover.'+suffix, inspection['media_type'], cover))
            report['cover'] = inspection
        if requested in {'epub', 'both'}:
            path = root/'book.epub'
            producer.build_epub(dict(manuscript=str(md), title=metadata['title'], author=metadata['author'],
                                    language=metadata['language'], output=str(path), cover=str(cover_path) if cover_path else None))
            structural = producer.validate_epub(str(path))
            if not structural['structuralValid']:
                raise ValueError('Generated EPUB failed structure checks: '+str(structural['problems']))
            report['epub'] = {'structural_valid': True, 'epubcheck': epubcheck(path), 'cover_embedded': bool(cover)}
            files.append(('book.epub', 'application/epub+zip', path.read_bytes()))
        if requested in {'pdf', 'both'}:
            pdf, pdf_report = text_pdf(manuscript, metadata, config.get('trim', '6x9'))
            report['pdf'] = pdf_report
            files.append(('interior.pdf', 'application/pdf', pdf))
    files.append(('validation.json', 'application/json', (json.dumps(report, indent=2)+'\n').encode()))
    return files, report


def compose_cover(payload, destination):
    """Atomically export art, a reproducible editable type recipe and rendered previews."""
    import publishing_core as core
    from publishing_project import load_input, digest
    for key in ('title','author','rights_basis','research_basis'):
        core.text(payload.get(key),key)
    if payload.get('provenance') not in {'human_provided','ai_generated','ai_assisted'}:
        raise ValueError('Declare artwork provenance')
    if payload.get('position','top') not in {'top','center','bottom'}:
        raise ValueError('Use top, center or bottom typography')
    art=load_input(Path(payload['art'])); report=inspect_image(art)
    if report['width']<1600 or report['height']<2560:
        raise ValueError('Supply art at least 1600×2560; do not silently upscale a small image')
    target=core.scoped_path(Path(destination))
    if target.exists() or target.is_symlink(): raise FileExistsError('Cover destination exists')
    target.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.beyondwords-art-cover-',dir=target.parent))
    try:
        extension='.png' if report['media_type']=='image/png' else '.jpg'
        (stage/('art'+extension)).write_bytes(art)
        (stage/'fonts').mkdir()
        for file in (PUBLISHER/'assets/fonts').iterdir():
            if file.is_file(): shutil.copy2(file,stage/'fonts'/file.name)
        recipe=dict(art='art'+extension,title=payload['title'],subtitle=payload.get('subtitle',''),author=payload['author'],
                    titleFont='fonts/Oswald-Variable.ttf',bodyFont='fonts/PlayfairDisplay-Variable.ttf',
                    position=payload.get('position','top'),casing=payload.get('casing','original'),
                    color=payload.get('color','auto'),authorStrip=True,output='cover.jpg',thumb='thumbnail.png')
        config=dict(recipe)
        for key in ('art','titleFont','bodyFont','output','thumb'): config[key]=str(stage/recipe[key])
        result=inherited('bw_compose').render(config)
        if not result.get('ok'): raise ValueError(result.get('error','Cover composition failed'))
        manifest=dict(schema=1,recipe=recipe,art_sha256=digest(art),provenance=payload['provenance'],
                      rights_basis=payload['rights_basis'],research_basis=payload['research_basis'],
                      visual_review='NOT_RUN',market_tested=False,publication_ready=False,
                      note='Center-cropped ebook front cover. Keep art and editable type recipe; rerender to a new revision. Print wrap requires a printer template.')
        (stage/'composition.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        if target.exists() or target.is_symlink(): raise FileExistsError('Cover destination appeared during generation')
        stage.rename(target)
    finally:
        if stage.exists(): shutil.rmtree(stage)
    return dict(directory=str(target),files=['cover.jpg','thumbnail.png','composition.json','art'+extension,'fonts/'],
                artwork=report,publication_ready=False,visual_review='NOT_RUN',market_tested=False)

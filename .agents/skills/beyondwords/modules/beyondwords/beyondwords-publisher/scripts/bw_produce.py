#!/usr/bin/env python3
"""bw_produce.py — Beyondwords production pipeline (original implementation).

Manuscript markdown → store-ready files. Pure stdlib for EPUB; reportlab for
print PDF when available (emits clear instructions JSON when not).

Commands (JSON envelope out):
  epub '{"manuscript":"manuscript.md","title":"…","author":"…",
         "cover":"cover.jpg","output":"book.epub","language":"en"}'
  validate <book.epub>              structural EPUB 3 checks (mimetype first &
                                    uncompressed, container/OPF/nav parse,
                                    manifest completeness; shells out to
                                    EPUBCheck if the host has it)
  pdf '{"manuscript":"manuscript.md","title":"…","author":"…","trim":"6x9",
        "output":"book.pdf","bodyFont":"…/PlayfairDisplay-Variable.ttf",
        "displayFont":"…/Oswald-Variable.ttf"}'

Print PDF: exact trim size, KDP gutter by page count (≤150pp 0.375" · 151–300
0.5" · 301–500 0.625" · 501–700 0.75" · 701–828 0.875"), outside margins 0.25"
min, chapters start on recto pages, page numbers, embedded TTF fonts.
Interior pages carry NO bleed by default (text interiors); the cover wrap math
lives in bw_cover_geo.py.
"""
import json
import os
import re
import sys
import uuid
import zipfile
from datetime import datetime, timezone
from html import escape

from pathlib import Path
import io
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from bw_io import write_new

TOOL = "bw_produce"
VERSION = "1.0.0"

TRIMS_PT = {"6x9": (6 * 72, 9 * 72), "5x8": (5 * 72, 8 * 72),
            "5.5x8.5": (5.5 * 72, 8.5 * 72), "8.5x11": (8.5 * 72, 11 * 72),
            "5.25x8": (5.25 * 72, 8 * 72)}

# KDP minimum inside (gutter) margin by page count — official table from
# "Set Trim Size, Bleed, and Margins" (kdp.amazon.com, verified 2026-09-30)
def gutter_inches(pages):
    for hi, g in ((150, 0.375), (300, 0.5), (500, 0.625), (700, 0.75), (828, 0.875)):
        if pages <= hi:
            return g
    return 0.875


def envelope(payload):
    return {"tool": TOOL, "version": VERSION, "ok": payload.get("ok", True), **payload}


# ------------------------- markdown → structured doc ------------------------

def esc(text):
    return escape(text, quote=True)


def inline(text):
    text = esc(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<em>\1</em>", text)
    return text


def parse_manuscript(md_text):
    """Split into sections on '# ' headings; each section → blocks.
    Block kinds: h1, h2, para, quote (takeaway box), list."""
    sections = []
    current = {"title": None, "blocks": []}
    for raw_line in md_text.splitlines():
        line = raw_line.rstrip()
        if line.startswith("# "):
            if current["blocks"] or current["title"]:
                sections.append(current)
            current = {"title": line[2:].strip(), "blocks": [{"kind": "h1", "text": line[2:].strip()}]}
        elif line.startswith("## "):
            current["blocks"].append({"kind": "h2", "text": line[3:].strip()})
        elif line.startswith("### "):
            current["blocks"].append({"kind": "h2", "text": line[4:].strip()})
        elif line.strip() == "---":
            pass
        elif line.startswith("> "):
            current["blocks"].append({"kind": "quote", "text": line[2:].strip()})
        elif re.match(r"^[-•] ", line):
            current["blocks"].append({"kind": "li", "text": line[2:].strip()})
        elif line.strip():
            current["blocks"].append({"kind": "para", "text": line.strip()})
    if current["blocks"] or current["title"]:
        sections.append(current)
    # merge consecutive list items
    for s in sections:
        merged = []
        for b in s["blocks"]:
            if b["kind"] == "li" and merged and merged[-1]["kind"] == "list":
                merged[-1]["items"].append(b["text"])
            elif b["kind"] == "li":
                merged.append({"kind": "list", "items": [b["text"]]})
            else:
                merged.append(b)
        s["blocks"] = merged
    return sections


def blocks_to_xhtml(blocks):
    out = []
    for b in blocks:
        if b["kind"] == "h1":
            out.append(f"<h1>{inline(b['text'])}</h1>")
        elif b["kind"] == "h2":
            out.append(f"<h2>{inline(b['text'])}</h2>")
        elif b["kind"] == "quote":
            out.append(f'<div class="takeaway"><p>{inline(b["text"])}</p></div>')
        elif b["kind"] == "list":
            items = "".join(f"<li>{inline(i)}</li>" for i in b["items"])
            out.append(f"<ul>{items}</ul>")
        else:
            out.append(f"<p>{inline(b['text'])}</p>")
    return "\n".join(out)


# ------------------------------- EPUB 3 -------------------------------------

EPUB_CSS = """
body { font-family: serif; line-height: 1.5; margin: 5%; }
h1 { font-family: sans-serif; page-break-before: always; }
h2 { font-family: sans-serif; }
.takeaway { border: 1px solid #888; padding: 0.8em; margin: 1em 0; background: #f4f4f4; }
ul { margin-left: 1.5em; }
"""

XHTML_HEAD = ('<?xml version="1.0" encoding="utf-8"?>\n'
              '<!DOCTYPE html>\n<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">\n'
              "<head><title>{title}</title><link rel=\"stylesheet\" type=\"text/css\" href=\"../style.css\"/></head>\n<body>\n")

CONTAINER_XML = """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""


def build_epub(cfg):
    md = Path(cfg["manuscript"]).read_text(encoding="utf-8")
    sections = parse_manuscript(md)
    if not sections:
        raise SystemExit("manuscript produced no sections — fail closed, nothing to build")
    title = cfg.get("title", "Untitled")
    author = cfg.get("author", "Anonymous")
    lang = cfg.get("language", "en")
    if not isinstance(lang, str) or not re.fullmatch(r'[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*', lang):
        raise ValueError('language must be a BCP-47 style language tag')
    uid = f"urn:uuid:{uuid.uuid4()}"
    cover = cfg.get("cover")
    if cover and not Path(cover).is_file():
        raise FileNotFoundError('Requested cover is missing')
    modified = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    files = {}  # arcname → bytes
    files["mimetype"] = b"application/epub+zip"
    files["META-INF/container.xml"] = CONTAINER_XML.encode("utf-8")
    files["OEBPS/style.css"] = EPUB_CSS.encode("utf-8")

    manifest, spine, nav_points, nav_li = [], [], [], []
    if cover and os.path.exists(cover):
        ext = os.path.splitext(cover)[1].lower().lstrip(".")
        media = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}[ext]
        files[f"OEBPS/cover.{ext}"] = Path(cover).read_bytes()
        manifest.append(f'<item id="cover-image" href="cover.{ext}" media-type="{media}" properties="cover-image"/>')
        cov = (XHTML_HEAD.format(title="Cover") + f'<p><img src="../cover.{ext}" alt="{esc(title)}"/></p>\n</body>\n</html>')
        files["OEBPS/text/cover.xhtml"] = cov.encode("utf-8")
        manifest.append('<item id="coverpage" href="text/cover.xhtml" media-type="application/xhtml+xml"/>')
        spine.append('<itemref idref="coverpage"/>')

    for i, s in enumerate(sections, 1):
        name = f"ch{i:03d}"
        body = blocks_to_xhtml(s["blocks"])
        files[f"OEBPS/text/{name}.xhtml"] = (XHTML_HEAD.format(title=esc(s["title"] or title))
                                             + body + "\n</body>\n</html>").encode("utf-8")
        manifest.append(f'<item id="{name}" href="text/{name}.xhtml" media-type="application/xhtml+xml"/>')
        spine.append(f'<itemref idref="{name}"/>')
        label = esc(s["title"] or f"Section {i}")
        nav_points.append(f'<navPoint id="np{i}" playOrder="{i}"><navLabel><text>{label}</text></navLabel>'
                          f'<content src="text/{name}.xhtml"/></navPoint>')
        nav_li.append(f'<li><a href="text/{name}.xhtml">{label}</a></li>')

    manifest.append('<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>')
    manifest.append('<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>')
    manifest.append('<item id="css" href="style.css" media-type="text/css"/>')

    opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pub-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="pub-id">{uid}</dc:identifier>
    <dc:title>{esc(title)}</dc:title>
    <dc:creator>{esc(author)}</dc:creator>
    <dc:language>{lang}</dc:language>
    <meta property="dcterms:modified">{modified}</meta>
  </metadata>
  <manifest>
    {' '.join(manifest)}
  </manifest>
  <spine toc="ncx">
    {' '.join(spine)}
  </spine>
</package>
"""
    files["OEBPS/content.opf"] = opf.encode("utf-8")

    nav = (XHTML_HEAD.format(title="Contents").replace('../style.css', 'style.css')
           + '<nav epub:type="toc"><h1>Contents</h1><ol>' + "".join(nav_li) + "</ol></nav>\n</body>\n</html>")
    files["OEBPS/nav.xhtml"] = nav.encode("utf-8")

    ncx = f"""<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head><meta name="dtb:uid" content="{uid}"/></head>
  <docTitle><text>{esc(title)}</text></docTitle>
  <navMap>{''.join(nav_points)}</navMap>
</ncx>
"""
    files["OEBPS/toc.ncx"] = ncx.encode("utf-8")

    out = cfg.get("output", "book.epub")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        # mimetype must be the first entry and stored uncompressed (EPUB spec)
        z.writestr(zipfile.ZipInfo("mimetype"), files.pop("mimetype"),
                   compress_type=zipfile.ZIP_STORED)
        for name, data in files.items():
            z.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)

    write_new(out, buffer.getvalue())
    return envelope({"publicationReady": False, "output": out, "format": "EPUB 3", "sections": len(sections),
                     "title": title, "author": author, "coverEmbedded": bool(cover and os.path.exists(cover)),
                     "bytes": os.path.getsize(out),
                     "nextStep": f"validate: python3 {os.path.basename(__file__)} validate {out}"})


def validate_epub(path):
    """Bounded structural validation; EPUBCheck is an independently reported gate."""
    import posixpath
    import shutil
    import subprocess
    from urllib.parse import unquote, urlsplit
    from xml.etree import ElementTree as ET
    problems, checks = [], []
    def check(name, passed):
        checks.append({"check": name, "pass": bool(passed)})
        if not passed:
            problems.append(name)
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            names = archive.namelist()
            if not infos:
                raise ValueError("empty EPUB archive")
            if len(infos) > 10000 or sum(i.file_size for i in infos) > 32 * 1024 * 1024:
                raise ValueError("archive exceeds validation size limit")
            check("unique archive entries", len(names) == len(set(names)))
            check("safe archive paths", all(not n.startswith("/") and ".." not in n.split("/") and "\\" not in n for n in names))
            check("mimetype is first entry", infos[0].filename == "mimetype")
            check("mimetype stored uncompressed", infos[0].compress_type == zipfile.ZIP_STORED)
            check("mimetype content", "mimetype" in names and archive.read("mimetype") == b"application/epub+zip")
            parsed = {}
            for name in names:
                if name.endswith((".xml", ".opf", ".xhtml", ".ncx")):
                    content = archive.read(name)
                    if b"<!ENTITY" in content.upper():
                        raise ValueError("XML entity declarations are not accepted")
                    try:
                        parsed[name] = ET.fromstring(content)
                        check(name + " well-formed XML", True)
                    except ET.ParseError:
                        check(name + " well-formed XML", False)
            container = parsed.get("META-INF/container.xml")
            check("container present and valid", container is not None)
            roots = [] if container is None else container.findall("{*}rootfiles/{*}rootfile")
            package_path = roots[0].get("full-path") if len(roots) == 1 else None
            package = parsed.get(package_path)
            check("single package present and valid", package is not None)
            if package is not None:
                items = package.findall("{*}manifest/{*}item")
                check("nonempty manifest", bool(items))
                check("navigation declared", any("nav" in i.get("properties", "").split() for i in items))
                item_ids = {i.get("id") for i in items}
                for item in items:
                    href = item.get("href", "")
                    url = urlsplit(href)
                    full = posixpath.normpath(posixpath.join(posixpath.dirname(package_path), unquote(url.path)))
                    check("manifest item " + href, not url.scheme and not url.netloc and full in names)
                spine = package.findall("{*}spine/{*}itemref")
                check("nonempty valid spine", bool(spine) and all(i.get("idref") in item_ids for i in spine))
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, RuntimeError) as exc:
        problems.append(str(exc))
    structural = not problems
    epubcheck = {"ran": False, "status": "UNAVAILABLE", "note": "EPUBCheck not installed; no conformance pass claimed"}
    if structural and shutil.which("epubcheck"):
        try:
            run = subprocess.run(["epubcheck", path], capture_output=True, text=True, timeout=120)
            epubcheck = {"ran": True, "status": "OK" if run.returncode == 0 else "ERROR",
                         "exitCode": run.returncode, "tail": (run.stdout + run.stderr)[-2000:]}
            if run.returncode:
                problems.append("EPUBCheck failed")
        except (OSError, subprocess.TimeoutExpired) as exc:
            epubcheck = {"ran": True, "status": "ERROR", "error": str(exc)}
            problems.append("EPUBCheck did not complete")
    return envelope({"file": str(path), "ok": not problems, "valid": not problems,
                     "structuralValid": structural, "publicationReady": False,
                     "validationLevel": "conformance" if epubcheck.get("exitCode") == 0 else "structure_only",
                     "checks": checks, "problems": problems, "epubcheck": epubcheck})


# ------------------------------- print PDF ----------------------------------

def build_pdf(cfg):
    try:
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import (BaseDocTemplate, Frame, PageBreak,
                                        PageTemplate, Paragraph, Spacer)
    except ImportError:
        return envelope({"ok": False, "error": "reportlab not available",
                         "instructions": [
                             "pip install reportlab, then re-run",
                             "or convert the EPUB with Calibre/Kindle Create as a manual fallback"],
                         "output": None})

    md = Path(cfg["manuscript"]).read_text(encoding="utf-8")
    sections = parse_manuscript(md)
    if not sections:
        return envelope({"ok": False, "error": "manuscript produced no sections — fail closed"})

    trim = cfg.get("trim", "6x9")
    if trim not in TRIMS_PT:
        return envelope({"ok": False, "error": f"unknown trim {trim!r}", "trims": sorted(TRIMS_PT)})
    page_w, page_h = TRIMS_PT[trim]

    # font embedding (bundled OFL TTFs)
    body_name, disp_name = "BWBody", "BWDisplay"
    try:
        pdfmetrics.registerFont(TTFont(body_name, cfg.get("bodyFont", "assets/fonts/PlayfairDisplay-Variable.ttf")))
        pdfmetrics.registerFont(TTFont(disp_name, cfg.get("displayFont", "assets/fonts/Oswald-Variable.ttf")))
    except Exception as exc:
        return envelope({"ok": False, "output": None, "fontsEmbedded": [],
                         "error": "Required font unavailable or unsupported: " + str(exc)})
    pdfmetrics.registerFontFamily(body_name, normal=body_name, bold=body_name, italic=body_name, boldItalic=body_name)
    pdfmetrics.registerFontFamily(disp_name, normal=disp_name, bold=disp_name, italic=disp_name, boldItalic=disp_name)

    est_words = len(re.findall(r"[A-Za-z']+", md))
    est_pages = max(24, round(est_words / 280))
    gutter = gutter_inches(est_pages)
    outside = 0.25

    body_style = ParagraphStyle("body", fontName=body_name, fontSize=11, leading=15,
                                spaceAfter=8)
    h1_style = ParagraphStyle("h1", fontName=disp_name, fontSize=22, leading=26,
                              spaceAfter=18)
    h2_style = ParagraphStyle("h2", fontName=disp_name, fontSize=14, leading=17,
                              spaceBefore=10, spaceAfter=6)
    quote_style = ParagraphStyle("quote", parent=body_style, leftIndent=14,
                                 borderColor="#888888", borderWidth=0.5, borderPadding=6,
                                 backColor="#F4F4F4")
    li_style = ParagraphStyle("li", parent=body_style, leftIndent=18, bulletIndent=6)

    out_path = cfg.get("output", "book.pdf")
    if os.path.exists(out_path):
        return envelope({"ok": False, "error": "ALREADY_EXISTS: choose a new output revision"})

    def on_page(canvas, doc):
        canvas.setFont(body_name, 9)
        canvas.drawCentredString(page_w / 2, 0.4 * inch, str(canvas.getPageNumber()))

    def rl_inline(text):
        text = esc(text)
        text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
        text = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<i>\1</i>", text)
        return text

    from reportlab.platypus import Flowable

    class Marker(Flowable):
        """Zero-size flowable; records its rendered page number at draw time."""
        def __init__(self, tag, sink):
            super().__init__()
            self.tag, self.sink = tag, sink
        def wrap(self, w, h):
            return (0, 0)
        def draw(self):
            self.sink[self.tag] = self.canv.getPageNumber()

    def make_doc(path):
        doc = BaseDocTemplate(path, pagesize=(page_w, page_h),
                              leftMargin=gutter * inch, rightMargin=outside * inch,
                              topMargin=0.75 * inch, bottomMargin=0.75 * inch,
                              title=cfg.get("title", "Untitled"), author=cfg.get("author", ""))
        frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="main")
        doc.addPageTemplates([PageTemplate(id="book", frames=[frame], onPage=on_page)])
        return doc

    def section_flowables(s):
        flow = []
        for b in s["blocks"]:
            if b["kind"] == "h1":
                flow.append(Paragraph(rl_inline(b["text"]), h1_style))
                flow.append(Spacer(1, 6))
            elif b["kind"] == "h2":
                flow.append(Paragraph(rl_inline(b["text"]), h2_style))
            elif b["kind"] == "quote":
                flow.append(Paragraph(rl_inline(b["text"]), quote_style))
            elif b["kind"] == "list":
                for item in b["items"]:
                    flow.append(Paragraph(rl_inline(item), li_style, bulletText="•"))
            else:
                flow.append(Paragraph(rl_inline(b["text"]), body_style))
        return flow

    # Pass 1: measure where each section lands (page numbers known at draw time).
    marks = {}
    story = []
    for i, s in enumerate(sections):
        if i > 0:
            story.append(PageBreak())
        story.append(Marker(f"sec{i}", marks))
        story.extend(section_flowables(s))
    make_doc(os.devnull if os.path.exists(os.devnull) else "/tmp/_bw_measure.pdf").build(story)

    # Plan recto starts: chapter starts must be on odd pages. Chapter page counts
    # don't change when blanks are inserted, so simulate and place blanks.
    starts = [marks[f"sec{i}"] for i in range(len(sections))]
    ends = starts[1:] + [max(marks.values())]
    lengths = [max(1, e - st) for st, e in zip(starts, ends)]
    blanks_before = set()
    page = 1  # book opens on recto page 1
    for i, ln in enumerate(lengths):
        if page % 2 == 0:
            blanks_before.add(i)
            page += 1
        page += ln

    # Pass 2: rebuild with the planned blank pages (recto chapter starts).
    story = []
    actual_marks = {}
    for i, s in enumerate(sections):
        if i > 0:
            story.append(PageBreak())
            if i in blanks_before:
                story.append(PageBreak())
        story.append(Marker(f"sec{i}", actual_marks))
        story.extend(section_flowables(s))
    import io
    buffer = io.BytesIO()
    make_doc(buffer).build(story)
    write_new(out_path, buffer.getvalue())

    return envelope({"output": out_path, "format": "print PDF", "trim": trim,
                     "pageSizeInches": [page_w / 72, page_h / 72],
                     "margins": {"gutterIn": gutter, "outsideIn": outside,
                                 "note": "gutter follows the KDP page-count table"},
                     "estimatedPages": est_pages,
                     "rectoChapterStarts": all(p % 2 == 1 for p in actual_marks.values()),
                     "chapterStartPages": actual_marks, "publicationReady": False,
                     "layoutReview": "NOT_RUN; gutter uses estimated pages; facing-page verification pending",
                     "blankPagesInserted": len(blanks_before),
                     "fontsEmbedded": [body_name, disp_name],
                     "bytes": os.path.getsize(out_path),
                     "note": "cover wrap is a separate file — compute with bw_cover_geo.py"})


def main():
    argv = sys.argv[1:]
    if not argv:
        raise SystemExit(__doc__)
    if argv[0] == "epub":
        out = build_epub(json.loads(argv[1] if len(argv) > 1 else sys.stdin.read()))
    elif argv[0] == "validate":
        out = validate_epub(argv[1])
    elif argv[0] == "pdf":
        out = build_pdf(json.loads(argv[1] if len(argv) > 1 else sys.stdin.read()))
    else:
        raise SystemExit(f'unknown command "{argv[0]}" — epub|validate|pdf')
    json.dump(out, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()

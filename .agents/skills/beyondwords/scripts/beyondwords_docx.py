"""Dependency-free editable prose handoff. No inferred metadata or approval.

This deliberately small OOXML writer preserves inline Markdown literally.
It is not a general Markdown converter, typesetter or KDP validator.
"""
from __future__ import annotations
import io
import re
import xml.etree.ElementTree as ET
import zipfile

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
REL = 'http://schemas.openxmlformats.org/package/2006/relationships'
OFFICE = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
CT = 'http://schemas.openxmlformats.org/package/2006/content-types'
DC = 'http://purl.org/dc/elements/1.1/'
CP = 'http://schemas.openxmlformats.org/package/2006/metadata/core-properties'
ET.register_namespace('w', W)


def node(parent, tag, **attributes):
    return ET.SubElement(parent, '{'+W+'}'+tag,
                         {'{'+W+'}'+key: str(value) for key, value in attributes.items()})


def xml(element):
    return ET.tostring(element, encoding='utf-8', xml_declaration=True)


def checked(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label+' must be nonempty text')
    if any(not (c in '\t\n\r' or 0x20 <= ord(c) <= 0xD7FF or
                0xE000 <= ord(c) <= 0xFFFD or 0x10000 <= ord(c) <= 0x10FFFF) for c in value):
        raise ValueError(label+' contains a character XML cannot represent')
    return value


def blocks(manuscript):
    """Keep every nonempty line, with no frontmatter stripping or chapter sorting."""
    paragraph = []
    result = []
    def flush():
        if paragraph:
            result.append(('Normal', '\n'.join(paragraph)))
            paragraph.clear()
    for line in manuscript.splitlines():
        heading = re.fullmatch(r'(#{1,6}) +(.+)', line)
        if heading:
            flush(); result.append(('Heading'+str(len(heading[1])), heading[2]))
        elif not line.strip():
            flush()
        elif re.match(r'\s*(?:[-*+] |\d+[.)] )', line):
            flush(); result.append(('Normal', line))
        else:
            paragraph.append(line)
    flush()
    return result


def run(parent, value):
    r = node(parent, 'r')
    # Tabs and soft line breaks must be OOXML elements, not control text.
    for part in re.split(r'(\t|\n)', value):
        if part == '\t': node(r, 'tab')
        elif part == '\n': node(r, 'br')
        elif part:
            t = node(r, 't'); t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve'); t.text = part


def paragraph(parent, value, style='Normal', bookmark=None):
    p = node(parent, 'p'); prop = node(p, 'pPr'); node(prop, 'pStyle', val=style)
    if bookmark is not None: node(p, 'bookmarkStart', id=bookmark, name='chapter_'+str(bookmark))
    run(p, value)
    if bookmark is not None: node(p, 'bookmarkEnd', id=bookmark)
    return p


def styles(language):
    root = ET.Element('{'+W+'}styles')
    defaults = node(root, 'docDefaults'); rp = node(node(defaults, 'rPrDefault'), 'rPr')
    node(rp, 'rFonts', ascii='Times New Roman', hAnsi='Times New Roman', cs='Times New Roman')
    node(rp, 'sz', val=24); node(rp, 'color', val='000000'); node(rp, 'lang', val=language)
    pp = node(node(defaults, 'pPrDefault'), 'pPr')
    node(pp, 'spacing', after=160, line=300, lineRule='auto'); node(pp, 'widowControl')
    for name, size in [('Normal',24), ('Title',40), ('Subtitle',28), ('Contents',28)] + [('Heading'+str(i), 32 if i==1 else 26) for i in range(1,7)]:
        style = node(root, 'style', type='paragraph', styleId=name)
        if name=='Normal': style.set('{'+W+'}default','1')
        node(style, 'name', val='heading '+name[7:] if name.startswith('Heading') else name)
        if name!='Normal': node(style, 'basedOn', val='Normal')
        node(style, 'next', val='Normal'); node(style, 'qFormat')
        pp=node(style, 'pPr')
        if name!='Normal': node(pp, 'keepNext'); node(pp, 'spacing', before=240, after=180)
        if name.startswith('Heading'): node(pp, 'outlineLvl', val=int(name[7:])-1)
        if name=='Heading1': node(pp, 'pageBreakBefore')
        rp=node(style,'rPr'); node(rp,'sz',val=size); node(rp,'color',val='000000')
        if name!='Normal': node(rp,'b')
    return root


def build_docx(manuscript, metadata):
    checked(manuscript, 'manuscript')
    if len(manuscript.encode('utf-8')) > 8*1024*1024: raise ValueError('Manuscript exceeds 8 MiB')
    for key in ('title','author','language'): checked(metadata.get(key), key)
    content = blocks(manuscript)
    root = ET.Element('{'+W+'}document'); body = node(root,'body')
    paragraph(body, metadata['title'], 'Title'); paragraph(body, metadata['author'], 'Subtitle')
    chapters = [text for style,text in content if style=='Heading1']
    if chapters:
        paragraph(body, 'Contents', 'Contents')
        for index,title in enumerate(chapters):
            p=node(body,'p'); link=node(p,'hyperlink',anchor='chapter_'+str(index),history=1); run(link,title)
    index=0
    for style,text in content:
        paragraph(body,text,style,index if style=='Heading1' else None)
        if style=='Heading1': index+=1
    section=node(body,'sectPr')
    # A4 editorial handoff; deliberately independent from the chosen print trim.
    node(section,'pgSz',w=11906,h=16838)
    node(section,'pgMar',top=1440,right=1440,bottom=1440,left=1440,header=720,footer=720,gutter=0)
    # Default OPC namespaces also work with LibreOffice's file detector.
    # Local xmlns attributes avoid changing ElementTree's global namespace map.
    types=ET.Element('Types', xmlns=CT)
    for extension, media in [('rels','application/vnd.openxmlformats-package.relationships+xml'),('xml','application/xml')]:
        ET.SubElement(types,'Default',Extension=extension,ContentType=media)
    for part, media in [('word/document.xml','application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'),('word/styles.xml','application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml'),('docProps/core.xml','application/vnd.openxmlformats-package.core-properties+xml')]:
        ET.SubElement(types,'Override',PartName='/'+part,ContentType=media)
    relationships=ET.Element('Relationships', xmlns=REL)
    ET.SubElement(relationships,'Relationship',Id='rId1',Type=OFFICE+'officeDocument',Target='word/document.xml')
    ET.SubElement(relationships,'Relationship',Id='rId2',Type=REL+'/metadata/core-properties',Target='docProps/core.xml')
    document_rels=ET.Element('Relationships', xmlns=REL)
    ET.SubElement(document_rels,'Relationship',Id='rId1',Type=OFFICE+'styles',Target='styles.xml')
    properties=ET.Element('{'+CP+'}coreProperties')
    for key,value in [('title',metadata['title']),('creator',metadata['author']),('language',metadata['language'])]:
        ET.SubElement(properties,'{'+DC+'}'+key).text=value
    parts={'[Content_Types].xml':types,'_rels/.rels':relationships,'word/document.xml':root,
           'word/styles.xml':styles(metadata['language']),'word/_rels/document.xml.rels':document_rels,
           'docProps/core.xml':properties}
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as package:
        for name,element in sorted(parts.items()):
            entry=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0)); entry.compress_type=zipfile.ZIP_DEFLATED
            package.writestr(entry,xml(element))
    return buffer.getvalue(), dict(chapters=len(chapters), editable=True, intended_use='EDITORIAL_HANDOFF',
        page_profile='A4 editorial copy; not print trim', contents='INTERNAL_BOOKMARK_LINKS',
        inline_markdown='PRESERVED_LITERAL', cover_embedded=False, fonts_embedded=False,
        word_application_acceptance='NOT_RUN', visual_review='NOT_RUN', retailer_acceptance='NOT_RUN')

#!/usr/bin/env python3
"""Exercise the published plan/prepare examples and inspect actual edition files."""
import json
from pathlib import Path
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / '.agents/skills/beyondwords'
sys.path.insert(0, str(SKILL/'scripts'))
from beyondwords_book import BookStore
import publishing_project


def check(root):
    guide = (SKILL/'references/12-complete-workflow.md').read_text(encoding='utf-8')
    examples = [json.loads(block) for block in re.findall(r'```json\n(.*?)\n```', guide, re.S)]
    example, = [item for item in examples if 'plan' in item and 'prepare' in item]
    plan, package = example['plan'], example['prepare']
    initial = publishing_project.initialize(root/'project', title=plan['title'], country='US',
                                            language='en', budget='0', currency='USD')
    store = BookStore(root/'project', initial['project_id'])
    state = store.enable(initial['revision'], synthetic=True)
    state = store.plan(state['revision'], plan)
    chapters = plan['chapters']
    for chapter in chapters:
        body = '# '+chapter['title']+'\n\nSynthetic paragraph for '+chapter['id']+'.'
        state = store.chapter(state['revision'], dict(id=chapter['id'], body=body, provenance='ai_generated',
                              rights_basis='Synthetic release fixture', change_summary='Initial test draft'))
    edition_id, = package['edition_ids']
    state = store.edition(state['revision'], dict(id=edition_id, format='both'))
    store.export('edition', edition_id, root/'edition')
    state = store.prepare(state['revision'], package)
    store.export('package', package['id'], root/'package')
    state = store.edition(state['revision'], dict(id='editorial', format='docx'))
    store.export('edition', 'editorial', root/'word')
    pages = PdfReader(root/'edition/interior.pdf').pages
    if len(pages) != len(chapters)+1:
        raise ValueError(f'Unexpected PDF pagination: {len(pages)} pages')
    with zipfile.ZipFile(root/'edition/book.epub') as epub:
        sections = sorted(n for n in epub.namelist() if re.fullmatch(r'OEBPS/text/ch\d+\.xhtml', n))
        if len(sections) != len(pages):
            raise ValueError('EPUB chapter count differs from the synthetic plan')
        for i, chapter in enumerate(chapters, start=1):
            title = chapter['title']
            body = 'Synthetic paragraph for '+chapter['id']+'.'
            lines = pages[i].extract_text().splitlines()
            section = ET.fromstring(epub.read(sections[i]))
            headings = [h.text for h in section.findall('.//{*}h1')]
            if lines.count(title) != 1 or body not in lines or headings != [title]:
                raise ValueError(f'Chapter heading or body mismatch in {title}')
    with zipfile.ZipFile(root/'word/review.docx') as word:
        doc = ET.fromstring(word.read('word/document.xml'))
        links = doc.findall('.//{*}bookmarkStart')
        if len(links) != len(pages):
            raise ValueError('Word chapter count differs from the synthetic plan')
    print(f'Passed the documented plan and prepare inputs and {len(pages)}-section PDF, EPUB and DOCX exports.')


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='beyondwords-export-') as folder:
        check(Path(folder))

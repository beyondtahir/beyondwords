#!/usr/bin/env python3
"""bw_build.py — Beyondwords manuscript assembly (original implementation).

Assembles chapter markdown into a single publishable manuscript: title page →
copyright/disclaimer → table of contents → chapters → review-ask page.
Validates structure (takeaway box per chapter, intro/conclusion present) and
word counts against an optional chapter contract.

Can consume a beyondwords-project.json handoff (from bw_discover.py / the research
skill) to prefill title/author/spec — the suite data loop.

Usage (JSON envelope out):
  bw_build.py '{"chaptersDir":"chapters/","output":"manuscript.md",
                "title":"...","subtitle":"...","author":"...",
                "contract":"contract.json","project":"beyondwords-project.json"}'
"""
import datetime
import glob
import json
import os
import re
import sys

from pathlib import Path
import io
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from bw_io import write_new

TOOL = "bw_build"
VERSION = "1.0.0"
PROJECT_SCHEMA = "beyondwords-project/1.0"

COPYRIGHT_PAGE = """Copyright © {year} {author}. All rights reserved.

No part of this book may be reproduced without written permission, except for brief quotations in reviews.

Disclaimer: The information in this book is provided for general educational purposes only and is not professional, medical, legal, or financial advice. The author and publisher make no representations about results and disclaim liability for actions taken based on this content. Consult a qualified professional for advice about your specific situation."""

REVIEW_PAGE = """# One Last Thing

You are welcome to leave an honest review sharing your own reading experience. A review is optional. Thank you for reading."""


def envelope(payload):
    return {"tool": TOOL, "version": VERSION, "ok": payload.get("assembled", False), **payload}


def wc(text):
    return len(re.findall(r"[A-Za-z']+", text))


def takeaway_present(text):
    return bool(re.search(r"(?im)^\s*(?:>|\*\*)?\s*key takeaways?", text))


def heading_of(path, text):
    m = re.search(r"(?m)^#{1,2}\s+(.+)$", text)
    return m.group(1).strip() if m else os.path.splitext(os.path.basename(path))[0]


def build(cfg):
    folder = cfg["chaptersDir"]
    files = sorted(f for f in glob.glob(os.path.join(folder, "*.md"))
                   if not os.path.basename(f).startswith("00_"))
    if not files:
        raise SystemExit(f"no chapter .md files in {folder}")

    project = None
    if cfg.get("project") and os.path.exists(cfg["project"]):
        project = json.load(open(cfg["project"]))
        if project.get("schema") != PROJECT_SCHEMA:
            raise SystemExit(f"project file schema must be {PROJECT_SCHEMA}")

    title = cfg.get("title") or (project or {}).get("title") or "Untitled"
    author = cfg.get("author") or (project or {}).get("author") or "Anonymous"
    contract = None
    if cfg.get("contract") and os.path.exists(cfg["contract"]):
        contract = json.load(open(cfg["contract"]))

    chapters, problems = [], []
    for i, path in enumerate(files, 1):
        text = open(path, encoding="utf-8").read()
        name = heading_of(path, text)
        words = wc(text)
        row = {"index": i, "file": os.path.basename(path), "title": name,
               "wordCount": words, "takeawayBox": takeaway_present(text)}
        if not row["takeawayBox"]:
            problems.append(f"chapter {i} ({name}): no key-takeaway box")
        if contract and i - 1 < len(contract.get("chapters", [])):
            c = contract["chapters"][i - 1]
            lo, hi = c.get("wordMin", 1000), c.get("wordMax", 2000)
            row["contract"] = {"wordMin": lo, "wordMax": hi, "withinBounds": lo <= words <= hi}
            if not row["contract"]["withinBounds"]:
                problems.append(f"chapter {i} ({name}): {words} words outside contract {lo}–{hi}")
        chapters.append(row)

    intro_ok = any(re.search(r"intro", c["title"], re.I) for c in chapters[:2])
    concl_ok = any(re.search(r"conclusion|final|one last", c["title"], re.I) for c in chapters[-2:])
    if not intro_ok:
        problems.append("no introduction detected in the first two chapters")
    if not concl_ok:
        problems.append("no conclusion detected in the last two chapters")

    body = [
        f"# {title}\n\n{'*' + cfg['subtitle'] + '*' + chr(10) + chr(10) if cfg.get('subtitle') else ''}### {author}",
        COPYRIGHT_PAGE.format(year=datetime.date.today().year, author=author),
        "# Contents\n\n" + "\n".join(f"{c['index']}. {c['title']}" for c in chapters),
    ]
    body += [open(p, encoding="utf-8").read().strip() for p in files]
    body.append(REVIEW_PAGE)
    manuscript = "\n\n---\n\n".join(body) + "\n"

    out_path = cfg.get("output", "manuscript.md")
    write_new(out_path, manuscript.encode("utf-8"))

    return envelope({
        "output": out_path, "title": title, "author": author,
        "projectConsumed": bool(project),
        "chapters": chapters, "totalWords": sum(c["wordCount"] for c in chapters),
        "structure": {"titlePage": True, "disclaimerPage": True, "toc": True,
                      "introPresent": intro_ok, "conclusionPresent": concl_ok,
                      "reviewAskPage": True},
        "validationIssues": problems,
        "assembled": True, "ready": False, "structuralChecksPassed": not problems,
        "editorialApproval": "NOT_EVALUATED", "publicationReadiness": "NOT_EVALUATED",
        "nextStep": "run bw_lint.py on the output, then hand to beyondwords-validator for the final gate",
    })


def main():
    raw = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()
    json.dump(build(json.loads(raw)), sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""bw_lint.py — Beyondwords manuscript lint (original implementation).

Deterministic prose-quality heuristics — an editing checklist, not an AI detector.

Per chapter + overall:
  - em-dash density per 1,000 words
  - stock-phrase hits (40+ formulaic AI transitions)
  - sentence-length variation (burstiness: coefficient of variation)
  - passive-voice estimate (auxiliary + participle heuristic)
  - Flesch reading ease per chapter
  - repeated-paragraph fingerprinting (normalized-paragraph hashing, cross-chapter)
  - dialogue ratio (share of sentences containing quoted speech — fiction health)
  - cross-chapter 5-gram overlap (recycled content)

Usage: bw_lint.py manuscript.md   |   bw_lint.py chapters/
Output: JSON envelope with per-chapter flags, overall humanScore (0–100), fixes.
Chapters split on top-level markdown headings (# or ##).
"""
import hashlib
import json
import os
import re
import statistics
import sys

TOOL = "bw_lint"
VERSION = "1.0.0"

STOCK_PHRASES = [
    "in today's digital age", "in today's fast-paced world", "in conclusion",
    "moreover", "furthermore", "it's important to note", "it is important to note",
    "it goes without saying", "at the end of the day", "when it comes to",
    "in the world of", "delve into", "delve", "unlock the", "unlock your",
    "elevate your", "take your", "to the next level", "game-changer",
    "look no further", "whether you're a beginner", "in this day and age",
    "needless to say", "as we all know", "it cannot be denied",
    "plays a crucial role", "plays a vital role", "a testament to",
    "navigate the", "landscape of", "embark on", "tapestry", "vibrant",
    "bustling", "in essence", "by and large", "first and foremost",
    "last but not least", "bear in mind", "keep in mind that",
    "it's worth noting", "worth mentioning", "dive into", "deep dive",
    "supercharge", "harness the power", "in the realm of", "a double-edged sword",
]

DASH_CHARS = "—–"
PASSIVE = re.compile(r"\b(?:is|are|was|were|be|been|being)\s+\w+(?:ed|en)\b", re.I)
SPEECH = re.compile(r'["“][^"”]{3,}["”]')


def envelope(payload):
    return {"tool": TOOL, "version": VERSION, "ok": True, **payload}


def tokenize(text):
    return re.findall(r"[A-Za-z']+", text.lower())


def sentence_split(text):
    return [s.strip() for s in re.split(r"[.!?]+(?:\s|$)", text) if len(s.strip()) > 2]


def syllables(word):
    word = word.lower()
    groups = re.findall(r"[aeiouy]+", word)
    n = len(groups)
    if word.endswith("e") and n > 1:
        n -= 1
    return max(1, n)


def flesch(text):
    words = tokenize(text)
    sents = sentence_split(text)
    if not words or not sents:
        return None
    wps = len(words) / len(sents)
    spw = sum(syllables(w) for w in words) / len(words)
    return round(206.835 - 1.015 * wps - 84.6 * spw, 1)


def para_fingerprint(paragraph):
    norm = " ".join(tokenize(paragraph))
    if len(norm) < 60:
        return None
    return hashlib.sha1(norm.encode()).hexdigest()[:12]


def shingle_set(tokens, n=5):
    return {tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)}


def chapter_chunks(text):
    parts = re.split(r"(?m)^(#{1,2})\s+(.+)$", text)
    chunks = []
    if parts[0].strip():
        chunks.append(("preamble", parts[0].strip()))
    for i in range(1, len(parts), 3):
        chunks.append((parts[i + 1].strip(), parts[i + 2].strip()))
    return chunks or [("manuscript", text)]


def lint_one(name, text):
    issues, fixes = [], []
    words = tokenize(text)
    wc = max(len(words), 1)

    dashes = sum(text.count(d) for d in DASH_CHARS)
    dash_rate = dashes / wc * 1000
    dash_bad = dash_rate > 8
    if dash_bad:
        issues.append(f"em-dash density {dash_rate:.1f}/1000 words (>8)")
        fixes.append(f"[{name}] swap most em-dashes for commas, colons, or periods")

    low = text.lower()
    hits = [p for p in STOCK_PHRASES if p in low]
    if hits:
        issues.append(f"stock phrases: {', '.join(hits[:8])}{' …' if len(hits) > 8 else ''}")
        for p in hits[:5]:
            line = text[: low.find(p)].count("\n") + 1
            fixes.append(f'[{name}] line ~{line}: cut or rewrite "{p}"')

    sents = sentence_split(text)
    lengths = [len(tokenize(s)) for s in sents if tokenize(s)]
    cv = round(statistics.stdev(lengths) / statistics.mean(lengths), 2) if len(lengths) >= 5 else None
    flat = cv is not None and cv < 0.45
    if flat:
        issues.append(f"flat sentence rhythm (variation CV {cv} < 0.45)")
        fixes.append(f"[{name}] alternate short punches with longer sentences; vary paragraph shapes")

    passive_share = len(PASSIVE.findall(text)) / max(len(sents), 1)
    passive_bad = passive_share > 0.25
    if passive_bad:
        issues.append(f"passive voice ≈{passive_share:.0%} of sentences (>25%)")
        fixes.append(f"[{name}] recast passive sentences with an active subject")

    ease = flesch(text)
    dialogue = round(len(SPEECH.findall(text)) / max(len(sents), 1), 3)

    return {
        "chapter": name, "wordCount": wc,
        "emDashPer1000": round(dash_rate, 1),
        "stockPhrases": hits,
        "sentenceVariationCV": cv,
        "passiveShare": round(passive_share, 3),
        "fleschReadingEase": ease,
        "dialogueRatio": dialogue,
        "flags": {"emDashes": dash_bad, "stockPhrases": bool(hits),
                  "flatRhythm": flat, "passiveVoice": passive_bad},
        "issues": issues, "fixes": fixes,
    }


MIN_WORDS = 500  # below this there is not enough text to evaluate — fail closed


def lint(text):
    total_words = len(tokenize(text))
    if total_words < MIN_WORDS:
        return envelope({
            "ok": False,
            "humanScore": 0,
            "verdict": "INSUFFICIENT CONTENT",
            "error": f"manuscript has {total_words} words (< {MIN_WORDS}); nothing meaningful to lint",
            "note": "fail-closed: an empty or tiny manuscript scores 0, never a pass",
            "chapters": [], "crossChapterRepetition": [], "duplicateParagraphs": [], "fixes": [
                "write the manuscript first — a lint of empty text is meaningless"],
        })
    chunks = chapter_chunks(text)
    reports = [lint_one(n, t) for n, t in chunks]

    shingles = [(n, shingle_set(tokenize(t))) for n, t in chunks if len(tokenize(t)) > 10]
    recycled, recycle_fixes = [], []
    for i in range(len(shingles)):
        for j in range(i + 1, len(shingles)):
            shared = shingles[i][1] & shingles[j][1]
            if len(shared) >= 3:
                recycled.append({"chapters": [shingles[i][0], shingles[j][0]],
                                 "sharedShingles": len(shared),
                                 "examples": [" ".join(g) for g in list(shared)[:3]]})
                recycle_fixes.append(
                    f"[{shingles[j][0]}] {len(shared)} repeated 5-grams shared with [{shingles[i][0]}] — cut or differentiate the recycled point")

    fingerprints = {}
    dup_paragraphs = []
    for n, t in chunks:
        for p in re.split(r"\n\s*\n", t):
            fp = para_fingerprint(p)
            if fp:
                if fp in fingerprints:
                    dup_paragraphs.append({"fingerprint": fp,
                                           "firstSeen": fingerprints[fp], "repeatedIn": n})
                else:
                    fingerprints[fp] = n
    dup_fixes = [f"[{d['repeatedIn']}] duplicates a paragraph from [{d['firstSeen']}] — delete one"
                 for d in dup_paragraphs]

    flag_count = sum(sum(r["flags"].values()) for r in reports)
    max_flags = max(len(reports) * 4, 1)
    penalty = min(20, len(recycled) * 7) + min(15, len(dup_paragraphs) * 5)
    score = max(0, round(100 - (flag_count / max_flags) * 80 - penalty))

    return envelope({
        "humanScore": score,
        "verdict": "PASS" if score >= 70 else ("NEEDS WORK" if score >= 45 else "AI-SLOP HEAVY"),
        "chapterCount": len(chunks),
        "chapters": reports,
        "crossChapterRepetition": recycled,
        "duplicateParagraphs": dup_paragraphs,
        "fixes": [f for r in reports for f in r["fixes"]] + recycle_fixes + dup_fixes,
        "note": "Deterministic heuristics, not an AI detector. Use as an editing checklist; a human editing pass is mandatory regardless of score.",
    })


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    target = sys.argv[1]
    if os.path.isdir(target):
        text = "\n\n".join(
            f"# {os.path.splitext(f)[0]}\n\n" + open(os.path.join(target, f), encoding="utf-8").read()
            for f in sorted(os.listdir(target)) if f.endswith((".md", ".txt")))
    else:
        text = open(target, encoding="utf-8").read()
    json.dump(lint(text), sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()

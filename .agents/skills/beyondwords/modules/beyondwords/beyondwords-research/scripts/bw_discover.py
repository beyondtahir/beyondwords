#!/usr/bin/env python3
"""Legacy supplied-fixture discovery and handoff compatibility.

Use publishing_core.py research for permission-scoped real collection and
transactional project state. This legacy path has no live transport, numeric
opportunity score or demand verdict. Generated keyword ideas are hypotheses.
Its JSON state/cache files are not a concurrent project database.

Commands: from-persona, resume, validate-project; use --offline-fixtures DIR.
Fixtures: autocomplete.json, serp_<slug>.html, detail_<ASIN>.html.
"""
import json
import os
import re
import string
import sys
import time

TOOL = "bw_discover"
VERSION = "1.0.0"
CACHE_TTL = 14 * 86400
PROJECT_SCHEMA = "beyondwords-project/1.0"

# Our own modifier matrices (from the persona-first transcript method):
GOAL_MODS = ["for beginners", "step by step", "in 30 days", "made simple", "for busy {persona}"]
PROBLEM_MODS = ["who hate {objection}", "on a budget", "with no experience", "after 50", "starting over"]
FORMAT_MODS = ["workbook", "guide", "planner", "journal", "handbook"]
EVENT_TERMS = ("world cup", "olympics", "fifa", "election")


def envelope(payload):
    return {"tool": TOOL, "version": VERSION, "ok": True, **payload}


def slug(text):
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


# ------------------------------ data sources --------------------------------

class LiveSource:
    def __init__(self):
        import bw_amazon
        self.engine = bw_amazon
        self.session = bw_amazon.BrowserSession()
        self.session.warm_up()

    def autocomplete(self, term):
        self._pause()
        return self.engine.run_suggest(self.session, term).get("suggestions", [])

    def serp(self, keyword):
        self._pause()
        r = self.engine.run_search(self.session, keyword, kindle=False)
        return r if r.get("blocked") or r.get("ok") is False else r.get("results", [])

    def detail(self, asin):
        self._pause()
        return self.engine.run_product(self.session, asin)

    @staticmethod
    def _pause():
        import random
        time.sleep(random.uniform(2.0, 4.0))


class FixtureSource:
    """Deterministic offline mode — fixtures dir with autocomplete.json + HTML files."""

    def __init__(self, folder):
        import bw_amazon
        self.engine = bw_amazon
        self.folder = folder

    def autocomplete(self, term):
        path = os.path.join(self.folder, "autocomplete.json")
        data = json.load(open(path)) if os.path.exists(path) else {}
        return data.get(term, data.get("*", []))

    def serp(self, keyword):
        path = os.path.join(self.folder, f"serp_{slug(keyword)}.html")
        if not os.path.exists(path):
            return []
        return self.engine.parse_search_cards(open(path, encoding="utf-8", errors="replace").read())

    def detail(self, asin):
        path = os.path.join(self.folder, f"detail_{asin}.html")
        if not os.path.exists(path):
            return {}
        return self.engine.parse_product_page(open(path, encoding="utf-8", errors="replace").read())


# ------------------------------ persistence ---------------------------------

def read_json(path, fallback):
    if path and os.path.exists(path):
        try:
            with open(path, encoding='utf-8') as stream:
                return json.load(stream)
        except (OSError, ValueError) as exc:
            raise ValueError("CORRUPT_STATE: preserve and inspect the original") from exc
    return fallback


def write_json(path, data):
    if path:
        import tempfile
        from pathlib import Path
        target = Path(path)
        if target.is_symlink(): raise ValueError("SYMLINK_STATE: refused")
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".bw-state-", dir=target.parent)
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(data, stream, indent=2); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)


def detail_cached(source, cache, asin):
    hit = cache.get(asin)
    if hit and time.time() - hit.get("ts", 0) < CACHE_TTL:
        return hit["data"]
    data = source.detail(asin)
    if data and not data.get("blocked"):
        cache[asin] = {"ts": time.time(), "data": data}
    return data


# --------------------------- generation + scoring ---------------------------

def generate_angles(persona, interest):
    """Persona × interest × modifier matrices → candidate keyword angles."""
    p, i = persona.strip().lower(), interest.strip().lower()
    objection = "gyms"  # generic objection token; the agent refines modifiers in conversation
    candidates = {f"{i} for {p}"}
    for gm in GOAL_MODS:
        candidates.add(f"{i} {gm}".format(persona=p))
        candidates.add(f"{i} for {p} {gm.split(' for ')[0]}".format(persona=p).strip())
    for fm in FORMAT_MODS:
        candidates.add(f"{i} {fm} for {p}")
    for pm in PROBLEM_MODS[:3]:
        candidates.add(f"{i} for {p} {pm}".format(objection=objection))
    return sorted(candidates)


def classify(bsr, reviews):
    return "UNKNOWN"


def opportunity_score(keyword, persona, books):
    return None, {"status": "UNAVAILABLE", "reason": "Ranks and review counts do not establish demand."}


def verdict(score, counts):
    return "UNKNOWN"  # A heuristic score is not evidence of demand or sales.


# -------------------------------- pipeline ----------------------------------

def run(persona, interest, max_candidates, state_path, cache_path, source):
    state = read_json(state_path, {"persona": persona, "interest": interest,
                                   "candidates": None, "results": {}, "done": False})
    if state.get("persona") != persona or state.get("interest") != interest:
        raise ValueError("PROJECT_MISMATCH: choose a new state file; existing work was preserved")
    cache_state = read_json(cache_path, {"persona": persona, "interest": interest, "items": {}})
    if cache_state.get("persona") != persona or cache_state.get("interest") != interest:
        raise ValueError("PROJECT_MISMATCH: choose a new cache; existing work preserved")
    cache = cache_state["items"]

    if state["candidates"] is None:
        angles = generate_angles(persona, interest)
        expanded, seen = [], set()
        for angle in angles:
            expanded.append(angle)
            for sug in source.autocomplete(angle):
                s = sug.strip().lower()
                if s and s not in seen and s not in angles:
                    seen.add(s)
                    expanded.append(s)
        state["candidates"] = expanded[:max_candidates]
        write_json(state_path, state)

    results = state["results"]
    for kw in state["candidates"]:
        if kw in results:
            continue
        response = source.serp(kw)
        if isinstance(response, dict):
            results[kw] = {"verdict": "UNKNOWN", "reason": "source unavailable or blocked", "sourceResult": response, "books": []}
            write_json(state_path, state)
            continue
        cards = [c for c in response if not c.get("sponsored")][:5]
        if not cards:
            results[kw] = {"verdict": "UNKNOWN", "reason": "no usable observations", "books": []}
            write_json(state_path, state)
            continue
        page1_authority = sum(1 for c in cards if (c.get("reviews") or 0) >= 500)
        if False:  # Retired unsupported authority threshold.
            results[kw] = {"verdict": "SKIP", "reason": "page 1 authority-dominated", "books": []}
            write_json(state_path, state)
            continue
        books, counts = [], {}
        for c in cards[:5]:
            data = detail_cached(source, cache, c["asin"]) if c.get("asin") else {}
            write_json(cache_path, cache_state)
            bsr = data.get("bsr")
            reviews = c.get("reviews") if c.get("reviews") is not None else data.get("reviews")
            cls = classify(bsr, reviews)
            counts[cls] = counts.get(cls, 0) + 1
            books.append({"asin": c.get("asin"), "title": c.get("title") or data.get("title"),
                          "bsr": bsr, "reviews": reviews,
                          "price": c.get("price") if c.get("price") is not None else data.get("price"),
                          "class": cls})
        score, parts = opportunity_score(kw, persona, books)
        results[kw] = {"verdict": verdict(score, counts), "opportunityScore": score,
                       "scoreBreakdown": parts, "counts": counts, "books": books}
        write_json(state_path, state)

    state["done"] = True
    write_json(state_path, state)

    ranked = sorted(results.items(), key=lambda kv: kv[0], reverse=True)
    return ranked, state


def export_project(path, persona, interest, results, ranked):
    if not ranked:
        return None
    best_kw, best = ranked[0]
    project = {
        "schema": PROJECT_SCHEMA,
        "title": None,
        "author": None,
        "persona": {"description": persona, "pointA": None, "pointB": None},
        "niche": {"keyword": best_kw, "opportunityScore": best.get("opportunityScore"),
                  "verdict": best.get("verdict"), "competitors": best.get("books", [])},
        "spec": {"bookType": None, "chapterCount": None, "priceBand": None, "formats": ["ebook", "paperback"]},
        "verdicts": {"sellability": None, "banRisk": None},
        "readiness": {"overall": None, "areas": {}},
        "provenance": {"seededBy": f"{TOOL} {VERSION}", "interest": interest, "ts": time.time()},
    }
    write_json(path, project)
    return path


def validate_project(path):
    data = json.load(open(path))
    problems = []
    if data.get("schema") != PROJECT_SCHEMA:
        problems.append(f"schema must be \"{PROJECT_SCHEMA}\"")
    for key in ("persona", "niche", "spec", "verdicts", "readiness"):
        if key not in data:
            problems.append(f"missing top-level key: {key}")
    if "persona" in data and not data["persona"].get("description"):
        problems.append("persona.description is required")
    return envelope({"path": path, "valid": not problems, "problems": problems,
                     "schema": PROJECT_SCHEMA})


def main():
    argv = sys.argv[1:]
    if not argv:
        raise SystemExit(__doc__)

    def opt(flag, default=None):
        return argv[argv.index(flag) + 1] if flag in argv else default

    cmd = argv[0]
    if cmd == "validate-project":
        out = validate_project(argv[1])
    else:
        fixture_dir = opt("--offline-fixtures")
        source = FixtureSource(fixture_dir) if fixture_dir else LiveSource()
        state_path = opt("--state", "bw_discover_state.json")
        cache_path = opt("--cache", "bw_asin_cache.json")
        if cmd == "from-persona":
            persona, interest = opt("--persona"), opt("--interest")
            if not (persona and interest):
                raise SystemExit("--persona and --interest are required")
            ranked, state = run(persona, interest, int(opt("--max-candidates", 12)),
                                state_path, cache_path, source)
        elif cmd == "resume":
            state = read_json(state_path, None)
            if not state:
                raise SystemExit(f"no state at {state_path}")
            ranked, state = run(state["persona"], state["interest"],
                                len(state["candidates"] or []), state_path, cache_path, source)
        else:
            raise SystemExit(f'unknown command "{cmd}" — from-persona|resume|validate-project')

        groups = {"GO": [], "WATCH": [], "SKIP": [], "UNKNOWN": []}
        for kw, r in ranked:
            groups[r["verdict"]].append({"keyword": kw, "opportunityScore": r.get("opportunityScore")})
        out = envelope({
            "persona": state["persona"], "interest": state["interest"],
            "candidatesEvaluated": len(state["results"]),
            "ranked": [{"keyword": kw, **{k: v for k, v in r.items() if k != "books"}}
                       for kw, r in ranked],
            "verdicts": groups,
            "detail": state["results"],
            "stateFile": state_path, "cacheFile": cache_path,
        })
        if opt("--export-project"):
            out["projectFile"] = export_project(opt("--export-project"), state["persona"],
                                                state["interest"], state["results"], ranked)
    json.dump(out, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()

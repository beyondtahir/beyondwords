#!/usr/bin/env python3
"""Beyondwords offline Amazon HTML parsers and legacy command compatibility.

Network collection moved to the permission-scoped BP-002 research adapter.
Missing selected editions and overall ranks remain unknown. Parser output is
untrusted extraction, not a verified market recommendation.
"""
import json
import re
import sys
import time
import urllib.parse

TOOL = "bw_amazon"
VERSION = "1.0.0"
HOST = "https://www.amazon.com"

CAPTCHA_SIGNALS = ("Robot Check", "validateCaptcha", "Enter the characters you see below")
SOFT_BLOCK_SIGNALS = ("Sorry! Something went wrong", "api.crhc.amazon.com")


class TransportError(Exception):
    pass


class BrowserSession:
    """Compatibility object: legacy network transport is intentionally unavailable.

    Use publishing_core.py research capture with an explicit source access record.
    Offline parsers remain available. No implicit installation or challenge bypass.
    """
    engine = "UNAVAILABLE: use the permission-scoped research adapter"

    def warm_up(self):
        return None

    def get(self, url, referer=None, attempts=1):
        raise TransportError(self.engine)


def _looks_soft_blocked(body: str) -> bool:
    if not body:
        return True
    if any(sig in body for sig in SOFT_BLOCK_SIGNALS):
        return True
    return False


def captcha_page(body: str) -> bool:
    return any(sig in body for sig in CAPTCHA_SIGNALS)


def blocked_payload() -> dict:
    return envelope({"blocked": True,
                     "advice": "Use the research importer for content you are authorized to collect and retain."})


def envelope(payload: dict) -> dict:
    return {"tool": TOOL, "version": VERSION, "ok": not (payload.get("blocked") or payload.get("error")), **payload}


# ------------------------- original parser toolkit --------------------------

def strip_markup(fragment: str) -> str:
    import html as h
    return h.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


def slice_blocks(body: str, marker_pattern: str):
    """Yield (match, chunk) for each occurrence of the marker pattern; the chunk
    runs to the next marker or a bounded window — data-attribute-driven splitting."""
    hits = list(re.finditer(marker_pattern, body))
    for i, m in enumerate(hits):
        end = hits[i + 1].start() if i + 1 < len(hits) else min(m.start() + 40000, len(body))
        yield m, body[m.start():end]


def first_attr(chunk: str, pattern: str):
    m = re.search(pattern, chunk, re.S)
    return m.group(1) if m else None


def to_number(text):
    if text is None:
        return None
    t = text.replace(" ", " ").strip()
    m = re.search(r"([\d][\d.,\s]*)", t)
    if not m:
        return None
    raw = m.group(1).strip().replace(" ", "")
    if "," in raw and "." in raw:
        raw = raw.replace(",", "") if raw.rfind(".") > raw.rfind(",") else raw.replace(".", "").replace(",", ".")
    elif "," in raw:
        parts = raw.split(",")
        raw = raw.replace(",", ".") if len(parts[-1]) == 2 and len(parts) == 2 else raw.replace(",", "")
    try:
        return float(raw)
    except ValueError:
        return None


REVIEW_LABEL = re.compile(r"([\d][\d,.\u00a0]*)\s+(?:ratings?|Bewertungen|évaluations|valoraciones|recensioni|avaliações)\b", re.I)


def parse_search_cards(body: str) -> list:
    cards = []
    for m, chunk in slice_blocks(body, r'data-asin="([A-Z0-9]{10})"[^>]*data-component-type="s-search-result"'):
        asin = m.group(1)
        title = None
        h2 = first_attr(chunk, r"<h2[^>]*>(.*?)</h2>")
        if h2:
            title = strip_markup(first_attr(h2, r"<span[^>]*>(.*?)</span>") or h2)
        if not title:
            aria = first_attr(chunk, r'<h2[^>]*aria-label="([^"]+)"')
            title = strip_markup(aria) if aria else None
        price = to_number(first_attr(chunk, r'<span class="a-offscreen">([^<]*\$[^<]*)</span>'))
        rating = None
        stars = first_attr(chunk, r'aria-label="([\d.,]+)\s*(?:out of|von|sur|su|de)\s*5')
        if stars:
            rating = float(stars.replace(",", "."))
        reviews = None
        for lab in re.findall(r'aria-label="([^"]+)"', chunk):
            rm = REVIEW_LABEL.search(lab)
            if rm:
                reviews = int(re.sub(r"\D", "", rm.group(1)))
                break
        if reviews is None:
            rev = first_attr(chunk, r'<span class="a-size-base s-underline-text">([\d,.\u00a0]+)</span>')
            if rev:
                reviews = int(re.sub(r"\D", "", rev))
        pos = first_attr(chunk, r'data-index="(\d+)"')
        cards.append({
            "asin": asin, "title": title, "price": price, "rating": rating,
            "reviews": reviews,
            "sponsored": "AdHolder" in chunk or "puis-sponsored-label" in chunk,
            "position": int(pos) if pos else None,
        })
    if not cards:  # degraded markup (partial paste): any data-asin with an h2 nearby
        for m, chunk in slice_blocks(body, r'data-asin="([A-Z0-9]{10})"'):
            if "<h2" not in chunk[:20000]:
                continue
            h2 = first_attr(chunk[:20000], r"<h2[^>]*>(.*?)</h2>")
            cards.append({"asin": m.group(1),
                          "title": strip_markup(h2) if h2 else None,
                          "price": to_number(first_attr(chunk[:20000], r'<span class="a-offscreen">([^<]*)</span>')),
                          "rating": None, "reviews": None, "sponsored": False, "position": None})
    seen, out = set(), []
    for c in cards:
        if c["asin"] not in seen and (c["title"] or c["price"] is not None):
            seen.add(c["asin"])
            out.append(c)
    return out


def detail_field_map(body: str) -> dict:
    """Reduce every structured detail region (spec tables + bullet lists) to one
    label -> value map. Field extraction then never touches raw HTML."""
    fields = {}
    for table in re.findall(r"<table[^>]*>(.*?)</table>", body, re.S):
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S):
            cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row, re.S)
            if len(cells) >= 2:
                key, val = strip_markup(cells[0]), strip_markup(cells[1])
                if key and val:
                    fields.setdefault(key, val)
    for item in re.findall(r"<li[^>]*>(.*?)</li>", body, re.S):
        txt = strip_markup(item)
        if ":" in txt and len(txt) < 600:
            key, val = txt.split(":", 1)
            if key.strip() and val.strip():
                fields.setdefault(key.strip(), val.strip())
    return fields


BSR_LABEL_RE = re.compile(r"best[- ]?sellers? rank|bestseller-rang|classement des meilleures", re.I)
RANK_PAIR_RE = re.compile(r"#\s*([\d][\d,. ]*)\s+(?:in|en|dans|su)\s+([^()#]+)")
ROOT_CATEGORIES = ("books", "kindle store")


def parse_product_page(body: str) -> dict:
    if captcha_page(body):
        return {"blocked": True}
    out = {}
    title = first_attr(body, r'<span id="(?:productTitle|ebooksProductTitle)"[^>]*>(.*?)</span>')
    if title:
        out["title"] = strip_markup(title)

    fields = detail_field_map(body)
    rank_blob = next((v for k, v in fields.items() if BSR_LABEL_RE.search(k)), None)
    if rank_blob is None:
        probe = re.search(r"Best Sellers Rank(.{0,3000})", body, re.S)
        if probe:
            rank_blob = strip_markup(probe.group(1))
    if rank_blob:
        pairs = [(int(re.sub(r"\D", "", r_)), cat.strip()) for r_, cat in RANK_PAIR_RE.findall(rank_blob)]
        root = [p for p in pairs if p[1].lower() in ROOT_CATEGORIES]
        subs = [p for p in pairs if p[1].lower() not in ROOT_CATEGORIES]
        if len(set(root)) == 1:
            out["bsr"] = root[0][0]
            out["bsrCategory"] = root[0][1]
        if subs:
            out["subcategoryRank"] = min(r for r, _ in subs)
            out["subcategories"] = [{"rank": r, "category": c} for r, c in subs[:5]]
    for target, keys in (("publisher", ("publisher",)), ("isbn13", ("isbn-13",)), ("isbn10", ("isbn-10",))):
        for k, v in fields.items():
            if k.lower().startswith(keys[0]):
                out[target] = v.split("(")[0].strip()
                break
    pub = re.search(r"publication\s+date\s*[:\u2013-]\s*([A-Za-z]+\s+\d{1,2},\s*\d{4})", body, re.I)
    if pub:
        out["publicationDate"] = pub.group(1)
    selected = first_attr(body, r'id=[\"\']selected-format[\"\'][^>]*>(.*?)</')
    selected = strip_markup(selected).lower() if selected else None
    formats = {"kindle edition": "kindle", "kindle": "kindle", "paperback": "paperback", "hardcover": "hardcover"}
    detail_formats = {formats[k.lower()] for k in fields if k.lower() in formats}
    out["format"] = formats.get(selected) if selected else (next(iter(detail_formats)) if len(detail_formats) == 1 else None)
    out["price"] = to_number(first_attr(body, r'<span class="a-offscreen">([^<]*\$[^<]*)</span>'))
    rev = first_attr(body, r'id="acrCustomerReviewText"[^>]*>([^<]+)<')
    if rev:
        m = REVIEW_LABEL.search(strip_markup(rev) + " ratings" if "rating" not in rev.lower() else rev)
        m = m or re.search(r"([\d,.\u00a0]+)", rev)
        if m:
            out["reviews"] = int(re.sub(r"\D", "", m.group(1)))
    if "bsr" not in out and "title" not in out:
        out["warning"] = "no recognizable product fields — variant layout or partial HTML?"
    return out


def parse_bestseller_page(body: str) -> dict:
    if captcha_page(body):
        return {"blocked": True}
    items = []
    for m, chunk in slice_blocks(body, r'id="gridItemRoot"'):
        rank = first_attr(chunk, r'class="zg-bdg-text"[^>]*>#?\s*([\d,]+)')
        link = first_attr(chunk, r'/dp/([A-Z0-9]{10})')
        title = first_attr(chunk, r'class="[^"]*line-clamp[^"]*"[^>]*>(.*?)</')
        price = first_attr(chunk, r'class="p13n-sc-price"[^>]*>([^<]+)<')
        delta = first_attr(chunk, r'twentyFourHourOldSalesRank\\?"?\s*[:=]\s*(\d+)')
        items.append({
            "rank": int(rank.replace(",", "")) if rank else None,
            "asin": link,
            "title": strip_markup(title) if title else None,
            "price": to_number(price),
            "rank24hAgo": int(delta) if delta else None,
        })
    tree = [strip_markup(c) for c in re.findall(r'class="[^"]*zg-browse-item[^"]*"[^>]*>(.*?)<', body, re.S)]
    note = ("full or near-full server render" if len(items) >= 45 or not items
            else "server renders ~30/50 cards — scroll the live page, save HTML, parse-file for the full 50")
    return {"items": items, "count": len(items), "categoryTree": tree, "hydrationNote": note}


# --------------------------------- commands ---------------------------------

def polite_pause(lo=2.0, hi=4.0):
    time.sleep(random.uniform(lo, hi))


def run_search(sess, keyword, kindle):
    idx = "digital-text" if kindle else "stripbooks"
    url = f"{HOST}/s?i={idx}&k={urllib.parse.quote(keyword)}"
    try:
        body = sess.get(url)
    except TransportError as exc:
        return envelope({"blocked": True, "error": str(exc),
                         "advice": "paste fallback: save the search page as HTML and run parse-file"})
    if captcha_page(body):
        return blocked_payload()
    cards = parse_search_cards(body)
    organic = [c for c in cards if not c["sponsored"]]
    return envelope({"keyword": keyword, "index": idx, "url": url, "engine": sess.engine,
                     "count": len(organic), "results": organic})


def run_product(sess, asin):
    try:
        body = sess.get(f"{HOST}/dp/{asin}", referer=f"{HOST}/s?k={asin}")
    except TransportError as exc:
        return envelope({"blocked": True, "error": str(exc),
                         "advice": "paste fallback: save the product page as HTML and run parse-file"})
    if captcha_page(body):
        return blocked_payload()
    return envelope({**parse_product_page(body), "asin": asin, "engine": sess.engine})


def run_niche(sess, keyword, kindle, limit=10):
    serp = run_search(sess, keyword, kindle)
    if serp.get("blocked"):
        return serp
    competitors = []
    for card in serp["results"][:limit]:
        polite_pause()
        prod = run_product(sess, card["asin"])
        if prod.get("blocked"):
            return envelope({"blocked": True, "partialCompetitors": competitors,
                             "advice": "paste fallback for the remaining product pages"})
        competitors.append({
            "title": card.get("title") or prod.get("title") or card["asin"],
            "bsr": prod.get("bsr"),
            "reviews": card.get("reviews") if card.get("reviews") is not None else prod.get("reviews"),
            "price": card.get("price") if card.get("price") is not None else prod.get("price"),
        })
    return envelope({"niche": keyword, "competitors": competitors, "engine": sess.engine,
                     "note": "pipe the competitors array into bw_niche.py score"})


def run_suggest(sess, prefix):
    params = {
        "prefix": prefix, "limit": "11", "alias": "aps", "plain-mid": "1",
        "mid": "ATVPDKIKX0DER", "lop": "en_US", "site-variant": "desktop",
        "version": "3", "event": "onKeyPress", "client-info": "amazon-search-ui",
        "session-id": "000-0000000-0000000",
    }
    params["suggestion-type"] = None  # placeholder replaced below (repeated param)
    url = ("https://completion.amazon.com/api/2017/suggestions?prefix=" + urllib.parse.quote(prefix)
           + "&suggestion-type=WIDGET&suggestion-type=KEYWORD&alias=aps&plain-mid=1"
           + "&mid=ATVPDKIKX0DER&lop=en_US&site-variant=desktop&version=3"
           + "&event=onKeyPress&client-info=amazon-search-ui&session-id=000-0000000-0000000")
    try:
        body = sess.get(url, referer=HOST + "/")
        data = json.loads(body)
        terms = [s["value"] for s in data.get("suggestions", []) if s.get("value")]
        return envelope({"prefix": prefix, "suggestions": terms, "engine": sess.engine,
                         "note": "US-only, undocumented endpoint — may change"})
    except Exception as exc:
        return envelope({"error": str(exc), "prefix": prefix,
                         "advice": "ask the user to type the prefix on amazon.com and paste the dropdown"})


def run_bestsellers(sess, url):
    try:
        body = sess.get(url)
    except TransportError as exc:
        return envelope({"blocked": True, "error": str(exc),
                         "advice": "scroll the live page fully, save HTML, run parse-file"})
    if captcha_page(body):
        return blocked_payload()
    return envelope({**parse_bestseller_page(body), "url": url, "engine": sess.engine})


def run_parse_file(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        body = fh.read()
    if captcha_page(body):
        return blocked_payload()
    if 'id="gridItemRoot"' in body:
        return envelope({**parse_bestseller_page(body), "detectedPageType": "bestsellers"})
    if "Best Sellers Rank" in body or "productTitle" in body:
        return envelope({**parse_product_page(body), "detectedPageType": "product"})
    cards = parse_search_cards(body)
    if cards:
        return envelope({"detectedPageType": "search", "count": len(cards), "results": cards})
    return envelope({"detectedPageType": "unknown",
                     "error": "no search cards, product details, or bestseller grid found"})


def main():
    argv = sys.argv[1:]
    if not argv:
        raise SystemExit(__doc__)
    command = argv[0]

    def opt(flag, default=None):
        return argv[argv.index(flag) + 1] if flag in argv else default

    if command == "parse-file":
        result = run_parse_file(argv[1])
    else:
        sess = BrowserSession()
        sess.warm_up()
        if command == "search":
            result = run_search(sess, argv[1], "--kindle" in argv)
        elif command == "product":
            result = run_product(sess, argv[1])
        elif command == "niche":
            result = run_niche(sess, argv[1], "--kindle" in argv, limit=int(opt("--limit", 10)))
        elif command == "suggest":
            result = run_suggest(sess, argv[1])
        elif command == "bestsellers":
            result = run_bestsellers(sess, argv[1])
        else:
            raise SystemExit(f'unknown command "{command}" — search|product|niche|suggest|bestsellers|parse-file')
    json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()

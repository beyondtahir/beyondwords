#!/usr/bin/env python3
"""Summarize legacy supplied competitor records without inventing demand or income."""
import json
import sys

TOOL = "bw_niche"
VERSION = "1.0.0"

MIN_SELLERS = 3
WEAK_MEDIAN = 50
GAP_BAND = (3.99, 5.99)
GAP_MIN = 3


def envelope(payload):
    return {"tool": TOOL, "version": VERSION, "ok": True, **payload}


def midpoint(values):
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def score_niche(niche: str, competitors: list) -> dict:
    """Describe supplied observations; rank thresholds cannot establish demand."""
    unique = {}
    missing = []
    for row in competitors:
        if not isinstance(row, dict) or not row.get("asin"):
            missing.append("competitor ASIN")
            continue
        key = (row["asin"], row.get("marketplace"), row.get("format"))
        unique.setdefault(key, row)
    rows = list(unique.values())
    return envelope({
        "ok": bool(rows), "status": "NEEDS_REVIEW" if rows else "PARTIAL",
        "niche": niche, "competitors": rows, "evaluatedCount": len(rows),
        "duplicatesRemoved": len(competitors) - len(rows) - len(missing),
        "demandConfirmed": None, "overallScore": None,
        "verdict": "INSUFFICIENT EVIDENCE — demand and commercial viability remain unverified.",
        "missing_fields": sorted(set(missing + ["source-linked comparable evidence", "reader validation", "production economics"])),
        "notes": ["Ranks and review counts alone do not establish sales, income or a probability of success.",
                  "Use the project research brief for source-linked observations, interpretation and next actions."],
    })


def main():
    argv = sys.argv[1:]
    if argv and argv[0] == "score":
        argv = argv[1:]
    raw = argv[0] if argv and argv[0] != "-" else sys.stdin.read()
    data = json.loads(raw)
    json.dump(score_niche(data["niche"], data["competitors"]), sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()

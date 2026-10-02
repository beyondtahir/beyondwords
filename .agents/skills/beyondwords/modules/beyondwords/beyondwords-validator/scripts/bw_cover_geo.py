#!/usr/bin/env python3
"""bw_cover_geo.py — Beyondwords cover geometry (original implementation).

Official KDP measurements (verified 2026-09-30 against KDP help "Create a
Paperback Cover", kdp.amazon.com/help/topic/G201953020):
  spine  = pages × paper thickness   (white 0.002252 · cream 0.0025 ·
           premium color 0.002347 · standard color 0.002252 — NO constant added)
  wrap W = 0.125" bleed + trim + spine + trim + 0.125" bleed
  wrap H = trim height + 0.25"
  spine text requires ≥ 79 pages · print minimum 24 pages · ebook cover 1600×2560 (1.6:1)
  cover PDF: single flattened PDF, fonts embedded, 300 DPI, NO crop marks,
  color bars, or printer's marks (KDP pre-publication checklist)

Commands (JSON envelope out):
  wrap --pages 200 --paper white --trim 6x9
  ebook-cover                      the Kindle cover spec
  trims                            common trim presets
"""
import json
import sys

TOOL = "bw_cover_geo"
VERSION = "1.1.0"

THICKNESS = {"white": 0.002252, "cream": 0.0025, "color-premium": 0.002347,
             "color": 0.002347, "color-standard": 0.002252}
BLEED = 0.125
MIN_SPINE_TEXT = 79
MIN_PAGES = 24

EBOOK_SPEC = {"widthPx": 1600, "heightPx": 2560, "ratio": "1.6:1", "format": "sRGB JPG",
              "note": "Kindle store ideal; the title must read at ~100 px wide (thumbnail)."}

TRIMS = [{"label": '5" × 8"', "width": 5.0, "height": 8.0},
         {"label": '5.5" × 8.5"', "width": 5.5, "height": 8.5},
         {"label": '6" × 9"', "width": 6.0, "height": 9.0},
         {"label": '8.5" × 11"', "width": 8.5, "height": 11.0}]


def envelope(payload):
    return {"tool": TOOL, "version": VERSION, "ok": True, **payload}


def wrap_spec(pages, paper, trim_w, trim_h):
    if paper not in THICKNESS:
        raise SystemExit(f"unknown paper {paper!r} — white|cream|color-standard|color-premium")
    spine = pages * THICKNESS[paper]
    warnings = []
    if pages < MIN_SPINE_TEXT:
        warnings.append(f"{pages} pages < {MIN_SPINE_TEXT}: no spine text allowed — keep the spine blank")
    if pages < MIN_PAGES:
        warnings.append(f"under {MIN_PAGES} pages: below the KDP print minimum")
    if spine < 0.1:
        warnings.append("spine is extremely thin — verify measurements before upload")
    return envelope({
        "pages": pages, "paper": paper, "trimWidth": trim_w, "trimHeight": trim_h,
        "spineWidth": round(spine, 4),
        "wrapWidth": round(BLEED + trim_w + spine + trim_w + BLEED, 4),
        "wrapHeight": round(trim_h + 2 * BLEED, 4),
        "spineTextAllowed": pages >= MIN_SPINE_TEXT,
        "bleedPerSide": BLEED,
        "warnings": warnings,
    })


def main():
    argv = sys.argv[1:]
    if not argv:
        raise SystemExit(__doc__)

    def opt(flag, default=None):
        return argv[argv.index(flag) + 1] if flag in argv else default

    if argv[0] == "wrap":
        tw, th = (opt("--trim", "6x9").lower().split("x") + ["9"])[:2]
        out = wrap_spec(int(opt("--pages")), opt("--paper", "white"), float(tw), float(th))
    elif argv[0] == "ebook-cover":
        out = envelope(dict(EBOOK_SPEC))
    elif argv[0] == "trims":
        out = envelope({"trims": TRIMS})
    else:
        raise SystemExit(f'unknown command "{argv[0]}" — wrap|ebook-cover|trims')
    json.dump(out, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()

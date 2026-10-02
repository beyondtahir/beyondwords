#!/usr/bin/env python3
"""bw_royalty.py — Beyondwords KDP royalty engine (original implementation).

Public KDP formulas (US marketplace, B&W interior):
  print:  rate = 0.50 if list < $9.99 else 0.60  (the "$9.99 cliff", June 2025+)
          print cost = $2.30 flat ≤108 pages, else $1.00 + $0.012 × pages
          royalty = rate × list − print cost
  ebook:  70% tier = 0.70 × (list − $0.15/MB delivery)   vs   35% tier = 0.35 × list
          break-even size = (10/3) × list MB — above it the 35% tier wins

Commands (JSON envelope out):
  print --list 9.99 --pages 300      quote + the $8.99 vs $9.99 cliff comparison
  ebook --list 4.99 --sizeMB 2.5     both tiers + winner + break-even size
"""
import json
import math
import sys

TOOL = "bw_royalty"
VERSION = "1.0.0"
CLIFF = 9.99
FLAT_COST_PAGES = 108
FLAT_COST = 2.30
PER_PAGE = 0.012
PER_PAGE_BASE = 1.00
DELIVERY_PER_MB = 0.15


def envelope(payload):
    return {"tool": TOOL, "version": VERSION, "ok": True, **payload}


def cost_of_print(pages):
    return FLAT_COST if pages <= FLAT_COST_PAGES else PER_PAGE_BASE + PER_PAGE * pages


def print_quote(list_price, pages):
    rate = 0.50 if list_price < CLIFF else 0.60
    cost = cost_of_print(pages)
    return {"list": list_price, "pages": pages, "rate": rate,
            "printCost": round(cost, 4), "royalty": round(rate * list_price - cost, 4)}


# KDP 70% ebook royalty eligibility band on Amazon.com: $2.99–$12.99.
# The ceiling was raised from $9.99 to $12.99 effective July 7, 2026 (KDP help
# "eBook List Price Requirements" FAQ, kdp.amazon.com/en_US/help/topic/G200634560).
# Minimum $2.99 and the 35% option are unchanged. Other eligibility rules: ebook
# must be ≥20% below any print list price, sold in eligible territories, and
# delivery costs apply to the 70% option only. UPDATE THIS CONSTANT if KDP moves it.
EBOOK_70_MIN = 2.99
EBOOK_70_MAX = 12.99


def ebook_quote(list_price, size_mb, print_price=None):
    if any(type(x) not in (int, float) or not math.isfinite(x) for x in (list_price, size_mb)) or list_price <= 0 or size_mb < 0:
        return {"ok": False, "error": "price and size must be finite, with positive price and nonnegative size", "winningTier": None}
    minimum35 = .99 if size_mb < 3 else 1.99 if size_mb < 10 else 2.99
    if not minimum35 <= list_price <= 200:
        return {"ok": False, "list": list_price, "sizeMB": size_mb, "tier35Eligible": False,
                "tier70Eligible": False, "tier35": None, "tier70": None, "winningTier": None,
                "winningRoyalty": None, "error": "Price outside the US file-size-dependent 35% band",
                "minimum35": minimum35, "source": "https://kdp.amazon.com/en_US/help/topic/G200634560"}
    tier35 = 0.35 * list_price
    eligible = EBOOK_70_MIN <= list_price <= EBOOK_70_MAX
    notes = []
    if not eligible:
        if list_price < EBOOK_70_MIN:
            notes.append(f"${list_price:.2f} is below the ${EBOOK_70_MIN:.2f} minimum — only the 35% option exists at this price")
        else:
            notes.append(f"${list_price:.2f} is above the ${EBOOK_70_MAX:.2f} ceiling — only the 35% option exists at this price")
    if print_price is not None and list_price > 0.8 * float(print_price):
        notes.append(f"70% eligibility also requires the ebook to be ≥20% below the print list price "
                     f"(print ${float(print_price):.2f} → ebook must be ≤ ${0.8 * float(print_price):.2f})")
        eligible = False
    if eligible:
        tier70 = 0.70 * (list_price - DELIVERY_PER_MB * size_mb)
        winner = 70 if tier70 >= tier35 else 35
        if winner == 35:
            notes.append("file size delivery cost makes the 35% tier pay more at this price/size")
        return {"list": list_price, "sizeMB": size_mb,
                "tier70": round(tier70, 4), "tier35": round(tier35, 4),
                "tier70Eligible": True, "winningTier": winner,
                "winningRoyalty": round(max(tier70, tier35), 4),
                "breakEvenMB": round(list_price * 10 / 3, 4),
                "band": [EBOOK_70_MIN, EBOOK_70_MAX], "notes": notes}
    return {"list": list_price, "sizeMB": size_mb,
            "tier70": None, "tier35": round(tier35, 4),
            "tier70Eligible": False, "winningTier": 35,
            "winningRoyalty": round(tier35, 4),
            "breakEvenMB": None,
            "band": [EBOOK_70_MIN, EBOOK_70_MAX], "notes": notes}


def main():
    argv = sys.argv[1:]
    if not argv:
        raise SystemExit(__doc__)

    def opt(flag, default=None):
        return argv[argv.index(flag) + 1] if flag in argv else default

    if argv[0] == "print":
        pages = int(opt("--pages"))
        quote = print_quote(float(opt("--list")), pages)
        below, above = print_quote(8.99, pages), print_quote(9.99, pages)
        out = envelope({"mode": "print", "quote": quote,
                        "cliff": {"at899": below, "at999": above,
                                  "delta": round(above["royalty"] - below["royalty"], 4)},
                        "cliffNote": (f"same {pages}-page book: $8.99 earns {below['royalty']:.2f}, "
                                      f"$9.99 earns {above['royalty']:.2f} — the 60% tier is worth "
                                      f"{above['royalty'] - below['royalty']:.2f} more per copy")})
    elif argv[0] == "ebook":
        pp = opt("--printPrice")
        out = envelope({"mode": "ebook", **ebook_quote(float(opt("--list")), float(opt("--sizeMB", 1.0)),
                                                       print_price=float(pp) if pp else None)})
    else:
        raise SystemExit(f'unknown command "{argv[0]}" — print|ebook')
    json.dump(out, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()

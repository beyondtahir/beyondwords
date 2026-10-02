# Royalty & Specs — Exact Formulas, Trim Sizes, Cover & Ebook Rules

This file documents the exact math behind the scripts. If the platform cannot run Python, apply these formulas exactly — never estimate.

## Contents
1. KDP print royalty (incl. the $9.99 cliff)
2. KDP ebook royalty (70% vs 35%)
3. Print cover geometry
4. KDP trim sizes & page limits
5. Ebook cover spec
6. Ebook format rules
7. Lulu economics (summary)

## 1. KDP print royalty (US marketplace, B&W interior)

Since June 10, 2025:

```
rate       = 0.50 if list < 9.99 else 0.60
printCost  = 2.30                      if pages <= 108
           = 1.00 + 0.012 * pages      otherwise
royalty    = rate * list - printCost
```

**The $9.99 cliff**: at $8.99 the rate is 50%; at $9.99 it is 60%. Always show the comparison:

```
royalty(8.99) = 0.50 * 8.99 - printCost
royalty(9.99) = 0.60 * 9.99 - printCost
```

Known-good check: 300 pages → printCost = $4.60; royalty($8.99) = **−$0.105** (you lose money); royalty($9.99) = **+$1.394**. Pricing at $8.99 instead of $9.99 costs ~$1.50 per copy here. Never price print under $9.99.

## 2. KDP ebook royalty

```
tier70 = 0.70 * (list - 0.15 * sizeMB)     # delivery fee $0.15/MB applies
tier35 = 0.35 * list                       # no delivery fee
```

- The 70% tier exists ONLY for list prices in the band **$2.99–$12.99** (Amazon.com; the ceiling was raised from $9.99 on July 7, 2026 — KDP "eBook List Price Requirements" FAQ, kdp.amazon.com/en_US/help/topic/G200634560). Outside the band, only 35% exists — never recommend 70% for an out-of-band price. Other eligibility rules: ebook ≥20% below any print list price; eligible territories.
- **Break-even file size**: `0.70(list − 0.15s) = 0.35·list` → `s = (10/3) × list`. Above this size, the 35% tier pays more — big illustrated books can earn MORE at 35%. Always show both tiers.
- Example: $4.99 at 2.5 MB → tier70 = $3.2305, tier35 = $1.7465 → 70% wins; break-even at ≈16.63 MB.

## 3. Print cover geometry

Official KDP formula (verified 2026-09-30 against KDP help "Create a Paperback Cover", kdp.amazon.com/help/topic/G201953020):

```
spine width = pages * thickness          # NO constant is added
thickness:  white 0.002252"/page | cream 0.0025"/page
            premium color 0.002347"/page | standard color 0.002252"/page
wrap width  = 0.125" bleed + trim width + spine + trim width + 0.125" bleed
wrap height = trim height + 0.25"
```

- Known-good check: 200 pages, white → spine = 200 × 0.002252 = **0.4504"**; 6×9" wrap = 12.7004" × 9.25".
- **No spine text under 79 pages.**
- Under 24 pages is below KDP's print minimum.
- Single flattened PDF, 300 DPI, 0.125" bleed on all sides, fonts embedded, **no crop marks, color bars, or printer's marks** (KDP pre-publication checklist).

## 4. KDP trim sizes & page limits

- Standard trim: **6" × 9"**. Other common presets: 5"×8", 5.5"×8.5", 8.5"×11".
- Paperback B&W: 24–828 pages.
- Hardcover: only 5 fixed sizes, 75–550 pages.

## 5. Ebook cover spec

- **1600 × 2560 px**, strict **1.6:1** aspect ratio, sRGB, JPG/TIFF, ≤ 50 MB.
- Must read at thumbnail size (~100 px wide) — the cover is the ad on Amazon.
- AI covers are not copyrightable in the US on their own; add a human typography/layout layer.

## 6. Ebook format rules

- **EPUB is preferred** for KDP upload (DOCX and KPF also accepted).
- **MOBI is fully dead** (fixed-layout MOBI ended March 18, 2025).
- Kindle Comic Creator and Kids' Book Creator were discontinued (Feb 2025): kids'/comic books = **fixed-layout EPUB 3** or KPF via Kindle Create.
- Validate EPUBs with EPUBCheck before upload.

## 7. Lulu economics (summary)

- Lulu bookstore print: 80% of revenue above print cost.
- Ebooks via Global Distribution: 90% after retailer fees; one-time **$4.99** submission fee; EPUB only.
- Lulu Direct (own store): ~100% minus print + shipping, and you keep customer emails.
- Detail in `references/lulu-guide.md`.

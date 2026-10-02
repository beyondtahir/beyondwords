# Canva Workflow — Free-Tier Cover Polish

## Contents
1. When to use Canva vs bw_compose.py
2. Ebook cover: numbered steps
3. Paperback wrap: numbered steps
4. Export settings
5. In-chat Canva (Claude connector / ChatGPT app)
6. Limits to respect

## 1. When to use Canva vs bw_compose.py

- `scripts/bw_compose.py` produces a finished, print-perfect 1600×2560 cover with zero external tools — the default path.
- Canva is the optional polish step: richer typography, texture overlays, brand consistency across a series, or when the user wants to tweak by hand.
- Never make Canva a hard dependency; the free tier is enough for everything below.

## 2. Ebook cover: numbered steps (free tier)

1. Open `https://www.canva.com/create/book-covers/` → **Custom size** → **1600 × 2560 px** (KDP ebook spec; Canva's default book-cover doc is 1410×2250 — override it).
2. Upload the agent-made cover art (the PNG/JPG from the platform's image generation) → set as background.
3. Add the title as a text box: bold display sans (the analysis hex palette from `bw_covers.py` sets the color), top or top-third placement, sized to read at thumbnail.
4. Add the subtitle at ~40% of the title size; author name on a bottom strip.
5. Use the exact hex codes from the niche analysis (e.g., title `#F8F8F4` on dark art).
6. Zoom out to ~6% (≈100 px wide): if the title does not read, increase size/contrast — this is the thumbnail test.

## 3. Paperback wrap: numbered steps

1. Compute exact dimensions first: `python3 scripts/bw_cover_geo.py wrap --pages 200 --paper white --trim 6x9` → wrap width × wrap height in inches.
2. Canva → Custom size in **inches** (wrap W × H), then design: back cover | spine | front cover left-to-right.
3. Spine text only if ≥ 79 pages; keep all critical elements 0.125" inside the trim (bleed area will be trimmed).
4. Download as **PDF Print**, 300 DPI, bleed included, CMYK color profile. **Do NOT include crop marks, registration marks, color bars, or template text — KDP's pre-publication checklist requires them removed** (KDP "Create a Paperback Cover", kdp.amazon.com/help/topic/G201953020). In Canva, use "PDF Print" with crop marks left OFF (the default), and flatten transparencies.

## 4. Export settings

| Deliverable | Format | Color | Notes |
|---|---|---|---|
| KDP ebook cover | JPG (or PNG) | sRGB | 1600×2560, ≤ 50 MB |
| KDP print wrap | PDF Print | CMYK, 300 DPI | Bleed on; **crop marks / color bars / printer's marks OFF** (KDP rejects them) |
| Lulu cover | PDF Print | 300 DPI | Use Lulu's generated template — Lulu bookstore and distribution network have different spine widths (two separate cover PDFs) |

## 5. In-chat Canva (Claude connector / ChatGPT app)

- **Claude**: enable the official Canva connector (Connectors directory; works on the Free plan) or add MCP server `https://mcp.canva.com/mcp` (OAuth). The agent can create/autofill designs in-chat; export and resize are finished in Canva itself.
- **ChatGPT**: use the official Canva app to generate/preview/edit designs conversationally. **Not available in the EU or China.** Export and Brand Kit application require opening the design in Canva.
- Pattern in both: agent supplies the art file, exact text strings, fonts, hex palette, and placement spec; Canva renders the editable design.

## 6. Limits to respect

- No fine-grained pixel/nudge editing via MCP/app — do coarse creation in-chat, fine work in Canva.
- Magic Resize unavailable in-chat.
- Brand Template autofill requires Enterprise; skip it for typical users.
- Everything above works on the free tier; never tell the user a paid plan is required.

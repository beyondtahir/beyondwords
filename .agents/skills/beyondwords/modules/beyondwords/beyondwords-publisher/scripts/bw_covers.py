#!/usr/bin/env python3
"""bw_covers.py — Beyondwords cover-set analyzer (original implementation).

Offline intelligence over a folder of competitor cover images (top-100 covers
collected live or saved by the user). Per cover: dominant palette, brightness /
saturation stats, large-type heuristic, light/dark class. Aggregate niche
conventions + rank-labeled contact sheets (20 covers per grid) sized for an AI
agent to vision-read.

Commands (JSON envelope out):
  analyze <folder> [--out <dir>]    analysis.json + contact sheets
  upscale-url <url>                 Amazon CDN size-token bump (_AC_UL320_ → _AC_UL600_)
"""
import json
import os
import re
import sys
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)

from pathlib import Path
import io
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from bw_io import write_new

TOOL = "bw_covers"
VERSION = "1.0.0"
IMG_EXTS = (".jpg", ".jpeg", ".png", ".webp")
GRID_COLS, GRID_ROWS = 5, 4
CELL_W = 320
LABEL_BAR = 28


def envelope(payload):
    return {"tool": TOOL, "version": VERSION, "ok": True, **payload}


def pil():
    try:
        from PIL import Image, ImageDraw
        return Image, ImageDraw
    except ImportError:
        raise SystemExit("Pillow required: pip install Pillow")


def palette(img, n=5):
    small = img.convert("RGB").resize((100, 150))
    q = small.quantize(colors=n, method=2)
    table = q.getpalette()[: n * 3]
    ranked = sorted(q.getcolors(), reverse=True)
    return [{"hex": f"#{table[i*3]:02X}{table[i*3+1]:02X}{table[i*3+2]:02X}",
             "share": round(count / 15000, 3)} for count, i in ranked]


def tone_stats(img):
    hsv = img.convert("RGB").resize((64, 96)).convert("HSV")
    data = list(hsv.getdata())
    n = len(data)
    return (round(sum(p[2] for p in data) / (n * 255), 3),
            round(sum(p[1] for p in data) / (n * 255), 3))


def type_heuristic(img):
    """Large display type leaves big high-contrast blobs. Downscale, use the
    median luminance as background, count far-from-background pixels overall and
    in the top third (classic title placement)."""
    gray = img.convert("L").resize((48, 72))
    data = list(gray.getdata())
    med = sorted(data)[len(data) // 2]
    mask = [1 if abs(p - med) > 60 else 0 for p in data]
    overall = sum(mask) / len(mask)
    third = 72 // 3
    top = sum(sum(mask[r * 48:(r + 1) * 48]) for r in range(third)) / (48 * third)
    return round(overall, 3), round(top, 3)


def analyze(folder, outdir):
    Image, ImageDraw = pil()
    names = sorted(f for f in os.listdir(folder)
                   if f.lower().endswith(IMG_EXTS) and os.path.isfile(os.path.join(folder, f)))
    if not names:
        raise SystemExit(f"no cover images in {folder}")
    os.makedirs(outdir, exist_ok=True)

    covers = []
    for rank, name in enumerate(names, 1):
        try:
            img = Image.open(os.path.join(folder, name))
            img.load()
        except Exception as exc:
            covers.append({"rank": rank, "file": name, "error": str(exc)})
            continue
        bright, sat = tone_stats(img)
        tr, top = type_heuristic(img)
        covers.append({"rank": rank, "file": name, "sizePx": list(img.size),
                       "palette": palette(img), "brightness": bright, "saturation": sat,
                       "lightOrDark": "light" if bright > 0.5 else "dark",
                       "largeTypeRatio": tr, "topThirdContrast": top})

    good = [c for c in covers if "error" not in c]
    aggregate = {
        "coverCount": len(good),
        "lightShare": round(sum(c["lightOrDark"] == "light" for c in good) / len(good), 3) if good else None,
        "meanBrightness": round(sum(c["brightness"] for c in good) / len(good), 3) if good else None,
        "meanSaturation": round(sum(c["saturation"] for c in good) / len(good), 3) if good else None,
        "meanLargeTypeRatio": round(sum(c["largeTypeRatio"] for c in good) / len(good), 3) if good else None,
        "leadHexes": [c["palette"][0]["hex"] for c in good[:20] if c["palette"]],
        "rankMeaning": "Display order only; filenames do not establish market rank",
        "agentNote": "vision-read the contact sheets; write the niche-convention summary (palette, typography, composition, thumbnail rules)",
    }

    sheets = contact_sheets(Image, ImageDraw, folder, good, outdir)
    analysis = {"aggregate": aggregate, "contactSheets": sheets, "covers": covers}
    out_path = os.path.join(outdir, "analysis.json")
    write_new(out_path, json.dumps(analysis, indent=2).encode())
    return envelope({"analysisJson": out_path, "coverCount": len(covers),
                     "contactSheets": sheets, "aggregate": aggregate})


def contact_sheets(Image, ImageDraw, folder, covers, outdir):
    paths = []
    per = GRID_COLS * GRID_ROWS
    cell_h = int(CELL_W * 1.6)
    for start in range(0, len(covers), per):
        batch = covers[start:start + per]
        sheet = Image.new("RGB", (GRID_COLS * CELL_W, GRID_ROWS * (cell_h + LABEL_BAR)), (30, 30, 30))
        pen = ImageDraw.Draw(sheet)
        for i, c in enumerate(batch):
            x = (i % GRID_COLS) * CELL_W
            y = (i // GRID_COLS) * (cell_h + LABEL_BAR)
            try:
                img = Image.open(os.path.join(folder, c["file"])).convert("RGB")
                img.thumbnail((CELL_W, cell_h))
                sheet.paste(img, (x + (CELL_W-img.width)//2, y + LABEL_BAR + (cell_h-img.height)//2))
            except Exception:
                pass
            pen.rectangle([x, y, x + CELL_W - 1, y + LABEL_BAR - 1], fill=(0, 0, 0))
            pen.text((x + 6, y + 7), f"#{c['rank']}  {c['file'][:28]}", fill=(255, 255, 0))
        path = os.path.join(outdir, f"contact_sheet_{start // per + 1}.png")
        output = io.BytesIO()
        sheet.save(output, format="PNG")
        write_new(path, output.getvalue())
        paths.append(path)
    return paths


def upscale_url(url):
    bumped = re.sub(r"\._AC_UL\d+(_SR\d+,\d+)?_", "._AC_UL600_", url)
    bumped = re.sub(r"\._AC_SX\d+_", "._AC_SX600_", bumped)
    return envelope({"original": url, "upgraded": bumped, "changed": bumped != url,
                     "note": "_AC_UL1000_ also works; the product-page main image is full resolution"})


def main():
    argv = sys.argv[1:]
    if not argv:
        raise SystemExit(__doc__)

    def opt(flag, default=None):
        return argv[argv.index(flag) + 1] if flag in argv else default

    if argv[0] == "analyze":
        folder = argv[1]
        out = analyze(folder, opt("--out", os.path.join(folder, "analysis")))
    elif argv[0] == "upscale-url":
        out = upscale_url(argv[1])
    else:
        raise SystemExit(f'unknown command "{argv[0]}" — analyze|upscale-url')
    json.dump(out, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()

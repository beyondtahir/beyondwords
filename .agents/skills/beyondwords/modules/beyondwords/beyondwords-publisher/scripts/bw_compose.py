#!/usr/bin/env python3
"""bw_compose.py — Beyondwords cover typography layer (original implementation).

Turns AI-generated background art into a finished ebook cover without any design
tool: title/subtitle/author composited with shrink-to-fit type, auto-contrast
color sampled from the art behind the text block, 8% safe margins, optional
author baseline strip. Outputs the 1600×2560 sRGB JPG + a 200 px thumbnail for
the legibility test.

Usage (JSON config via CLI arg or stdin; JSON envelope out):
  bw_compose.py '{"art":"bg.png","title":"Strong After 50",
                  "subtitle":"7 Steps to Lifelong Strength","author":"A. Writer",
                  "titleFont":"assets/fonts/Oswald-Variable.ttf",
                  "bodyFont":"assets/fonts/PlayfairDisplay-Variable.ttf",
                  "position":"top","casing":"upper","color":"auto",
                  "authorStrip":true,"output":"cover.jpg","thumb":"thumb.png"}'
"""
import json
import os
import sys
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)

from pathlib import Path
import io
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from bw_io import write_new

TOOL = "bw_compose"
VERSION = "1.0.0"
CANVAS_W, CANVAS_H = 1600, 2560
SAFE_INSET = 0.08
THUMB_WIDTH = 200
SUB_SCALE = 0.42
AUTHOR_SCALE = 0.30


def envelope(payload):
    return {"tool": TOOL, "version": VERSION, "ok": True, **payload}


def pil():
    try:
        from PIL import Image, ImageDraw, ImageFont
        return Image, ImageDraw, ImageFont
    except ImportError:
        raise SystemExit("Pillow required: pip install Pillow")


def sized_font(ImageFont, path, px, named_weight="Bold"):
    font = ImageFont.truetype(path, px)
    try:
        font.set_variation_by_name(named_weight)
    except Exception:
        pass
    return font


def largest_fitting(ImageFont, draw, text, path, max_px_width, start_px, weight):
    size = max(12, start_px)
    while True:
        font = sized_font(ImageFont, path, size, weight)
        box = draw.textbbox((0, 0), text, font=font)
        if box[2] - box[0] <= max_px_width:
            return font, size, box
        if size == 12:
            raise ValueError("Text does not fit safely; shorten it or use a multiline design")
        size = max(12, size - 4)


def contrast_color(image, region_box):
    zone = image.crop(region_box).convert("L").resize((32, 32))
    data = list(zone.getdata())
    mean = sum(data) / len(data)
    return (22, 22, 26) if mean > 140 else (248, 248, 244)


def _render(cfg):
    Image, ImageDraw, ImageFont = pil()
    art = Image.open(cfg["art"]).convert("RGB")

    # center-crop to the 1.6:1 cover ratio, then resize to spec
    want = CANVAS_W / CANVAS_H
    have = art.width / art.height
    if have > want:
        w2 = int(art.height * want)
        x0 = (art.width - w2) // 2
        art = art.crop((x0, 0, x0 + w2, art.height))
    else:
        h2 = int(art.width / want)
        y0 = (art.height - h2) // 2
        art = art.crop((0, y0, art.width, y0 + h2))
    canvas = art.resize((CANVAS_W, CANVAS_H), Image.LANCZOS)
    draw = ImageDraw.Draw(canvas)

    mx = int(CANVAS_W * SAFE_INSET)
    max_w = CANVAS_W - 2 * mx

    casing = cfg.get("casing", "upper")
    title = cfg["title"].upper() if casing == "upper" else (cfg["title"].title() if casing == "title" else cfg["title"])
    subtitle = cfg.get("subtitle", "")
    author = cfg.get("author", "")
    t_path = cfg["titleFont"]
    b_path = cfg.get("bodyFont", t_path)
    weight = cfg.get("weight", "Bold")

    t_font, t_px, _ = largest_fitting(ImageFont, draw, title, t_path, max_w, int(CANVAS_H * 0.11), weight)
    s_font = s_px = None
    if subtitle:
        s_font, s_px, _ = largest_fitting(ImageFont, draw, subtitle, b_path, max_w, int(t_px * SUB_SCALE), "Regular")
    a_font = a_px = None
    if author:
        a_font, a_px, _ = largest_fitting(ImageFont, draw, author, b_path, max_w, int(t_px * AUTHOR_SCALE), "Regular")

    t_box = draw.textbbox((0, 0), title, font=t_font)
    s_box = draw.textbbox((0, 0), subtitle, font=s_font) if subtitle else (0, 0, 0, 0)
    block = (t_box[3] - t_box[1]) + (s_box[3] - s_box[1] + int(t_px * 0.35) if subtitle else 0)

    pos = cfg.get("position", "top")
    if pos == "top":
        y = int(CANVAS_H * (SAFE_INSET + 0.04))
    elif pos == "center":
        y = (CANVAS_H - block) // 2
    else:
        y = CANVAS_H - int(CANVAS_H * SAFE_INSET) - block - int(CANVAS_H * 0.10)

    color_cfg = cfg.get("color", "auto")
    if color_cfg == "auto":
        ink = contrast_color(canvas, (mx, y, CANVAS_W - mx, y + block))
    else:
        h = color_cfg.lstrip("#")
        ink = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))

    def centered(text, font, y_top, fill):
        b = draw.textbbox((0, 0), text, font=font)
        draw.text(((CANVAS_W - (b[2] - b[0])) // 2, y_top - b[1]), text, font=font, fill=fill)
        return b[3] - b[1]

    used = centered(title, t_font, y, ink)
    if subtitle:
        centered(subtitle, s_font, y + used + int(t_px * 0.35), ink)

    if author:
        ab = draw.textbbox((0, 0), author, font=a_font)
        ah = ab[3] - ab[1]
        ay = CANVAS_H - int(CANVAS_H * SAFE_INSET) - int(ah * 1.8)
        if cfg.get("authorStrip"):
            veil = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
            vd = ImageDraw.Draw(veil)
            tone = (0, 0, 0, 110) if sum(ink) > 300 else (255, 255, 255, 110)
            vd.rectangle([0, ay - int(ah * 0.5), CANVAS_W, ay + int(ah * 1.6)], fill=tone)
            canvas = Image.alpha_composite(canvas.convert("RGBA"), veil).convert("RGB")
            draw = ImageDraw.Draw(canvas)
        draw.text(((CANVAS_W - (ab[2] - ab[0])) // 2, ay - ab[1]), author, font=a_font, fill=ink)

    out_path = cfg.get("output", "cover.jpg")
    buffer = io.BytesIO()
    canvas.convert("RGB").save(buffer, "JPEG", quality=95, dpi=(300, 300))
    if len(buffer.getvalue()) > 5 * 1024 * 1024:
        raise ValueError("Cover exceeds the reviewed 5 MiB profile; revise/compress and inspect before export")
    write_new(out_path, buffer.getvalue())
    thumb_path = cfg.get("thumb", os.path.splitext(out_path)[0] + "_thumb.png")
    buffer = io.BytesIO()
    canvas.resize((THUMB_WIDTH, THUMB_WIDTH * CANVAS_H // CANVAS_W), Image.LANCZOS).save(buffer, "PNG")
    write_new(thumb_path, buffer.getvalue())

    return envelope({
        "publicationReady": False, "visualReview": "NOT_RUN",
        "cover": {"path": out_path, "widthPx": CANVAS_W, "heightPx": CANVAS_H,
                  "ratio": "1.6:1", "format": "RGB JPG", "dpi": 300},
        "thumbnail": {"path": thumb_path, "widthPx": THUMB_WIDTH,
                      "note": "if the title does not read at this width, redesign"},
        "typography": {"titlePx": t_px, "subtitlePx": s_px, "authorPx": a_px,
                       "position": pos, "color": "#%02X%02X%02X" % ink,
                       "safeInset": SAFE_INSET},
        "printWrapNext": {"tool": "bw_cover_geo.py",
                          "example": 'bw_cover_geo.py wrap --pages 200 --paper white --trim 6x9'},
    })


def render(cfg):
    try:
        cfg = dict(cfg)
        cfg.setdefault("output", "cover.jpg")
        cfg.setdefault("thumb", os.path.splitext(cfg["output"])[0]+"_thumb.png")
        for key in ("output", "thumb"):
            if cfg.get(key) and os.path.exists(cfg[key]):
                return envelope({"ok": False, "error": "ALREADY_EXISTS: choose a new output revision"})
        return _render(cfg)
    except ValueError as exc:
        return envelope({"ok": False, "error": str(exc), "status": "NEEDS_REVIEW"})


def main():
    raw = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()
    json.dump(render(json.loads(raw)), sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()

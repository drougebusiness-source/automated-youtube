"""Three thumbnail designs per video, for A/B testing with YouTube Studio's "Test & Compare".

  A "gallery"  - the whole painting, title across the bottom (the original style, refined)
  B "detail"   - a close-up of the most striking part of the painting, very little text
  C "framed"   - the painting in a gilded frame, with the composer and length beside it
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .visuals import length_label

W, H = 1280, 720
FONTS = {"display": "Cinzel.ttf", "serif": "PlayfairDisplay.ttf", "text": "CormorantGaramond.ttf"}
GOLD = (222, 190, 120)
CREAM = (246, 238, 222)


def _font(root: Path, kind: str, size: int, weight: str = "Bold") -> ImageFont.FreeTypeFont:
    path = root / "assets" / "fonts" / FONTS[kind]
    try:
        f = ImageFont.truetype(str(path), size)
        try:
            f.set_variation_by_name(weight)
        except (OSError, ValueError):
            pass
        return f
    except OSError:
        return ImageFont.load_default(size)


def _cover(img: Image.Image, w: int, h: int, focus: tuple[float, float] = (0.5, 0.5)) -> Image.Image:
    scale = max(w / img.width, h / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    left = int(np.clip(focus[0] * img.width - w / 2, 0, img.width - w))
    top = int(np.clip(focus[1] * img.height - h / 2, 0, img.height - h))
    return img.crop((left, top, left + w, top + h))


def _fit_text(d: ImageDraw.ImageDraw, text: str, root: Path, kind: str, size: int, max_w: int, weight="Bold"):
    font = _font(root, kind, size, weight)
    while size > 24 and d.textbbox((0, 0), text, font=font)[2] > max_w:
        size -= 4
        font = _font(root, kind, size, weight)
    return font


def _shadowed(d, xy, text, font, fill, anchor="la", blur_layer=None):
    x, y = xy
    d.text((x + 3, y + 3), text, font=font, fill=(0, 0, 0), anchor=anchor)
    d.text((x, y), text, font=font, fill=fill, anchor=anchor)


def most_striking_point(img: Image.Image) -> tuple[float, float]:
    """Where the painting has the most detail and colour: a cheap 'saliency' map."""
    small = np.asarray(img.convert("RGB").resize((96, 54)), dtype=np.float32)
    gray = small.mean(axis=2)
    edges = np.abs(np.diff(gray, axis=0))[:, :-1] + np.abs(np.diff(gray, axis=1))[:-1, :]
    sat = (small.max(axis=2) - small.min(axis=2))[:-1, :-1]
    score = edges / (edges.mean() + 1e-6) + 0.6 * sat / (sat.mean() + 1e-6)
    k = 9  # average over windows so one bright pixel doesn't win
    pad = np.pad(score, k // 2, mode="edge")
    windows = np.lib.stride_tricks.sliding_window_view(pad, (k, k)).mean(axis=(2, 3))
    yy, xx = np.unravel_index(np.argmax(windows), windows.shape)
    return (xx + 0.5) / windows.shape[1], (yy + 0.5) / windows.shape[0]


def gallery(painting: Image.Image, title: str, subtitle: str, minutes: int, root: Path) -> Image.Image:
    img = _cover(painting.convert("RGB"), W, H)
    ramp = (215 * np.clip((np.arange(H) / H - 0.42) / 0.58, 0, 1) ** 1.2).astype(np.uint8)
    shade = Image.fromarray(np.repeat(ramp[:, None], W, axis=1), mode="L")
    img = Image.composite(Image.new("RGB", img.size, (8, 6, 4)), img, shade)
    d = ImageDraw.Draw(img)
    f1 = _fit_text(d, title.upper(), root, "display", 104, 1180)
    _shadowed(d, (W // 2, 520), title.upper(), f1, CREAM, anchor="ms")
    f2 = _fit_text(d, subtitle, root, "text", 54, 1100, "SemiBold")
    _shadowed(d, (W // 2, 600), subtitle, f2, GOLD, anchor="ms")
    d.line([(W // 2 - 160, 545), (W // 2 + 160, 545)], fill=GOLD, width=2)
    return img


def detail(painting: Image.Image, title: str, subtitle: str, minutes: int, root: Path) -> Image.Image:
    p = painting.convert("RGB")
    fx, fy = most_striking_point(p)
    zoom = 2.0
    img = _cover(p, int(W * zoom), int(H * zoom), (fx, fy)).resize((W, H), Image.LANCZOS) \
        if min(p.width / W, p.height / H) < zoom else _cover(p.crop(_zoom_box(p, fx, fy, zoom)), W, H)
    vignette = Image.new("L", (W, H), 0)
    ImageDraw.Draw(vignette).ellipse([-W * 0.25, -H * 0.35, W * 1.25, H * 1.35], fill=255)
    vignette = vignette.filter(ImageFilter.GaussianBlur(120))
    img = Image.composite(img, Image.new("RGB", img.size, (10, 8, 6)), vignette)
    d = ImageDraw.Draw(img)
    badge = length_label(minutes)
    fb = _font(root, "display", 44)
    bw = d.textbbox((0, 0), badge, font=fb)[2] + 48
    d.rounded_rectangle([40, 36, 40 + bw, 104], radius=10, fill=(16, 12, 8), outline=GOLD, width=3)
    d.text((40 + bw / 2, 72), badge, font=fb, fill=GOLD, anchor="mm")
    f = _fit_text(d, subtitle, root, "serif", 78, 1150, "Bold Italic")
    _shadowed(d, (56, H - 60), subtitle, f, CREAM, anchor="ls")
    return img


def _zoom_box(p: Image.Image, fx: float, fy: float, zoom: float):
    cw, ch = p.width / zoom, p.width / zoom * H / W
    if ch > p.height:
        ch, cw = p.height, p.height * W / H
    left = np.clip(fx * p.width - cw / 2, 0, p.width - cw)
    top = np.clip(fy * p.height - ch / 2, 0, p.height - ch)
    return int(left), int(top), int(left + cw), int(top + ch)


def framed(painting: Image.Image, title: str, subtitle: str, minutes: int, root: Path) -> Image.Image:
    p = painting.convert("RGB")
    # Dark wall from a blurred, darkened copy of the painting itself.
    wall = _cover(p, W, H).filter(ImageFilter.GaussianBlur(40))
    wall = Image.blend(wall, Image.new("RGB", (W, H), (12, 9, 6)), 0.78)
    max_w, max_h = 640, 560
    s = min(max_w / p.width, max_h / p.height)
    art = p.resize((int(p.width * s), int(p.height * s)), Image.LANCZOS)
    fw = 22
    frame = Image.new("RGB", (art.width + 2 * fw, art.height + 2 * fw), (150, 112, 52))
    fd = ImageDraw.Draw(frame)
    for i, col in enumerate([(196, 152, 76), (120, 86, 36), (226, 190, 112), (150, 112, 52)]):
        fd.rectangle([i * 4, i * 4, frame.width - 1 - i * 4, frame.height - 1 - i * 4], outline=col, width=4)
    frame.paste(art, (fw, fw))
    x0, y0 = 60, (H - frame.height) // 2
    shadow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(shadow).rectangle([x0 + 14, y0 + 18, x0 + frame.width + 14, y0 + frame.height + 18], fill=180)
    wall = Image.composite(Image.new("RGB", (W, H), (0, 0, 0)), wall, shadow.filter(ImageFilter.GaussianBlur(18)))
    wall.paste(frame, (x0, y0))
    d = ImageDraw.Draw(wall)
    tx = x0 + frame.width + 50
    tw = W - tx - 40
    words = title.upper().split()
    lines = [" ".join(words[:len(words) // 2 or 1]), " ".join(words[len(words) // 2 or 1:])] if len(words) > 1 else words
    y = H // 2 - 110
    for line in lines:
        f = _fit_text(d, line, root, "display", 72, tw)
        _shadowed(d, (tx, y), line, f, CREAM)
        y += 84
    d.line([(tx, y + 6), (tx + min(tw, 260), y + 6)], fill=GOLD, width=2)
    f2 = _fit_text(d, subtitle, root, "text", 44, tw, "SemiBold")
    _shadowed(d, (tx, y + 22), subtitle, f2, GOLD)
    f3 = _font(root, "display", 40)
    _shadowed(d, (tx, y + 86), length_label(minutes), f3, CREAM)
    return wall


VARIANTS = {"A-gallery": gallery, "B-detail": detail, "C-framed": framed}


def subtitle_for(theme: dict, tracklist: list[dict], minutes: int) -> str:
    """'Chopin Nocturnes · 1 Hour'-style line from the music actually in the video."""
    if tracklist:
        names: dict[str, int] = {}
        for t in tracklist:
            last = t["composer"].split()[-1]
            names[last] = names.get(last, 0) + 1
        top = sorted(names, key=lambda n: -names[n])[:2]
        who = " & ".join(top)
    else:
        who = theme.get("style", "Classical Music")
    return f"{who} · {length_label(minutes).title()}"


def make_variants(painting_path: Path, out_dir: Path, theme: dict, minutes: int, tracklist: list[dict],
                  root: Path) -> dict[str, Path]:
    painting = Image.open(painting_path)
    sub = subtitle_for(theme, tracklist, minutes)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, fn in VARIANTS.items():
        p = out_dir / f"thumbnail_{name}.jpg"
        who = sub.split(" · ")[0]
        text = {"A-gallery": sub, "B-detail": f"{theme['name']} · {who}", "C-framed": who}[name]
        fn(painting, theme["name"], text, minutes, root).save(p, quality=90)
        paths[name] = p
    return paths

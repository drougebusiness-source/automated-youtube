"""Background art, a seamless slow-zoom loop, the final video, and the thumbnail."""

from __future__ import annotations

import base64
import os
import random
from pathlib import Path

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import ffmpeg

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
FONT_CANDIDATES = [
    "assets/fonts/title.ttf",
    "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
    "/Library/Fonts/Georgia Bold.ttf",
    "C:/Windows/Fonts/georgiab.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
]


def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _cover(img: Image.Image, w: int, h: int) -> Image.Image:
    """Resize and centre-crop to exactly w x h."""
    scale = max(w / img.width, h / img.height)
    img = img.convert("RGB").resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    left, top = (img.width - w) // 2, (img.height - h) // 2
    return img.crop((left, top, left + w, top + h))


def procedural_background(colors: list[str], w: int, h: int, seed: int) -> Image.Image:
    rng = np.random.default_rng(seed)
    c1, c2 = (np.array(_hex(c), np.float32) for c in colors[:2])
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    angle = rng.uniform(0, np.pi)
    t = (np.cos(angle) * xx / w + np.sin(angle) * yy / h)
    t = (t - t.min()) / (t.max() - t.min())
    base = c1 * (1 - t[..., None]) + c2 * t[..., None]
    img = Image.fromarray(base.clip(0, 255).astype(np.uint8))

    # Soft glowing orbs (bokeh) for depth.
    glow = Image.new("RGB", (w, h), (0, 0, 0))
    d = ImageDraw.Draw(glow)
    for _ in range(int(rng.integers(10, 22))):
        r = int(rng.uniform(0.03, 0.16) * w)
        x, y = rng.uniform(0, w), rng.uniform(0, h)
        tint = (c2 * rng.uniform(0.6, 1.3) + 40).clip(0, 255).astype(int)
        d.ellipse([x - r, y - r, x + r, y + r], fill=tuple(int(v) for v in tint))
    glow = glow.filter(ImageFilter.GaussianBlur(w / 40))
    img = Image.blend(img, Image.fromarray(np.maximum(np.asarray(img), np.asarray(glow))), 0.45)

    # A few faint stars / dust specks.
    d = ImageDraw.Draw(img)
    for _ in range(int(rng.integers(60, 160))):
        x, y = rng.uniform(0, w), rng.uniform(0, h * 0.7)
        s = rng.uniform(0.6, 2.0)
        a = int(rng.uniform(120, 230))
        d.ellipse([x - s, y - s, x + s, y + s], fill=(a, a, a))
    # Vignette.
    v = 1 - 0.45 * (((xx / w - 0.5) ** 2 + (yy / h - 0.5) ** 2) / 0.5)
    arr = np.asarray(img).astype(np.float32) * v[..., None]
    return Image.fromarray(arr.clip(0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1))


def openai_background(prompt: str, w: int, h: int) -> Image.Image:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("visuals.background_source is 'openai' but OPENAI_API_KEY is not set in .env")
    resp = requests.post(
        "https://api.openai.com/v1/images/generations",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": "gpt-image-1", "prompt": prompt, "size": "1536x1024", "n": 1},
        timeout=300,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"OpenAI image error {resp.status_code}: {resp.text[:500]}")
    from io import BytesIO
    data = base64.b64decode(resp.json()["data"][0]["b64_json"])
    return _cover(Image.open(BytesIO(data)), w, h)


def folder_background(folder: Path, w: int, h: int, seed: int) -> Image.Image:
    files = sorted(p for p in folder.rglob("*") if p.suffix.lower() in IMAGE_EXT)
    if not files:
        raise RuntimeError(f"visuals.background_source is 'folder' but {folder} has no images")
    return _cover(Image.open(random.Random(seed).choice(files)), w, h)


def make_background(cfg_visuals: dict, theme: dict, root: Path, out: Path, seed: int) -> Path:
    w, h = cfg_visuals["width"], cfg_visuals["height"]
    source = cfg_visuals.get("background_source", "procedural")
    if source == "openai":
        img = openai_background(theme["image_prompt"], w, h)
    elif source == "folder":
        img = folder_background(root / "assets" / "backgrounds", w, h, seed)
    else:
        img = procedural_background(theme["colors"], w, h, seed)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, quality=95)
    return out


def make_loop_clip(image: Path, out: Path, cfg_visuals: dict) -> Path:
    """A short clip that slowly zooms in and back out, so it loops with no visible jump."""
    w, h, fps = cfg_visuals["width"], cfg_visuals["height"], cfg_visuals["fps"]
    secs = cfg_visuals.get("loop_seconds", 20)
    zoom = cfg_visuals.get("zoom_amount", 0.05)
    frames = int(secs * fps)
    # Upscale first so the slow zoom doesn't jitter.
    vf = (f"scale={w * 2}:{h * 2}:flags=lanczos,"
          f"zoompan=z='1+{zoom}*(1-cos(2*PI*on/{frames}))/2':d=1:"
          f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps={fps},format=yuv420p")
    ffmpeg.run([
        "-loop", "1", "-i", str(image), "-vf", vf, "-frames:v", str(frames),
        "-c:v", "libx264", "-preset", "medium", "-b:v", cfg_visuals.get("video_bitrate", "2500k"),
        "-g", str(fps * 2), "-movflags", "+faststart", str(out),
    ])
    return out


def make_video(loop_clip: Path, audio: Path, out: Path, seconds: float) -> Path:
    """Repeats the loop clip for the full length without re-encoding, then adds the audio."""
    ffmpeg.run([
        "-stream_loop", "-1", "-i", str(loop_clip), "-i", str(audio),
        "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "copy",
        "-t", f"{seconds:.3f}", "-movflags", "+faststart", str(out),
    ])
    return out


def _font(root: Path, size: int) -> ImageFont.ImageFont:
    for cand in FONT_CANDIDATES:
        p = Path(cand) if Path(cand).is_absolute() else root / cand
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default(size)


def length_label(minutes: int) -> str:
    if minutes % 60 == 0:
        hours = minutes // 60
        return f"{hours} HOUR" + ("S" if hours > 1 else "")
    return f"{minutes} MINUTE" + ("S" if minutes != 1 else "")


def make_thumbnail(background: Path, out: Path, title: str, minutes: int, root: Path) -> Path:
    img = Image.open(background).convert("RGB").resize((1280, 720), Image.LANCZOS)
    # Darken the lower part so text stays readable on any art.
    ramp = (200 * np.clip((np.arange(720) / 720 - 0.35) / 0.65, 0, 1)).astype(np.uint8)
    shade = Image.fromarray(np.repeat(ramp[:, None], 1280, axis=1), mode="L")
    img = Image.composite(Image.new("RGB", img.size, (0, 0, 0)), img, shade)
    d = ImageDraw.Draw(img)
    big, small = _font(root, 110), _font(root, 64)

    def centered(text, font, y):
        box = d.textbbox((0, 0), text, font=font)
        x = (1280 - (box[2] - box[0])) // 2
        d.text((x + 3, y + 3), text, font=font, fill=(0, 0, 0))
        d.text((x, y), text, font=font, fill=(255, 255, 255))

    size = 110
    while size > 50 and d.textbbox((0, 0), title.upper(), font=big)[2] > 1200:
        size -= 6
        big = _font(root, size)
    centered(title.upper(), big, 430)
    centered(length_label(minutes), small, 570)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, quality=90)
    return out


def cover_image(src: Path, out: Path, w: int, h: int) -> Path:
    """Centre-cropped w x h copy of an image (used for thumbnails)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    _cover(Image.open(src), w, h).save(out, quality=95)
    return out


def make_pan_loop(image: Path, out: Path, cfg_visuals: dict) -> Path:
    """A slow, smooth camera glide from one end of the painting to the other and back.

    Wide paintings pan left/right; squarer or tall ones pan top/bottom so the whole width
    stays visible. The glide eases in and out and returns to its start, so the clip loops
    seamlessly for the whole video. Frames are drawn with sub-pixel precision (no stutter).
    """
    import subprocess

    w, h, fps = cfg_visuals["width"], cfg_visuals["height"], cfg_visuals["fps"]
    one_way = float(cfg_visuals.get("pan_seconds", 60))
    frames = int(2 * one_way * fps)
    img = Image.open(image).convert("RGB")
    aspect = img.width / img.height
    min_slack = 1.12  # the painting is always at least 12% bigger than the frame along the pan
    if aspect >= 1.5:   # wide: fit height, pan horizontally
        scale = max(h / img.height, min_slack * w / img.width)
        horizontal = True
    else:               # square-ish or tall: fit width, pan vertically
        scale = max(w / img.width, min_slack * h / img.height)
        horizontal = False
    big = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    slack_x, slack_y = big.width - w, big.height - h

    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
           "-c:v", "libx264", "-preset", "medium", "-b:v", cfg_visuals.get("video_bitrate", "2500k"),
           "-pix_fmt", "yuv420p", "-g", str(fps * 2), "-movflags", "+faststart", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for i in range(frames):
            pos = 0.5 - 0.5 * np.cos(2 * np.pi * i / frames)  # 0 -> 1 -> 0, eased
            ox = slack_x * pos if horizontal else slack_x / 2
            oy = slack_y / 2 if horizontal else slack_y * pos
            frame = big.transform((w, h), Image.AFFINE, (1, 0, ox, 0, 1, oy), resample=Image.BILINEAR)
            proc.stdin.write(frame.tobytes())
        proc.stdin.close()
    except BrokenPipeError:
        pass
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed making pan loop: {proc.stderr.read().decode()[-1500:]}")
    return out

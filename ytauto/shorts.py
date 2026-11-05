"""Vertical YouTube Shorts (1080x1920, under 60 s) made from the same paintings and recordings
as the long videos. Four kinds, each with its own angle so a day's Shorts never repeat:

  pov      - a relatable hook ("POV: it's raining and you have to study")
  story    - the painting's story in timed captions, using the museum's own catalogue facts
  moment   - the most powerful passage of a piece, captioned with composer and title
  sleep    - a darker, slower wind-down clip before bed

Every Short tells viewers where the full-length version is.
"""

from __future__ import annotations

import subprocess
import wave
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from . import ffmpeg, thumbs

W, H, FPS = 1080, 1920, 24
SR = 44100
SAFE_X = 70            # left margin; the right edge is covered by Shorts' buttons
TEXT_W = W - SAFE_X - 170


@dataclass
class Caption:
    text: str
    start: float
    end: float
    y: int
    size: int = 70
    font: str = "serif"
    weight: str = "Bold"
    color: tuple = thumbs.CREAM


@dataclass
class ShortSpec:
    kind: str
    painting: Path
    audio: Path
    seconds: float = 50.0
    passage: str = "start"          # "start", "climax" or "calm"
    captions: list[Caption] = field(default_factory=list)
    darken: float = 0.0              # 0..1, for the sleep kind
    pan: str = "auto"                # "auto", "horizontal" or "vertical"
    reverse: bool = False            # glide the other way (e.g. to end on the painting's focal point)


# ----------------------------------------------------------------------------- audio

def _mono(path: Path, workdir: Path) -> tuple[np.ndarray, int]:
    tmp = workdir / "analysis.wav"
    ffmpeg.run(["-i", str(path), "-ac", "1", "-ar", "8000", "-c:a", "pcm_s16le", str(tmp)])
    with wave.open(str(tmp)) as w:
        data = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float32) / 32768
    tmp.unlink(missing_ok=True)
    return data, 8000


def pick_passage(path: Path, seconds: float, mode: str, workdir: Path) -> float:
    """Start time (s) of the best `seconds`-long passage: the loudest stretch for 'climax',
    a steady quiet-but-present stretch for 'calm', the opening for 'start'."""
    if mode == "start":
        return 0.0
    data, sr = _mono(path, workdir)
    hop = sr // 2
    rms = np.sqrt(np.convolve(data ** 2, np.ones(hop) / hop, mode="valid")[::hop] + 1e-9)
    n = int(seconds * 2)
    if len(rms) <= n:
        return 0.0
    windows = np.lib.stride_tricks.sliding_window_view(rms, n)
    mean, std = windows.mean(axis=1), windows.std(axis=1)
    if mode == "climax":
        score = mean
    else:  # calm: present but gentle, and steady
        score = -np.abs(mean - np.median(mean)) - 0.5 * std
    score[: 4] -= 1e3  # avoid starting mid-silence at the very top
    return float(np.argmax(score)) / 2


def make_audio(spec: ShortSpec, workdir: Path) -> Path:
    start = pick_passage(spec.audio, spec.seconds, spec.passage, workdir)
    fade_in = 0.4 if start == 0 else 2.0
    out = workdir / "short_audio.m4a"
    ffmpeg.run(["-ss", f"{start:.2f}", "-i", str(spec.audio), "-t", f"{spec.seconds:.2f}",
                "-af", f"afade=t=in:d={fade_in},afade=t=out:st={spec.seconds - 3:.2f}:d=3,"
                       f"loudnorm=I=-15:TP=-1.5:LRA=11,aresample={SR}",
                "-ac", "2", "-c:a", "aac", "-b:a", "192k", str(out)])
    return out


# ----------------------------------------------------------------------------- text

def _caption_layer(cap: Caption, root: Path) -> Image.Image:
    """A full-frame transparent layer with one caption, wrapped to the safe width."""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    font = thumbs._font(root, cap.font, cap.size, cap.weight)
    lines, line = [], ""
    for word in cap.text.split():
        trial = (line + " " + word).strip()
        if d.textbbox((0, 0), trial, font=font)[2] <= TEXT_W:
            line = trial
        else:
            lines.append(line)
            line = word
    lines.append(line)
    lh = int(cap.size * 1.25)
    y = cap.y
    for ln in lines:
        x = SAFE_X
        for dx, dy in ((3, 3), (2, 2)):
            d.text((x + dx, y + dy), ln, font=font, fill=(0, 0, 0, 200))
        d.text((x, y), ln, font=font, fill=(*cap.color, 255))
        y += lh
    return layer


# ----------------------------------------------------------------------------- video

def _prepare_painting(spec: ShortSpec) -> tuple[Image.Image, bool]:
    img = Image.open(spec.painting).convert("RGB")
    if spec.darken:
        img = ImageEnhance.Brightness(img).enhance(1 - spec.darken)
        img = ImageEnhance.Color(img).enhance(1 - spec.darken * 0.4)
    horizontal = spec.pan == "horizontal" or (spec.pan == "auto" and img.width / img.height > W / H * 1.15)
    if horizontal:
        scale = H * 1.04 / img.height
    else:
        scale = max(W / img.width, H * 1.2 / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    return img, horizontal


def brand_layer(root: Path, channel: str, handle: str = "") -> Image.Image:
    """Always-on channel branding: name at the top (below Shorts' header) so viewers know
    whose channel this is, plus the @handle if set, so they can find the full videos."""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    name_font = thumbs._font(root, "display", 40, "Bold")
    y = 170
    for dx in (2,):
        d.text((SAFE_X + dx, y + dx), channel.upper(), font=name_font, fill=(0, 0, 0, 190))
    d.text((SAFE_X, y), channel.upper(), font=name_font, fill=(*thumbs.GOLD, 255))
    w = d.textbbox((0, 0), channel.upper(), font=name_font)[2]
    d.line([(SAFE_X, y + 56), (SAFE_X + w, y + 56)], fill=(*thumbs.GOLD, 200), width=2)
    if handle:
        hf = thumbs._font(root, "text", 34, "SemiBold")
        d.text((SAFE_X + 2, y + 72), handle, font=hf, fill=(0, 0, 0, 190))
        d.text((SAFE_X, y + 70), handle, font=hf, fill=(*thumbs.CREAM, 235))
    return layer


def render(spec: ShortSpec, out: Path, root: Path, workdir: Path,
           channel: str = "Rest and Relaxation", handle: str = "") -> Path:
    workdir.mkdir(parents=True, exist_ok=True)
    audio = make_audio(spec, workdir)
    big, horizontal = _prepare_painting(spec)
    slack_x, slack_y = max(big.width - W, 0), max(big.height - H, 0)

    # Soft dark bands at top and bottom so text reads on any painting.
    grad = np.zeros((H, 1), np.float32)
    top, bottom = np.linspace(0.62, 0, 700), np.linspace(0, 0.7, 900)
    grad[:700, 0] = top
    grad[H - 900:, 0] = bottom
    shade = Image.fromarray((np.repeat(grad, W, axis=1) * 255).astype(np.uint8), "L")
    black = Image.new("RGB", (W, H), (6, 5, 4))

    layers = [(c, _caption_layer(c, root)) for c in spec.captions]
    brand = brand_layer(root, channel, handle)
    frames = int(spec.seconds * FPS)
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", str(audio), "-map", "0:v", "-map", "1:a", "-shortest",
           "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "copy", "-movflags", "+faststart", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for i in range(frames):
            t = i / FPS
            pos = 0.5 - 0.5 * np.cos(np.pi * i / max(frames - 1, 1))   # one smooth glide, eased
            if spec.reverse:
                pos = 1 - pos
            ox = slack_x * pos if horizontal else slack_x / 2
            oy = slack_y / 2 if horizontal else slack_y * pos
            frame = big.transform((W, H), Image.AFFINE, (1, 0, ox, 0, 1, oy), resample=Image.BILINEAR)
            frame = Image.composite(black, frame, shade)
            frame.paste(brand, (0, 0), brand)
            for cap, layer in layers:
                if cap.start <= t < cap.end:
                    a = min(1.0, (t - cap.start) / 0.6, (cap.end - t) / 0.6)
                    if a < 1:
                        layer_a = layer.copy()
                        layer_a.putalpha(layer.getchannel("A").point(lambda v, a=a: int(v * a)))
                        frame.paste(layer_a, (0, 0), layer_a)
                    else:
                        frame.paste(layer, (0, 0), layer)
            proc.stdin.write(frame.tobytes())
        proc.stdin.close()
    except BrokenPipeError:
        pass
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed making Short: {proc.stderr.read().decode()[-1500:]}")
    audio.unlink(missing_ok=True)
    return out

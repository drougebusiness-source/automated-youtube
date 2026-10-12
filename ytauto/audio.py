"""Joins tracks into one continuous mix of an exact length, with crossfades and loudness normalization."""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

from . import ffmpeg

SR = 44100


def to_wav(src: Path, dst: Path) -> Path:
    ffmpeg.run(["-i", str(src), "-vn", "-ac", "2", "-ar", str(SR), "-c:a", "pcm_s16le", str(dst)])
    return dst


def _read(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        data = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    return data.reshape(-1, 2).astype(np.float32) / 32768


def crossfade_concat(tracks: list[Path], out: Path, crossfade_s: float, max_seconds: float) -> Path:
    """Equal-power crossfade between consecutive tracks, streamed to disk. Stops once max_seconds is reached."""
    xf = int(crossfade_s * SR)
    limit = int(max_seconds * SR)
    written = 0
    tail: np.ndarray | None = None
    with wave.open(str(out), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)

        def emit(chunk: np.ndarray) -> None:
            nonlocal written
            chunk = chunk[: max(limit - written, 0)]
            w.writeframes((np.clip(chunk, -1, 1) * 32767).astype("<i2").tobytes())
            written += len(chunk)

        for path in tracks:
            if written >= limit:
                break
            audio = _read(path)
            if tail is not None:
                n = min(xf, len(tail), len(audio) // 3)
                theta = np.linspace(0, np.pi / 2, n, dtype=np.float32)[:, None]
                head = tail[len(tail) - n:] * np.cos(theta) + audio[:n] * np.sin(theta)
                emit(tail[: len(tail) - n])
                audio = np.concatenate([head, audio[n:]])
            keep = min(xf, len(audio) // 3)
            emit(audio[: len(audio) - keep])
            tail = audio[len(audio) - keep:]
        if tail is not None:
            emit(tail)
    return out


def build_mix(tracks: list[Path], workdir: Path, seconds: float, crossfade_s: float, target_lufs: float) -> Path:
    """Returns an AAC .m4a file exactly `seconds` long."""
    wavs = []
    for i, t in enumerate(tracks):
        wavs.append(t if t.suffix.lower() == ".wav" else to_wav(t, workdir / f"conv_{i:02d}.wav"))
    joined = crossfade_concat(wavs, workdir / "joined.wav", crossfade_s, seconds)
    have = ffmpeg.duration(joined)
    if have < seconds - 0.5:
        raise RuntimeError(f"Not enough music: got {have:.0f}s, need {seconds:.0f}s")
    out = workdir / "mix.m4a"
    fade_out = min(10.0, seconds / 6)
    ffmpeg.run([
        "-i", str(joined), "-t", f"{seconds:.3f}",
        "-af", f"afade=t=in:d=3,afade=t=out:st={seconds - fade_out:.3f}:d={fade_out:.3f},"
               f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11,aresample={SR}",
        "-c:a", "aac", "-b:a", "192k", str(out),
    ])
    joined.unlink(missing_ok=True)
    return out

"""Tracks from a folder of audio you own (assets/music_library)."""

from __future__ import annotations

import random
from pathlib import Path

AUDIO_EXT = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac"}


def list_audio(folder: Path) -> list[Path]:
    return sorted(p for p in folder.rglob("*") if p.suffix.lower() in AUDIO_EXT)


def make_tracks(folder: Path, total_seconds: float, seed: int, durations: dict[Path, float]) -> list[Path]:
    """Pick a random order of tracks long enough to fill the video. Repeats only if it must."""
    files = list_audio(folder)
    if not files:
        raise RuntimeError(f"music.source is 'library' but {folder} has no audio files")
    rng = random.Random(seed)
    picked, made = [], 0.0
    while made < total_seconds:
        batch = files[:]
        rng.shuffle(batch)
        for f in batch:
            picked.append(f)
            made += durations[f] if f in durations else 180
            if made >= total_seconds:
                break
    return picked

"""AI-composed music from the ElevenLabs Music API (POST /v1/music)."""

from __future__ import annotations

import os
import time
from pathlib import Path

import requests

API_URL = "https://api.elevenlabs.io/v1/music"
MAX_TRACK_SECONDS = 600  # the API allows up to 10 minutes per request


def compose(path: Path, prompt: str, seconds: float, model_id: str = "") -> Path:
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        raise RuntimeError("music.source is 'elevenlabs' but ELEVENLABS_API_KEY is not set in .env")
    body = {"prompt": prompt, "music_length_ms": int(min(seconds, MAX_TRACK_SECONDS) * 1000)}
    if model_id:
        body["model_id"] = model_id
    for attempt in range(4):
        resp = requests.post(API_URL, json=body, headers={"xi-api-key": key}, timeout=600)
        if resp.status_code == 429 or resp.status_code >= 500:
            time.sleep(10 * (attempt + 1))
            continue
        if resp.status_code != 200:
            raise RuntimeError(f"ElevenLabs error {resp.status_code}: {resp.text[:500]}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(resp.content)
        return path
    raise RuntimeError("ElevenLabs kept failing (rate limit or server error); try again later")


VARIATIONS = [
    "", "gentle variation", "slightly brighter", "slightly darker and deeper",
    "more spacious", "softer and more minimal", "with a new melody", "warmer tone",
]


def make_tracks(workdir: Path, total_seconds: float, track_seconds: float, theme: dict,
                seed: int, model_id: str = "") -> list[Path]:
    track_seconds = min(track_seconds, MAX_TRACK_SECONDS)
    tracks, made, i = [], 0.0, 0
    while made < total_seconds:
        length = min(track_seconds, max(total_seconds - made + 10, 30))
        variation = VARIATIONS[(seed + i) % len(VARIATIONS)]
        prompt = theme["music_prompt"] + (f", {variation}" if variation else "") + ", instrumental only, no vocals"
        tracks.append(compose(workdir / f"track_{i:02d}.mp3", prompt, length, model_id))
        made += length
        i += 1
    return tracks

"""Real classical recordings that are in the public domain.

Every recording in assets/music.json comes from Musopen's own collections on the Internet
Archive, which Musopen dedicated to the public domain (CC0 / Public Domain Mark): free for
commercial use. The compositions are centuries old and public domain too.
"""

from __future__ import annotations

import json
import random
import time
from pathlib import Path
from urllib.parse import quote

import requests

HEADERS = {"User-Agent": "ChannelUploader/1.0 (automated-youtube)"}
CREDIT = ("Music: recordings by Musopen (musopen.org), dedicated to the public domain (CC0 / Public Domain Mark). "
          "All compositions are in the public domain.")


def load_catalog(root: Path) -> dict[str, list[dict]]:
    return json.loads((root / "assets" / "music.json").read_text(encoding="utf-8"))["themes"]


def download(track: dict, cache_dir: Path) -> Path:
    folder = cache_dir / track["collection"]
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / Path(track["file"]).name
    if path.exists() and path.stat().st_size > 100_000:
        return path
    url = f"https://archive.org/download/{track['collection']}/{quote(track['file'])}"
    last = None
    for attempt in range(4):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=300)
            if resp.status_code == 200 and len(resp.content) > 100_000:
                tmp = path.with_suffix(".part")
                tmp.write_bytes(resp.content)
                tmp.replace(path)
                return path
            last = f"HTTP {resp.status_code}"
        except requests.RequestException as exc:
            last = str(exc)
        time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"Could not download {track['title']}: {last}")


def choose(catalog: dict[str, list[dict]], theme_name: str, total_seconds: float, seed: int) -> list[dict]:
    """A shuffled playlist for one video: no piece repeats unless the theme runs out."""
    pool = catalog.get(theme_name) or [t for ts in catalog.values() for t in ts]
    rng = random.Random(seed)
    playlist, made = [], 0.0
    while made < total_seconds:
        order = pool[:]
        rng.shuffle(order)
        for t in order:
            playlist.append(t)
            made += t["seconds"]
            if made >= total_seconds:
                break
    return playlist


def make_tracks(root: Path, total_seconds: float, theme: dict, seed: int) -> list[tuple[Path, dict]]:
    catalog = load_catalog(root)
    cache = root / "assets" / "music_cache"
    return [(download(t, cache), t) for t in choose(catalog, theme["name"], total_seconds, seed)]

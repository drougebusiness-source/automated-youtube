"""Public-domain paintings from the Art Institute of Chicago's open-access collection.

Every painting in assets/paintings.json is marked CC0 (public domain) by the museum, so it is
free for commercial use. Each video's description credits the painting it uses.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import requests

HEADERS = {"AIC-User-Agent": "channel-uploader (automated-youtube)", "User-Agent": "Mozilla/5.0"}
IIIF = "https://www.artic.edu/iiif/2/{image_id}/full/!3000,3000/0/default.jpg"


def load_catalog(root: Path) -> dict[str, list[dict]]:
    return json.loads((root / "assets" / "paintings.json").read_text(encoding="utf-8"))["themes"]


def pick(catalog: dict[str, list[dict]], theme_name: str, used: list[int]) -> dict:
    """The theme's next unused painting; once all are used, the one used longest ago."""
    options = catalog.get(theme_name) or [p for ps in catalog.values() for p in ps]
    unused = [p for p in options if p["id"] not in used]
    if unused:
        return unused[0]
    last_use = {pid: i for i, pid in enumerate(used)}
    return min(options, key=lambda p: last_use[p["id"]])


def download(painting: dict, cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"aic_{painting['id']}.jpg"
    if path.exists() and path.stat().st_size > 10_000:
        return path
    url = IIIF.format(image_id=painting["image_id"])
    for attempt in range(4):
        resp = requests.get(url, headers=HEADERS, timeout=120)
        if resp.status_code == 200 and len(resp.content) > 10_000:
            path.write_bytes(resp.content)
            return path
        time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"Could not download painting {painting['id']} (HTTP {resp.status_code})")


def credit(painting: dict) -> str:
    return (f"Artwork: \"{painting['title']}\" by {painting['artist']} ({painting['date']}). "
            f"Public domain (CC0), courtesy of the Art Institute of Chicago — "
            f"https://www.artic.edu/artworks/{painting['id']}")

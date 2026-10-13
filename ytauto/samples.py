"""Short preview videos (one per theme) plus an overview sheet of every painting, for choosing."""

from __future__ import annotations

import json
import logging

from PIL import Image, ImageDraw

from . import ffmpeg, metadata, paintings, pipeline, visuals
from .config import Config

log = logging.getLogger(__name__)


def make_samples(cfg: Config, seconds: int = 60) -> bool:
    ffmpeg.require_ffmpeg()
    out = cfg.output_dir / "samples"
    catalog = paintings.load_catalog(cfg.root)
    ok = True
    for i, theme in enumerate(cfg.themes):
        painting = catalog.get(theme["name"], [None])[0] if cfg["visuals"].get("background_source") == "paintings" else None
        folder = out / f"{i + 1}-{theme['name'].lower().replace(' ', '-')}"
        log.info("Sample %d/%d: %s%s", i + 1, len(cfg.themes), theme["name"],
                 f" with {painting['title']}" if painting else "")
        try:
            files = pipeline.make_video(cfg, theme, seconds / 60, folder, 1000 + i, 60, painting)
            meta = metadata.generate(theme, 60, cfg.raw, [], variant=i)
            desc = metadata.full_description(meta, cfg.raw, pipeline.credits_block(cfg, files, painting))
            (folder / "title_and_description.txt").write_text(f"{meta.title}\n\n{desc}\n", encoding="utf-8")
        except Exception:
            ok = False
            log.exception("  sample failed")
    overview(cfg, catalog, out / "all_paintings.jpg")
    log.info("Samples are in %s", out)
    return ok


def overview(cfg: Config, catalog: dict, path) -> None:
    """One image showing every painting in the catalogue, grouped by theme."""
    cache = cfg.root / "assets" / "painting_cache"
    tile_w, tile_h, cols = 360, 250, 5
    rows = []
    for theme, items in catalog.items():
        tiles = []
        for p in items:
            im = Image.open(paintings.download(p, cache)).convert("RGB")
            im.thumbnail((tile_w - 10, tile_h - 40))
            t = Image.new("RGB", (tile_w, tile_h), (24, 24, 24))
            t.paste(im, ((tile_w - im.width) // 2, 5))
            d = ImageDraw.Draw(t)
            d.text((6, tile_h - 32), f"{p['title'][:44]}", fill=(240, 240, 240))
            d.text((6, tile_h - 17), f"{p['artist'][:30]} ({p['date']})"[:52], fill=(170, 170, 170))
            tiles.append(t)
        header = Image.new("RGB", (tile_w * cols, 40), (0, 0, 0))
        ImageDraw.Draw(header).text((10, 12), theme.upper(), fill=(255, 220, 150))
        rows.append(header)
        for k in range(0, len(tiles), cols):
            row = Image.new("RGB", (tile_w * cols, tile_h), (0, 0, 0))
            for j, t in enumerate(tiles[k:k + cols]):
                row.paste(t, (j * tile_w, 0))
            rows.append(row)
    sheet = Image.new("RGB", (tile_w * cols, sum(r.height for r in rows)), (0, 0, 0))
    y = 0
    for r in rows:
        sheet.paste(r, (0, y))
        y += r.height
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path, quality=85)

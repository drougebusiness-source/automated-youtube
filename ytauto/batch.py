"""Make many days of videos in one go, upload them as private while YouTube allows, and
keep a list of anything still waiting so it can be uploaded later."""

from __future__ import annotations

import csv
import json
import logging
import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from . import ffmpeg, metadata, paintings, pipeline, youtube
from .config import Config

log = logging.getLogger(__name__)
LIMIT_REASONS = ("quotaExceeded", "uploadLimitExceeded", "dailyLimitExceeded", "rateLimitExceeded")
MIN_FREE_GB = 3


def _path(cfg: Config) -> Path:
    return cfg.state_dir / "batch.json"


def load(cfg: Config) -> dict:
    p = _path(cfg)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"items": []}


def save(cfg: Config, data: dict) -> None:
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    _path(cfg).write_text(json.dumps(data, indent=2), encoding="utf-8")
    write_upload_list(cfg, data)


def write_upload_list(cfg: Config, data: dict) -> None:
    """A spreadsheet of every batch video: when to schedule it, its title, and where it is."""
    out = cfg.output_dir / "batch" / "UPLOAD_LIST.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["schedule_date", "schedule_time", "minutes", "theme", "title", "status", "youtube_link", "file", "painting"])
        for it in sorted(data["items"], key=lambda i: (i["publish_date"], i["slot"])):
            status = "uploaded (private)" if it.get("video_id") else ("ready to upload" if Path(it["folder"], "video.mp4").exists() else "missing")
            w.writerow([it["publish_date"], it["publish_at"], it["minutes"], it["theme"], it["title"], status,
                        f"https://youtu.be/{it['video_id']}" if it.get("video_id") else "",
                        str(Path(it["folder"], "video.mp4")), it.get("painting_credit", "")])


def _is_limit(exc: Exception) -> bool:
    text = str(exc) + str(getattr(exc, "content", b""))
    return any(r in text for r in LIMIT_REASONS)


def _upload_item(cfg: Config, yt, item: dict) -> None:
    folder = Path(item["folder"])
    meta = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
    when = None
    if cfg["upload"].get("mode", "private") == "scheduled":
        d = date.fromisoformat(item["publish_date"])
        when = pipeline.publish_time(cfg, d, item["publish_at"])
    vid = youtube.upload(yt, folder / "video.mp4", folder / "thumbnail.jpg", meta["title"], meta["description"],
                         meta["tags"], cfg["upload"], when)
    item["video_id"] = vid
    log.info("  uploaded: https://youtu.be/%s", vid)
    if not cfg["output"].get("keep_files_after_upload", False):
        (folder / "video.mp4").unlink(missing_ok=True)


def run_batch(cfg: Config, days: int, upload: bool = True, start: date | None = None,
              stop_at_limit: bool = False) -> bool:
    """stop_at_limit: stop making videos once YouTube's daily limit is hit (for servers that
    don't keep files between runs). The next run continues where this one stopped."""
    ffmpeg.require_ffmpeg()
    data = load(cfg)
    state = pipeline.load_state(cfg)
    tz = ZoneInfo(cfg["channel"].get("timezone", "UTC"))
    if start is None:
        start = datetime.now(tz).date() + timedelta(days=1)
    yt = youtube.client(cfg.root) if upload and cfg["upload"].get("enabled", True) else None
    can_upload = yt is not None
    done = {(it["publish_date"], it["slot"]): it for it in data["items"]}
    recent_titles = [it["title"] for it in data["items"]] + [v.get("title", "") for v in state["videos"]]
    total = days * len(cfg["schedule"]["videos"])
    count, ok = 0, True

    for day in range(days):
        pd = (start + timedelta(days=day)).isoformat()
        for slot, entry in enumerate(cfg["schedule"]["videos"]):
            count += 1
            item = done.get((pd, slot))
            if item and (item.get("video_id") or Path(item["folder"], "video.mp4").exists()):
                if can_upload and not item.get("video_id"):
                    can_upload = _try_upload(cfg, yt, item, data)
                continue
            if stop_at_limit and upload and not can_upload:
                log.info("Stopping for today: YouTube's upload limit was reached. Run again tomorrow to continue.")
                save(cfg, data)
                return ok
            free_gb = shutil.disk_usage(cfg.root).free / 1e9
            if free_gb < MIN_FREE_GB:
                log.error("Stopping: only %.1f GB of disk space left. Upload or delete some videos, then run again.", free_gb)
                return False
            # A slot that was planned before (but never finished) keeps its theme, so each day
            # still gets three different themes.
            planned = next((t for t in cfg.themes if item and t["name"] == item["theme"]), None)
            theme = planned
            if theme is None:
                used_today = {i["theme"] for i in data["items"] if i["publish_date"] == pd}
                for k in range(len(cfg.themes)):
                    theme = cfg.themes[(state["theme_index"] + k) % len(cfg.themes)]
                    if theme["name"] not in used_today:
                        break
            minutes = int(entry["minutes"])
            folder = cfg.output_dir / "batch" / pd / f"{slot}-{minutes}min-{theme['name'].lower().replace(' ', '-')}"
            log.info("[%d/%d] %s, %d min, %s", count, total, pd, minutes, theme["name"])
            try:
                painting = pipeline.choose_painting(cfg, theme, state)
                seed = pipeline.seed_for(pd, slot) ^ 0x5EED
                files = pipeline.make_video(cfg, theme, minutes, folder, seed, minutes, painting)
                # Each theme cycles through the title wordings, so repeat themes get new titles.
                variant = sum(1 for i in data["items"] if i["theme"] == theme["name"] and (i["publish_date"], i["slot"]) != (pd, slot))
                meta = metadata.generate(theme, minutes, cfg.raw, recent_titles, variant=variant)
                credit = paintings.credit(painting) if painting else ""
                description = metadata.full_description(meta, cfg.raw, pipeline.credits_block(cfg, files, painting))
                (folder / "metadata.json").write_text(json.dumps(
                    {"title": meta.title, "description": description, "tags": meta.tags}, indent=2), encoding="utf-8")
                (folder / "title_and_description.txt").write_text(
                    f"{meta.title}\n\n{description}\n\nTags: {', '.join(meta.tags)}\n", encoding="utf-8")
                item = {"publish_date": pd, "slot": slot, "publish_at": entry["publish_at"], "minutes": minutes,
                        "theme": theme["name"], "title": meta.title, "folder": str(folder),
                        "painting": painting["id"] if painting else None, "painting_credit": credit}
                data["items"] = [i for i in data["items"] if (i["publish_date"], i["slot"]) != (pd, slot)] + [item]
                done[(pd, slot)] = item
                recent_titles.append(meta.title)
                if not planned:
                    state["theme_index"] += 1
                if painting:
                    state.setdefault("paintings_used", []).append(painting["id"])
                pipeline.save_state(cfg, state)
                save(cfg, data)
            except Exception:
                ok = False
                log.exception("  FAILED making this video; moving on to the next one")
                continue
            if can_upload:
                can_upload = _try_upload(cfg, yt, item, data)
    save(cfg, data)
    waiting = sum(1 for i in data["items"] if not i.get("video_id"))
    log.info("Batch finished. %d videos made, %d waiting to upload. See %s",
             len(data["items"]), waiting, cfg.output_dir / "batch" / "UPLOAD_LIST.csv")
    if waiting and upload:
        log.info("Upload the rest on another day with:  python -m ytauto upload-pending")
    return ok


def _try_upload(cfg: Config, yt, item: dict, data: dict) -> bool:
    """Returns False once YouTube's daily limit is reached, so later videos aren't attempted today."""
    try:
        log.info("  uploading as private: %s", item["title"])
        _upload_item(cfg, yt, item)
        save(cfg, data)
        return True
    except Exception as exc:
        if _is_limit(exc):
            log.warning("  YouTube's daily upload limit reached. Videos keep being made; "
                        "run `python -m ytauto upload-pending` tomorrow to upload the rest.")
            return False
        log.exception("  upload failed for this video; it stays on the waiting list")
        return True


def upload_pending(cfg: Config) -> bool:
    data = load(cfg)
    yt = youtube.client(cfg.root)
    pending = [i for i in sorted(data["items"], key=lambda i: (i["publish_date"], i["slot"]))
               if not i.get("video_id") and Path(i["folder"], "video.mp4").exists()]
    log.info("%d videos waiting to upload", len(pending))
    for item in pending:
        if not _try_upload(cfg, yt, item, data):
            break
    save(cfg, data)
    left = sum(1 for i in data["items"] if not i.get("video_id"))
    log.info("%d still waiting.%s", left, " Run this again tomorrow." if left else " All uploaded!")
    return True

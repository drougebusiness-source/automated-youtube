"""A performance report for the channel's videos: views, likes and comments, grouped by
theme, length and painting, so we can see what works."""

from __future__ import annotations

import csv
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone

from . import youtube
from .config import Config

log = logging.getLogger(__name__)


def _known_videos(cfg: Config) -> dict[str, dict]:
    """Every video the bot uploaded, with what we know about it (theme, length, painting...)."""
    known: dict[str, dict] = {}
    for name in ("history.json", "batch.json"):
        path = cfg.state_dir / name
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for v in data.get("videos", []) + data.get("items", []):
            if v.get("video_id"):
                known[v["video_id"]] = v
    return known


def report(cfg: Config) -> bool:
    yt = youtube.client(cfg.root)
    ch = yt.channels().list(part="statistics,snippet", mine=True).execute()["items"][0]
    st = ch["statistics"]
    log.info("Channel %s: %s subscribers, %s total views, %s videos", ch["snippet"]["title"],
             st.get("subscriberCount", "hidden"), st.get("viewCount"), st.get("videoCount"))

    known = _known_videos(cfg)
    ids = list(known)
    rows = []
    now = datetime.now(timezone.utc)
    for i in range(0, len(ids), 50):
        resp = yt.videos().list(part="snippet,statistics,status", id=",".join(ids[i:i + 50])).execute()
        for v in resp.get("items", []):
            meta = known[v["id"]]
            s = v.get("statistics", {})
            published = v["snippet"].get("publishedAt")
            age_days = None
            if v["status"].get("privacyStatus") == "public" and published:
                age_days = max((now - datetime.fromisoformat(published.replace("Z", "+00:00"))).total_seconds() / 86400, 0.1)
            rows.append({
                "video_id": v["id"], "status": v["status"].get("privacyStatus"),
                "publish_at": v["status"].get("publishAt", ""), "published": published,
                "theme": meta.get("theme", ""), "minutes": meta.get("minutes", ""),
                "slot_time": meta.get("publish_at", ""), "painting": meta.get("painting", ""),
                "views": int(s.get("viewCount", 0)), "likes": int(s.get("likeCount", 0)),
                "comments": int(s.get("commentCount", 0)),
                "views_per_day": round(int(s.get("viewCount", 0)) / age_days, 1) if age_days else "",
                "title": v["snippet"]["title"],
            })
    rows.sort(key=lambda r: -r["views"])
    out = cfg.output_dir / "stats.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["video_id"])
        w.writeheader()
        w.writerows(rows)

    public = [r for r in rows if r["status"] == "public"]
    log.info("%d videos found: %d public, %d private/scheduled", len(rows), len(public), len(rows) - len(public))
    log.info("--- every public video, most viewed first ---")
    for r in public:
        log.info("%6d views %4d likes %3d comments  %5s/day  %-16s %3s min %s  %s",
                 r["views"], r["likes"], r["comments"], r["views_per_day"], r["theme"], r["minutes"],
                 r["slot_time"], r["title"][:70])
    for key in ("theme", "minutes", "slot_time"):
        groups: dict[str, list[dict]] = defaultdict(list)
        for r in public:
            groups[str(r[key])].append(r)
        log.info("--- by %s (average views per day) ---", key)
        for k, rs in sorted(groups.items(), key=lambda kv: -sum(float(r["views_per_day"] or 0) for r in kv[1]) / len(kv[1])):
            avg = sum(float(r["views_per_day"] or 0) for r in rs) / len(rs)
            log.info("  %-20s %5.1f views/day over %d videos (%d views total)", k, avg, len(rs), sum(r["views"] for r in rs))
    return True

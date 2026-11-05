"""Four Shorts a day, each pointing to one of that day's long videos.

  07:00 pov     - relatable hook          -> the day's Rainy Study video (else the 1-hour one)
  12:00 story   - the painting's story    -> the day's 30-minute video
  16:00 moment  - a piece's high point    -> the day's 15-minute video
  21:00 sleep   - wind-down before bed    -> the day's Deep Sleep video (else the 1-hour one)

Paintings and passages differ from each other and from the day's long videos. Painting facts
come only from the Art Institute of Chicago's catalogue (CC0).
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from . import paintings, pipeline, shorts, thumbs, youtube
from .config import Config
from .music import classical_pd
from .shorts import Caption as C, ShortSpec
from .visuals import length_label

log = logging.getLogger(__name__)

SLOTS = [("pov", "07:00"), ("story", "12:00"), ("moment", "16:00"), ("sleep", "21:00")]
HOOKS = {
    "Rainy Study": ["POV: it's raining and you still have to study", "POV: 2 AM, one more chapter to go",
                    "POV: library window, rain outside, deadline tomorrow", "POV: rainy Sunday, notes everywhere"],
    "Deep Sleep": ["POV: you finally put your phone down", "POV: the house is quiet and the lights are off"],
    "Morning Light": ["POV: slow morning, coffee still warm", "POV: you woke up before the alarm"],
    "Forest Wind": ["POV: reading by an open window", "POV: a long walk with nowhere to be"],
    "Ocean Meditation": ["POV: waves outside, nowhere to be", "POV: the sea is calm and so are you"],
    "Starlight Focus": ["POV: late-night deep work session", "POV: everyone's asleep and you're finally focused"],
}
AIC = "https://api.artic.edu/api/v1/artworks/{id}?fields=title,artist_title,date_display,short_description,medium_display,is_on_view"
HEADERS = {"AIC-User-Agent": "channel-uploader (automated-youtube)", "User-Agent": "Mozilla/5.0"}


def _path(cfg: Config) -> Path:
    return cfg.state_dir / "shorts.json"


def load(cfg: Config) -> dict:
    p = _path(cfg)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"items": []}


def save(cfg: Config, data: dict) -> None:
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    _path(cfg).write_text(json.dumps(data, indent=2), encoding="utf-8")


def _sentences(text: str, max_len: int = 110, count: int = 3) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    return [p for p in parts if 0 < len(p) <= max_len][:count]


def _facts(pid: int) -> dict:
    try:
        r = requests.get(AIC.format(id=pid), headers=HEADERS, timeout=30)
        r.raise_for_status()
        return r.json()["data"]
    except Exception as exc:
        log.warning("  could not fetch museum facts for %s (%s)", pid, exc)
        return {}


def _link_for(kind: str, longs: list[dict]) -> dict | None:
    by_slot = {i["slot"]: i for i in longs}
    by_theme = {i["theme"]: i for i in longs}
    pick = {"pov": by_theme.get("Rainy Study") or by_slot.get(0),
            "story": by_slot.get(1), "moment": by_slot.get(2),
            "sleep": by_theme.get("Deep Sleep") or by_slot.get(0)}[kind]
    return pick or (longs[0] if longs else None)


def _pick_painting(cfg, theme: str, avoid: set[int], used: list[int]) -> dict:
    options = paintings.load_catalog(cfg.root).get(theme) or []
    fresh = [p for p in options if p["id"] not in avoid]
    pool = fresh or options
    last = {pid: i for i, pid in enumerate(used)}
    return min(pool, key=lambda p: last.get(p["id"], -1))


def _pick_track(cfg, theme: str, avoid: set[str], used: list[str], min_seconds: int = 70) -> dict:
    options = [t for t in classical_pd.load_catalog(cfg.root).get(theme, []) if t["seconds"] >= min_seconds]
    pool = [t for t in options if t["file"] not in avoid] or options
    last = {f: i for i, f in enumerate(used)}
    return min(pool, key=lambda t: last.get(t["file"], -1))


def plan_short(cfg, kind: str, day_index: int, link: dict, avoid_paintings: set[int], avoid_tracks: set[str],
               data: dict) -> tuple[ShortSpec, dict]:
    theme = "Deep Sleep" if kind == "sleep" else link["theme"]
    used_p = [i["painting"] for i in data["items"]]
    used_t = [i["track"] for i in data["items"]]
    painting = _pick_painting(cfg, theme, avoid_paintings, used_p)
    facts = {}
    if kind == "story":
        # Prefer a painting the museum has written a short story about.
        options = sorted(paintings.load_catalog(cfg.root).get(theme) or [],
                         key=lambda p: (p["id"] in avoid_paintings, -max([i for i, x in enumerate(used_p) if x == p["id"]] or [-1]) * -1))
        for cand in options[:8]:
            f = _facts(cand["id"])
            if f.get("short_description"):
                painting, facts = cand, f
                break
    track = _pick_track(cfg, theme, avoid_tracks, used_t)
    p_path = paintings.download(painting, cfg.root / "assets" / "painting_cache")
    a_path = classical_pd.download(track, cfg.root / "assets" / "music_cache")
    composer = track["composer"]
    last = composer.split()[-1]
    piece = track["title"]
    m = int(link["minutes"])
    span = f"{m // 60}-hour" if m % 60 == 0 else f"{m}-minute"
    cta = f"Full {span} {link['theme']} on the channel"
    credit = f"{painting['artist'].split(' (')[0]} · {painting['title']} ({painting['date']})"
    G = thumbs.GOLD
    if kind == "pov":
        hooks = HOOKS.get(theme, HOOKS["Rainy Study"])
        hook = hooks[day_index % len(hooks)]
        caps = [C(hook, 0.3, 15, 300, 78, "serif", "Bold"),
                C(f"{last} · {piece.split(':')[0]}", 2, 49.5, 1390, 42, "text", "SemiBold", G),
                C(cta, 36, 49.5, 1460, 44, "text", "Bold")]
        spec = ShortSpec("pov", p_path, a_path, 50, "start", caps)
        title = f"{hook} | {last} #shorts"
    elif kind == "story":
        f = facts or _facts(painting["id"])
        lines = _sentences(f.get("short_description") or "")
        if not lines and f.get("medium_display"):
            lines = [f"{f['medium_display']}."]
        if f.get("is_on_view"):
            lines.append("It hangs today in the Art Institute of Chicago.")
        else:
            lines.append("It belongs to the Art Institute of Chicago.")
        caps = [C(painting["title"], 0.3, 8.5, 300, 88, "display", "Bold"),
                C(f"{painting['artist'].split(' (')[0]}, {painting['date']}", 0.8, 8.5, 440, 50, "text", "SemiBold", G)]
        t, step = 8.5, (45 - 8.5) / max(len(lines), 1)
        for ln in lines:
            caps.append(C(ln, t, t + step, 300, 62, "serif", "Bold"))
            t += step
        caps += [C(f"Music: {last}, {piece.split(':')[0]}", 2, 54.5, 1390, 38, "text", "SemiBold", G),
                 C(cta, 45, 54.5, 1460, 44, "text", "Bold")]
        spec = ShortSpec("story", p_path, a_path, 55, "start", caps)
        title = f"{painting['title']} by {painting['artist'].split(' (')[0]}, with {last} #shorts"
    elif kind == "moment":
        caps = [C(composer, 0.3, 11, 300, 78, "display", "Bold"),
                C(piece, 0.8, 11, 420, 50, "text", "SemiBold", G),
                C(credit, 2, 49.5, 1390, 38, "text", "SemiBold", G),
                C(cta, 38, 49.5, 1460, 44, "text", "Bold")]
        spec = ShortSpec("moment", p_path, a_path, 50, "climax", caps)
        title = f"{last} – {piece.split(':')[0]} #shorts"
    else:  # sleep
        caps = [C("Close your eyes.", 1, 13, 320, 88, "serif", "Bold Italic"),
                C(f"Let {last} carry you to sleep.", 13, 26, 320, 72, "serif", "Bold Italic"),
                C(f"{credit}  ·  {last}", 2, 57.5, 1390, 34, "text", "SemiBold", G),
                C(cta, 44, 57.5, 1450, 44, "text", "Bold")]
        spec = ShortSpec("sleep", p_path, a_path, 58, "start", caps, darken=0.12, reverse=True)
        title = f"Close your eyes: {last} for sleep #shorts"
    url = f"https://youtu.be/{link['video_id']}"
    description = "\n\n".join([
        f"Full version: {url}",
        f"Music: {composer} – {piece}. Recording by Musopen (musopen.org), public domain.",
        paintings.credit(painting),
        f"{cfg['channel']['name']}: timeless classical music and art, for sleep, study and calm.",
        "#shorts #classicalmusic #relaxingmusic",
    ])
    meta = {"title": title[:100], "description": description,
            "tags": ["shorts", "classical music", last.lower(), link["theme"].lower(), "relaxing music"]}
    item = {"kind": kind, "painting": painting["id"], "track": track["file"], "links_to": link["video_id"],
            "theme": theme, "title": meta["title"]}
    return spec, {"item": item, "meta": meta}


def run_shorts(cfg: Config, start: date, days: int, upload: bool = True, stop_at_limit: bool = False) -> bool:
    from .batch import _is_limit
    longs_all = json.loads((cfg.state_dir / "batch.json").read_text(encoding="utf-8"))["items"]
    data = load(cfg)
    done = {(i["publish_date"], i["slot"]) for i in data["items"] if i.get("video_id")}
    tz = ZoneInfo(cfg["channel"].get("timezone", "UTC"))
    now = datetime.now(timezone.utc)
    yt = youtube.client(cfg.root) if upload else None
    can_upload, ok, comment_ok = upload, True, True
    for d in range(days):
        day = start + timedelta(days=d)
        pd = day.isoformat()
        longs = [i for i in longs_all if i["publish_date"] == pd and i.get("video_id")]
        if not longs:
            log.info("%s: no long video to point to; skipping that day's Shorts", pd)
            continue
        avoid_p = {i.get("painting") for i in longs} | {i["painting"] for i in data["items"] if i["publish_date"] == pd}
        avoid_t = {i["track"] for i in data["items"] if i["publish_date"] == pd}
        for slot, (kind, hhmm) in enumerate(SLOTS):
            if (pd, slot) in done:
                continue
            when = pipeline.publish_time(cfg, day, hhmm)
            if when <= now + timedelta(minutes=20):
                log.info("%s %s %s: time already passed, skipping", pd, hhmm, kind)
                continue
            if stop_at_limit and upload and not can_upload:
                save(cfg, data)
                return ok
            link = _link_for(kind, longs)
            folder = cfg.output_dir / "shorts" / pd / f"{slot}-{kind}"
            log.info("[short] %s %s %s -> %s", pd, hhmm, kind, link["theme"])
            try:
                spec, plan = plan_short(cfg, kind, d, link, avoid_p, avoid_t, data)
                folder.mkdir(parents=True, exist_ok=True)
                video = shorts.render(spec, folder / "short.mp4", cfg.root, folder / "work",
                                      cfg["channel"]["name"], cfg["channel"].get("handle", ""))
                shutil.rmtree(folder / "work", ignore_errors=True)
                (folder / "metadata.json").write_text(json.dumps(plan["meta"], indent=2), encoding="utf-8")
            except Exception:
                ok = False
                log.exception("  FAILED making this Short; moving on")
                continue
            item = plan["item"] | {"publish_date": pd, "slot": slot, "publish_at": hhmm}
            avoid_p.add(item["painting"])
            avoid_t.add(item["track"])
            data["items"] = [i for i in data["items"] if (i["publish_date"], i["slot"]) != (pd, slot)] + [item]
            save(cfg, data)
            if not can_upload:
                continue
            try:
                vid = youtube.upload(yt, video, None, plan["meta"]["title"], plan["meta"]["description"],
                                     plan["meta"]["tags"], cfg["upload"] | {"contains_synthetic_media": False}, None)
                item["video_id"] = vid
                log.info("  uploaded: https://youtu.be/%s", vid)
                yt.videos().update(part="status", body={"id": vid, "status": {
                    "privacyStatus": "private", "publishAt": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "selfDeclaredMadeForKids": False, "containsSyntheticMedia": False}}).execute()
                item["scheduled_for"] = when.isoformat()
                log.info("  scheduled for %s UTC", when.strftime("%Y-%m-%d %H:%M"))
                video.unlink(missing_ok=True)
                if comment_ok:
                    try:
                        yt.commentThreads().insert(part="snippet", body={"snippet": {"videoId": vid, "topLevelComment": {
                            "snippet": {"textOriginal": f"Full {link['theme']} version: https://youtu.be/{link['video_id']}"}}}}).execute()
                    except Exception as exc:
                        comment_ok = False
                        log.warning("  can't post comments with this sign-in (%s); the link is in the description", exc)
            except Exception as exc:
                if _is_limit(exc):
                    can_upload = False
                    log.warning("  YouTube's daily upload limit reached; the rest continue next run")
                else:
                    ok = False
                    log.exception("  upload failed for this Short; it will be retried next run")
            save(cfg, data)
    save(cfg, data)
    n = sum(1 for i in data["items"] if i.get("video_id"))
    log.info("Shorts: %d uploaded and scheduled in total", n)
    return ok

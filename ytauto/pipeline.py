"""The daily run: make each scheduled video, then upload it."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import shutil
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from . import audio, ffmpeg, metadata, paintings, thumbs, visuals, youtube
from .config import Config
from .music import classical, classical_pd, elevenlabs, library, procedural

log = logging.getLogger(__name__)


# ----------------------------------------------------------------------------- state

def load_state(cfg: Config) -> dict:
    path = cfg.state_dir / "history.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"theme_index": 0, "videos": []}


def save_state(cfg: Config, state: dict) -> None:
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    (cfg.state_dir / "history.json").write_text(json.dumps(state, indent=2), encoding="utf-8")


def already_done(state: dict, publish_date: str, slot: int) -> bool:
    return any(v["publish_date"] == publish_date and v["slot"] == slot and v.get("video_id")
               for v in state["videos"])


def seed_for(publish_date: str, slot: int) -> int:
    return int(hashlib.sha256(f"{publish_date}-{slot}".encode()).hexdigest()[:8], 16)


def publish_time(cfg: Config, publish_date: date, hhmm: str) -> datetime:
    tz = ZoneInfo(cfg["channel"].get("timezone", "UTC"))
    h, m = (int(x) for x in hhmm.split(":"))
    return datetime.combine(publish_date, time(h, m), tzinfo=tz).astimezone(timezone.utc)


# ----------------------------------------------------------------------------- music

def make_music(cfg: Config, theme: dict, workdir: Path, seconds: float, seed: int) -> tuple[Path, list[dict]]:
    """Returns the finished mix and a tracklist [{start, composer, title}] (empty for generated music)."""
    m = cfg["music"]
    xf = float(m.get("crossfade_seconds", 8))
    track_s = float(m.get("track_minutes", 4)) * 60
    # Crossfades overlap tracks, so ask for a little more than the video length.
    need = seconds + xf * (math.ceil(seconds / max(track_s - xf, 1)) + 2) + 5
    source = m.get("source", "procedural")
    tracks_dir = workdir / "tracks"
    tracks_dir.mkdir(parents=True, exist_ok=True)
    info: list[dict] = []

    if source == "classical_pd":
        # Extra margin: silence trimming and crossfades shorten the playlist a little.
        picked = classical_pd.make_tracks(cfg.root, seconds * 1.08 + 240, theme, seed)
        tracks, info = [p for p, _ in picked], [t for _, t in picked]
    elif source == "elevenlabs":
        tracks = elevenlabs.make_tracks(tracks_dir, need, track_s, theme, seed, m.get("elevenlabs_model", ""))
    elif source == "classical":
        tracks = classical.make_tracks(tracks_dir, cfg.root / "assets" / "midi", m.get("soundfont", ""),
                                       need, seed, ffmpeg.duration)
    elif source == "library":
        folder = cfg.root / "assets" / "music_library"
        durations = {f: ffmpeg.duration(f) for f in library.list_audio(folder)}
        tracks = library.make_tracks(folder, need, seed, durations)
    else:
        tracks = procedural.make_tracks(tracks_dir, need, track_s, theme, seed)

    mix, starts = audio.build_mix(tracks, workdir, seconds, xf, float(m.get("target_lufs", -16)),
                                  level_tracks=(source == "classical_pd"))
    shutil.rmtree(tracks_dir, ignore_errors=True)
    for f in workdir.glob("conv_*.wav"):
        f.unlink()
    tracklist = [{"start": st, "composer": t["composer"], "title": t["title"]}
                 for st, t in zip(starts, info) if st < seconds - 20]
    return mix, tracklist


def music_credit(cfg: Config) -> str:
    return classical_pd.CREDIT if cfg["music"].get("source") == "classical_pd" else ""


# ----------------------------------------------------------------------------- one video

def make_video(cfg: Config, theme: dict, minutes: float, workdir: Path, seed: int,
               label_minutes: int | None = None, painting: dict | None = None,
               thumb_variant: str | None = None) -> dict:
    seconds = minutes * 60
    workdir.mkdir(parents=True, exist_ok=True)
    log.info("  music (%s)...", cfg["music"].get("source", "procedural"))
    mix, tracklist = make_music(cfg, theme, workdir, seconds, seed)
    if painting is not None:
        log.info("  painting: %s, %s", painting["title"], painting["artist"])
        src = paintings.download(painting, cfg.root / "assets" / "painting_cache")
        bg = visuals.cover_image(src, workdir / "background.jpg", cfg["visuals"]["width"], cfg["visuals"]["height"])
        log.info("  video (slow pan across the painting)...")
        loop = visuals.make_pan_loop(src, workdir / "loop.mp4", cfg["visuals"])
    else:
        log.info("  artwork (%s)...", cfg["visuals"].get("background_source", "procedural"))
        bg = visuals.make_background(cfg["visuals"], theme, cfg.root, workdir / "background.jpg", seed)
        log.info("  video...")
        loop = visuals.make_loop_clip(bg, workdir / "loop.mp4", cfg["visuals"])
    video = visuals.make_video(loop, mix, workdir / "video.mp4", seconds)
    loop.unlink(missing_ok=True)
    mix.unlink(missing_ok=True)
    if painting is not None:
        # Three designs for A/B testing; the one assigned to this video is uploaded,
        # the others are kept for YouTube Studio's "Test & Compare".
        variants = thumbs.make_variants(src, workdir, theme, label_minutes or round(minutes), tracklist, cfg.root)
        thumb = variants.get(thumb_variant or "A-gallery", variants["A-gallery"])
    else:
        thumb = visuals.make_thumbnail(bg, workdir / "thumbnail.jpg", theme["name"], label_minutes or round(minutes), cfg.root)
    return {"video": video, "thumbnail": thumb, "background": bg, "tracklist": tracklist}


def credits_block(cfg: Config, files: dict, painting: dict | None) -> str:
    """Tracklist with timestamps (YouTube turns these into chapters) plus artwork and music credits."""
    parts = []
    if files.get("tracklist"):
        lines = [f"{metadata.timestamp(t['start'])} {t['composer']} – {t['title']}" for t in files["tracklist"]]
        parts.append("Tracklist:\n" + "\n".join(lines))
    if painting:
        parts.append(paintings.credit(painting))
    if music_credit(cfg):
        parts.append(music_credit(cfg))
    return "\n\n".join(parts)


def choose_painting(cfg: Config, theme: dict, state: dict) -> dict | None:
    if cfg["visuals"].get("background_source") != "paintings":
        return None
    return paintings.pick(paintings.load_catalog(cfg.root), theme["name"], state.setdefault("paintings_used", []))


def run(cfg: Config, *, upload: bool = True, test: bool = False, run_date: date | None = None,
        only: int | None = None) -> bool:
    ffmpeg.require_ffmpeg()
    state = load_state(cfg)
    tz = ZoneInfo(cfg["channel"].get("timezone", "UTC"))
    today = run_date or datetime.now(tz).date()
    publish_date = today + timedelta(days=int(cfg["schedule"].get("publish_days_ahead", 1)))
    upload = upload and cfg["upload"].get("enabled", True) and not test
    yt = youtube.client(cfg.root) if upload else None
    recent_titles = [v["title"] for v in state["videos"] if v.get("title")]
    ok = True

    for slot, entry in enumerate(cfg["schedule"]["videos"]):
        if only is not None and slot != only:
            continue
        pd = publish_date.isoformat()
        if upload and already_done(state, pd, slot):
            log.info("Slot %d for %s already uploaded, skipping", slot, pd)
            continue
        minutes = 1 if test else float(entry["minutes"])
        theme = cfg.themes[state["theme_index"] % len(cfg.themes)]
        seed = seed_for(pd, slot)
        workdir = cfg.output_dir / pd / f"{slot}-{int(entry['minutes'])}min-{theme['name'].lower().replace(' ', '-')}"
        log.info("Making %s min '%s' video for %s -> %s", minutes, theme["name"], pd, workdir)
        try:
            painting = choose_painting(cfg, theme, state)
            files = make_video(cfg, theme, minutes, workdir, seed, int(entry["minutes"]), painting)
            meta = metadata.generate(theme, int(entry["minutes"]), cfg.raw, recent_titles, variant=len(state["videos"]))
            description = metadata.full_description(meta, cfg.raw, credits_block(cfg, files, painting))
            (workdir / "metadata.json").write_text(json.dumps(
                {"title": meta.title, "description": description, "tags": meta.tags}, indent=2), encoding="utf-8")
            record = {"publish_date": pd, "slot": slot, "minutes": entry["minutes"], "theme": theme["name"],
                      "title": meta.title, "made_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}

            if upload:
                when = None
                if cfg["upload"].get("mode", "scheduled") == "scheduled":
                    when = publish_time(cfg, publish_date, entry["publish_at"])
                log.info("  uploading '%s'%s", meta.title, f" (goes public {when:%Y-%m-%d %H:%M} UTC)" if when else " (private)")
                vid = youtube.upload(yt, files["video"], files["thumbnail"], meta.title, description,
                                     meta.tags, cfg["upload"], when)
                playlist = (cfg["upload"].get("playlists") or {}).get(int(entry["minutes"]))
                if playlist:
                    youtube.add_to_playlist(yt, playlist, vid)
                record.update(video_id=vid, url=f"https://youtu.be/{vid}",
                              publish_at=when.isoformat() if when else None)
                log.info("  done: https://youtu.be/%s", vid)
                if not cfg["output"].get("keep_files_after_upload", False):
                    files["video"].unlink(missing_ok=True)
            else:
                log.info("  saved (not uploaded): %s", files["video"])

            state["theme_index"] += 1
            if painting:
                state.setdefault("paintings_used", []).append(painting["id"])
                record["painting"] = painting["id"]
            if not test:
                state["videos"].append(record)
                save_state(cfg, state)
            recent_titles.append(meta.title)
        except Exception:
            ok = False
            log.exception("  FAILED making/uploading slot %d", slot)
    return ok

import json
import wave
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from ytauto import audio, metadata, pipeline, visuals, youtube
from ytauto.config import Config, load_config
from ytauto.music import procedural

THEME = {"name": "Ocean Meditation", "use": "Meditation", "mood": "calm, waves",
         "music_prompt": "ambient", "colors": ["#0f3b4c", "#7fc8c2"],
         "procedural": {"key": "A", "scale": "pentatonic", "texture": "ocean", "bells": True}}


def wav_seconds(path: Path) -> float:
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


def test_config_loads():
    cfg = load_config()
    assert cfg.themes and cfg["schedule"]["videos"]


def test_procedural_track_is_original_audio(tmp_path):
    out = procedural.generate_track(tmp_path / "t.wav", 12, THEME["procedural"], seed=3)
    assert wav_seconds(out) == pytest.approx(12, abs=0.01)
    with wave.open(str(out)) as w:
        data = np.frombuffer(w.readframes(w.getnframes()), "<i2")
    assert 0.5 < np.abs(data).max() / 32767 <= 0.91  # loud enough, never clipped


def test_crossfade_concat_length(tmp_path):
    a = procedural.generate_track(tmp_path / "a.wav", 10, THEME["procedural"], 1)
    b = procedural.generate_track(tmp_path / "b.wav", 10, THEME["procedural"], 2)
    out = audio.crossfade_concat([a, b], tmp_path / "j.wav", crossfade_s=2, max_seconds=100)
    assert wav_seconds(out) == pytest.approx(18, abs=0.01)
    out = audio.crossfade_concat([a, b], tmp_path / "k.wav", crossfade_s=2, max_seconds=15)
    assert wav_seconds(out) == pytest.approx(15, abs=0.01)


def test_publish_time_converts_channel_timezone_to_utc():
    cfg = Config(raw={"channel": {"timezone": "America/New_York"}})
    when = pipeline.publish_time(cfg, date(2026, 10, 10), "08:00")
    assert when.strftime("%Y-%m-%dT%H:%M:%SZ") == "2026-10-10T12:00:00Z"


def test_already_done_only_counts_uploaded():
    state = {"videos": [{"publish_date": "2026-10-10", "slot": 0, "video_id": "abc"},
                        {"publish_date": "2026-10-10", "slot": 1}]}
    assert pipeline.already_done(state, "2026-10-10", 0)
    assert not pipeline.already_done(state, "2026-10-10", 1)


def test_template_metadata_and_cleaning():
    meta = metadata.template(THEME, 60, "Calm Hours")
    assert meta.title.startswith("Ocean Meditation | 1 Hour")
    dirty = metadata.VideoMetadata(title="<b>" + "x" * 200, description="hi <there>", tags=["a,b", "<c>"] + ["t" * 100] * 10)
    clean = metadata._clean(dirty, 15)
    assert len(clean.title) <= 100 and "<" not in clean.title
    assert clean.tags[:2] == ["a b", "c"]
    assert sum(len(t) + 1 for t in clean.tags) <= 480


def test_claude_metadata_used_when_available(monkeypatch):
    import anthropic

    parsed = metadata.VideoMetadata(title="Ocean Waves for Meditation | 1 Hour", description="Calm.", tags=["ocean"])

    class FakeMessages:
        def parse(self, **kwargs):
            assert kwargs["output_format"] is metadata.VideoMetadata
            return SimpleNamespace(stop_reason="end_turn", parsed_output=parsed)

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(anthropic, "Anthropic", lambda: SimpleNamespace(messages=FakeMessages()))
    cfg = {"channel": {"name": "Calm Hours"}, "metadata": {"use_claude": True}}
    assert metadata.generate(THEME, 60, cfg, []).title == parsed.title


def test_claude_failure_falls_back_to_template(monkeypatch):
    import anthropic

    def boom():
        raise RuntimeError("network down")

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(anthropic, "Anthropic", boom)
    cfg = {"channel": {"name": "Calm Hours"}, "metadata": {"use_claude": True}}
    assert metadata.generate(THEME, 15, cfg, []).title.startswith("Ocean Meditation | 15 Minutes")


def test_upload_sends_schedule_and_flags(tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"0" * 10)
    sent = {}

    class Req:
        def next_chunk(self):
            return None, {"id": "VID123"}

    class Videos:
        def insert(self, part, body, media_body):
            sent.update(body)
            return Req()

    yt = SimpleNamespace(videos=lambda: Videos())
    from datetime import datetime, timezone
    vid = youtube.upload(yt, video, None, "t", "d", ["x"], {"contains_synthetic_media": True},
                         datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc))
    assert vid == "VID123"
    assert sent["status"] == {"privacyStatus": "private", "selfDeclaredMadeForKids": False,
                              "containsSyntheticMedia": True, "publishAt": "2026-10-10T12:00:00Z"}
    assert sent["snippet"]["categoryId"] == "10"


def test_length_label():
    assert visuals.length_label(60) == "1 HOUR"
    assert visuals.length_label(120) == "2 HOURS"
    assert visuals.length_label(1) == "1 MINUTE"
    assert visuals.length_label(15) == "15 MINUTES"


def test_paintings_catalog_is_public_domain_and_covers_every_theme():
    from ytauto import paintings
    cfg = load_config()
    catalog = paintings.load_catalog(cfg.root)
    for theme in cfg.themes:
        assert len(catalog[theme["name"]]) >= 7, theme["name"]  # two weeks without repeating
    data = json.loads((cfg.root / "assets" / "paintings.json").read_text(encoding="utf-8"))
    assert "CC0" in data["source"]


def test_painting_pick_rotates_then_reuses_oldest():
    from ytauto import paintings
    catalog = {"T": [{"id": 1}, {"id": 2}, {"id": 3}]}
    assert paintings.pick(catalog, "T", [])["id"] == 1
    assert paintings.pick(catalog, "T", [1, 2])["id"] == 3
    assert paintings.pick(catalog, "T", [2, 1, 3])["id"] == 2


def test_painting_credit_names_artist_and_licence():
    from ytauto import paintings
    c = paintings.credit({"id": 5, "title": "Water Lilies", "artist": "Claude Monet", "date": "1906"})
    assert "Claude Monet" in c and "Public domain" in c and "artic.edu/artworks/5" in c


def test_pan_loop_is_seamless(tmp_path):
    from PIL import Image
    img = tmp_path / "p.jpg"
    Image.fromarray((np.random.default_rng(0).random((300, 600, 3)) * 255).astype("uint8")).save(img)
    cfg_v = {"width": 160, "height": 90, "fps": 4, "pan_seconds": 2, "video_bitrate": "200k"}
    out = visuals.make_pan_loop(img, tmp_path / "loop.mp4", cfg_v)
    from ytauto import ffmpeg as ff
    assert ff.duration(out) == pytest.approx(4, abs=0.3)


def test_batch_detects_youtube_limits():
    from ytauto import batch
    assert batch._is_limit(Exception("<HttpError 400 ... uploadLimitExceeded>"))
    assert batch._is_limit(Exception("quotaExceeded"))
    assert not batch._is_limit(Exception("backendError"))


def test_full_description_includes_credit():
    meta = metadata.VideoMetadata(title="t", description="Calm music.", tags=[])
    cfg = {"channel": {"description_footer": "Footer."}}
    assert metadata.full_description(meta, cfg, "Artwork: X") == "Calm music.\n\nArtwork: X\n\nFooter."


def test_music_catalog_has_an_hour_per_theme_without_repeats():
    from ytauto.music import classical_pd
    cfg = load_config()
    catalog = classical_pd.load_catalog(cfg.root)
    for theme in cfg.themes:
        tracks = catalog[theme["name"]]
        assert sum(t["seconds"] for t in tracks) > 65 * 60, theme["name"]
        assert len({t["file"] for t in tracks}) == len(tracks)
    data = json.loads((cfg.root / "assets" / "music.json").read_text(encoding="utf-8"))
    assert all("CC0" in c["license"] or "Public Domain" in c["license"] for c in data["collections"].values())


def test_playlist_avoids_repeats_within_a_video():
    from ytauto.music import classical_pd
    catalog = {"T": [{"file": str(i), "seconds": 300} for i in range(20)]}
    picks = classical_pd.choose(catalog, "T", 3600, seed=1)
    assert sum(t["seconds"] for t in picks) >= 3600
    assert len({t["file"] for t in picks}) == len(picks)
    assert classical_pd.choose(catalog, "T", 3600, seed=1) == picks  # same seed, same playlist


def test_timestamps_and_tracklist_block():
    from types import SimpleNamespace as NS
    assert metadata.timestamp(0) == "0:00"
    assert metadata.timestamp(754) == "12:34"
    assert metadata.timestamp(3725) == "1:02:05"
    cfg = Config(raw={"music": {"source": "classical_pd"}})
    files = {"tracklist": [{"start": 0, "composer": "Chopin", "title": "Nocturne"},
                           {"start": 300.5, "composer": "Bach", "title": "Aria"}]}
    block = pipeline.credits_block(cfg, files, None)
    assert block.startswith("Tracklist:\n0:00 Chopin – Nocturne\n5:00 Bach – Aria")
    assert "public domain" in block


def test_start_times_account_for_crossfades(tmp_path):
    a = procedural.generate_track(tmp_path / "a.wav", 10, THEME["procedural"], 1)
    b = procedural.generate_track(tmp_path / "b.wav", 10, THEME["procedural"], 2)
    assert audio.start_times([a, b, a], 2) == pytest.approx([0, 8, 16], abs=0.01)

"""Public-domain compositions (MIDI) rendered with a SoundFont via FluidSynth.

The composition is public domain and you make the recording yourself, so nobody else
owns it. Get MIDI files from mutopiaproject.org or similar and put them in assets/midi.
"""

from __future__ import annotations

import random
import shutil
import subprocess
from pathlib import Path


def render(midi: Path, out: Path, soundfont: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["fluidsynth", "-ni", "-g", "0.8", "-r", "44100", "-F", str(out), str(soundfont), str(midi)],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or not out.exists():
        raise RuntimeError(f"FluidSynth failed on {midi.name}: {result.stderr[-1000:]}")
    return out


def make_tracks(workdir: Path, midi_dir: Path, soundfont: str, total_seconds: float, seed: int,
                duration_of) -> list[Path]:
    if not shutil.which("fluidsynth"):
        raise RuntimeError("music.source is 'classical' but FluidSynth is not installed (see README)")
    if not soundfont or not Path(soundfont).exists():
        raise RuntimeError("music.soundfont must point to an existing .sf2 file (see README)")
    midis = sorted(list(midi_dir.rglob("*.mid")) + list(midi_dir.rglob("*.midi")))
    if not midis:
        raise RuntimeError(f"No MIDI files found in {midi_dir}")
    rng = random.Random(seed)
    rng.shuffle(midis)
    tracks, made, i = [], 0.0, 0
    while made < total_seconds:
        midi = midis[i % len(midis)]
        wav = render(midi, workdir / f"track_{i:02d}_{midi.stem[:40]}.wav", Path(soundfont))
        tracks.append(wav)
        made += duration_of(wav)
        i += 1
    return tracks

"""Free ambient music generator: slow chord pads, soft bells and nature textures.

Everything is synthesized from sine waves and noise, so the result is original audio
that you own outright. It cannot match anyone else's recording in Content ID.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SR = 44100
NOTE_INDEX = {"C": 0, "C#": 1, "DB": 1, "D": 2, "D#": 3, "EB": 3, "E": 4, "F": 5, "F#": 6,
              "GB": 6, "G": 7, "G#": 8, "AB": 8, "A": 9, "A#": 10, "BB": 10, "B": 11}
SCALES = {
    "major": [0, 2, 4, 5, 7, 9, 11],
    "minor": [0, 2, 3, 5, 7, 8, 10],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "lydian": [0, 2, 4, 6, 7, 9, 11],
    "pentatonic": [0, 2, 4, 7, 9],
}
CHORD_SECONDS = {"slow": 10.0, "very_slow": 16.0}


def midi_to_hz(note: float) -> float:
    return 440.0 * 2 ** ((note - 69) / 12)


def scale_note(root_midi: int, scale: list[int], degree: int) -> int:
    octave, idx = divmod(degree, len(scale))
    return root_midi + 12 * octave + scale[idx]


def _hann(n: int) -> np.ndarray:
    return (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(n) / n)).astype(np.float32)


def _pads(rng, n, root, scale, chord_s) -> np.ndarray:
    """Overlapping chords with 50%-overlap Hann envelopes, which sum to a constant level."""
    out = np.zeros((n, 2), np.float32)
    hop = int(chord_s * SR)
    win = 2 * hop
    env = _hann(win)
    t = np.arange(win, dtype=np.float32) / SR
    degrees = [0, 3, 4, 5] if len(scale) == 7 else [0, 1, 2, 3, 4]
    degree = 0
    for start in range(-hop, n, hop):
        # Random walk that keeps coming home to the root chord.
        degree = 0 if rng.random() < 0.3 else int(rng.choice(degrees))
        notes = [scale_note(root, scale, degree + k) for k in (0, 2, 4)]
        notes.append(scale_note(root - 12, scale, degree))  # bass
        if rng.random() < 0.5:
            notes.append(scale_note(root + 12, scale, degree + 2))  # airy top note
        seg = np.zeros((win, 2), np.float32)
        for note in notes:
            f = midi_to_hz(note)
            for ch, detune in ((0, 0.9985), (1, 1.0015)):
                ph = rng.random() * 2 * np.pi
                tone = (np.sin(2 * np.pi * f * detune * t + ph)
                        + 0.35 * np.sin(4 * np.pi * f * detune * t + ph)
                        + 0.12 * np.sin(6 * np.pi * f * detune * t + ph))
                seg[:, ch] += tone.astype(np.float32)
        seg *= env[:, None] / len(notes)
        a, b = max(start, 0), min(start + win, n)
        out[a:b] += seg[a - start:b - start]
    # Slow "breathing" swell.
    tt = np.arange(n, dtype=np.float32) / SR
    out *= (1 + 0.15 * np.sin(2 * np.pi * 0.05 * tt + rng.random() * 6))[:, None]
    return out


def _bells(rng, n, root, scale) -> np.ndarray:
    """Sparse singing-bowl tones with inharmonic partials."""
    out = np.zeros((n, 2), np.float32)
    dur = int(6 * SR)
    t = np.arange(dur, dtype=np.float32) / SR
    pos = int(rng.uniform(2, 6) * SR)
    while pos < n:
        f = midi_to_hz(scale_note(root + 24, scale, int(rng.integers(0, len(scale) * 2))))
        tone = (np.sin(2 * np.pi * f * t) + 0.4 * np.sin(2 * np.pi * f * 2.71 * t)
                + 0.15 * np.sin(2 * np.pi * f * 5.15 * t))
        tone *= np.exp(-t * rng.uniform(0.6, 1.2)) * (1 - np.exp(-t * 200))
        pan = rng.uniform(0.2, 0.8)
        end = min(pos + dur, n)
        out[pos:end, 0] += (tone[: end - pos] * (1 - pan)).astype(np.float32)
        out[pos:end, 1] += (tone[: end - pos] * pan).astype(np.float32)
        pos += int(rng.uniform(4, 11) * SR)
    return out * 0.25


def _shaped_noise(rng, n, weight) -> np.ndarray:
    out = np.zeros((n, 2), np.float32)
    freqs = np.fft.rfftfreq(n, 1 / SR)
    w = weight(np.maximum(freqs, 1.0))
    for ch in range(2):
        spec = np.fft.rfft(rng.standard_normal(n)) * w
        sig = np.fft.irfft(spec, n)
        out[:, ch] = (sig / (np.abs(sig).max() + 1e-9)).astype(np.float32)
    return out


def _texture(rng, n, kind) -> np.ndarray:
    tt = np.arange(n, dtype=np.float32) / SR
    if kind == "rain":
        noise = _shaped_noise(rng, n, lambda f: (f / 3000) ** 0.5 / (1 + (f / 9000) ** 2) / np.sqrt(f / 200))
        return noise * 0.22
    if kind == "ocean":
        noise = _shaped_noise(rng, n, lambda f: 1 / (1 + (f / 400) ** 2) / np.sqrt(f / 50))
        period = rng.uniform(7, 10)
        swell = (0.5 + 0.5 * np.sin(2 * np.pi * tt / period)) ** 2
        return noise * (0.08 + 0.35 * swell)[:, None]
    if kind == "wind":
        noise = _shaped_noise(rng, n, lambda f: np.exp(-((np.log(f) - np.log(500)) ** 2) / 0.8))
        gust = 0.5 + 0.5 * np.sin(2 * np.pi * tt / rng.uniform(11, 17)) * np.sin(2 * np.pi * tt / 29)
        return noise * (0.08 + 0.25 * gust)[:, None]
    return np.zeros((n, 2), np.float32)


def _reverb(rng, x: np.ndarray, seconds=2.8, wet=0.35) -> np.ndarray:
    """Convolution reverb with a synthetic decaying-noise impulse (block overlap-add)."""
    m = int(seconds * SR)
    ir_t = np.arange(m) / SR
    block = 1 << 18
    nfft = 1 << int(np.ceil(np.log2(block + m)))
    out = np.zeros((len(x) + m, 2), np.float64)
    for ch in range(2):
        ir = rng.standard_normal(m) * np.exp(-ir_t * 6.9 / seconds)
        ir /= np.sqrt(np.sum(ir ** 2))
        ir_f = np.fft.rfft(ir, nfft)
        for start in range(0, len(x), block):
            seg = x[start:start + block, ch]
            y = np.fft.irfft(np.fft.rfft(seg, nfft) * ir_f, nfft)[: len(seg) + m]
            out[start:start + len(y), ch] += y
    return ((1 - wet) * x + wet * out[: len(x)]).astype(np.float32)


def generate_track(path: Path, seconds: float, theme_settings: dict, seed: int) -> Path:
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    key = str(theme_settings.get("key", "C")).upper()
    scale = SCALES.get(theme_settings.get("scale", "major"), SCALES["major"])
    root = 48 + NOTE_INDEX.get(key, 0)  # octave 3
    chord_s = CHORD_SECONDS.get(theme_settings.get("tempo", "slow"), 10.0) * rng.uniform(0.85, 1.15)

    music = _pads(rng, n, root, scale, chord_s)
    if theme_settings.get("bells", False):
        music += _bells(rng, n, root, scale)
    music = _reverb(rng, music)
    mix = music / (np.abs(music).max() + 1e-9) * 0.8
    mix += _texture(rng, n, theme_settings.get("texture", "none"))

    fade = min(int(3 * SR), n // 4)
    ramp = np.linspace(0, 1, fade, dtype=np.float32)[:, None]
    mix[:fade] *= ramp
    mix[-fade:] *= ramp[::-1]
    mix = mix / (np.abs(mix).max() + 1e-9) * 0.9
    write_wav(path, mix)
    return path


def write_wav(path: Path, audio: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def make_tracks(workdir: Path, total_seconds: float, track_seconds: float, theme: dict, seed: int) -> list[Path]:
    settings = theme.get("procedural", {})
    tracks = []
    made = 0.0
    i = 0
    while made < total_seconds:
        length = min(track_seconds, max(total_seconds - made + 10, 20))
        tracks.append(generate_track(workdir / f"track_{i:02d}.wav", length, settings, seed * 1000 + i))
        made += length
        i += 1
    return tracks

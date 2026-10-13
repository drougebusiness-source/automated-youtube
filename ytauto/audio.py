"""Joins tracks into one continuous mix of an exact length, with crossfades and loudness normalization."""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

from . import ffmpeg

SR = 44100


def to_wav(src: Path, dst: Path, level_lufs: float | None = None) -> Path:
    """Decode to 44.1 kHz stereo WAV. With level_lufs, also trim silence at both ends and even
    out the loudness, so pieces recorded at different levels sit well next to each other."""
    args = ["-i", str(src), "-vn", "-ac", "2", "-ar", str(SR)]
    if level_lufs is not None:
        trim = "silenceremove=start_periods=1:start_threshold=-55dB:start_silence=0.3"
        args += ["-af", f"{trim},areverse,{trim},areverse,loudnorm=I={level_lufs}:TP=-2:LRA=14,aresample={SR}"]
    ffmpeg.run([*args, "-c:a", "pcm_s16le", str(dst)])
    return dst


def wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


def _read(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        data = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    return data.reshape(-1, 2).astype(np.float32) / 32768


def crossfade_concat(tracks: list[Path], out: Path, crossfade_s: float, max_seconds: float) -> Path:
    """Equal-power crossfade between consecutive tracks, streamed to disk. Stops once max_seconds is reached."""
    xf = int(crossfade_s * SR)
    limit = int(max_seconds * SR)
    written = 0
    tail: np.ndarray | None = None
    with wave.open(str(out), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)

        def emit(chunk: np.ndarray) -> None:
            nonlocal written
            chunk = chunk[: max(limit - written, 0)]
            w.writeframes((np.clip(chunk, -1, 1) * 32767).astype("<i2").tobytes())
            written += len(chunk)

        for path in tracks:
            if written >= limit:
                break
            audio = _read(path)
            if tail is not None:
                n = min(xf, len(tail), len(audio) // 3)
                theta = np.linspace(0, np.pi / 2, n, dtype=np.float32)[:, None]
                head = tail[len(tail) - n:] * np.cos(theta) + audio[:n] * np.sin(theta)
                emit(tail[: len(tail) - n])
                audio = np.concatenate([head, audio[n:]])
            keep = min(xf, len(audio) // 3)
            emit(audio[: len(audio) - keep])
            tail = audio[len(audio) - keep:]
        if tail is not None:
            emit(tail)
    return out


def start_times(wavs: list[Path], crossfade_s: float) -> list[float]:
    """When each track starts in the joined mix (consecutive tracks overlap by the crossfade)."""
    starts, t = [], 0.0
    for w in wavs:
        starts.append(t)
        t += wav_seconds(w) - crossfade_s
    return starts


def build_mix(tracks: list[Path], workdir: Path, seconds: float, crossfade_s: float, target_lufs: float,
              level_tracks: bool = False) -> tuple[Path, list[float]]:
    """Returns an AAC .m4a file exactly `seconds` long, and the time each track starts in it."""
    wavs = []
    for i, t in enumerate(tracks):
        if level_tracks:
            wavs.append(to_wav(t, workdir / f"conv_{i:02d}.wav", level_lufs=target_lufs - 2))
        else:
            wavs.append(t if t.suffix.lower() == ".wav" else to_wav(t, workdir / f"conv_{i:02d}.wav"))
    starts = start_times(wavs, crossfade_s)
    joined = crossfade_concat(wavs, workdir / "joined.wav", crossfade_s, seconds)
    have = ffmpeg.duration(joined)
    if have < seconds - 0.5:
        raise RuntimeError(f"Not enough music: got {have:.0f}s, need {seconds:.0f}s")
    out = workdir / "mix.m4a"
    fade_out = min(10.0, seconds / 6)
    ffmpeg.run([
        "-i", str(joined), "-t", f"{seconds:.3f}",
        "-af", f"afade=t=in:d=3,afade=t=out:st={seconds - fade_out:.3f}:d={fade_out:.3f},"
               f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11,aresample={SR}",
        "-c:a", "aac", "-b:a", "192k", str(out),
    ])
    joined.unlink(missing_ok=True)
    return out, starts

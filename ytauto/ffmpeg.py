"""Thin wrapper around the ffmpeg command line."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


def require_ffmpeg() -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError(
            "ffmpeg is not installed. Install it first: https://ffmpeg.org/download.html "
            "(Mac: `brew install ffmpeg`, Windows: `winget install ffmpeg`, Linux: `sudo apt install ffmpeg`)."
        )


def run(args: list[str]) -> None:
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {' '.join(cmd)}\n{result.stderr[-2000:]}")


def duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    return float(json.loads(out)["format"]["duration"])

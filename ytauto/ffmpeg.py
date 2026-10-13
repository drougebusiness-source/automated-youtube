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


def run(args: list[str], timeout: float = 1800) -> None:
    """Runs ffmpeg. A run that takes longer than `timeout` seconds is stopped and reported as an
    error, so one stuck file can never stall a whole batch."""
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", *args]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"ffmpeg took longer than {timeout:.0f}s and was stopped: {' '.join(cmd)[:300]}")
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {' '.join(cmd)}\n{result.stderr[-2000:]}")


def duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    return float(json.loads(out)["format"]["duration"])

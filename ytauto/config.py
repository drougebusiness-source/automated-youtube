"""Loads config.yaml and the .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent


def load_env(path: Path = ROOT / ".env") -> None:
    """Read KEY=value lines from .env into os.environ (real env vars win)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        if value and key.strip() not in os.environ:
            os.environ[key.strip()] = value


@dataclass
class Config:
    raw: dict[str, Any]
    root: Path = ROOT

    def __getitem__(self, key: str) -> Any:
        return self.raw[key]

    @property
    def themes(self) -> list[dict[str, Any]]:
        return self.raw["themes"]

    @property
    def output_dir(self) -> Path:
        return self.root / "output"

    @property
    def state_dir(self) -> Path:
        return self.root / "state"


def load_config(path: Path | None = None) -> Config:
    load_env()
    path = path or ROOT / "config.yaml"
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not raw.get("themes"):
        raise ValueError("config.yaml needs at least one theme")
    if not raw.get("schedule", {}).get("videos"):
        raise ValueError("config.yaml needs at least one entry under schedule.videos")
    return Config(raw=raw)

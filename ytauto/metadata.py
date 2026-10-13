"""Titles, descriptions and tags. Written by Claude when available, otherwise from templates."""

from __future__ import annotations

import logging
import os

from pydantic import BaseModel, Field

from .visuals import length_label

log = logging.getLogger(__name__)


class VideoMetadata(BaseModel):
    title: str = Field(description="YouTube title, at most 90 characters")
    description: str = Field(description="2-4 short paragraphs for the description box, no hashtags")
    tags: list[str] = Field(description="Search tags, most important first")


SYSTEM = (
    "You write YouTube metadata for a background-music channel (meditation, sleep, study, ambient). "
    "Titles must be honest about what the video is, inviting, and searchable: lead with the use case "
    "or mood, include the length (e.g. '1 Hour'), and avoid clickbait, ALL CAPS and emoji spam. "
    "Never claim health or medical benefits (no 'cures anxiety', 'heals', 'Hz healing' claims). "
    "Descriptions are calm, warm and specific to this video's theme. Tags are short search phrases."
)


def _clean(meta: VideoMetadata, max_tags: int) -> VideoMetadata:
    title = meta.title.replace("<", "").replace(">", "").strip()[:100]
    desc = meta.description.replace("<", "").replace(">", "").strip()
    tags, total = [], 0
    for t in meta.tags[:max_tags]:
        t = t.replace("<", "").replace(">", "").replace(",", " ").strip()
        if t and total + len(t) + 1 <= 480:
            tags.append(t)
            total += len(t) + 1
    return VideoMetadata(title=title, description=desc, tags=tags)


TITLE_PATTERNS = [
    "{name} | {label} of {style} for {use}",
    "{name} | {label} of Calm {style} for {use}",
    "{label} of {name} {style} | Peaceful Background Music",
    "{name} – {label} of Gentle {style} for {use}",
    "Relaxing {style} ({label}) | {name} for {use}",
    "{label} of {name} {style} | Relax, Focus & Unwind",
]
INTROS = [
    "{label} of {lstyle}: {mood}.",
    "Settle in with {label_l} of {lstyle}, {mood}.",
    "A calm {label_l} of {lstyle}: {mood}.",
    "{label} of slow, gentle {lstyle} to help you unwind: {mood}.",
]


def template(theme: dict, minutes: int, channel: str, variant: int = 0) -> VideoMetadata:
    """Built-in title and description. `variant` picks different wording so batches don't repeat."""
    label = length_label(minutes).title()
    name = theme["name"]
    use = theme.get("use", "Relaxation")
    style = theme.get("style", "Ambient Music")
    title = TITLE_PATTERNS[variant % len(TITLE_PATTERNS)].format(name=name, label=label, use=use, style=style)
    volume = variant // len(TITLE_PATTERNS) + 1
    if volume > 1:
        title += f" · Vol. {volume}"
    intro = INTROS[variant % len(INTROS)].format(
        label=label, label_l=label.lower(), lname=name.lower(), lstyle=style.lower(), mood=theme["mood"])
    return VideoMetadata(
        title=title,
        description=(
            f"{intro}\n\n"
            f"Put it on in the background while you sleep, study, work, read or meditate. "
            f"New calm music every day on {channel}."
        ),
        tags=[name.lower(), style.lower(), "relaxing music", "calm music", "sleep music", "study music",
              f"{minutes} minute music", "background music", *theme.get("tags", [])],
    )


def generate(theme: dict, minutes: int, cfg: dict, recent_titles: list[str], variant: int = 0) -> VideoMetadata:
    channel = cfg["channel"]["name"]
    meta_cfg = cfg.get("metadata", {})
    max_tags = meta_cfg.get("max_tags", 15)
    if not meta_cfg.get("use_claude", True) or not os.environ.get("ANTHROPIC_API_KEY"):
        return _clean(template(theme, minutes, channel, variant), max_tags)
    try:
        import anthropic

        client = anthropic.Anthropic()
        recent = "\n".join(f"- {t}" for t in recent_titles[-20:]) or "(none yet)"
        prompt = (
            f"Channel: {channel}\n"
            f"Video length: {length_label(minutes).title()} ({minutes} minutes)\n"
            f"Theme: {theme['name']}\nMood: {theme['mood']}\n"
            f"Music: {theme.get('music_prompt', '')}\n\n"
            f"Recent titles on the channel (make this one clearly different):\n{recent}\n\n"
            f"Write the title, description and up to {max_tags} tags."
        )
        response = client.messages.parse(
            model=meta_cfg.get("model", "claude-opus-5-5"),
            max_tokens=4000,
            output_config={"effort": "low"},
            system=SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            output_format=VideoMetadata,
        )
        if response.stop_reason == "refusal" or response.parsed_output is None:
            raise RuntimeError(f"no usable output (stop_reason={response.stop_reason})")
        return _clean(response.parsed_output, max_tags)
    except Exception as exc:  # metadata must never block a daily upload
        log.warning("Claude metadata failed (%s); using template", exc)
        return _clean(template(theme, minutes, channel, variant), max_tags)


def timestamp(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def full_description(meta: VideoMetadata, cfg: dict, credit: str = "") -> str:
    footer = cfg["channel"].get("description_footer", "").strip()
    parts = [meta.description, credit, footer]
    return "\n\n".join(p.strip() for p in parts if p and p.strip())[:4900]

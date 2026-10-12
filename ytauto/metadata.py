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


def template(theme: dict, minutes: int, channel: str) -> VideoMetadata:
    label = length_label(minutes).title()
    name = theme["name"]
    return VideoMetadata(
        title=f"{name} | {label} of Ambient Music for {theme.get('use', 'Relaxation')}",
        description=(
            f"{label} of {name.lower()} music: {theme['mood']}.\n\n"
            f"Put it on in the background while you sleep, study, work, read or meditate. "
            f"New calm music every day on {channel}."
        ),
        tags=[name.lower(), "ambient music", "relaxing music", "meditation music", "sleep music",
              "study music", "calm music", f"{minutes} minute music", "background music"],
    )


def generate(theme: dict, minutes: int, cfg: dict, recent_titles: list[str]) -> VideoMetadata:
    channel = cfg["channel"]["name"]
    meta_cfg = cfg.get("metadata", {})
    max_tags = meta_cfg.get("max_tags", 15)
    if not meta_cfg.get("use_claude", True) or not os.environ.get("ANTHROPIC_API_KEY"):
        return _clean(template(theme, minutes, channel), max_tags)
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
        return _clean(template(theme, minutes, channel), max_tags)


def full_description(meta: VideoMetadata, cfg: dict) -> str:
    footer = cfg["channel"].get("description_footer", "").strip()
    return f"{meta.description}\n\n{footer}".strip()[:4900]

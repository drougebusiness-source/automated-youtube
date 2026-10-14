"""YouTube Data API: one-time sign-in and video upload."""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",  # thumbnails and playlists
]


def authorize(root: Path) -> Path:
    """Opens a browser so you can sign in to the channel's Google account. Saves token.json."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    secrets = sorted(root.glob("client_secret*.json"))
    if not secrets:
        raise SystemExit(
            "No client_secret.json found. Download it from Google Cloud Console "
            "(APIs & Services > Credentials > your OAuth client > Download JSON) and put it in "
            f"{root}. See README step 3."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(secrets[0]), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
    token = root / "token.json"
    token.write_text(creds.to_json(), encoding="utf-8")
    return token


def _credentials(root: Path):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    raw = os.environ.get("YOUTUBE_TOKEN_JSON")
    token_file = root / "token.json"
    if raw:
        info = json.loads(raw)
    elif token_file.exists():
        info = json.loads(token_file.read_text(encoding="utf-8"))
    else:
        raise RuntimeError("Not signed in to YouTube. Run `python -m ytauto auth` first (README step 3).")
    creds = Credentials.from_authorized_user_info(info, SCOPES)
    if not creds.valid:
        creds.refresh(Request())
    return creds


def client(root: Path):
    from googleapiclient.discovery import build

    return build("youtube", "v3", credentials=_credentials(root), cache_discovery=False)


def upload(yt, video: Path, thumbnail: Path | None, title: str, description: str, tags: list[str],
           upload_cfg: dict, publish_at: datetime | None) -> str:
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    status = {
        "privacyStatus": "private",
        "selfDeclaredMadeForKids": bool(upload_cfg.get("made_for_kids", False)),
        "containsSyntheticMedia": bool(upload_cfg.get("contains_synthetic_media", True)),
    }
    if publish_at is not None:
        status["publishAt"] = publish_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": str(upload_cfg.get("category_id", "10")),
            "defaultLanguage": upload_cfg.get("default_language", "en"),
            "defaultAudioLanguage": upload_cfg.get("default_language", "en"),
        },
        "status": status,
    }
    media = MediaFileUpload(str(video), mimetype="video/mp4", chunksize=16 * 1024 * 1024, resumable=True)
    request = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    response, retries = None, 0
    while response is None:
        try:
            progress, response = request.next_chunk()
            if progress:
                log.info("  uploaded %d%%", int(progress.progress() * 100))
        except HttpError as e:
            if e.resp.status in (500, 502, 503, 504) and retries < 8:
                retries += 1
                time.sleep(2 ** retries)
                continue
            raise
        except (OSError, ConnectionError, TimeoutError) as e:
            # Dropped connections (e.g. "SSL: EOF occurred") are common on long uploads.
            # The upload is resumable, so retrying continues from the last chunk YouTube received.
            if retries < 8:
                retries += 1
                log.warning("  connection dropped (%s); retrying in %ds", type(e).__name__, 2 ** retries)
                time.sleep(2 ** retries)
                continue
            raise
    video_id = response["id"]

    if thumbnail is not None:
        try:
            yt.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(str(thumbnail))).execute()
        except HttpError as e:
            # Custom thumbnails need a phone-verified channel; don't fail the whole run.
            log.warning("  thumbnail not set (%s). Verify your channel at youtube.com/verify.", e.reason)
    return video_id


def add_to_playlist(yt, playlist_id: str, video_id: str) -> None:
    yt.playlistItems().insert(
        part="snippet",
        body={"snippet": {"playlistId": playlist_id, "resourceId": {"kind": "youtube#video", "videoId": video_id}}},
    ).execute()

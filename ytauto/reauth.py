"""Re-sign-in without a computer: GitHub Actions prints a Google sign-in link; after you allow access,
the address your browser lands on (a "can't be reached" localhost page) is passed back in. The new
sign-in is stored encrypted in state/token.enc with a key derived from the YOUTUBE_TOKEN_JSON secret,
so only this repository's workflows can read it."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import urllib.parse
from pathlib import Path

import requests

REDIRECT = "http://localhost:8765/"
INFO = b"ytauto-token-v1"


def _key(raw: str) -> bytes:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=INFO).derive(raw.encode())


def decrypt(root: Path, raw: str) -> dict | None:
    path = root / "state" / "token.enc"
    if not path.exists():
        return None
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    try:
        blob = base64.b64decode(path.read_text())
        return json.loads(AESGCM(_key(raw)).decrypt(blob[:12], blob[12:], INFO))
    except Exception:
        return None  # the secret was replaced since; fall back to it


def link() -> str:
    from .youtube import SCOPES
    info = json.loads(os.environ["YOUTUBE_TOKEN_JSON"])
    q = {"client_id": info["client_id"], "redirect_uri": REDIRECT, "response_type": "code",
         "scope": " ".join(SCOPES), "access_type": "offline", "prompt": "consent", "include_granted_scopes": "true"}
    return "https://accounts.google.com/o/oauth2/auth?" + urllib.parse.urlencode(q)


def finish(root: Path, answer: str) -> list[str]:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    raw = os.environ["YOUTUBE_TOKEN_JSON"]
    info = json.loads(raw)
    m = re.search(r"[?&]code=([^&\s]+)", answer)
    code = urllib.parse.unquote(m.group(1) if m else answer.strip())
    r = requests.post(info.get("token_uri", "https://oauth2.googleapis.com/token"), data={
        "code": code, "client_id": info["client_id"], "client_secret": info["client_secret"],
        "redirect_uri": REDIRECT, "grant_type": "authorization_code"}, timeout=30)
    if r.status_code != 200:
        raise SystemExit(f"Google refused the sign-in ({r.status_code}): {r.json().get('error_description') or r.json().get('error')}. "
                         "The code works once and expires in a few minutes: run this again for a fresh link.")
    tok = r.json()
    scopes = tok.get("scope", "").split()
    new = {"token": tok["access_token"], "refresh_token": tok.get("refresh_token") or info["refresh_token"],
           "token_uri": info.get("token_uri", "https://oauth2.googleapis.com/token"),
           "client_id": info["client_id"], "client_secret": info["client_secret"], "scopes": scopes}
    nonce = os.urandom(12)
    blob = nonce + AESGCM(_key(raw)).encrypt(nonce, json.dumps(new).encode(), INFO)
    (root / "state" / "token.enc").write_text(base64.b64encode(blob).decode())
    return scopes

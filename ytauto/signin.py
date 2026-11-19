"""Sign in to YouTube on this PC and save the sign-in straight into the repo's GitHub secret.

The sign-in is never written to a file, printed, or committed: it goes from Google to
`gh secret set` through a pipe. Run it with `python -m ytauto signin <client_secret.json>`
(or scripts\reauth.bat). It needs the GitHub CLI signed in as the repo owner."""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO = "drougebusiness-source/automated-youtube"
SECRET = "YOUTUBE_TOKEN_JSON"


def run(client_file: Path) -> list[str]:
    """Returns the permissions Google did NOT grant (empty when everything was ticked)."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    from .youtube import SCOPES

    flow = InstalledAppFlow.from_client_secrets_file(str(client_file), SCOPES)
    creds = flow.run_local_server(
        port=8765, prompt="consent", access_type="offline",
        authorization_prompt_message=("\nYour browser is opening Google sign-in. Pick the Rest and Relaxation "
                                      "account, tick every box and click Continue.\nIf it doesn't open: {url}\n"),
        success_message="Signed in. You can close this tab and go back to the terminal.")
    if not creds.refresh_token:
        raise SystemExit("Google sent no refresh token. Remove the app's access at "
                         "myaccount.google.com/permissions and run this again.")
    subprocess.run(["gh", "secret", "set", SECRET, "-R", REPO], input=creds.to_json(), text=True, check=True)
    granted = set(creds.scopes or [])
    return [s for s in SCOPES if s not in granted]

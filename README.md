# Automated YouTube music channel

This project makes and posts background-music videos (meditation, sleep, study, ambient, classical) to YouTube every day, without you doing anything. Each day it:

1. **Makes the music.** Original ambient music generated from scratch (free), AI-composed tracks (ElevenLabs), public-domain classical pieces rendered as new recordings, or your own licensed library.
2. **Mixes it** to an exact length (60, 30 and 15 minutes by default), with smooth crossfades and the loudness YouTube expects.
3. **Makes the artwork.** A background picture, a slow seamless zoom loop for the video, and a thumbnail with the title and length.
4. **Writes the title, description and tags**, using Claude if you add a key, otherwise built-in templates.
5. **Uploads it** to your channel, scheduled to go public at the times you choose.

Each video in a day gets a **different theme, different music and different art**. That is deliberate: YouTube's monetization rules penalize channels that upload the same content repeatedly.

---

## Step 1: Install (one time, about 10 minutes)

You need **Python 3.11 or newer** and **ffmpeg**.

| | Python | ffmpeg |
|---|---|---|
| **Mac** | `brew install python` (or python.org) | `brew install ffmpeg` |
| **Windows** | python.org installer, and tick "Add Python to PATH" | `winget install ffmpeg` |
| **Linux** | usually already installed | `sudo apt install ffmpeg` |

Then open a terminal **inside this folder** and run:

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Step 2: Make a test batch (no YouTube needed)

```bash
python -m ytauto run --test
```

This makes three **1-minute** sample videos in `output/<date>/` in about a minute and a half, each with its `thumbnail.jpg` and `metadata.json`. Watch them. Then open **`config.yaml`** and make it yours: channel name, publish times, themes, colours, music style. Everything is explained in comments in the file.

To make one full-length video without uploading: `python -m ytauto run --no-upload --only 2` (slot 2 is the 15-minute one).

## Step 3: Connect your YouTube channel (one time, about 15 minutes)

Google requires you to create your own free "app" so the bot can upload to your channel.

1. Go to <https://console.cloud.google.com/> and sign in with the Google account that owns the channel. Create a **new project**, e.g. "channel uploader".
2. **APIs & Services → Library**: search for **YouTube Data API v3** and click **Enable**.
3. **APIs & Services → OAuth consent screen**: choose **External**, fill in the app name and your email, and add yourself under **Test users**.
4. **Important:** on the same screen, click **Publish app** so the status says **In production**. If you leave it in "Testing", Google signs the bot out every 7 days. You don't need Google's verification for your own channel; you'll just see an "unverified app" warning when you sign in, and you can click through it.
5. **APIs & Services → Credentials → Create credentials → OAuth client ID** → application type **Desktop app**. Click **Download JSON** and save the file in this folder as `client_secret.json`.
6. Run:
   ```bash
   python -m ytauto auth
   ```
   A browser opens. Pick your channel's account and allow access. This creates `token.json`. **Keep it private**: it gives access to your channel.

Also verify your channel at <https://www.youtube.com/verify> (a phone number). Without this, YouTube blocks **videos longer than 15 minutes** and **custom thumbnails**.

## Step 4: Google's API audit (why videos may start out private)

Google locks videos uploaded through a new, unaudited API project to **private**. Until your project passes Google's free compliance audit:

- Set `upload.mode: "private"` in `config.yaml`. The bot uploads every day, and each morning you open YouTube Studio and click **Publish** or **Schedule** on the new videos, which takes about 2 minutes. This doubles as your quality check.
- Apply for the audit with the **YouTube API Services Audit and Quota Extension form** (search for that name; it's linked from the YouTube API "Quota and compliance audits" page). Describe it truthfully: "uploads videos to my own channel on a schedule". Approval can take a few weeks.
- Once you're approved, set `upload.mode: "scheduled"`. From then on, videos go public at your chosen times by themselves.

The default daily API allowance (10,000 units) covers 3 uploads plus thumbnails.

## Step 5: Choose the music and art sources (optional)

Copy `.env.example` to `.env` and add only the keys you use:

| Setting in `config.yaml` | What it does | Needs | Rough cost |
|---|---|---|---|
| `music.source: procedural` (default) | Original ambient music: chord pads, singing bowls, rain/ocean/wind | nothing | free |
| `music.source: elevenlabs` | AI-composed music in any style | `ELEVENLABS_API_KEY`, on a plan that **includes commercial use** | depends on plan; ~105 min of new music a day at the default schedule |
| `music.source: classical` | Public-domain pieces (Bach, Satie, Debussy…) rendered as **your own** recordings | MIDI files in `assets/midi`, FluidSynth, a `.sf2` SoundFont | free |
| `music.source: library` | Your own files in `assets/music_library` | music you own or have a licence for | n/a |
| `visuals.background_source: procedural` (default) | Soft gradient art in the theme's colours | nothing | free |
| `visuals.background_source: folder` | Random image from `assets/backgrounds` | your images (1920×1080 or larger) | n/a |
| `visuals.background_source: openai` | A new AI painting for every video | `OPENAI_API_KEY` | a few cents per image |
| `ANTHROPIC_API_KEY` set | Claude writes varied, searchable titles and descriptions | Anthropic API key | well under $1/month |

**About classical music:** the *compositions* are public domain, but almost every *recording* belongs to a label, which is why classical uploads get Content ID claims. Rendering the sheet music yourself avoids that. Free MIDI files: <https://www.mutopiaproject.org>. The free General MIDI SoundFont sounds basic; a good piano or orchestral SoundFont makes a big difference. Install FluidSynth with `brew install fluidsynth` or `sudo apt install fluidsynth`, then set `music.soundfont` to the `.sf2` path.

## Step 6: Put it on autopilot

### Option A: GitHub Actions (recommended; works while your computer is off)

1. Create a **private** repository on GitHub and upload the contents of this folder, so that `config.yaml` sits at the top level. Never upload `.env`, `token.json` or `client_secret.json`. The `.gitignore` already excludes them.
2. In the repository, go to **Settings → Secrets and variables → Actions → New repository secret** and add:
   - `YOUTUBE_TOKEN_JSON`: the whole contents of your `token.json`
   - optionally `ANTHROPIC_API_KEY`, `ELEVENLABS_API_KEY`, `OPENAI_API_KEY`
3. Open the **Actions** tab and enable workflows. Click **Daily videos → Run workflow** once to test it.

It then runs every day at the time set in `.github/workflows/daily-videos.yml` (09:17 UTC by default). Each run saves `state/history.json` back to the repository, so the theme rotation continues and a re-run never uploads a duplicate. If a run fails, GitHub emails you. Each run also keeps the thumbnails and metadata for 14 days under the run's **Artifacts**.

### Option B: your own computer

Use `scripts/run_daily.sh` with cron (Mac/Linux) or `scripts/run_daily.bat` with Task Scheduler (Windows). Instructions are at the top of each file. The computer must be on at that time.

---

## What stays manual

| Task | How often | Why |
|---|---|---|
| Google setup, sign-in, channel verification | once | Google requires a person |
| Publish the day's private uploads | daily (2 min), **only until the audit is approved** | Google rule for unaudited projects |
| Watch or listen to a few minutes of new uploads | a few times a week | catch odd-sounding AI output early |
| Dispute any Content ID claims | rarely | claims need a human decision |
| Check the licence terms of any paid AI tool you add | when you add or change a tool | your channel's safety depends on it |
| Add themes, read analytics, adjust | weekly | strategy is yours |

## Staying monetizable

- YouTube's YPP policy on **"inauthentic" (mass-produced, repetitive) content** is the main risk for automated channels. Keep many themes in `config.yaml` (the more variety the better), and don't post three cuts of the same thing.
- `upload.contains_synthetic_media: true` tells YouTube that AI tools were involved. Keep the description footer honest.
- Never claim medical benefits in titles. The Claude prompt already avoids "heals anxiety"-style wording.

## Painting backgrounds

With `visuals.background_source: "paintings"` (the default), each video shows a famous public-domain
painting chosen to suit its theme (Monet, Whistler, Van Gogh, Caillebotte, Inness, Turner and others), with a slow,
smooth camera glide across the canvas and back. The paintings come from the Art Institute of Chicago's
open-access collection, which releases them under CC0 (free for commercial use). The list is in
`assets/paintings.json`, and every description credits the painting, its artist and the museum automatically.

## Making weeks of videos at once

```bash
python -m ytauto samples                 # one short preview per theme, plus an overview of all paintings
python -m ytauto batch --days 14         # 14 days x 3 videos, uploaded as private while YouTube allows
python -m ytauto upload-pending          # next day: upload whatever is still waiting
```

`batch` saves `output/batch/UPLOAD_LIST.csv`, a spreadsheet of every video with its suggested schedule
date and time, title, status and YouTube link. If it's stopped or the computer restarts, run the same
command again: it continues where it left off and never makes or uploads a video twice. Pause the daily
GitHub workflow while you use batch videos (Actions → Daily videos → ⋯ → Disable workflow).

## Commands

```bash
python -m ytauto run              # make today's videos and upload them
python -m ytauto run --test       # 1-minute samples, nothing uploaded
python -m ytauto run --no-upload  # full-length videos, nothing uploaded
python -m ytauto run --only 0     # just the first video in the schedule
python -m ytauto run --date 2026-12-01   # pretend it's another day
python -m ytauto status           # list recent uploads
python -m ytauto auth             # (re)connect your YouTube channel
python -m pytest -q tests         # run the self-checks
```

## Troubleshooting

- **"invalid_grant" / "Token has been expired or revoked"**: your consent screen is still in Testing (step 3.4), or you removed access. Publish the app, run `python -m ytauto auth` again, and update the `YOUTUBE_TOKEN_JSON` secret.
- **Videos stay private even in scheduled mode**: the API audit isn't approved yet (step 4).
- **"thumbnail not set"**: verify your channel's phone number (step 3).
- **"quotaExceeded"**: you uploaded more than about 6 videos in one day. Wait until midnight Pacific time.
- **ffmpeg not found**: install it (step 1) and open a new terminal.

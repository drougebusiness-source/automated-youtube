# Rest and Relaxation: automated YouTube channel

Read this first. It is the full handover for anyone (human or AI) working on this channel.

## The business
- Channel: **Rest and Relaxation** (YouTube), owned by **Rouge Ventures LLC**. Owner: Darrell.
- Content: public-domain classical music (Musopen recordings) over famous public-domain paintings
  (Art Institute of Chicago, CC0) with a slow pan. Every description credits the painting and the music.
- Goal: YouTube Partner Program. Ads need **1,000 subscribers + 4,000 public watch hours** in 12 months
  (lower tier: 500 subs + 3,000 h unlocks memberships/tips only).
- Costs: ~$0. The repo is public, so GitHub Actions minutes are free. Music and art are free to use.
- Legal pages (OAuth consent screen): https://drougebusiness-source.github.io (index, privacy, terms).

## Where everything is
- Code and automation: GitHub **drougebusiness-source/automated-youtube** (public, branch `main`).
  A dev copy is in drougebusiness-source/polybot under `automated-youtube/` (branch claude/nice-planck-vqr3fx).
- Python package `ytauto/`; settings in `config.yaml` (the only file to edit for normal changes).
- State (committed by the bots): `state/batch.json` (long videos), `state/shorts.json`,
  `state/comments.json`, `state/channel.json` (channel ID UCwV7BkDpNfz_iJ7IuIFr8eg), `state/history.json`.
- YouTube sign-in: GitHub secret `YOUTUBE_TOKEN_JSON`, plus a newer sign-in with comment and analytics
  permissions stored **encrypted** in `state/token.enc` (key derived from that secret; only the
  workflows can read it). To sign in again: run the "Sign in again" workflow with an empty answer,
  open the link from its log, then run it again with the localhost address pasted as `answer`.
  Never commit token.json, client_secret*.json or .env.

## What runs by itself (GitHub Actions)
| Workflow | What | When |
|---|---|---|
| Batch videos (`batch-videos.yml`) | Makes long videos, uploads them as private, schedules them | Daily continuation; refills when < 10 days are queued; stops at 290 min |
| Shorts (`shorts-videos.yml`) | 4 Shorts a day, each linked to that day's long video | Daily continuation (needs the long videos uploaded first) |
| Link comments (`link-comments.yml`) | Posts the "full version" link under each Short once it's public; a question under each long video (from Nov 13) | Every 3 h |
| Channel stats (`channel-stats.yml`) | Views, likes and watch hours; breakdowns by theme, length, thumbnail and Short type | On demand |
| Sign in again (`reauth.yml`) | Re-authorizes YouTube without a computer | On demand |

Batch and Shorts share the concurrency group `batch-videos`, so only one runs at a time and a newer
*pending* run replaces an older pending one. If a dispatched run disappears, it was replaced:
dispatch it again. GitHub's cron runs are often hours late or skipped.

Uploads from this (unaudited) API project are forced to private, then scheduled with
`videos.update` publishAt, which works. The API audit form was submitted (Oct).

## Current schedule (since Nov 13; agreed Nov 1 and applied Nov 10)
- **Long videos (Eastern):** 08:00 1-hour, 13:00 30-min, 20:00 **3-hour Deep Sleep** nightly. The 15-min slot was dropped.
- **Theme mix:** Rainy Study ~1/3, Deep Sleep ~1/3, rest Morning Light + Forest Wind.
  Ocean Meditation and Starlight Focus are paused (`active: false`). Deep Sleep borrows calm
  Bach/Schubert piano so 3 hours never repeats a piece.
- **Titles:** "[Theme] | [Length] of Calm [Style] for [Use]" + main composer; since 102de86, also the painting so no title repeats.
- **Descriptions:** a subscribe link first, then the tracklist with timestamps, then art and music credits.
- **Thumbnails:** design A (whole painting) is the default and won ~3x. Every 5th video tests B.
- **Shorts (Eastern):** 07:00 POV, 12:00 painting story, 16:00 musical moment, 21:00 sleep;
  all branded "REST AND RELAXATION"; each links to a long video (sleep → the 3-hour Deep Sleep).

## Status (Nov 11, 2026)
- Scheduled through **Nov 22** (30 long videos + 40 Shorts from Nov 13). Nov 23–26 were being made on Nov 11.
- Nov 10 numbers: **38 subscribers**, 8,961 views, **533 watch hours** (12 months), ~15–30 watch h/day,
  avg view 6–8 min. Subscribers jumped once Shorts started (3 in 5 days → 10 in 4 days).
- Shorts views/day per Short: **POV ~207**, sleep ~87, moment ~56, story ~25. Long videos ~5–6.
- Long-video themes by views per video: Deep Sleep and Rainy Study best; Starlight/Ocean worst.
- Projection: watch hours reach 3,000–4,000 around Feb–Jun 2027. **Subscribers are the bottleneck**
  (~2.5/day → 500 by ~May, 1,000 in ~a year). Shorts are the main lever.

## Open items
1. Ask Darrell for the channel **@handle** and put it in `config.yaml` → `channel.handle` (shown on Shorts).
2. Proposed, not yet approved: replace the 12:00 painting-story Short with a second POV Short
   (POV ~8x the views).
3. Darrell has added the watermark (assets/watermark.png) and channel keywords in Studio. Suggested but not
   confirmed: an end screen with Subscribe on the top video (Rainy Study 1-hour).
4. Re-run Channel stats every week or two and compare against the numbers above.

## How to run things
- Tests: `pip install -r requirements.txt pytest && python -m pytest -q tests`.
- Test a batch locally without uploading: `python -m ytauto batch --days 1 --start YYYY-MM-DD --no-upload`.
- Windows launchers are in `scripts/*.bat` (make_videos, upload_pending, schedule_videos, channel_stats, reauth).
- Known ffmpeg trap: never put `areverse` and `loudnorm` in one filter chain (it hangs); `audio.to_wav` runs them as two passes.

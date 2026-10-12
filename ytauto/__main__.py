"""Command line: python -m ytauto <command>"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

from .config import load_config


def main() -> int:
    parser = argparse.ArgumentParser(prog="ytauto", description="Automated YouTube music channel")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("auth", help="sign in to YouTube once (opens a browser)")
    p_run = sub.add_parser("run", help="make today's videos and upload them")
    p_run.add_argument("--no-upload", action="store_true", help="make the videos but don't upload")
    p_run.add_argument("--test", action="store_true", help="quick 1-minute versions, no upload")
    p_run.add_argument("--date", help="pretend today is YYYY-MM-DD")
    p_run.add_argument("--only", type=int, help="only make this slot (0 = first video in schedule)")
    sub.add_parser("status", help="show recent uploads")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    for noisy in ("googleapiclient", "httpx", "httpx2", "anthropic"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    cfg = load_config()

    if args.cmd == "auth":
        from .youtube import authorize
        token = authorize(cfg.root)
        print(f"Signed in. Saved {token}.\nFor GitHub Actions, paste this file's contents into a "
              "repository secret named YOUTUBE_TOKEN_JSON (README step 6).")
        return 0
    if args.cmd == "status":
        from .pipeline import load_state
        for v in load_state(cfg)["videos"][-15:]:
            print(f"{v['publish_date']}  {v['minutes']:>3} min  {v['theme']:<18} {v.get('url', '(not uploaded)')}  {v['title']}")
        return 0

    from .pipeline import run
    ok = run(cfg, upload=not args.no_upload, test=args.test,
             run_date=date.fromisoformat(args.date) if args.date else None, only=args.only)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

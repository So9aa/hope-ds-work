#!/usr/bin/env python3
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from urllib import error, request

DEFAULT_WEBHOOK_URL = os.environ.get(
    "DISCORD_WEBHOOK_URL",
    "https://discordapp.com/api/webhooks/1553463314422698085/tmWHGyzq7leGIFI1km9VbvnkVRsTexrL-JOsdPVoWoMR1AF7sfHVcx-zbf_DFbW2BEMj",
)


def send_message(webhook_url: str, content: str) -> int:
    payload = json.dumps({"content": content}).encode("utf-8")
    req = request.Request(
        webhook_url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "lunch-webhook/1.0",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=15) as resp:
            return resp.status
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"Discord webhook failed: HTTP {exc.code} {body}", file=sys.stderr)
        return exc.code
    except Exception as exc:
        print(f"Discord webhook failed: {exc}", file=sys.stderr)
        return 1


def build_status_text(status: str, detail: str, exit_code: int | None, repo: str) -> str:
    emoji = "✅" if status.lower() in {"done", "success", "ok"} else "❌"
    title = "Lunch completed" if status.lower() in {"done", "success", "ok"} else "Lunch failed"
    if exit_code is not None:
        exit_info = f" | exit code: {exit_code}"
    else:
        exit_info = ""
    when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (
        f"{emoji} {title} {repo}{exit_info}\n"
        f"{detail}\n"
        f"Time: {when}"
    )


def parse_args():
    parser = argparse.ArgumentParser(description="Send a Discord webhook message after lunch/done or failed status.")
    parser.add_argument("--status", choices=["done", "failed"], default="done")
    parser.add_argument("--detail", default="Lunch command finished.")
    parser.add_argument("--exit-code", type=int, default=None)
    parser.add_argument("--repo", default="hope-ds-work")
    parser.add_argument("--webhook", default=DEFAULT_WEBHOOK_URL)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    message = build_status_text(args.status, args.detail, args.exit_code, args.repo)
    http_code = send_message(args.webhook, message)
    if http_code in {200, 204}:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

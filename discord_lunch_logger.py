#!/usr/bin/env python3
import argparse
import json
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from urllib import error, request

DEFAULT_WEBHOOK_URL = os.environ.get(
    "DISCORD_WEBHOOK_URL",
    "https://discordapp.com/api/webhooks/1553463314422698085/tmWHGyzq7leGIFI1km9VbvnkVRsTexrL-JOsdPVoWoMR1AF7sfHVcx-zbf_DFbW2BEMj",
)


def build_status_text(status: str, detail: str, exit_code: int | None, repo: str, log_text: str = "") -> str:
    emoji = "✅" if status.lower() in {"done", "success", "ok"} else "❌"
    title = "Lunch completed" if status.lower() in {"done", "success", "ok"} else "Lunch failed"
    if exit_code is not None:
        exit_info = f" | exit code: {exit_code}"
    else:
        exit_info = ""
    when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    summary = (
        f"{emoji} {title} {repo}{exit_info}\n"
        f"{detail}\n"
        f"Time: {when}"
    )
    return summary


def read_log_file(path: str | None) -> str:
    if not path:
        return ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def build_form_data(payload_json: str, text_path: str) -> tuple[bytes, str]:
    boundary = "----webhook-" + uuid.uuid4().hex
    file_name = os.path.basename(text_path)
    body_parts = []

    def add_field(name: str, value: str, filename: str | None = None, content_type: str | None = None):
        body_parts.append(f"--{boundary}\r\n".encode("utf-8"))
        if filename:
            body_parts.append(f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode("utf-8"))
            if content_type:
                body_parts.append(f"Content-Type: {content_type}\r\n".encode("utf-8"))
            body_parts.append(b"\r\n")
            body_parts.append(value.encode("utf-8") if isinstance(value, str) else value)
        else:
            body_parts.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
            body_parts.append(value.encode("utf-8"))
        body_parts.append(b"\r\n")

    with open(text_path, "rb") as fh:
        file_bytes = fh.read()

    add_field("payload_json", payload_json)
    add_field("file", file_bytes, filename=file_name, content_type="text/plain")
    body_parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(body_parts), boundary


def send_message(webhook_url: str, content: str, file_path: str) -> int:
    summary = content
    payload_json = json.dumps({"content": summary})
    try:
        data, boundary = build_form_data(payload_json, file_path)
        req = request.Request(
            webhook_url,
            data=data,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": "lunch-webhook/1.0",
            },
            method="POST",
        )
        with request.urlopen(req, timeout=20) as resp:
            return resp.status
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"Discord webhook failed: HTTP {exc.code} {body}", file=sys.stderr)
        return exc.code
    except Exception as exc:
        print(f"Discord webhook failed: {exc}", file=sys.stderr)
        return 1


def parse_args():
    parser = argparse.ArgumentParser(description="Send a Discord webhook message after lunch/done or failed status.")
    parser.add_argument("--status", choices=["done", "failed"], default="done")
    parser.add_argument("--detail", default="Lunch command finished.")
    parser.add_argument("--exit-code", type=int, default=None)
    parser.add_argument("--repo", default="hope-ds-work")
    parser.add_argument("--webhook", default=DEFAULT_WEBHOOK_URL)
    parser.add_argument("--log-file", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    log_text = read_log_file(args.log_file) or "No console output captured."
    summary = build_status_text(args.status, args.detail, args.exit_code, args.repo, log_text)
    if not args.log_file:
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt", encoding="utf-8") as fh:
            fh.write(log_text)
            log_path = fh.name
    else:
        log_path = args.log_file
    try:
        http_code = send_message(args.webhook, summary, log_path)
    finally:
        if args.log_file is None:
            try:
                os.unlink(log_path)
            except OSError:
                pass
    if http_code in {200, 204}:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

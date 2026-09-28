#!/usr/bin/env python3
"""Serve the PS5 test page and relay completed logs to a private Discord webhook.

Set DISCORD_WEBHOOK_URL in the server environment; never put that URL in page
source or a browser URL. The client sends log JSON to /discord-log. The server
also accepts the existing plain-text /log posts and /latch requests.
"""

from __future__ import annotations

import datetime as dt
import hmac
import json
import os
import re
import sys
import threading
import time
import uuid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
WEBROOT = ROOT / "serve"
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8080"))
MAX_BODY_BYTES = 1024 * 1024
MAX_LOG_BYTES = 768 * 1024
MAX_POSTS_PER_MINUTE = 12
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
RELAY_TOKEN = os.environ.get("PS5_RELAY_TOKEN", "").strip()
ALLOWED_ORIGINS = {
    item.strip() for item in os.environ.get(
        "PS5_ALLOWED_ORIGINS", "https://so9aa.github.io"
    ).split(",") if item.strip()
}

LATCH = {"set": False, "detail": ""}
_RATE_LOCK = threading.Lock()
_RATE = {}
_LOG_LOCK = threading.RLock()
_RUN_LOGS = {}
_FINALIZED_RUNS = set()
PARTIAL_FLUSH_SECONDS = 90


def ts() -> str:
    return dt.datetime.now().strftime("%H:%M:%S")


def safe_filename(value: str) -> str:
    value = Path(str(value or "ps5-run.log.txt")).name
    value = re.sub(r"[^A-Za-z0-9_.-]", "_", value)[:100]
    return value or "ps5-run.log.txt"


def _check_webhook() -> str:
    parts = urlsplit(DISCORD_WEBHOOK_URL)
    if (parts.scheme != "https" or parts.hostname not in {"discord.com", "discordapp.com"}
            or not re.fullmatch(r"/api/webhooks/[0-9]+/[^/]+", parts.path)):
        raise ValueError("DISCORD_WEBHOOK_URL must be a Discord HTTPS webhook URL")
    query = parse_qs(parts.query)
    query["wait"] = ["true"]
    return urlunsplit((parts.scheme, parts.netloc, parts.path,
                       urlencode(query, doseq=True), ""))


def send_discord_log(label: str, run_id: str, text: str, filename: str) -> None:
    """Upload one bounded text attachment to the configured Discord webhook."""
    webhook = _check_webhook()
    content = f"PS5 run {run_id}: {label}"[:500]
    filename = safe_filename(filename)
    boundary = "----ps5log" + uuid.uuid4().hex
    attachment = text.encode("utf-8", "replace")
    payload = {
        "content": content,
        "allowed_mentions": {"parse": []},
        "attachments": [{"id": 0, "filename": filename}],
    }
    chunks = [
        f"--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="payload_json"\r\n',
        b"Content-Type: application/json\r\n\r\n",
        json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        b"\r\n",
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="files[0]"; filename="{filename}"\r\n'.encode(),
        b"Content-Type: text/plain; charset=utf-8\r\n\r\n",
        attachment,
        b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ]
    request = Request(
        webhook,
        data=b"".join(chunks),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urlopen(request, timeout=15) as response:
        if response.status not in (200, 204):
            raise RuntimeError(f"Discord returned HTTP {response.status}")


def rate_limited(ip: str) -> bool:
    now = time.monotonic()
    with _RATE_LOCK:
        recent = [t for t in _RATE.get(ip, []) if now - t < 60]
        if len(recent) >= MAX_POSTS_PER_MINUTE:
            _RATE[ip] = recent
            return True
        recent.append(now)
        _RATE[ip] = recent
        return False


def queue_console_log(run_id: str, text: str) -> None:
    run_id = re.sub(r"[^A-Za-z0-9_-]", "", str(run_id or ""))[:64]
    if not run_id or not text or not DISCORD_WEBHOOK_URL or not RELAY_TOKEN:
        return
    with _LOG_LOCK:
        if run_id in _FINALIZED_RUNS:
            return
        state = _RUN_LOGS.setdefault(run_id, {"text": "", "timer": None})
        joined = (state["text"] + "\n" + text).strip()
        encoded = joined.encode("utf-8", "replace")
        if len(encoded) > MAX_LOG_BYTES:
            encoded = encoded[-MAX_LOG_BYTES:]
            joined = encoded.decode("utf-8", "replace")
        state["text"] = joined
        timer = state.get("timer")
        if timer:
            timer.cancel()
        timer = threading.Timer(PARTIAL_FLUSH_SECONDS, flush_partial_log, args=(run_id,))
        timer.daemon = True
        state["timer"] = timer
        timer.start()


def finalize_console_log(run_id: str) -> None:
    run_id = re.sub(r"[^A-Za-z0-9_-]", "", str(run_id or ""))[:64]
    if not run_id:
        return
    with _LOG_LOCK:
        _FINALIZED_RUNS.add(run_id)
        while len(_FINALIZED_RUNS) > 500:
            _FINALIZED_RUNS.pop()
        state = _RUN_LOGS.pop(run_id, None)
        if state and state.get("timer"):
            state["timer"].cancel()


def flush_partial_log(run_id: str) -> None:
    with _LOG_LOCK:
        state = _RUN_LOGS.pop(run_id, None)
        if run_id in _FINALIZED_RUNS or not state:
            return
        _FINALIZED_RUNS.add(run_id)
        text = state.get("text", "")
    if not text.strip():
        return
    try:
        send_discord_log("Partial console log (quiet timeout)", run_id, text,
                         f"ps5-run-{run_id}-partial.log.txt")
        sys.stderr.write(f"[{ts()}] Discord partial log sent run={run_id}\n")
    except Exception as exc:
        sys.stderr.write(f"[{ts()}] Discord partial log failed run={run_id}: {str(exc)[:160]}\n")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEBROOT), **kwargs)

    def log_message(self, fmt, *args):
        # Do not echo query strings (which could contain user-supplied settings).
        path = urlsplit(self.path).path
        sys.stderr.write(f"[{ts()}] {self.client_address[0]} {self.command} {path}\n")

    def _cors(self):
        origin = self.headers.get("Origin")
        host = self.headers.get("Host", "")
        same_origin = False
        if origin:
            try:
                same_origin = urlsplit(origin).netloc == host
            except Exception:
                same_origin = False
        if not origin:
            self.send_header("Access-Control-Allow-Origin", "*")
        elif same_origin or origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Relay-Token")
        self.send_header("Access-Control-Max-Age", "600")

    def _send(self, code: int, body, content_type="application/json"):
        data = body if isinstance(body, bytes) else str(body).encode("utf-8")
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if data:
            self.wfile.write(data)

    def _json(self, code: int, value):
        self._send(code, json.dumps(value), "application/json; charset=utf-8")

    def _read_body(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length < 0 or length > MAX_BODY_BYTES:
            return None
        return self.rfile.read(length) if length else b""

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        parsed = urlsplit(self.path)
        if parsed.path == "/":
            self.send_response(302)
            self.send_header("Location", "/document/en/ps5/")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if parsed.path == "/health":
            return self._json(200, {"ok": True})
        if parsed.path == "/discord-status":
            if not RELAY_TOKEN or not hmac.compare_digest(
                    self.headers.get("X-Relay-Token", ""), RELAY_TOKEN):
                return self._json(401, {"configured": False, "error": "invalid relay token"})
            return self._json(200, {"configured": bool(DISCORD_WEBHOOK_URL and RELAY_TOKEN)})
        if parsed.path == "/latch":
            q = parse_qs(parsed.query)
            if "set" in q or "detail" in q:
                LATCH["set"] = q.get("set", ["1"])[0] not in ("0", "false")
                LATCH["detail"] = q.get("detail", [""])[0][:200]
                sys.stderr.write(f"[{ts()}] LATCH-SET(GET)\n")
            return self._json(200, LATCH)
        if parsed.path.startswith("/log/"):
            line = parsed.path[len("/log/"):]
            self._emit_log(line)
            queue_console_log(parse_qs(parsed.query).get("run", [""])[0], line)
            return self._send(200, "ok", "text/plain; charset=utf-8")
        return super().do_GET()

    def do_POST(self):
        parsed = urlsplit(self.path)
        body = self._read_body()
        if body is None:
            return self._json(413, {"ok": False, "error": "request too large"})

        if parsed.path == "/latch":
            text = body.decode("utf-8", "replace")
            LATCH["set"] = True
            LATCH["detail"] = text[:200]
            sys.stderr.write(f"[{ts()}] LATCH-SET(POST)\n")
            return self._json(200, LATCH)

        if parsed.path == "/log":
            text = body.decode("utf-8", "replace")
            self._emit_log(text)
            queue_console_log(parse_qs(parsed.query).get("run", [""])[0], text)
            return self._send(200, "ok", "text/plain; charset=utf-8")

        if parsed.path == "/discord-log":
            if not DISCORD_WEBHOOK_URL or not RELAY_TOKEN:
                return self._json(503, {"ok": False, "error": "Discord relay is not configured on the host"})
            supplied_token = self.headers.get("X-Relay-Token", "")
            if not hmac.compare_digest(supplied_token, RELAY_TOKEN):
                return self._json(401, {"ok": False, "error": "invalid relay token"})
            if rate_limited(self.client_address[0]):
                return self._json(429, {"ok": False, "error": "rate limit"})
            try:
                request = json.loads(body.decode("utf-8"))
                text = str(request.get("text", ""))
                if not text.strip():
                    return self._json(400, {"ok": False, "error": "empty log"})
                encoded = text.encode("utf-8", "replace")
                if len(encoded) > MAX_LOG_BYTES:
                    return self._json(413, {"ok": False, "error": "log exceeds relay limit"})
                label = str(request.get("label", "completed PS5 run"))[:400]
                run_id = re.sub(r"[^A-Za-z0-9_-]", "", str(request.get("run_id", "unknown")))[:64]
                filename = safe_filename(request.get("filename", f"ps5-run-{run_id}.log.txt"))
                send_discord_log(label, run_id or "unknown", text, filename)
                finalize_console_log(run_id)
                sys.stderr.write(f"[{ts()}] Discord log sent run={run_id or 'unknown'} bytes={len(encoded)}\n")
                return self._json(200, {"ok": True})
            except HTTPError as exc:
                return self._json(502, {"ok": False, "error": f"Discord HTTP {exc.code}"})
            except (URLError, TimeoutError) as exc:
                return self._json(502, {"ok": False, "error": f"Discord request failed: {exc.reason if isinstance(exc, URLError) else 'timeout'}"})
            except (ValueError, RuntimeError, json.JSONDecodeError) as exc:
                return self._json(400, {"ok": False, "error": str(exc)[:200]})
            except Exception:
                sys.stderr.write(f"[{ts()}] Discord relay failed run=request-error\n")
                return self._json(500, {"ok": False, "error": "internal relay error"})

        return self._json(404, {"ok": False, "error": "not found"})

    @staticmethod
    def _emit_log(text: str):
        text = text.rstrip("\r\n")
        if not text:
            return
        stamp = dt.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        for logical in text.splitlines():
            print(f"[{stamp}] {logical}", flush=True)


if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.daemon_threads = True
    print(f"[*] HTTP on {HOST}:{PORT}; webroot={WEBROOT}", flush=True)
    print("[*] Discord relay:", "configured" if DISCORD_WEBHOOK_URL and RELAY_TOKEN else "not configured", flush=True)
    print("[*] Open /document/en/ps5/ or visit / for redirect.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] shutting down", flush=True)
    finally:
        server.server_close()

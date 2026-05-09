#!/usr/bin/env python3
"""Todoist reminder notification daemon.

Polls Todoist every 30 s and fires a desktop notification + sound
when a task's due time arrives (within a ±90 s window to survive
daemon startup and minor clock drift).

If YANDEX_STATION_IP and YANDEX_STATION_TOKEN are set in .env,
also sends TTS to the Yandex Station over the local network.
Run station_token.py once to populate those values.
"""

import base64
import json
import os
import socket
import ssl
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

POLL_SEC = 30
# Notify if due time is within [now - LOOKBACK, now + LOOKAHEAD]
LOOKBACK_SEC = 90
LOOKAHEAD_SEC = 60

SOUND = "/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga"

STATE_DIR = Path.home() / ".local/share/todoist-remind"
ENV_FILE = STATE_DIR / ".env"
NOTIFIED_FILE = STATE_DIR / "notified.json"

NOTIFIED_TTL_SEC = 3600  # forget entries older than 1 h


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    if not ENV_FILE.exists():
        return env
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def load_notified() -> dict[str, float]:
    if not NOTIFIED_FILE.exists():
        return {}
    try:
        return json.loads(NOTIFIED_FILE.read_text())
    except Exception:
        return {}


def save_notified(notified: dict[str, float]) -> None:
    NOTIFIED_FILE.write_text(json.dumps(notified))


def prune_notified(notified: dict[str, float], now_ts: float) -> dict[str, float]:
    return {k: v for k, v in notified.items() if now_ts - v < NOTIFIED_TTL_SEC}


def fetch_tasks(token: str, project_id: str) -> list[dict]:
    url = "https://api.todoist.com/api/v1/tasks"
    if project_id:
        url += f"?project_id={project_id}"
    result = subprocess.run(
        ["curl", "-sf", "-H", f"Authorization: Bearer {token}", url],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    try:
        data = json.loads(result.stdout)
        return data.get("results", [])
    except Exception:
        return []


def parse_due_ts(due: dict) -> float | None:
    """Return UTC timestamp or None if task has no due datetime."""
    dt_str = due.get("datetime") or due.get("date")
    if not dt_str:
        return None
    try:
        # ISO 8601: 2025-05-04T14:30:00Z  or  2025-05-04
        dt_str = dt_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            # date-only tasks have no specific time — skip
            return None
        return dt.timestamp()
    except Exception:
        return None


def _station_tts(ip: str, token: str, text: str) -> None:
    """Send TTS to Yandex Station via local glagol WebSocket (stdlib only)."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    sock = socket.create_connection((ip, 1961), timeout=5)
    tls = ctx.wrap_socket(sock, server_hostname=ip)
    try:
        ws_key = base64.b64encode(os.urandom(16)).decode()
        tls.sendall((
            f"GET / HTTP/1.1\r\n"
            f"Host: {ip}:1961\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {ws_key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n"
            f"\r\n"
        ).encode())

        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = tls.recv(1024)
            if not chunk:
                break
            buf += chunk
        if b" 101 " not in buf:
            raise RuntimeError(f"WS handshake failed: {buf[:120]!r}")

        payload = json.dumps({
            "conversationToken": token,
            "id": str(uuid4()),
            "sentTime": time.time(),
            "payload": {"command": "sendText", "text": text},
        }, ensure_ascii=False).encode()

        mask = os.urandom(4)
        n = len(payload)
        if n < 126:
            header = bytes([0x81, 0x80 | n]) + mask
        elif n < 65536:
            header = bytes([0x81, 0xFE]) + n.to_bytes(2, "big") + mask
        else:
            header = bytes([0x81, 0xFF]) + n.to_bytes(8, "big") + mask
        tls.sendall(header + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))
    finally:
        tls.close()


def notify(content: str, due_local: str, station_ip: str = "", station_token: str = "") -> None:
    env = {**os.environ, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    subprocess.Popen(
        [
            "notify-send",
            "--urgency=critical",
            "--icon=alarm-symbolic",
            "--app-name=Напоминание",
            f"⏰ {content}",
            due_local,
        ],
        env=env,
    )
    if os.path.exists(SOUND):
        subprocess.Popen(["paplay", SOUND])
    if station_ip and station_token:
        try:
            _station_tts(station_ip, station_token, f"Напоминание: {content}")
        except Exception as exc:
            print(f"[station-tts] {exc} — запустите station_token.py для обновления токена", flush=True)


def format_local(ts: float) -> str:
    dt = datetime.fromtimestamp(ts)
    return dt.strftime("%d.%m.%Y %H:%M")


def run() -> None:
    notified: dict[str, float] = load_notified()

    while True:
        env = load_env()
        token = env.get("TODOIST_TOKEN", "")
        project_id = env.get("TODOIST_PROJECT_ID", "")
        station_ip = env.get("YANDEX_STATION_IP", "")
        station_token = env.get("YANDEX_STATION_TOKEN", "")

        if not token:
            time.sleep(POLL_SEC)
            continue

        now_ts = time.time()
        tasks = fetch_tasks(token, project_id)

        notified = prune_notified(notified, now_ts)

        for task in tasks:
            task_id: str = task.get("id", "")
            content: str = task.get("content", "")
            due = task.get("due")
            if not due:
                continue
            due_ts = parse_due_ts(due)
            if due_ts is None:
                continue

            already = notified.get(task_id)
            if already is not None and abs(already - due_ts) < 1:
                # already notified for this exact due time
                continue

            if now_ts - LOOKBACK_SEC <= due_ts <= now_ts + LOOKAHEAD_SEC:
                notify(content, format_local(due_ts), station_ip, station_token)
                notified[task_id] = due_ts
                save_notified(notified)

        time.sleep(POLL_SEC)


if __name__ == "__main__":
    run()

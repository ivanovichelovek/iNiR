#!/usr/bin/env python3
"""Todoist reminder notification daemon.

Polls Todoist every 30 s and fires a desktop notification + sound
when a task's due time arrives (within a ±90 s window to survive
daemon startup and minor clock drift).
"""

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

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


def notify(content: str, due_local: str) -> None:
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


def format_local(ts: float) -> str:
    dt = datetime.fromtimestamp(ts)
    return dt.strftime("%d.%m.%Y %H:%M")


def run() -> None:
    notified: dict[str, float] = load_notified()

    while True:
        env = load_env()
        token = env.get("TODOIST_TOKEN", "")
        project_id = env.get("TODOIST_PROJECT_ID", "")

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
                notify(content, format_local(due_ts))
                notified[task_id] = due_ts
                save_notified(notified)

        time.sleep(POLL_SEC)


if __name__ == "__main__":
    run()

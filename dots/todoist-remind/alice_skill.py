#!/usr/bin/env python3
"""Yandex Alice skill webhook for Todoist reminders.

Listens on 0.0.0.0:PORT — point Cloudflare Tunnel at that port,
then register <tunnel-url>/alice as the webhook in Yandex Dialogs.
"""

from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import urllib.request
import urllib.error

PORT_DEFAULT = 5757
ENV_FILE = Path.home() / ".local/share/todoist-remind/.env"


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


def fetch_tasks(token: str, project_id: str) -> list[dict]:
    url = "https://api.todoist.com/api/v1/tasks"
    if project_id:
        url += f"?project_id={project_id}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read()).get("results", [])
    except Exception:
        return []


def parse_due_dt(due: dict) -> datetime | None:
    dt_str = due.get("datetime") or due.get("date")
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt if dt.tzinfo is not None else None
    except Exception:
        return None


def _count_form(n: int) -> str:
    if 11 <= n % 100 <= 14:
        return f"{n} напоминаний"
    mod = n % 10
    if mod == 1:
        return f"{n} напоминание"
    if 2 <= mod <= 4:
        return f"{n} напоминания"
    return f"{n} напоминаний"


def speech_dt(dt: datetime) -> str:
    local = dt.astimezone()
    now = datetime.now().astimezone()
    months = [
        "января", "февраля", "марта", "апреля", "мая", "июня",
        "июля", "августа", "сентября", "октября", "ноября", "декабря",
    ]
    h, m = local.hour, local.minute
    time_str = f"в {h}:{m:02d}"
    if local.date() == now.date():
        return f"сегодня {time_str}"
    if local.date() == (now + timedelta(days=1)).date():
        return f"завтра {time_str}"
    return f"{local.day} {months[local.month - 1]} {time_str}"


def get_next(token: str, project_id: str) -> tuple[datetime, dict] | None:
    now = datetime.now(timezone.utc)
    best: tuple[datetime, dict] | None = None
    for task in fetch_tasks(token, project_id):
        due = task.get("due")
        if not due:
            continue
        dt = parse_due_dt(due)
        if dt and dt > now and (best is None or dt < best[0]):
            best = (dt, task)
    return best


def get_next_24h(token: str, project_id: str) -> list[tuple[datetime, dict]]:
    now = datetime.now(timezone.utc)
    deadline = now + timedelta(hours=24)
    result = []
    for task in fetch_tasks(token, project_id):
        due = task.get("due")
        if not due:
            continue
        dt = parse_due_dt(due)
        if dt and now < dt <= deadline:
            result.append((dt, task))
    result.sort(key=lambda x: x[0])
    return result


def _intent(cmd: str) -> str:
    LIST_WORDS = ("сутк", "включи", "список", "перечисл", "что у меня")
    NEXT_WORDS = ("ближайш", "следующ", "когда")
    if any(w in cmd for w in LIST_WORDS):
        return "list"
    if any(w in cmd for w in NEXT_WORDS):
        return "next"
    if "напоминани" in cmd:
        return "list"
    return "unknown"


HELP = (
    "Спрашивай. Например: ближайшее напоминание — и я скажу ближайшее. "
    "Или: напоминания на сутки — и я перечислю все на ближайшие двадцать четыре часа."
)


def handle(body: bytes) -> bytes | None:
    try:
        req = json.loads(body)
    except Exception:
        return None

    env = load_env()
    session = req.get("session", {})

    skill_id = env.get("YANDEX_SKILL_ID", "")
    if skill_id and session.get("skill_id", "") != skill_id:
        return None

    token = env.get("TODOIST_TOKEN", "")
    project_id = env.get("TODOIST_PROJECT_ID", "")
    command = req.get("request", {}).get("command", "").strip().lower()
    is_new = session.get("new", False)

    if not token:
        text, end = "Токен Todoist не настроен.", True
    elif is_new and not command:
        text, end = HELP, False
    else:
        intent = _intent(command)
        if intent == "next":
            item = get_next(token, project_id)
            if item is None:
                text = "Предстоящих напоминаний нет."
            else:
                dt, task = item
                text = f"Ближайшее: {task['content']} — {speech_dt(dt)}."
            end = True
        elif intent == "list":
            items = get_next_24h(token, project_id)
            if not items:
                text = "На ближайшие сутки напоминаний нет."
            elif len(items) == 1:
                dt, task = items[0]
                text = f"Одно напоминание: {task['content']} — {speech_dt(dt)}."
            else:
                parts = [f"{task['content']} — {speech_dt(dt)}" for dt, task in items]
                text = f"На ближайшие сутки {_count_form(len(items))}: {'; '.join(parts)}."
            end = True
        else:
            text = "Не понял. Скажи: ближайшее напоминание, или: напоминания на сутки."
            end = False

    resp = {
        "version": "1.0",
        "session": {
            "session_id": session.get("session_id", ""),
            "message_id": session.get("message_id", 0),
        },
        "response": {"text": text, "end_session": end},
    }
    return json.dumps(resp, ensure_ascii=False).encode()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_POST(self):
        if self.path != "/alice":
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", 0))
        data = handle(self.rfile.read(length))
        if data is None:
            self.send_response(400)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    env = load_env()
    port = int(env.get("ALICE_SKILL_PORT", PORT_DEFAULT))
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"[alice-skill] :{port}/alice", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass

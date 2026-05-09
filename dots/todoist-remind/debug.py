# /// script
# requires-python = ">=3.11"
# dependencies = ["rich"]
# ///
"""Debug script for todoist-remind + Alice skill.

Usage:
  uv run debug.py            # full check
  uv run debug.py todoist    # only Todoist API
  uv run debug.py webhook    # only local webhook
  uv run debug.py station    # only Yandex Station ping
"""

import json
import socket
import ssl
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich import print as rprint

console = Console()

ENV_FILE = Path.home() / ".local/share/todoist-remind/.env"
WEBHOOK_PORT = 5757


# ── helpers ──────────────────────────────────────────────────────────────────

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


def mask(s: str) -> str:
    return s[:6] + "…" + s[-4:] if len(s) > 12 else "***"


def parse_due_dt(due: dict) -> datetime | None:
    dt_str = due.get("datetime") or due.get("date")
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt if dt.tzinfo is not None else None
    except Exception:
        return None


# ── checks ────────────────────────────────────────────────────────────────────

def check_env(env: dict) -> None:
    console.rule("[bold cyan].env")

    keys = ["TODOIST_TOKEN", "TODOIST_PROJECT_ID",
            "YANDEX_SKILL_ID", "ALICE_SKILL_PORT",
            "YANDEX_STATION_IP", "YANDEX_STATION_TOKEN", "YANDEX_OAUTH_TOKEN"]

    t = Table(show_header=False, box=None, padding=(0, 2))
    for k in keys:
        v = env.get(k, "")
        if not v:
            t.add_row(f"[dim]{k}[/dim]", "[dim]не задан[/dim]")
        elif "TOKEN" in k or "SECRET" in k:
            t.add_row(f"[green]{k}[/green]", mask(v))
        else:
            t.add_row(f"[green]{k}[/green]", v)
    console.print(t)


def check_todoist(env: dict) -> list[dict]:
    console.rule("[bold cyan]Todoist API")

    token = env.get("TODOIST_TOKEN", "")
    project_id = env.get("TODOIST_PROJECT_ID", "")

    if not token:
        rprint("[red]✗[/red] TODOIST_TOKEN не задан")
        return []

    url = "https://api.todoist.com/api/v1/tasks"
    if project_id:
        url += f"?project_id={project_id}"

    try:
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
            data = json.loads(raw)
    except urllib.error.HTTPError as e:
        rprint(f"[red]✗[/red] HTTP {e.code}: {e.reason}")
        if e.code == 401:
            rprint("  → Токен недействителен")
        return []
    except Exception as e:
        rprint(f"[red]✗[/red] {e}")
        return []

    tasks = data.get("results", [])
    rprint(f"[green]✓[/green] Получено задач: [bold]{len(tasks)}[/bold]")

    if not tasks:
        rprint("[yellow]  Список пуст — задач в Todoist нет (или не в этом проекте)[/yellow]")
        return []

    now = datetime.now(timezone.utc)

    t = Table(title="Задачи", show_lines=True)
    t.add_column("#", style="dim", width=3)
    t.add_column("Название")
    t.add_column("due.date", style="cyan")
    t.add_column("due.datetime", style="cyan")
    t.add_column("parse_due_dt")
    t.add_column("Статус")

    for i, task in enumerate(tasks, 1):
        due = task.get("due") or {}
        raw_date = due.get("date", "—")
        raw_datetime = due.get("datetime", "—") or "—"
        parsed = parse_due_dt(due)

        if parsed is None and due:
            status = "[yellow]нет времени (date-only)[/yellow]"
            parsed_str = "[yellow]None[/yellow]"
        elif parsed is None:
            status = "[dim]нет due[/dim]"
            parsed_str = "—"
        elif parsed > now:
            status = "[green]предстоит[/green]"
            parsed_str = parsed.astimezone().strftime("%d.%m %H:%M")
        else:
            status = "[red]в прошлом[/red]"
            parsed_str = parsed.astimezone().strftime("%d.%m %H:%M")

        t.add_row(str(i), task.get("content", ""), raw_date, raw_datetime, parsed_str, status)

    console.print(t)
    return tasks


def check_webhook(env: dict) -> None:
    console.rule("[bold cyan]Локальный webhook (localhost:5757)")

    port = int(env.get("ALICE_SKILL_PORT", WEBHOOK_PORT))
    skill_id = env.get("YANDEX_SKILL_ID", "")

    payload = {
        "version": "1.0",
        "session": {
            "session_id": "debug-session",
            "message_id": 1,
            "skill_id": skill_id,
            "new": False,
        },
        "request": {
            "command": "ближайшее напоминание",
            "original_utterance": "ближайшее напоминание",
            "type": "SimpleUtterance",
            "nlu": {},
        },
    }

    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"http://localhost:{port}/alice",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read())
            text = result.get("response", {}).get("text", "")
            rprint(f"[green]✓[/green] Сервис отвечает")
            rprint(f"  Ответ Алисы: [bold]{text!r}[/bold]")
    except urllib.error.HTTPError as e:
        rprint(f"[red]✗[/red] HTTP {e.code}")
        if e.code == 400:
            rprint("  → Вероятно, YANDEX_SKILL_ID не совпадает с тем, что в .env")
    except ConnectionRefusedError:
        rprint(f"[red]✗[/red] Сервис не запущен на порту {port}")
        rprint("  → systemctl --user start todoist-remind-alice")
    except Exception as e:
        rprint(f"[red]✗[/red] {e}")

    # Also test "list" intent
    payload["request"]["command"] = "напоминания на сутки"
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"http://localhost:{port}/alice",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read())
            text = result.get("response", {}).get("text", "")
            rprint(f"  Ответ (сутки): [bold]{text!r}[/bold]")
    except Exception:
        pass


def check_station(env: dict) -> None:
    console.rule("[bold cyan]Яндекс Станция (локальная сеть)")

    ip = env.get("YANDEX_STATION_IP", "")
    token = env.get("YANDEX_STATION_TOKEN", "")

    if not ip:
        rprint("[dim]YANDEX_STATION_IP не задан — пропускаю[/dim]")
        return

    # TCP ping
    try:
        sock = socket.create_connection((ip, 1961), timeout=3)
        sock.close()
        rprint(f"[green]✓[/green] {ip}:1961 доступен")
    except Exception as e:
        rprint(f"[red]✗[/red] {ip}:1961 недоступен: {e}")
        rprint("  → Проверьте IP и что станция в той же сети")
        return

    if not token:
        rprint("[yellow]  YANDEX_STATION_TOKEN не задан — запустите station_token.py[/yellow]")
        return

    # TLS handshake
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        sock = socket.create_connection((ip, 1961), timeout=3)
        tls = ctx.wrap_socket(sock, server_hostname=ip)
        tls.close()
        rprint("[green]✓[/green] TLS handshake успешен")
        rprint("[dim]  WebSocket и токен проверяются только при реальном срабатывании[/dim]")
    except Exception as e:
        rprint(f"[red]✗[/red] TLS ошибка: {e}")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"

    env = load_env()

    if mode in ("all", "env"):
        check_env(env)

    if mode in ("all", "todoist"):
        check_todoist(env)

    if mode in ("all", "webhook"):
        check_webhook(env)

    if mode in ("all", "station"):
        check_station(env)

    console.rule()


if __name__ == "__main__":
    main()

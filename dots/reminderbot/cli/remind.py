#!/usr/bin/env python3
"""CLI client for ReminderBot API. Run from any directory."""

import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

API_URL = os.getenv("API_URL", "http://localhost:8000")
API_KEY = os.getenv("API_KEY", "")


def _headers():
    return {"X-API-Key": API_KEY}


def cmd_add(name: str, remind_at: str):
    r = httpx.post(
        f"{API_URL}/reminders",
        json={"name": name, "remind_at": remind_at},
        headers=_headers(),
    )
    if r.status_code == 201:
        d = r.json()
        print(f"Added #{d['id']}: {d['name']}  ({d['remind_at']})")
    else:
        print(f"Error {r.status_code}: {r.text}", file=sys.stderr)
        sys.exit(1)


def cmd_list(page: int = 0):
    r = httpx.get(f"{API_URL}/reminders", params={"page": page}, headers=_headers())
    if r.status_code != 200:
        print(f"Error {r.status_code}: {r.text}", file=sys.stderr)
        sys.exit(1)
    d = r.json()
    if not d["reminders"]:
        print("No active reminders.")
        return
    print(f"Page {d['page'] + 1}/{d['total_pages']}  (total: {d['total']})")
    for rem in d["reminders"]:
        print(f"  #{rem['id']}  {rem['name']}  —  {rem['remind_at']}")


def cmd_delete(reminder_id: int):
    r = httpx.delete(f"{API_URL}/reminders/{reminder_id}", headers=_headers())
    if r.status_code == 200:
        print(f"Deleted #{reminder_id}")
    elif r.status_code == 404:
        print(f"Reminder #{reminder_id} not found", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"Error {r.status_code}: {r.text}", file=sys.stderr)
        sys.exit(1)


def usage():
    print(
        "Usage:\n"
        '  remind add "<name>" "<DD.MM.YYYY HH:MM>"\n'
        "  remind list [page]\n"
        "  remind delete <id>"
    )
    sys.exit(1)


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        usage()

    match args[0]:
        case "add":
            if len(args) < 3:
                usage()
            cmd_add(args[1], args[2])
        case "list":
            cmd_list(int(args[1]) if len(args) > 1 else 0)
        case "delete" | "del":
            if len(args) < 2:
                usage()
            cmd_delete(int(args[1]))
        case _:
            usage()

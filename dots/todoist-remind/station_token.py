#!/usr/bin/env python3
"""Get Yandex Station local JWT for proactive TTS.

Run once to set up, and again whenever the token stops working:
  python3 ~/.local/share/todoist-remind/station_token.py

Saves YANDEX_OAUTH_TOKEN and YANDEX_STATION_TOKEN to
~/.local/share/todoist-remind/.env
"""

import json
import sys
import urllib.request
import urllib.error
from pathlib import Path

ENV_FILE = Path.home() / ".local/share/todoist-remind/.env"

# Standard Yandex Smart Home OAuth client — used by the community
# (same as Home Assistant Yandex Smart Home integration).
OAUTH_URL = (
    "https://oauth.yandex.ru/authorize"
    "?response_type=token"
    "&client_id=c0ebe342af7d48fbbbfcf2d2eedb8f9e"
)
QUASAR = "https://quasar.yandex.net"


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


def set_env_key(key: str, value: str) -> None:
    content = ENV_FILE.read_text() if ENV_FILE.exists() else ""
    lines = content.splitlines()
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("#") or "=" not in s:
            continue
        if s.split("=", 1)[0].strip() == key:
            lines[i] = f"{key}={value}"
            ENV_FILE.write_text("\n".join(lines) + "\n")
            return
    lines.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(lines) + "\n")


def quasar(path: str, token: str) -> dict:
    req = urllib.request.Request(
        QUASAR + path,
        headers={"Authorization": f"OAuth {token}"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def main() -> None:
    print()
    print("=== Яндекс Станция: получение токена ===")
    print()

    env = load_env()
    oauth_token = env.get("YANDEX_OAUTH_TOKEN", "").strip()

    if not oauth_token:
        print("Шаг 1. Откройте эту ссылку в браузере и войдите в Яндекс:")
        print()
        print(f"  {OAUTH_URL}")
        print()
        print("  После входа браузер перенаправит на страницу с URL вида:")
        print("  https://oauth.yandex.ru/...#access_token=AQAAA...&...")
        print("  Скопируйте значение access_token из адресной строки.")
        print()
        oauth_token = input("Вставьте access_token: ").strip()
        if not oauth_token:
            print("Токен не введён. Выход.")
            sys.exit(1)
        set_env_key("YANDEX_OAUTH_TOKEN", oauth_token)
        print("OAuth-токен сохранён.")

    print()
    print("Запрашиваю список устройств...")
    try:
        data = quasar("/glagol/device_list", oauth_token)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            print(
                "Ошибка 401: OAuth-токен недействителен или истёк.\n"
                f"Удалите строку YANDEX_OAUTH_TOKEN из {ENV_FILE} и запустите скрипт снова."
            )
        else:
            print(f"Ошибка: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Ошибка: {e}")
        sys.exit(1)

    devices = data.get("devices", [])
    # Prefer speakers, but show all if nothing matches
    speakers = [d for d in devices if "station" in d.get("platform", "") or "quasar" in d.get("platform", "")]
    if not speakers:
        speakers = devices
    if not speakers:
        print("Устройства не найдены. Убедитесь, что станция добавлена в аккаунт Яндекса.")
        sys.exit(1)

    print()
    print("Найденные устройства:")
    for i, d in enumerate(speakers, 1):
        print(f"  {i}. {d.get('name', '—')}  ({d.get('platform', '—')})")

    print()
    raw = input(f"Выберите устройство [1–{len(speakers)}]: ").strip()
    try:
        device = speakers[int(raw) - 1]
    except (ValueError, IndexError):
        print("Неверный выбор.")
        sys.exit(1)

    device_id = device.get("id", "")
    platform = device.get("platform", "")
    name = device.get("name", "")

    print(f"\nПолучаю токен для «{name}»...")
    try:
        result = quasar(f"/glagol/token?device_id={device_id}&platform={platform}", oauth_token)
    except Exception as e:
        print(f"Ошибка: {e}")
        sys.exit(1)

    token = result.get("token", "")
    if not token:
        print("Сервер не вернул токен. Попробуйте позже.")
        sys.exit(1)

    set_env_key("YANDEX_STATION_TOKEN", token)
    print(f"Токен сохранён в {ENV_FILE}")
    print()
    print("Последний шаг — добавьте локальный IP станции в .env:")
    print("  YANDEX_STATION_IP=192.168.x.x")
    print()
    print("Найти IP: откройте админку роутера, или выполните:")
    print("  nmap -sn 192.168.1.0/24 | grep -i yandex -A1")


if __name__ == "__main__":
    main()

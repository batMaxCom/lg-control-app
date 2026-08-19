from __future__ import annotations

import os
from pathlib import Path

import flet as ft

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

from app import LGRemoteApp


DEFAULT_PORT = 3000


def _load_env() -> None:
    env_path = Path(__file__).resolve().parent / ".env"
    if load_dotenv is not None:
        load_dotenv(env_path)
        return
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


async def main(page: ft.Page) -> None:
    _load_env()
    prefs = ft.SharedPreferences()

    saved_ip = await prefs.get("lg_remote.tv_ip")
    saved_port = await prefs.get("lg_remote.tv_port")
    saved_mac = await prefs.get("lg_remote.tv_mac")

    env_ip = os.environ.get("TV_IP", "").strip()
    env_port = os.environ.get("TV_SERVER_PORT", "").strip()
    env_mac = os.environ.get("TV_MAC", "").strip()

    tv_ip = str(saved_ip or env_ip or "").strip()
    try:
        tv_port = int(saved_port or env_port or DEFAULT_PORT)
    except (TypeError, ValueError):
        tv_port = DEFAULT_PORT
    tv_mac = str(saved_mac or env_mac or "").strip()

    app = LGRemoteApp(
        page,
        prefs=prefs,
        tv_ip=tv_ip,
        tv_port=tv_port,
        tv_mac=tv_mac,
    )
    app.mount()


if __name__ == "__main__":
    ft.run(main)

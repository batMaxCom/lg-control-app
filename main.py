from __future__ import annotations

import json

import flet as ft

from app import LGRemoteApp


DEFAULT_PORT = 3000


async def main(page: ft.Page) -> None:
    prefs = ft.SharedPreferences()

    saved_ip = await prefs.get("lg_remote.tv_ip")
    saved_port = await prefs.get("lg_remote.tv_port")
    saved_mac = await prefs.get("lg_remote.tv_mac")
    last_ip = await prefs.get("lg_remote.last_tv_ip")
    discovered_tvs_json = await prefs.get("lg_remote.discovered_tvs") or ""
    tv_keys_json = await prefs.get("lg_remote.tv_keys") or ""
    saved_tvs_json = await prefs.get("lg_remote.saved_tvs") or ""

    tv_ip = str(saved_ip or last_ip or "").strip()
    try:
        tv_port = int(saved_port or DEFAULT_PORT)
    except (TypeError, ValueError):
        tv_port = DEFAULT_PORT
    tv_mac = str(saved_mac or "").strip()

    app = LGRemoteApp(
        page,
        prefs=prefs,
        tv_ip=tv_ip,
        tv_port=tv_port,
        tv_mac=tv_mac,
        discovered_tvs_json=discovered_tvs_json,
        tv_keys_json=tv_keys_json,
        saved_tvs_json=saved_tvs_json,
    )
    app.mount()


if __name__ == "__main__":
    ft.run(main)

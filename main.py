import json
import os
from pathlib import Path

import flet as ft

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - tiny built-in fallback
    load_dotenv = None

from all_commands import commands, TAG_ICONS, InputControl
from tv_client import TVClient

TV_SERVER_PORT = 3000
WS_URL = ""


def _load_env() -> None:
    """Load .env next to this file. Uses python-dotenv if available."""
    if load_dotenv is not None:
        load_dotenv(Path(__file__).resolve().parent / ".env")
        return
    env_file = Path(__file__).resolve().parent / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _tv_target_from_env() -> tuple[str | None, int | None]:
    """Return (host, port) of the TV from .env, or (None, None)."""
    ip = os.environ.get("TV_IP", "").strip()
    if not ip:
        return None, None
    port = int(os.environ.get("TV_SERVER_PORT", "").strip() or TV_SERVER_PORT)
    return ip, port


def main(page: ft.Page):
    page.title = "LG Remote"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 0
    page.window.width = 400
    page.window.height = 860
    page.window.min_width = 320
    page.window.min_height = 480

    global WS_URL
    _load_env()
    tv_host, tv_port = _tv_target_from_env()
    WS_URL = f"ws://{tv_host}:{tv_port}" if tv_host else ""
    tv_available = bool(tv_host)

    status_text = ft.Text("Stopped", size=12)

    ws_client: TVClient | None = None
    if tv_host:
        ws_client = TVClient(ip=tv_host, port=tv_port)

    # ── статус вкладок: при входе и после каждой команды ────────────────────
    STATUS_QUERIES = {
        "Питание": [],
        "Звук": [
            ("Уровень / звук", "ssap://audio/getStatus", {}),
            ("Аудиовыход", "ssap://audio/getSoundOutput", {}),
        ],
        "Каналы": [
            ("Список каналов", "ssap://tv/getChannelList", {}),
        ],
        "Приложения": [
            ("Список приложений", "ssap://com.webos.applicationManager/listApps", {}),
        ],
        "Входы": [
            ("Список входов", "ssap://tv/getExternalInputList", {}),
        ],
    }

    status_texts: dict[str, list] = {}
    _active_tag = ["Питание"]
    power_status = ft.Text("…", size=11, selectable=True, expand=True)

    def _fmt_status(resp: dict) -> str:
        if resp.get("type") != "response":
            err = resp.get("error")
            if isinstance(err, dict):
                msg = err.get("message", resp.get("type"))
            elif err:
                msg = err
            else:
                msg = resp.get("type")
            return "ошибка: " + str(msg)
        p = resp.get("payload") or {}
        if p.get("state"):
            return str(p["state"])
        if p.get("modelName"):
            return f"Включён ({p.get('modelName', '?')})"
        if "volume" in p:
            muted = p.get("muted", p.get("mute"))
            parts = [f"громкость {p['volume']}"]
            if muted is not None:
                parts.append("звук выкл" if muted else "звук вкл")
            return ", ".join(parts)
        if "soundOutput" in p:
            return str(p["soundOutput"])
        if "channelList" in p:
            return f"{len(p['channelList'])} каналов"
        if "apps" in p:
            return f"{len(p['apps'])} приложений"
        if "devices" in p:
            return f"{len(p['devices'])} входов"
        return json.dumps(p, ensure_ascii=False)[:120]

    def build_status_panel(tag: str):
        if tag == "Питание":
            return ft.Column(
                spacing=1,
                controls=[
                    ft.Text("Статус", size=11, weight=ft.FontWeight.W_600),
                    ft.Row(spacing=6, controls=[
                        ft.Text("Состояние", size=11, opacity=0.7, width=150),
                        power_status,
                    ]),
                    ft.Divider(height=1, thickness=1),
                ],
            )
        queries = STATUS_QUERIES.get(tag)
        if not queries:
            return None
        texts, rows = [], []
        for label, _uri, _payload in queries:
            t = ft.Text("…", size=11, selectable=True, expand=True)
            texts.append(t)
            rows.append(ft.Row(spacing=6, controls=[
                ft.Text(label, size=11, opacity=0.7, width=150),
                t,
            ]))
        status_texts[tag] = texts
        return ft.Column(
            spacing=1,
            controls=[
                ft.Text("Статус", size=11, weight=ft.FontWeight.W_600),
                *rows,
                ft.Divider(height=1, thickness=1),
            ],
        )

    def refresh_status(tag: str) -> None:
        queries = STATUS_QUERIES.get(tag)
        texts = status_texts.get(tag)
        if not queries or texts is None or ws_client is None:
            return
        for t in texts:
            t.value = "…"
        page.update()

        def work():
            for i, (_label, uri, payload) in enumerate(queries):
                texts[i].value = _fmt_status(_send(uri, payload))
            page.update()

        page.run_thread(work)

    def set_active_tag(tag: str) -> None:
        _active_tag[0] = tag
        refresh_status(tag)
        if tag == "Приложения":
            page.run_thread(load_apps)
        elif tag == "Входы":
            page.run_thread(load_inputs)

    def _send(uri: str, payload: dict) -> dict:
        """Send a command to the TV over WebSocket."""
        if ws_client is not None and ws_client.is_open():
            try:
                return ws_client.request(uri, payload)
            except Exception as ex:
                return {"type": "error", "error": {"code": "ws", "message": str(ex)}}
        return {"type": "error", "error": {"code": "closed", "message": "ТВ не подключено"}}

    def send_command(uri: str, payload: dict) -> dict:
        data = _send(uri, payload)
        status = "OK" if data.get("type") == "response" else "ERR"
        print(f"[CMD] {uri} [{status}]")
        refresh_status(_active_tag[0])
        return data

    # ── Приложения: сетка иконок ───────────────────────────────────────────
    apps_grid = ft.GridView(
        expand=True,
        runs_count=4,
        max_extent=96,
        spacing=6,
        run_spacing=6,
    )
    apps_status = ft.Text("…", size=11, selectable=True)

    def load_apps():
        apps_grid.controls.clear()
        apps_grid.controls.append(ft.Text("Загрузка…", size=11))
        page.update()
        if ws_client is None:
            return
        resp = _send("ssap://com.webos.applicationManager/listLaunchPoints", {})
        apps_grid.controls.clear()
        if resp.get("type") != "response":
            apps_grid.controls.append(ft.Text(_fmt_status(resp), size=11))
            page.update()
            return
        apps = (resp.get("payload") or {}).get("launchPoints") or []
        for a in apps:
            app_id = a.get("id")
            title = (a.get("title") or app_id or "").strip()
            icon = a.get("largeIcon") or a.get("icon") or a.get("smallIcon")
            img = (ft.Image(src=icon, width=52, height=52, fit=ft.BoxFit.CONTAIN)
                   if icon else ft.Icon(ft.Icons.APPS, size=48, color=ft.Colors.WHITE))
            tile = ft.Column(
                spacing=2,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    img,
                    ft.Text(title, size=9, width=88, max_lines=2,
                            text_align=ft.TextAlign.CENTER, overflow=ft.TextOverflow.ELLIPSIS),
                ],
            )
            apps_grid.controls.append(
                ft.GestureDetector(
                    content=tile,
                    on_tap=lambda e, i=app_id: send_command("ssap://system.launcher/launch", {"id": i}),
                )
            )
        apps_status.value = f"{len(apps)} приложений"
        page.update()

    # ── Входы: выбор входа ──────────────────────────────────────────────────
    inputs_dd = ft.Dropdown(
        label="Входы",
        hint_text="Выберите вход",
        expand=True,
        on_select=lambda e: switch_input(e.control.value),
    )

    def switch_input(input_id: str) -> None:
        if input_id:
            send_command("ssap://tv/switchInput", {"inputId": input_id})

    def load_inputs():
        if ws_client is None:
            return
        resp = _send("ssap://tv/getExternalInputList", {})
        devices = (resp.get("payload") or {}).get("devices") or []
        inputs_dd.options = [
            ft.DropdownOption(key=d.get("id", ""), text=d.get("label") or d.get("id") or "?")
            for d in devices
        ]
        page.update()

    def _connect_tv():
        if ws_client is None:
            return
        ok = ws_client.connect(timeout=15)
        if ok:
            status_text.value = "Running"
            power_status.value = "Включён"
            print("[Server] подключено")
            if ws_client.connect_pointer():
                print("[Input] pointer socket подключён")
            else:
                print("[Input] pointer socket недоступен — включите «Mobile TV On» в настройках ТВ")
            set_active_tag(_active_tag[0])
        else:
            status_text.value = "Stopped"
            power_status.value = "Отключён"
            print("[Server] не удалось подключиться")
        page.update()

    def _on_client_state(client):
        if client.paired:
            status_text.value = "Running"
            power_status.value = "Включён"
            if not client.pointer_connected:
                page.run_thread(client.connect_pointer)
        elif client.connected:
            status_text.value = "Pairing"
            power_status.value = "Ожидание подтверждения на ТВ…"
        else:
            status_text.value = "Stopped"
            power_status.value = "Отключён"
        page.update()

    if ws_client is not None:
        ws_client.on_state_change = _on_client_state

    def _input_button(name: str):
        if ws_client is not None and ws_client.pointer_connected:
            ws_client.button(name)
            print(f"[Input] {name}")
        else:
            print(f"[Input] {name}: pointer socket не подключён")
        page.update()

    def _input_click(e):
        if ws_client is not None and ws_client.pointer_connected:
            ws_client.click()
            print("[Input] click")
        else:
            print("[Input] click: pointer socket не подключён")
        page.update()

    def _pointer_mean(kind: str):
        label = "dx dy" if kind == "scroll" else "x y"
        tf = ft.TextField(label=f"Укажите {label}", hint_text="10 20", autofocus=True)

        def submit(dlg):
            try:
                a, b = [int(v) for v in tf.value.strip().replace(",", " ").split()][:2]
                if ws_client is not None and ws_client.pointer_connected:
                    (ws_client.scroll(a, b) if kind == "scroll" else ws_client.move(a, b))
                    print(f"[Input] {kind}: {a} {b}")
                else:
                    print(f"[Input] {kind}: pointer socket не подключён")
            except Exception:
                pass
            dlg.open = False
            page.update()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(kind.title()),
            content=ft.Row(controls=[tf, ft.IconButton(ft.Icons.SEND, on_click=lambda e: submit(dlg))]),
            actions=[ft.TextButton("Отмена", on_click=lambda e: close_dialog(dlg))],
        )
        page.overlay.append(dlg)
        page.update()
        dlg.open = True
        page.update()

    def close_dialog(dlg):
        dlg.open = False
        page.update()

    AUDIO_OUTPUTS = [
        ("tv_speaker", "tv_speaker — встроенные динамики ТВ"),
        ("external_optical", "external_optical — оптический выход (Digital Optical)"),
        ("external_arc", "external_arc — подключение по HDMI ARC / eARC"),
        ("bt_soundbar", "bt_soundbar — беспроводная аудиосистема или наушники через Bluetooth"),
        ("headphone", "headphone — проводные наушники (разъем 3.5 мм Mini-Jack)"),
        ("tv_external_speaker", "tv_external_speaker — одновременный вывод (Динамики ТВ + Оптика)"),
        ("lineout", "lineout — линейный аудиовыход"),
    ]

    def show_audio_output_dialog():
        dd = ft.Dropdown(
            label="Аудиовыход",
            options=[ft.DropdownOption(key=key, text=text) for key, text in AUDIO_OUTPUTS],
            expand=True,
        )

        def submit(e):
            if dd.value:
                send_command("ssap://audio/changeSoundOutput", {"output": dd.value})
            dlg.open = False
            page.update()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Установить аудиовыход"),
            content=dd,
            actions=[
                ft.TextButton("Применить", on_click=submit),
                ft.TextButton("Отмена", on_click=lambda e: close_dialog(dlg)),
            ],
        )
        page.overlay.append(dlg)
        page.update()
        dlg.open = True
        page.update()

    def show_input_dialog(title: str, uri: str, field_label: str, field_hint: str, payload_fn=None):
        tf = ft.TextField(label=field_label, hint_text=field_hint, expand=True, autofocus=True,
                          keyboard_type=ft.KeyboardType.NUMBER if payload_fn else None)
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(title),
            content=ft.Row(controls=[tf, ft.IconButton(ft.Icons.SEND, on_click=lambda e: submit_dialog(e, uri, tf, payload_fn))]),
            actions=[ft.TextButton("Отмена", on_click=lambda e: close_dialog(dlg))],
        )
        page.overlay.append(dlg)
        page.update()
        dlg.open = True
        page.update()

    def submit_dialog(e, uri, tf: ft.TextField, payload_fn=None):
        text = tf.value.strip()
        if text:
            if payload_fn:
                payload = payload_fn(text)
            elif "open" in uri:
                payload = {"target": text}
            else:
                payload = {"text": text}
            send_command(uri, payload)
        dlg = e.control.parent.parent
        dlg.open = False
        page.update()

    def build_command_button(name, uri, payload):
        if uri == "ssap://system.launcher/open":
            return ft.Button(
                name,
                on_click=lambda e, u=uri: show_input_dialog("Открыть браузер по URL", u, "URL", "https://example.com"),
            )
        elif uri == "ssap://audio/changeSoundOutput":
            return ft.Button(name, on_click=lambda e: show_audio_output_dialog())
        elif uri == "ssap://audio/setVolume":
            volume_slider = ft.Slider(min=0, max=100, divisions=100, value=15, label="{value}", expand=True)
            volume_slider.on_change_end = lambda e, u=uri: send_command(u, {"volume": int(e.control.value)})
            return ft.Row(
                controls=[ft.Button(name, disabled=True), volume_slider],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        elif uri == "ssap://com.webos.service.ime/insertText":
            return ft.Button(
                name,
                on_click=lambda e, u=uri: show_input_dialog("Ввести текст", u, "Текст", "Введите текст"),
            )
        elif uri == "ssap://tv/openChannel":
            return ft.Button(
                name,
                on_click=lambda e, u=uri: show_input_dialog(
                    "Установить канал", u, "Номер канала", "1",
                    payload_fn=lambda t: {"channelId": t},
                ),
            )
        else:
            return ft.Button(
                name,
                on_click=lambda e, u=uri, p=payload: send_command(u, p),
            )

    def build_commands_view():
        tags: dict[str, list] = {}
        for name, uri, payload, tag in commands:
            tags.setdefault(tag, []).append((name, uri, payload))

        tabs = []
        views = []
        for tag, items in tags.items():
            panel = build_status_panel(tag)
            controls = [build_command_button(name, uri, payload) for name, uri, payload in items]
            tabs.append(ft.Tab(label=tag, icon=TAG_ICONS.get(tag)))

            if tag == "Приложения":
                views.append(ft.Container(
                    content=ft.Column(
                        expand=True,
                        spacing=4,
                        controls=[
                            ft.Row(spacing=6, controls=[
                                ft.Text("Приложения", size=11, weight=ft.FontWeight.W_600),
                                ft.Container(expand=True),
                                ft.IconButton(ft.Icons.REFRESH, icon_size=16,
                                              on_click=lambda e: page.run_thread(load_apps)),
                            ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                            ft.Container(content=apps_grid, expand=True),
                            ft.Text("Запуск по клику на иконку", size=10, opacity=0.6),
                        ],
                    ),
                    padding=8,
                    expand=True,
                ))
            elif tag == "Входы":
                views.append(ft.Container(
                    content=ft.Column(
                        expand=True,
                        spacing=4,
                        controls=[
                            *(panel.controls if panel else []),
                            inputs_dd,
                            *controls,
                        ],
                    ),
                    padding=8,
                    expand=True,
                ))
            else:
                lv_controls = ([panel] if panel else []) + controls
                views.append(ft.Container(
                    content=ft.ListView(controls=lv_controls, spacing=4, expand=True),
                    padding=8,
                    expand=True,
                ))

        tag_order = [*tags.keys(), "Input"]

        def key_button(name: str):
            line = dict(InputControl.INPUT_COMMANDS[name]["command"])
            return ft.Button(InputControl.INPUT_COMMANDS[name]["label"],
                             on_click=lambda e, n=line["name"]: _input_button(n))

        def input_section(title: str, controls: list):
            return ft.Column(
                spacing=4,
                controls=[ft.Text(title, size=11, weight=ft.FontWeight.W_600), *controls],
            )

        ic = InputControl.INPUT_COMMANDS
        ime = InputControl.COMMANDS
        nav = ["home", "back", "menu", "info", "exit", "dash", "cc", "mute"]
        digits = [f"num_{d}" for d in range(1, 10)] + ["num_0", "asterisk"]
        colors = ["red", "green", "yellow", "blue"]
        media = ["play", "pause", "stop", "rewind", "fastforward"]
        vol_chan = ["volume_up", "volume_down", "channel_up", "channel_down"]

        input_rows = [
            input_section("Навигация", [
                ft.Row(spacing=6, controls=[key_button(k) for k in nav]),
            ]),
            input_section("Цифры", [
                ft.Row(spacing=6, controls=[key_button(k) for k in digits[:9]]),
                ft.Row(spacing=6, controls=[key_button(k) for k in digits[9:]]),
            ]),
            input_section("Цвета", [
                ft.Row(spacing=6, controls=[key_button(k) for k in colors]),
            ]),
            input_section("Медиа", [
                ft.Row(spacing=6, controls=[key_button(k) for k in media]),
            ]),
            input_section("Громкость / Каналы", [
                ft.Row(spacing=6, controls=[key_button(k) for k in vol_chan]),
            ]),
            input_section("Указатель", [
                ft.Row(spacing=6, controls=[
                    ft.Button(ic["click"]["label"], on_click=_input_click),
                    ft.Button(ic["move"]["label"], on_click=lambda e: _pointer_mean("move")),
                    ft.Button(ic["scroll"]["label"], on_click=lambda e: _pointer_mean("scroll")),
                    ft.Button(ic["ok"]["label"], on_click=lambda e: (
                        _input_button("ENTER") if (ws_client is not None and ws_client.pointer_connected)
                        else send_command(ime["enter"]["uri"], {})
                    )),
                ]),
            ]),
            input_section("Ввод (IME)", [
                ft.Row(spacing=6, controls=[
                    ft.Button(ime["type"]["label"], on_click=lambda e: show_input_dialog(
                        ime["type"]["label"], ime["type"]["uri"], "Текст", "Введите текст",
                    )),
                    ft.Button(ime["delete"]["label"], on_click=lambda e: show_input_dialog(
                        ime["delete"]["label"], ime["delete"]["uri"],
                        "Кол-во", "1", payload_fn=lambda t: {"count": int(t)},
                    )),
                ]),
            ]),
        ]

        tabs.append(ft.Tab(label="Input", icon=ft.Icons.KEYBOARD))
        views.append(ft.Container(
            content=ft.ListView(controls=input_rows, spacing=10, expand=True),
            padding=8,
            expand=True,
        ))

        def on_tab_change(e):
            idx = e.control.selected_index
            if 0 <= idx < len(tag_order):
                set_active_tag(tag_order[idx])

        tab_bar = ft.TabBar(tabs=tabs, expand=True)
        tab_view = ft.TabBarView(controls=views, expand=True)
        tabs_widget = ft.Tabs(
            content=ft.Column(controls=[tab_bar, tab_view], expand=True),
            length=len(views),
            expand=True,
            on_change=on_tab_change,
        )
        return ft.Column(
            expand=True,
            spacing=0,
            controls=[
                ft.Row(controls=[
                    ft.Text("LG Remote", size=18, weight=ft.FontWeight.W_600),
                    ft.Container(expand=True),
                    status_text,
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Divider(height=1, thickness=1),
                ft.Container(
                    expand=True,
                    padding=ft.Padding(left=0, right=0, top=4, bottom=4),
                    content=tabs_widget,
                ),
            ],
        )

    page.add(ft.SafeArea(build_commands_view()))

    if tv_host and ws_client is not None:
        page.run_thread(_connect_tv)


if __name__ == "__main__":
    ft.run(main)
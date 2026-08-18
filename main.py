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

    log = ft.ListView(expand=True, spacing=2, auto_scroll=True)
    status_text = ft.Text("Stopped", size=12)

    ws_client: TVClient | None = None
    if tv_host:
        ws_client = TVClient(ip=tv_host, port=tv_port)

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
        log.controls.append(
            ft.Text(f">>> {uri}  [{status}]\n    {json.dumps(data, ensure_ascii=False, indent=2)}", size=11)
        )
        page.update()
        return data

    def _connect_tv():
        if ws_client is None:
            return
        ok = ws_client.connect(timeout=15)
        if ok:
            status_text.value = "Running"
            log.controls.append(ft.Text(f"[Server] подключено: {WS_URL}"))
            if ws_client.connect_pointer():
                log.controls.append(ft.Text("[Input] pointer socket подключён"))
            else:
                log.controls.append(
                    ft.Text("[Input] pointer socket недоступен — включите «Mobile TV On» в настройках ТВ")
                )
        else:
            status_text.value = "Stopped"
            log.controls.append(ft.Text(f"[Server] не удалось подключиться к {WS_URL}"))
        page.update()

    def _on_client_state(client):
        if client.paired:
            status_text.value = "Running"
            if not client.pointer_connected:
                page.run_thread(client.connect_pointer)
        elif client.connected:
            status_text.value = "Pairing"
        else:
            status_text.value = "Stopped"
        page.update()

    if ws_client is not None:
        ws_client.on_state_change = _on_client_state

    def _input_button(name: str):
        if ws_client is not None and ws_client.pointer_connected:
            ws_client.button(name)
            log.controls.append(ft.Text(f"[Input] {name}"))
        else:
            log.controls.append(ft.Text(f"[Input] {name}: pointer socket не подключён"))
        page.update()

    def _input_click(e):
        if ws_client is not None and ws_client.pointer_connected:
            ws_client.click()
            log.controls.append(ft.Text("[Input] click"))
        else:
            log.controls.append(ft.Text("[Input] click: pointer socket не подключён"))
        page.update()

    def _pointer_mean(kind: str):
        label = "dx dy" if kind == "scroll" else "x y"
        tf = ft.TextField(label=f"Укажите {label}", hint_text="10 20", autofocus=True)

        def submit(dlg):
            try:
                a, b = [int(v) for v in tf.value.strip().replace(",", " ").split()][:2]
                if ws_client is not None and ws_client.pointer_connected:
                    (ws_client.scroll(a, b) if kind == "scroll" else ws_client.move(a, b))
                    log.controls.append(ft.Text(f"[Input] {kind}: {a} {b}"))
                else:
                    log.controls.append(ft.Text(f"[Input] {kind}: pointer socket не подключён"))
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
            controls = [build_command_button(name, uri, payload) for name, uri, payload in items]
            tabs.append(ft.Tab(label=tag, icon=TAG_ICONS.get(tag)))
            views.append(ft.Container(
                content=ft.ListView(controls=controls, spacing=4, expand=True),
                padding=8,
                expand=True,
            ))

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

        page_h = int(page.height) if page.height else 860
        header_h = 29
        avail = max(page_h - header_h, 400)
        top_h = avail // 2
        bottom_h = avail - top_h

        tab_bar = ft.TabBar(tabs=tabs, expand=True)
        tab_view = ft.TabBarView(controls=views, expand=True)
        tabs_widget = ft.Tabs(
            content=ft.Column(controls=[tab_bar, tab_view], expand=True),
            length=len(views),
            height=top_h - 1,
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
                    height=top_h,
                    content=tabs_widget,
                    border=ft.Border(
                        bottom=ft.BorderSide(1, ft.Colors.with_opacity(0.12, ft.Colors.WHITE))
                    ),
                ),
                ft.Container(
                    height=bottom_h,
                    padding=ft.Padding(left=8, right=8, top=4, bottom=4),
                    border=ft.Border(
                        top=ft.BorderSide(1, ft.Colors.with_opacity(0.12, ft.Colors.WHITE))
                    ),
                    content=ft.Column(
                        expand=True,
                        spacing=2,
                        controls=[
                            ft.Text("Log", size=11, weight=ft.FontWeight.W_600),
                            log,
                        ],
                    ),
                ),
            ],
        )

    page.add(ft.SafeArea(build_commands_view()))

    if tv_host and ws_client is not None:
        page.run_thread(_connect_tv)


if __name__ == "__main__":
    ft.run(main)
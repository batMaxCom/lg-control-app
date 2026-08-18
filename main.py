import json
import threading

import flet as ft
import requests
import uvicorn

from all_commands import commands, TAG_ICONS
from mock_server import app

API_PORT = 8000
API_URL = f"http://127.0.0.1:{API_PORT}"

server: uvicorn.Server | None = None
server_thread: threading.Thread | None = None


def run_server():
    global server
    config = uvicorn.Config(app, host="127.0.0.1", port=API_PORT, log_level="info")
    server = uvicorn.Server(config)
    server.run()


def main(page: ft.Page):
    page.title = "Mock webOS TV"
    page.window.width = 700
    page.window.height = 800

    status = ft.Text("Server stopped", weight=ft.FontWeight.BOLD)
    btn_start = ft.Button("Start Server")
    btn_stop = ft.Button("Stop Server", disabled=True)
    log = ft.ListView(expand=True, spacing=2, auto_scroll=True)

    def send_command(uri: str, payload: dict):
        try:
            resp = requests.post(f"{API_URL}/ssap", json={"uri": uri, "payload": payload}, timeout=3)
            data = resp.json()
            color = ft.Colors.GREEN if data.get("type") == "response" else ft.Colors.RED
            log.controls.append(
                ft.Text(f">>> {uri}\n    {json.dumps(data, ensure_ascii=False, indent=2)}", color=color, size=11)
            )
        except Exception as ex:
            log.controls.append(ft.Text(f">>> {uri}\n    ERROR: {ex}", color=ft.Colors.RED, size=11))
        page.update()

    def on_start(e):
        global server_thread
        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        status.value = f"Running on {API_URL}"
        status.color = ft.Colors.GREEN
        btn_start.disabled = True
        btn_stop.disabled = False
        page.update()

    def on_stop(e):
        if server:
            server.should_exit = True
        status.value = "Server stopped"
        status.color = None
        btn_start.disabled = False
        btn_stop.disabled = True
        page.update()

    btn_start.on_click = on_start
    btn_stop.on_click = on_stop

    def show_input_dialog(title: str, uri: str, field_label: str, field_hint: str, payload_fn=None):
        tf = ft.TextField(label=field_label, hint_text=field_hint, expand=True, autofocus=True, keyboard_type=ft.KeyboardType.NUMBER if payload_fn else None)
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

    def close_dialog(dlg):
        dlg.open = False
        page.update()

    def build_command_button(name, uri, payload):
        if uri == "ssap://system.launcher/open":
            return ft.Button(
                name,
                style=ft.ButtonStyle(padding=8),
                on_click=lambda e, u=uri: show_input_dialog("Открыть браузер по URL", u, "URL", "https://example.com"),
            )
        elif uri == "ssap://audio/setVolume":
            volume_slider = ft.Slider(min=0, max=100, divisions=100, value=15, label="{value}", expand=True)
            volume_slider.on_change_end = lambda e, u=uri: send_command(u, {"volume": int(e.control.value)})
            return ft.Row(
                controls=[
                    ft.Button(name, style=ft.ButtonStyle(padding=8), disabled=True),
                    volume_slider,
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        elif uri == "ssap://com.webos.service.ime/insertText":
            return ft.Button(
                name,
                style=ft.ButtonStyle(padding=8),
                on_click=lambda e, u=uri: show_input_dialog("Ввести текст", u, "Текст", "Введите текст"),
            )
        elif uri == "ssap://tv/openChannel":
            return ft.Button(
                name,
                style=ft.ButtonStyle(padding=8),
                on_click=lambda e, u=uri: show_input_dialog(
                    "Установить канал", u, "Номер канала", "1",
                    payload_fn=lambda t: {"channelId": t},
                ),
            )
        else:
            return ft.Button(
                name,
                style=ft.ButtonStyle(padding=8),
                on_click=lambda e, u=uri, p=payload: send_command(u, p),
            )

    tags: dict[str, list] = {}
    for name, uri, payload, tag in commands:
        tags.setdefault(tag, []).append((name, uri, payload))

    tab_bar_tabs = []
    tab_views = []
    for tag, items in tags.items():
        icon = TAG_ICONS.get(tag, ft.Icons.CIRCLE)
        controls = []
        for name, uri, payload in items:
            controls.append(build_command_button(name, uri, payload))
        tab_bar_tabs.append(ft.Tab(label=tag, icon=icon))
        tab_views.append(ft.Container(
            content=ft.ListView(controls=controls, spacing=4, expand=True),
            padding=8,
        ))

    tab_bar = ft.TabBar(tabs=tab_bar_tabs, expand=True)
    tab_view = ft.TabBarView(controls=tab_views, expand=True)
    tabs_widget = ft.Tabs(
        content=ft.Column(controls=[tab_bar, tab_view], expand=True),
        length=len(tab_views),
        expand=True,
    )

    page.add(
        ft.Column(
            expand=True,
            controls=[
                ft.Row(controls=[btn_start, btn_stop, status]),
                ft.Divider(),
                tabs_widget,
                ft.Divider(),
                ft.Text("Log", weight=ft.FontWeight.BOLD),
                ft.Container(content=log, expand=True, border=ft.Border.all(1, ft.Colors.OUTLINE), border_radius=8, padding=8),
            ],
        )
    )

ft.run(main)

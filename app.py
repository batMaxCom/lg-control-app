from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from typing import Any

import flet as ft

from all_commands import (
    ApplicationControl,
    AudioControl,
    ChannelControl,
    InputControl,
    MediaControl,
    PowerControl,
    SourceControl,
    SystemControl,
)
from app_state import RemoteState
from components import (
    ambient_background,
    bottom_nav_item,
    color_key,
    glass_panel,
    icon_disc,
    pill_button,
    remote_circle,
    section_title,
    status_pair,
    tab_item,
)
from theme import C, S, active_gradient, border, glass_gradient, shadow
from tv_client import TVClient, wake_on_lan
from ssdp_discovery import discover_lg_tvs


TAB_DEFS = [
    ("remote", "Remote", ft.Icons.DASHBOARD),
    ("touch", "Тачпад", ft.Icons.TOUCH_APP),
    ("power", "Питание", ft.Icons.POWER_SETTINGS_NEW),
    ("sound", "Звук", ft.Icons.VOLUME_UP),
    ("media", "Медиа", ft.Icons.PLAY_CIRCLE),
    ("channels", "Каналы", ft.Icons.TV),
    ("apps", "Приложения", ft.Icons.APPS),
    ("system", "Система", ft.Icons.SETTINGS),
    ("inputs", "Входы", ft.Icons.INPUT),
]


AUDIO_OUTPUTS = [
    ("tv_speaker", "Встроенные динамики ТВ"),
    ("external_optical", "Оптический выход (Digital Optical)"),
    ("external_arc", "HDMI ARC / eARC"),
    ("bt_soundbar", "Bluetooth-аудиосистема / наушники"),
    ("headphone", "Проводные наушники (3.5 мм)"),
    ("tv_external_speaker", "Динамики ТВ + внешний выход"),
    ("lineout", "Линейный аудиовыход"),
]


class LGRemoteApp:
    def __init__(
        self,
        page: ft.Page,
        *,
        prefs: ft.SharedPreferences,
        tv_ip: str = "",
        tv_port: int = 3000,
        tv_mac: str = "",
        discovered_tvs_json: str = "",
        tv_keys_json: str = "",
    ) -> None:
        self.page = page
        self.prefs = prefs
        self.state = RemoteState(tv_ip=tv_ip, tv_port=tv_port, tv_mac=tv_mac)
        self.client: TVClient | None = None
        self._monitor_running = True
        self._last_connection_snapshot: tuple[Any, ...] | None = None
        self._discovered_tvs_raw = discovered_tvs_json
        self._tv_keys_raw = tv_keys_json
        self._discovery_cancel: asyncio.Event | None = None
        self._discovery_loop: asyncio.AbstractEventLoop | None = None

        self.header_host = ft.Container()
        self.tabs_host = ft.Container()
        self.content_host = ft.Container(expand=True)
        self.bottom_host = ft.Container()

    # ------------------------------------------------------------------
    # Lifecycle / shell
    # ------------------------------------------------------------------

    def mount(self) -> None:
        self.page.title = "LG Remote"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.padding = 0
        self.page.bgcolor = C.BG

        # Desktop dimensions are only a preview aid. Mobile ignores window sizing.
        try:
            self.page.window.width = 420
            self.page.window.height = 900
            self.page.window.min_width = 340
            self.page.window.min_height = 620
        except Exception:
            pass

        self.state.discovered_tvs = self._load_discovered_tvs()
        self.state.tv_keys = self._load_tv_keys()

        # Restore last successful TV connection if manual IP is empty.
        if not self.state.tv_ip:
            for saved_tv in self.state.discovered_tvs:
                if saved_tv.get("ip") == self.state.last_tv_ip:
                    self.state.tv_ip = saved_tv.get("ip", "")
                    self.state.tv_port = int(saved_tv.get("port", 3000))
                    self.state.tv_mac = saved_tv.get("mac", "")
                    break

        # Refresh SSDP cache on startup. Saved TVs remain available offline.
        self.page.run_thread(self._discover_tvs_worker, True)

        self.page.on_disconnect = self._on_disconnect
        self.page.add(self._build_root())
        self.refresh_view()
        self.page.run_task(self._connection_monitor)

        if self.state.tv_ip:
            self.page.run_thread(self._connect_worker)
        else:
            self.state.connection_stage = "not_configured"
            self.refresh_view()

    def _on_disconnect(self, _e: ft.Event) -> None:
        self._monitor_running = False
        if self.client is not None:
            self.client.close()

    def _build_root(self) -> ft.Control:
        return ft.Stack(
            expand=True,
            controls=[
                ambient_background(),
                ft.SafeArea(
                    expand=True,
                    content=ft.Column(
                        expand=True,
                        spacing=0,
                        controls=[
                            self.header_host,
                            self.tabs_host,
                            ft.Container(
                                expand=True,
                                padding=ft.Padding(
                                    left=S.PAGE_X,
                                    right=S.PAGE_X,
                                    top=12,
                                    bottom=8,
                                ),
                                content=ft.Column(
                                    expand=True,
                                    scroll=ft.ScrollMode.AUTO,
                                    controls=[self.content_host],
                                ),
                            ),
                            self.bottom_host,
                        ],
                    ),
                ),
            ],
        )

    def refresh_view(self) -> None:
        self.header_host.content = self._build_header()
        self.tabs_host.content = self._build_tabs()
        self.content_host.content = self._build_section()
        self.bottom_host.content = self._build_bottom_nav()
        try:
            self.page.update()
        except Exception:
            # The page can already be disconnected while TVClient is shutting down.
            pass

    def _build_header(self) -> ft.Control:
        stage = self.state.connection_stage
        label, color = {
            "connected": ("Подключено", C.GREEN),
            "pairing": ("Подтвердите на ТВ", C.YELLOW),
            "connecting": ("Подключение…", C.BLUE),
            "offline": ("Нет связи", C.RED),
            "not_configured": ("Не настроено", C.TEXT_3),
        }.get(stage, (stage, C.TEXT_3))

        return ft.Container(
            height=S.HEADER_H,
            padding=ft.Padding(left=S.PAGE_X, right=S.PAGE_X),
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Container(width=92),
                    ft.Text(
                        "LG Remote",
                        size=21,
                        color=C.TEXT,
                        weight=ft.FontWeight.W_600,
                    ),
                    ft.Container(
                        width=92,
                        content=ft.Row(
                            spacing=5,
                            alignment=ft.MainAxisAlignment.END,
                            controls=[
                                ft.Container(
                                    width=8,
                                    height=8,
                                    shape=ft.BoxShape.CIRCLE,
                                    bgcolor=color,
                                    shadow=[ft.BoxShadow(blur_radius=8, color=color)],
                                ),
                                ft.Text(label, size=9.5, color=color, max_lines=1),
                            ],
                        ),
                    ),
                ],
            ),
        )

    def _build_tabs(self) -> ft.Control:
        return ft.Container(
            height=S.TABS_H,
            padding=ft.Padding(left=2, right=2),
            content=ft.Column(
                spacing=4,
                controls=[
                    ft.Row(
                        scroll=ft.ScrollMode.AUTO,
                        spacing=3,
                        controls=[
                            tab_item(
                                label=label,
                                icon=icon,
                                active=self.state.active_section == key,
                                on_click=self._section_handler(key, "input"),
                            )
                            for key, label, icon in TAB_DEFS
                        ],
                    ),
                    ft.Container(height=1, bgcolor=C.DIVIDER),
                ],
            ),
        )

    def _build_bottom_nav(self) -> ft.Control:
        defs = [
            ("input", "Ввод", ft.Icons.KEYBOARD, "input"),
            ("activity", "Активность", ft.Icons.SCHEDULE, "activity"),
            ("settings", "Ещё", ft.Icons.MORE_HORIZ, "settings"),
        ]
        return ft.Container(
            height=S.BOTTOM_H + 8,
            padding=ft.Padding(left=10, right=10, bottom=8),
            content=glass_panel(
                ft.Row(
                    spacing=2,
                    controls=[
                        bottom_nav_item(
                            label=label,
                            icon=icon,
                            active=self.state.active_bottom == bottom_key,
                            on_click=self._section_handler(section, bottom_key),
                        )
                        for bottom_key, label, icon, section in defs
                    ],
                ),
                padding=4,
                radius=24,
                height=S.BOTTOM_H - 2,
            ),
        )

    def _section_handler(self, section: str, bottom: str):
        def handler(_e: ft.Event) -> None:
            self.state.active_section = section
            self.state.active_bottom = bottom
            self.refresh_view()
            self._refresh_section_async(section)

        return handler

    def _build_section(self) -> ft.Control:
        builders: dict[str, Callable[[], ft.Control]] = {
            "remote": self._remote_screen,
            "touch": self._touch_screen,
            "power": self._power_screen,
            "sound": self._sound_screen,
            "media": self._media_screen,
            "channels": self._channels_screen,
            "apps": self._apps_screen,
            "system": self._system_screen,
            "inputs": self._inputs_screen,
            "input": self._input_screen,
            "activity": self._activity_screen,
            "settings": self._settings_screen,
        }
        return builders.get(self.state.active_section, self._remote_screen)()

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    async def _connection_monitor(self) -> None:
        while self._monitor_running:
            client = self.client
            snapshot = (
                bool(client and client.connected),
                bool(client and client.paired),
                bool(client and client.pointer_connected),
                self.state.tv_ip,
            )
            if snapshot != self._last_connection_snapshot:
                previous_snapshot = self._last_connection_snapshot
                self._last_connection_snapshot = snapshot
                connected, paired, pointer, ip = snapshot
                self.state.pointer_connected = bool(pointer)
                if not ip:
                    self.state.connection_stage = "not_configured"
                elif connected and paired:
                    self.state.connection_stage = "connected"
                elif connected:
                    self.state.connection_stage = "pairing"
                elif self.state.connection_stage != "connecting":
                    self.state.connection_stage = "offline"
                self.refresh_view()

                if connected and paired and client is not None:
                    if not pointer:
                        self.page.run_thread(self._connect_pointer_worker)
                    # Pairing may complete asynchronously after the WebSocket was
                    # opened. Load the current section on the unpaired -> paired
                    # transition so the user immediately sees real TV data.
                    was_paired = bool(previous_snapshot and previous_snapshot[1])
                    if not was_paired:
                        self.page.run_thread(self._load_section_data, self.state.active_section)
            await asyncio.sleep(0.55)

    def _connect_worker(
        self,
        _e: ft.Event | None = None,
        *,
        ip: str | None = None,
        port: int | None = None,
        mac: str | None = None,
    ) -> None:
        connect_ip = ip if ip is not None else self.state.tv_ip
        connect_port = port if port is not None else self.state.tv_port

        if not connect_ip:
            self.state.connection_stage = "not_configured"
            self.refresh_view()
            return

        self.state.tv_ip = connect_ip
        self.state.tv_port = connect_port
        if mac is not None:
            self.state.tv_mac = mac

        self.state.connection_stage = "connecting"
        self.refresh_view()

        if self.client is not None:
            self.client.close()

        tv_key = self.state.tv_keys.get(connect_ip, "")
        self.client = TVClient(ip=connect_ip, port=connect_port, client_key=tv_key)

        ok = self.client.connect(timeout=18)
        if not ok:
            self.state.connection_stage = "offline"
            self.state.add_activity("Подключение", False, "Не удалось открыть WebSocket")
            self.refresh_view()
            return

        if self.client.paired:
            self.state.connection_stage = "connected"
            self._connect_pointer_worker()
            self.state.add_activity("Подключение", True, connect_ip)
            new_key = self.client.client_key
            if new_key:
                self.state.tv_keys[connect_ip] = new_key
                self._save_tv_keys()
            import asyncio as _aio
            _aio.run(self.prefs.set("lg_remote.last_tv_ip", connect_ip))
            self._load_section_data(self.state.active_section)
        else:
            self.state.connection_stage = "pairing"
            self.state.add_activity("Сопряжение", True, "Ожидание подтверждения на ТВ")
        self.refresh_view()

    def _connect_pointer_worker(self) -> None:
        client = self.client
        if client is None or not client.connected or not client.paired:
            return
        client.connect_pointer(timeout=10)
        self.state.pointer_connected = client.pointer_connected
        self.refresh_view()

    def _reconnect(self, _e: ft.Event | None = None) -> None:
        self.page.run_thread(self._connect_worker)

    def _wake_tv(self, _e: ft.Event | None = None) -> None:
        self.page.run_thread(self._wake_worker)

    def _wake_worker(self) -> None:
        if not self.state.tv_mac:
            self._show_message(
                "Wake-on-LAN",
                "Укажите MAC-адрес телевизора в разделе «Ещё», чтобы включать ТВ, когда WebSocket недоступен.",
            )
            return
        try:
            wake_on_lan(self.state.tv_mac)
            self.state.add_activity("Wake-on-LAN", True, self.state.tv_mac)
            self.state.connection_stage = "connecting"
            self.refresh_view()
            time.sleep(2.0)
            self._connect_worker()
        except Exception as exc:
            self.state.add_activity("Wake-on-LAN", False, str(exc))
            self._show_message("Wake-on-LAN", str(exc))

    def _screen_toggle(self, uri: str, payload: dict[str, Any], label: str) -> None:
        self.page.run_thread(self._screen_toggle_worker, uri, payload, label)

    def _screen_toggle_worker(self, uri: str, payload: dict[str, Any], label: str) -> None:
        client = self.client
        if client is None or not client.is_open() or not client.paired:
            self.state.add_activity(label, False, "Телевизор не подключён")
            self.refresh_view()
            return

        resp = client.request(uri, payload)
        if self._ok(resp):
            self.state.add_activity(label, True)
            self.refresh_view()
            return

        err_text = self._error_text(resp)
        if "404" in err_text:
            self.state.add_activity(label, False, "Метод не поддерживается этим ТВ")
            self.refresh_view()
            self._show_message(
                label,
                "Этот телевизор не поддерживает функцию выключения/включения экрана "
                "без полного выключения.\n\n"
                "Используйте «Выключить телевизор» для полного выключения.",
            )
            return

        self.state.add_activity(label, False, err_text)
        self.refresh_view()

    # ------------------------------------------------------------------
    # Request helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _ok(resp: dict[str, Any]) -> bool:
        return resp.get("type") in {"response", "registered"}

    @staticmethod
    def _error_text(resp: dict[str, Any]) -> str:
        err = resp.get("error")
        if isinstance(err, dict):
            return str(err.get("message") or err.get("code") or "Ошибка")
        if err:
            return str(err)
        return str(resp.get("type") or "Ошибка")

    @staticmethod
    def _pretty_payload(resp: dict[str, Any]) -> str:
        if resp.get("type") != "response":
            return LGRemoteApp._error_text(resp)
        payload = resp.get("payload") or {}
        return json.dumps(payload, ensure_ascii=False, indent=2)[:7000]

    def _request(
        self,
        uri: str,
        payload: dict[str, Any] | None = None,
        *,
        label: str,
        show_response: bool = False,
        after: Callable[[dict[str, Any]], None] | None = None,
        refresh_section: bool = False,
    ) -> None:
        self.page.run_thread(
            self._request_worker,
            uri,
            payload or {},
            label,
            show_response,
            after,
            refresh_section,
        )

    def _request_worker(
        self,
        uri: str,
        payload: dict[str, Any],
        label: str,
        show_response: bool,
        after: Callable[[dict[str, Any]], None] | None,
        refresh_section: bool,
    ) -> None:
        client = self.client
        if client is None or not client.is_open() or not client.paired:
            resp = {
                "type": "error",
                "error": {"code": "closed", "message": "Телевизор не подключён"},
            }
        else:
            resp = client.request(uri, payload)

        ok = self._ok(resp)
        detail = "OK" if ok else self._error_text(resp)
        self.state.add_activity(label, ok, detail)
        self.state.last_response = self._pretty_payload(resp)

        if after is not None:
            try:
                after(resp)
            except Exception as exc:
                self.state.add_activity(f"Обработка: {label}", False, str(exc))

        if refresh_section and ok:
            self._load_section_data(self.state.active_section)
        else:
            self.refresh_view()

        if show_response:
            self._show_response(label, resp)

    def _pointer(self, button_name: str, label: str | None = None) -> None:
        self.page.run_thread(self._pointer_worker, button_name, label or button_name)

    def _pointer_worker(self, button_name: str, label: str) -> None:
        client = self.client
        if client is None or not client.paired:
            self.state.add_activity(label, False, "Нет подключения")
            self.refresh_view()
            return
        if not client.pointer_connected:
            client.connect_pointer(timeout=8)
        if not client.pointer_connected:
            self.state.add_activity(label, False, "Pointer socket недоступен")
            self.refresh_view()
            return
        client.button(button_name)
        self.state.add_activity(label, True)
        self.refresh_view()

    def _show_response(self, title: str, resp: dict[str, Any]) -> None:
        color = C.TEXT if self._ok(resp) else C.RED
        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                bgcolor=C.BG_ALT,
                title=ft.Text(title, color=C.TEXT),
                content=ft.Container(
                    width=430,
                    height=360,
                    content=ft.Column(
                        scroll=ft.ScrollMode.AUTO,
                        controls=[
                            ft.Text(
                                self._pretty_payload(resp),
                                selectable=True,
                                size=11,
                                color=color,
                            )
                        ],
                    ),
                ),
                actions=[ft.TextButton("Закрыть", on_click=lambda e: self.page.pop_dialog())],
            )
        )

    def _show_message(self, title: str, text: str) -> None:
        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                bgcolor=C.BG_ALT,
                title=ft.Text(title, color=C.TEXT),
                content=ft.Text(text, color=C.TEXT_2),
                actions=[ft.TextButton("Закрыть", on_click=lambda e: self.page.pop_dialog())],
            )
        )

    # ------------------------------------------------------------------
    # Section data refresh
    # ------------------------------------------------------------------

    def _refresh_section_async(self, section: str) -> None:
        if section in {"power", "sound", "channels", "apps", "inputs"}:
            self.page.run_thread(self._load_section_data, section)

    def _load_section_data(self, section: str) -> None:
        client = self.client
        if client is None or not client.is_open() or not client.paired:
            if section == "apps":
                self.state.apps_status = "ТВ не подключён"
            elif section == "inputs":
                self.state.inputs_status = "ТВ не подключён"
            self.refresh_view()
            return

        if section == "power":
            resp = client.request(PowerControl.COMMANDS["power_state"]["uri"], {})
            if self._ok(resp):
                p = resp.get("payload") or {}
                self.state.power_text = str(p.get("state") or p.get("modelName") or "Включён")
            else:
                self.state.power_text = self._error_text(resp)

        elif section == "sound":
            status = client.request(AudioControl.COMMANDS["get_status"]["uri"], {})
            if self._ok(status):
                p = status.get("payload") or {}
                if "volume" in p:
                    try:
                        self.state.volume = int(p["volume"])
                    except (TypeError, ValueError):
                        pass
                muted = p.get("muted", p.get("mute"))
                if muted is not None:
                    self.state.muted = bool(muted)
            output = client.request(AudioControl.COMMANDS["get_audio_output"]["uri"], {})
            if self._ok(output):
                self.state.audio_output = str((output.get("payload") or {}).get("soundOutput") or "—")

        elif section == "channels":
            resp = client.request(ChannelControl.COMMANDS["channel_list"]["uri"], {})
            if self._ok(resp):
                channels = (resp.get("payload") or {}).get("channelList") or []
                self.state.channel_status = f"{len(channels)} каналов"
            else:
                self.state.channel_status = f"ошибка: {self._error_text(resp)}"

        elif section == "apps":
            resp = client.request(ApplicationControl.COMMANDS["list_launch_points"]["uri"], {})
            if self._ok(resp):
                apps = (resp.get("payload") or {}).get("launchPoints") or []
                self.state.apps = list(apps)
                self.state.apps_status = f"{len(apps)} приложений"
            else:
                self.state.apps = []
                self.state.apps_status = f"ошибка: {self._error_text(resp)}"

        elif section == "inputs":
            resp = client.request(SourceControl.COMMANDS["list_sources"]["uri"], {})
            if self._ok(resp):
                devices = (resp.get("payload") or {}).get("devices") or []
                self.state.inputs = list(devices)
                self.state.inputs_status = f"{len(devices)} входов"
                ids = {str(d.get("id")) for d in devices if d.get("id")}
                if self.state.selected_input_id not in ids:
                    self.state.selected_input_id = next(iter(ids), None)
            else:
                self.state.inputs = []
                self.state.inputs_status = f"ошибка: {self._error_text(resp)}"

        self.refresh_view()

    # ------------------------------------------------------------------
    # REMOTE
    # ------------------------------------------------------------------

    def _remote_screen(self) -> ft.Control:
        return ft.Column(
            spacing=16,
            controls=[
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_AROUND,
                    controls=[
                        remote_circle(
                            icon=ft.Icons.POWER_SETTINGS_NEW,
                            label="Питание",
                            color=C.RED,
                            on_click=self._section_handler("power", "input"),
                        ),
                        remote_circle(
                            icon=ft.Icons.HOME,
                            label="Домой",
                            on_click=lambda e: self._pointer("HOME", "Домой"),
                        ),
                        remote_circle(
                            icon=ft.Icons.APPS,
                            label="Приложения",
                            on_click=self._section_handler("apps", "input"),
                        ),
                    ],
                ),
                self._build_dpad(),
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_AROUND,
                    controls=[
                        remote_circle(
                            icon=ft.Icons.ARROW_BACK,
                            label="Назад",
                            size=S.REMOTE_SECONDARY,
                            on_click=lambda e: self._pointer("BACK", "Назад"),
                        ),
                        self._voice_control(),
                        remote_circle(
                            icon=ft.Icons.INPUT,
                            label="Источник",
                            size=S.REMOTE_SECONDARY,
                            on_click=self._section_handler("inputs", "input"),
                        ),
                    ],
                ),
                ft.Row(
                    spacing=9,
                    controls=[
                        ft.Container(
                            expand=True,
                            content=pill_button(
                                "Громкость −",
                                icon=ft.Icons.REMOVE,
                                height=52,
                                on_click=lambda e: self._request(
                                    AudioControl.COMMANDS["volume_down"]["uri"],
                                    {},
                                    label="Громкость −",
                                ),
                            ),
                        ),
                        ft.Container(
                            width=58,
                            content=remote_circle(
                                icon=ft.Icons.VOLUME_OFF,
                                size=52,
                                on_click=lambda e: self._pointer("MUTE", "Mute"),
                            ),
                        ),
                        ft.Container(
                            expand=True,
                            content=pill_button(
                                "Громкость +",
                                icon=ft.Icons.ADD,
                                height=52,
                                on_click=lambda e: self._request(
                                    AudioControl.COMMANDS["volume_up"]["uri"],
                                    {},
                                    label="Громкость +",
                                ),
                            ),
                        ),
                    ],
                ),
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_AROUND,
                    controls=[
                        color_key(C.KEY_RED, 1, lambda e: self._pointer("RED", "Красная кнопка")),
                        color_key(C.KEY_GREEN, 2, lambda e: self._pointer("GREEN", "Зелёная кнопка")),
                        color_key(C.KEY_YELLOW, 3, lambda e: self._pointer("YELLOW", "Жёлтая кнопка")),
                        color_key(C.KEY_BLUE, 4, lambda e: self._pointer("BLUE", "Синяя кнопка")),
                    ],
                ),
                ft.Container(height=2),
            ],
        )

    def _build_dpad(self) -> ft.Control:
        size = S.D_PAD
        hit = 72

        def pos_button(icon: ft.IconData, name: str, *, left=None, right=None, top=None, bottom=None):
            return ft.Container(
                width=hit,
                height=hit,
                left=left,
                right=right,
                top=top,
                bottom=bottom,
                shape=ft.BoxShape.CIRCLE,
                alignment=ft.Alignment.CENTER,
                ink=True,
                ink_color="#18FFFFFF",
                on_click=lambda e, n=name: self._pointer(n, n),
                content=ft.Icon(icon, size=40, color=C.TEXT),
            )

        return ft.Row(
            alignment=ft.MainAxisAlignment.CENTER,
            controls=[
                ft.Container(
                    width=size,
                    height=size,
                    border_radius=size / 2,
                    border=border("#48FFFFFF"),
                    gradient=ft.RadialGradient(
                        center=ft.Alignment.TOP_RIGHT,
                        radius=1.2,
                        colors=["#532B344C", "#45131B2D", "#5A101827"],
                        stops=[0.0, 0.52, 1.0],
                    ),
                    shadow=shadow(30, "50"),
                    content=ft.Stack(
                        controls=[
                            pos_button(
                                ft.Icons.KEYBOARD_ARROW_UP,
                                "UP",
                                left=(size - hit) / 2,
                                top=10,
                            ),
                            pos_button(
                                ft.Icons.KEYBOARD_ARROW_DOWN,
                                "DOWN",
                                left=(size - hit) / 2,
                                bottom=10,
                            ),
                            pos_button(
                                ft.Icons.KEYBOARD_ARROW_LEFT,
                                "LEFT",
                                left=10,
                                top=(size - hit) / 2,
                            ),
                            pos_button(
                                ft.Icons.KEYBOARD_ARROW_RIGHT,
                                "RIGHT",
                                right=10,
                                top=(size - hit) / 2,
                            ),
                            ft.Container(
                                left=(size - S.OK) / 2,
                                top=(size - S.OK) / 2,
                                content=remote_circle(
                                    text="OK",
                                    size=S.OK,
                                    active=True,
                                    on_click=lambda e: self._pointer("ENTER", "OK"),
                                ),
                            ),
                        ],
                    ),
                )
            ],
        )

    def _voice_control(self) -> ft.Control:
        return ft.Column(
            spacing=4,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Container(
                    width=72,
                    height=72,
                    shape=ft.BoxShape.CIRCLE,
                    padding=3,
                    gradient=ft.LinearGradient(
                        begin=ft.Alignment.TOP_LEFT,
                        end=ft.Alignment.BOTTOM_RIGHT,
                        colors=[C.CYAN, C.VIOLET, C.MAGENTA],
                    ),
                    shadow=[
                        ft.BoxShadow(blur_radius=22, color="#4468D8FF"),
                        ft.BoxShadow(blur_radius=22, color="#449F6FFF"),
                    ],
                    on_click=self._show_voice_placeholder,
                    content=ft.Container(
                        shape=ft.BoxShape.CIRCLE,
                        alignment=ft.Alignment.CENTER,
                        bgcolor="#F0151B2C",
                        content=ft.Icon(ft.Icons.MIC, size=31, color=C.TEXT),
                    ),
                ),
                ft.Text("Голос", size=10, color=C.TEXT_2),
            ],
        )

    def _show_voice_placeholder(self, _e: ft.Event) -> None:
        self._show_message(
            "Голосовое управление",
            "В исходном проекте нет модуля распознавания речи, поэтому UI-кнопка сохранена без фиктивной отправки команд. Её можно подключить к Speech-to-Text следующим этапом.",
        )

    # ------------------------------------------------------------------
    # TOUCH
    # ------------------------------------------------------------------

    def _touch_screen(self) -> ft.Control:
        self._touch_last_send = 0.0
        self._touch_acc_x = 0.0
        self._touch_acc_y = 0.0

        mode = self.state.touch_mode
        mode_label = {"move": "Курсор", "drag": "Перетаскивание", "scroll": "Прокрутка"}.get(mode, mode)
        mode_icon = {
            "move": ft.Icons.OPEN_WITH,
            "drag": ft.Icons.DRAG_INDICATOR,
            "scroll": ft.Icons.SWAP_VERT,
        }.get(mode, ft.Icons.OPEN_WITH)

        def set_mode(m: str):
            def handler(_e: ft.Event) -> None:
                self.state.touch_mode = m
                self.refresh_view()
            return handler

        def on_pan_update(e: ft.DragUpdateEvent) -> None:
            if e.local_delta is None:
                return
            dx = e.local_delta.x
            dy = e.local_delta.y
            m = self.state.touch_mode
            now = time.monotonic()

            if m == "scroll":
                self._touch_acc_x += dx
                self._touch_acc_y += dy
                if now - self._touch_last_send >= 0.05 and (abs(self._touch_acc_x) > 2 or abs(self._touch_acc_y) > 2):
                    self._touch_last_send = now
                    sx = int(self._touch_acc_x)
                    sy = int(self._touch_acc_y)
                    self._touch_acc_x = 0.0
                    self._touch_acc_y = 0.0
                    client = self.client
                    if client is not None and client.pointer_connected:
                        client.scroll(sx, sy)
            else:
                scale = 3.0
                self._touch_acc_x += dx * scale
                self._touch_acc_y += dy * scale
                if now - self._touch_last_send >= 0.033:
                    self._touch_last_send = now
                    mx = int(self._touch_acc_x)
                    my = int(self._touch_acc_y)
                    self._touch_acc_x -= mx
                    self._touch_acc_y -= my
                    client = self.client
                    if client is not None and client.pointer_connected:
                        if m == "drag":
                            client.drag(mx, my, down=1)
                        else:
                            client.move(mx, my)

        def on_pan_start(_e: ft.DragStartEvent) -> None:
            client = self.client
            if client is not None and not client.pointer_connected:
                self.page.run_thread(client.connect_pointer, 8)

        def on_pan_end(_e: ft.DragEndEvent) -> None:
            if self.state.touch_mode == "drag":
                client = self.client
                if client is not None and client.pointer_connected:
                    client.drag(0, 0, down=0)

        def on_tap(_e: ft.TapEvent) -> None:
            self._touch_pointer_op("click", "Нажатие")

        def on_double_tap(_e: ft.Event) -> None:
            self._touch_pointer_op("button", "HOME", name="HOME")

        def on_long_press(_e: ft.Event) -> None:
            self._touch_pointer_op("button", "MENU", name="MENU")

        touchpad = ft.GestureDetector(
            content=ft.Container(
                height=300,
                border_radius=22,
                border=border(),
                gradient=ft.LinearGradient(
                    begin=ft.Alignment.TOP_LEFT,
                    end=ft.Alignment.BOTTOM_RIGHT,
                    colors=["#18101E38", "#220E1A2E", "#1A0C1626"],
                ),
                shadow=shadow(24, "40"),
                alignment=ft.Alignment.CENTER,
                content=ft.Column(
                    spacing=6,
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Icon(mode_icon, size=38, color=C.CYAN),
                        ft.Text(mode_label, size=13, color=C.TEXT_2),
                        ft.Container(
                            width=40,
                            height=2,
                            border_radius=2,
                            bgcolor=C.CYAN,
                            opacity=0.5,
                        ),
                        ft.Text(
                            "Свайп — движение\nНажатие — клик\nДвойной тап — Домой\nУдержание — Меню",
                            size=10,
                            color=C.TEXT_3,
                            text_align=ft.TextAlign.CENTER,
                        ),
                    ],
                ),
            ),
            on_pan_update=on_pan_update,
            on_pan_start=on_pan_start,
            on_pan_end=on_pan_end,
            on_tap_up=on_tap,
            on_double_tap=on_double_tap,
            on_long_press_start=on_long_press,
        )

        mode_buttons = ft.Row(
            spacing=8,
            controls=[
                ft.Container(
                    expand=True,
                    content=pill_button(
                        "Курсор",
                        icon=ft.Icons.OPEN_WITH,
                        icon_color=C.CYAN if mode == "move" else C.TEXT,
                        active=mode == "move",
                        height=48,
                        on_click=set_mode("move"),
                    ),
                ),
                ft.Container(
                    expand=True,
                    content=pill_button(
                        "Тащить",
                        icon=ft.Icons.DRAG_INDICATOR,
                        icon_color=C.CYAN if mode == "drag" else C.TEXT,
                        active=mode == "drag",
                        height=48,
                        on_click=set_mode("drag"),
                    ),
                ),
                ft.Container(
                    expand=True,
                    content=pill_button(
                        "Скролл",
                        icon=ft.Icons.SWAP_VERT,
                        icon_color=C.CYAN if mode == "scroll" else C.TEXT,
                        active=mode == "scroll",
                        height=48,
                        on_click=set_mode("scroll"),
                    ),
                ),
            ],
        )

        nav_row = ft.Row(
            spacing=8,
            controls=[
                ft.Container(
                    expand=True,
                    content=pill_button(
                        "Назад",
                        icon=ft.Icons.ARROW_BACK,
                        height=52,
                        on_click=lambda e: self._touch_pointer_op("button", "Назад", name="BACK"),
                    ),
                ),
                ft.Container(
                    width=64,
                    content=remote_circle(
                        icon=ft.Icons.MOUSE,
                        size=64,
                        on_click=lambda e: self._touch_pointer_op("click", "Клик"),
                    ),
                ),
                ft.Container(
                    expand=True,
                    content=pill_button(
                        "Домой",
                        icon=ft.Icons.HOME,
                        height=52,
                        on_click=lambda e: self._touch_pointer_op("button", "Домой", name="HOME"),
                    ),
                ),
            ],
        )

        nav_row2 = ft.Row(
            spacing=8,
            controls=[
                ft.Container(
                    expand=True,
                    content=pill_button(
                        "Меню",
                        icon=ft.Icons.MENU,
                        height=52,
                        on_click=lambda e: self._touch_pointer_op("button", "Меню", name="MENU"),
                    ),
                ),
                ft.Container(
                    expand=True,
                    content=pill_button(
                        "Вверх",
                        icon=ft.Icons.KEYBOARD_ARROW_UP,
                        height=52,
                        on_click=lambda e: self._touch_pointer_op("button", "Вверх", name="UP"),
                    ),
                ),
                ft.Container(
                    expand=True,
                    content=pill_button(
                        "Вниз",
                        icon=ft.Icons.KEYBOARD_ARROW_DOWN,
                        height=52,
                        on_click=lambda e: self._touch_pointer_op("button", "Вниз", name="DOWN"),
                    ),
                ),
            ],
        )

        return ft.Column(
            spacing=14,
            controls=[
                section_title("Тачпад", "Сенсорное управление курсором"),
                touchpad,
                mode_buttons,
                nav_row,
                nav_row2,
            ],
        )

    def _touch_pointer_op(self, op: str, label: str, *, name: str = "") -> None:
        self.page.run_thread(self._touch_pointer_worker, op, label, name)

    def _touch_pointer_worker(self, op: str, label: str, name: str) -> None:
        client = self.client
        if client is None or not client.paired:
            self.state.add_activity(label, False, "Нет подключения")
            self.refresh_view()
            return
        if not client.pointer_connected:
            client.connect_pointer(timeout=8)
        if not client.pointer_connected:
            self.state.add_activity(label, False, "Pointer socket недоступен")
            self.refresh_view()
            return
        if op == "click":
            client.click()
        elif op == "button":
            client.button(name)
        self.state.add_activity(label, True)
        self.refresh_view()

    # ------------------------------------------------------------------
    # POWER
    # ------------------------------------------------------------------

    def _power_screen(self) -> ft.Control:
        connected = self.state.connection_stage == "connected"
        state_color = C.CYAN if connected else C.TEXT_2
        return ft.Column(
            spacing=12,
            controls=[
                glass_panel(
                    ft.Row(
                        spacing=14,
                        controls=[
                            icon_disc(ft.Icons.POWER_SETTINGS_NEW, size=60, icon_size=32, color=C.VIOLET),
                            ft.Column(
                                expand=True,
                                spacing=8,
                                controls=[
                                    ft.Text("Статус", size=19, color=C.TEXT, weight=ft.FontWeight.W_600),
                                    status_pair("Состояние", self.state.power_text, value_color=state_color),
                                ],
                            ),
                        ],
                    )
                ),
                pill_button(
                    "Включить телевизор",
                    icon=ft.Icons.POWER_SETTINGS_NEW,
                    icon_color=C.CYAN,
                    on_click=self._wake_tv if not connected else lambda e: self._request(
                        PowerControl.COMMANDS["turn_on"]["uri"], {}, label="Включить телевизор", refresh_section=True
                    ),
                    active=not connected,
                ),
                pill_button(
                    "Выключить телевизор",
                    icon=ft.Icons.POWER_SETTINGS_NEW,
                    icon_color=C.RED,
                    on_click=lambda e: self._request(
                        PowerControl.COMMANDS["turn_off"]["uri"], {}, label="Выключить телевизор"
                    ),
                ),
                pill_button(
                    "Состояние питания",
                    icon=ft.Icons.MONITOR_HEART,
                    icon_color=C.BLUE,
                    on_click=lambda e: self._request(
                        PowerControl.COMMANDS["power_state"]["uri"],
                        {},
                        label="Состояние питания",
                        show_response=True,
                        refresh_section=True,
                    ),
                ),
                pill_button(
                    "Выключить экран",
                    icon=ft.Icons.TV_OFF,
                    icon_color=C.RED,
                    on_click=lambda e: self._screen_toggle(
                        PowerControl.COMMANDS["screen_off"]["uri"],
                        PowerControl.COMMANDS["screen_off"].get("payload", {}),
                        "Выключить экран",
                    ),
                ),
                pill_button(
                    "Включить экран",
                    icon=ft.Icons.TV,
                    icon_color=C.BLUE,
                    on_click=lambda e: self._screen_toggle(
                        PowerControl.COMMANDS["screen_on"]["uri"],
                        PowerControl.COMMANDS["screen_on"].get("payload", {}),
                        "Включить экран",
                    ),
                ),
            ],
        )

    # ------------------------------------------------------------------
    # SOUND
    # ------------------------------------------------------------------

    def _sound_screen(self) -> ft.Control:
        volume_value = ft.Text(str(self.state.volume), size=15, color=C.TEXT, weight=ft.FontWeight.W_600)

        def on_change(e: ft.Event) -> None:
            try:
                self.state.volume = int(e.control.value)
            except (TypeError, ValueError):
                return
            volume_value.value = str(self.state.volume)
            volume_value.update()

        def on_change_end(e: ft.Event) -> None:
            try:
                value = int(e.control.value)
            except (TypeError, ValueError):
                return
            self._request(
                AudioControl.COMMANDS["set_volume"]["uri"],
                {"volume": value},
                label=f"Громкость {value}",
            )

        muted_text = "—" if self.state.muted is None else ("выкл" if self.state.muted else "вкл")

        return ft.Column(
            spacing=11,
            controls=[
                glass_panel(
                    ft.Row(
                        spacing=14,
                        controls=[
                            icon_disc(ft.Icons.GRAPHIC_EQ, size=58, icon_size=30, color=C.VIOLET),
                            ft.Column(
                                expand=True,
                                spacing=8,
                                controls=[
                                    status_pair("Уровень / звук", f"громкость {self.state.volume}, звук {muted_text}"),
                                    ft.Container(height=1, bgcolor=C.DIVIDER),
                                    status_pair("Аудиовыход", self.state.audio_output),
                                ],
                            ),
                        ],
                    )
                ),
                pill_button(
                    "Получить статус звука",
                    icon=ft.Icons.REFRESH,
                    icon_color=C.BLUE,
                    on_click=lambda e: self._refresh_section_async("sound"),
                ),
                glass_panel(
                    ft.Column(
                        spacing=5,
                        controls=[
                            ft.Text("Установить громкость", size=14, color=C.TEXT, weight=ft.FontWeight.W_500),
                            ft.Row(
                                controls=[
                                    ft.Icon(ft.Icons.VOLUME_DOWN, size=22, color=C.TEXT_2),
                                    ft.Container(
                                        expand=True,
                                        content=ft.Slider(
                                            min=0,
                                            max=100,
                                            divisions=100,
                                            value=self.state.volume,
                                            active_color=C.CYAN,
                                            inactive_color="#30495766",
                                            thumb_color=C.BLUE,
                                            on_change=on_change,
                                            on_change_end=on_change_end,
                                        ),
                                    ),
                                    ft.Container(
                                        width=42,
                                        height=42,
                                        shape=ft.BoxShape.CIRCLE,
                                        alignment=ft.Alignment.CENTER,
                                        border=border(C.BORDER_ACTIVE),
                                        gradient=active_gradient(),
                                        content=volume_value,
                                    ),
                                ],
                            ),
                        ],
                    )
                ),
                ft.Row(
                    spacing=9,
                    controls=[
                        ft.Container(
                            expand=True,
                            content=pill_button(
                                "Увеличить",
                                icon=ft.Icons.ADD,
                                height=54,
                                on_click=lambda e: self._request(AudioControl.COMMANDS["volume_up"]["uri"], {}, label="Увеличить громкость", refresh_section=True),
                            ),
                        ),
                        ft.Container(
                            expand=True,
                            content=pill_button(
                                "Уменьшить",
                                icon=ft.Icons.REMOVE,
                                height=54,
                                on_click=lambda e: self._request(AudioControl.COMMANDS["volume_down"]["uri"], {}, label="Уменьшить громкость", refresh_section=True),
                            ),
                        ),
                    ],
                ),
                ft.Row(
                    spacing=9,
                    controls=[
                        ft.Container(
                            expand=True,
                            content=pill_button(
                                "Заглушить",
                                icon=ft.Icons.VOLUME_OFF,
                                height=54,
                                on_click=lambda e: self._request(AudioControl.COMMANDS["mute"]["uri"], {"mute": True}, label="Заглушить звук", refresh_section=True),
                            ),
                        ),
                        ft.Container(
                            expand=True,
                            content=pill_button(
                                "Включить звук",
                                icon=ft.Icons.VOLUME_UP,
                                height=54,
                                on_click=lambda e: self._request(AudioControl.COMMANDS["unmute"]["uri"], {"mute": False}, label="Включить звук", refresh_section=True),
                            ),
                        ),
                    ],
                ),
                pill_button(
                    "Узнать аудиовыход",
                    icon=ft.Icons.OUTPUT,
                    on_click=lambda e: self._request(
                        AudioControl.COMMANDS["get_audio_output"]["uri"], {}, label="Узнать аудиовыход", show_response=True, refresh_section=True
                    ),
                    height=54,
                ),
                pill_button(
                    "Установить аудиовыход",
                    icon=ft.Icons.INPUT,
                    active=True,
                    on_click=self._audio_output_dialog,
                    height=54,
                ),
            ],
        )

    def _audio_output_dialog(self, _e: ft.Event) -> None:
        dd = ft.Dropdown(
            label="Аудиовыход",
            value=self.state.audio_output if self.state.audio_output != "—" else None,
            color=C.TEXT,
            filled=True,
            fill_color=C.BG_ALT,
            border_color=C.BORDER_ACTIVE,
            border_radius=14,
            options=[ft.DropdownOption(key=key, text=f"{key} — {desc}") for key, desc in AUDIO_OUTPUTS],
        )

        def apply(_event: ft.Event) -> None:
            value = dd.value
            self.page.pop_dialog()
            if value:
                self._request(
                    AudioControl.COMMANDS["set_audio_output"]["uri"],
                    {"output": value},
                    label="Установить аудиовыход",
                    refresh_section=True,
                )

        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                bgcolor=C.BG_ALT,
                title=ft.Text("Установить аудиовыход", color=C.TEXT),
                content=ft.Container(width=390, content=dd),
                actions=[
                    ft.TextButton("Отмена", on_click=lambda e: self.page.pop_dialog()),
                    ft.TextButton("Применить", on_click=apply),
                ],
            )
        )

    # ------------------------------------------------------------------
    # MEDIA
    # ------------------------------------------------------------------

    def _media_screen(self) -> ft.Control:
        actions = [
            ("Воспроизведение", ft.Icons.PLAY_ARROW, "play"),
            ("Остановить", ft.Icons.STOP, "stop"),
            ("Пауза", ft.Icons.PAUSE, "pause"),
            ("Перемотка назад", ft.Icons.FAST_REWIND, "rewind"),
            ("Перемотка вперёд", ft.Icons.FAST_FORWARD, "fast_forward"),
        ]
        return ft.Column(
            spacing=14,
            controls=[
                ft.Row(
                    alignment=ft.MainAxisAlignment.CENTER,
                    controls=[
                        ft.Icon(ft.Icons.PLAY_ARROW, size=14, color=C.BLUE),
                        ft.Text("Управление воспроизведением", size=12, color=C.BLUE),
                    ],
                ),
                *[
                    pill_button(
                        label,
                        icon=icon,
                        height=72,
                        on_click=lambda e, key=key, text=label: self._request(
                            MediaControl.COMMANDS[key]["uri"], {}, label=text
                        ),
                    )
                    for label, icon, key in actions
                ],
            ],
        )

    # ------------------------------------------------------------------
    # CHANNELS
    # ------------------------------------------------------------------

    def _channels_screen(self) -> ft.Control:
        error = self.state.channel_status.startswith("ошибка:")
        return ft.Column(
            spacing=11,
            controls=[
                glass_panel(
                    ft.Column(
                        spacing=8,
                        controls=[
                            ft.Text("Статус", size=18, color=C.TEXT, weight=ft.FontWeight.W_600),
                            ft.Row(
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                controls=[
                                    ft.Text("Список каналов", size=12, color=C.TEXT_2),
                                    ft.Row(
                                        spacing=5,
                                        controls=[
                                            ft.Icon(ft.Icons.ERROR_OUTLINE, size=18, color=C.RED) if error else ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, size=18, color=C.GREEN),
                                            ft.Text(self.state.channel_status, size=11, color=C.RED if error else C.TEXT),
                                        ],
                                    ),
                                ],
                            ),
                        ],
                    )
                ),
                pill_button("Канал вверх", icon=ft.Icons.KEYBOARD_ARROW_UP, trailing=True, on_click=lambda e: self._request(ChannelControl.COMMANDS["channel_up"]["uri"], {}, label="Канал вверх", refresh_section=True)),
                pill_button("Канал вниз", icon=ft.Icons.KEYBOARD_ARROW_DOWN, trailing=True, on_click=lambda e: self._request(ChannelControl.COMMANDS["channel_down"]["uri"], {}, label="Канал вниз", refresh_section=True)),
                pill_button("Установить канал", icon=ft.Icons.TUNE, trailing=True, on_click=self._channel_dialog),
                pill_button("Текущий канал", icon=ft.Icons.TV, trailing=True, on_click=lambda e: self._request(ChannelControl.COMMANDS["get_current_channel"]["uri"], {}, label="Текущий канал", show_response=True)),
                pill_button("Список каналов", icon=ft.Icons.LIST, trailing=True, on_click=lambda e: self._request(ChannelControl.COMMANDS["channel_list"]["uri"], {}, label="Список каналов", show_response=True, refresh_section=True)),
                pill_button("Текущая программа", icon=ft.Icons.EVENT, trailing=True, on_click=lambda e: self._request(ChannelControl.COMMANDS["get_current_program"]["uri"], {}, label="Текущая программа", show_response=True)),
            ],
        )

    def _channel_dialog(self, _e: ft.Event) -> None:
        tf = ft.TextField(label="ID / номер канала", hint_text="1", autofocus=True)

        def submit(_event: ft.Event) -> None:
            value = (tf.value or "").strip()
            self.page.pop_dialog()
            if value:
                self._request(
                    ChannelControl.COMMANDS["set_channel"]["uri"],
                    {"channelId": value},
                    label=f"Установить канал {value}",
                    show_response=True,
                )

        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                bgcolor=C.BG_ALT,
                title=ft.Text("Установить канал", color=C.TEXT),
                content=tf,
                actions=[
                    ft.TextButton("Отмена", on_click=lambda e: self.page.pop_dialog()),
                    ft.TextButton("Открыть", on_click=submit),
                ],
            )
        )

    # ------------------------------------------------------------------
    # APPS
    # ------------------------------------------------------------------

    def _apps_screen(self) -> ft.Control:
        tiles = [self._app_tile(app) for app in self.state.apps]
        if not tiles:
            tiles = [
                glass_panel(
                    ft.Column(
                        spacing=8,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Icon(ft.Icons.APPS, size=34, color=C.TEXT_3),
                            ft.Text(self.state.apps_status, size=12, color=C.TEXT_2, text_align=ft.TextAlign.CENTER),
                        ],
                    ),
                    padding=18,
                )
            ]

        return ft.Column(
            spacing=16,
            controls=[
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        section_title("Приложения", self.state.apps_status),
                        remote_circle(icon=ft.Icons.REFRESH, size=46, on_click=lambda e: self._refresh_section_async("apps")),
                    ],
                ),
                ft.Row(
                    wrap=True,
                    spacing=10,
                    run_spacing=10,
                    controls=tiles,
                ),
                ft.Text("Запуск по нажатию на карточку приложения", size=11, color=C.TEXT_3),
            ],
        )

    def _app_tile(self, app: dict[str, Any]) -> ft.Control:
        app_id = str(app.get("id") or "")
        title = str(app.get("title") or app_id or "Приложение")
        icon = app.get("largeIcon") or app.get("icon") or app.get("smallIcon")
        visual: ft.Control
        if icon:
            src = self._normalise_icon_url(str(icon))
            visual = ft.Image(
                src=src,
                width=54,
                height=54,
                fit=ft.BoxFit.CONTAIN,
                error_content=ft.Icon(ft.Icons.APPS, size=32, color=C.CYAN),
            )
        else:
            visual = ft.Icon(ft.Icons.APPS, size=34, color=C.CYAN)

        return ft.Container(
            width=96,
            height=122,
            padding=9,
            border_radius=18,
            border=border(),
            gradient=glass_gradient(),
            shadow=shadow(16, "30"),
            ink=True,
            ink_color="#18FFFFFF",
            on_click=lambda e: self._request(
                ApplicationControl.COMMANDS["launch"]["uri"],
                {"id": app_id},
                label=f"Запуск: {title}",
            ),
            content=ft.Column(
                spacing=8,
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Container(width=58, height=58, alignment=ft.Alignment.CENTER, content=visual),
                    ft.Text(title, size=10, max_lines=2, color=C.TEXT, text_align=ft.TextAlign.CENTER),
                ],
            ),
        )

    def _normalise_icon_url(self, src: str) -> str:
        if src.startswith("http://") or src.startswith("https://"):
            return src
        if src.startswith("/") and self.state.tv_ip:
            return f"http://{self.state.tv_ip}:3000{src}"
        return src

    # ------------------------------------------------------------------
    # SYSTEM
    # ------------------------------------------------------------------

    def _system_screen(self) -> ft.Control:
        actions = [
            ("Информация о системе", ft.Icons.INFO_OUTLINE, "system_info"),
            ("Информация о ПО", ft.Icons.INFO_OUTLINE, "software_info"),
            ("Список сервисов", ft.Icons.LIST, "service_list"),
            ("Настройки изображения", ft.Icons.IMAGE, "picture_settings"),
        ]
        controls: list[ft.Control] = [
            pill_button(
                label,
                icon=icon,
                trailing=True,
                on_click=lambda e, key=key, text=label: self._request(
                    SystemControl.COMMANDS[key]["uri"],
                    SystemControl.COMMANDS[key].get("payload", {}),
                    label=text,
                    show_response=True,
                ),
            )
            for label, icon, key in actions
        ]
        controls += [
            pill_button("Показать уведомление", icon=ft.Icons.NOTIFICATIONS_NONE, trailing=True, on_click=lambda e: self._message_payload_dialog("Показать уведомление", SystemControl.COMMANDS["show_toast"]["uri"], alert=False)),
            pill_button("Показать предупреждение", icon=ft.Icons.WARNING_AMBER, trailing=True, on_click=lambda e: self._message_payload_dialog("Показать предупреждение", SystemControl.COMMANDS["create_alert"]["uri"], alert=True)),
            pill_button("Закрыть предупреждение", icon=ft.Icons.CLOSE, trailing=True, on_click=self._close_alert),
            pill_button("Включить 3D", icon=ft.Icons.VIEW_IN_AR, trailing=True, on_click=lambda e: self._request(SystemControl.COMMANDS["set_3d_on"]["uri"], {}, label="Включить 3D")),
            pill_button("Выключить 3D", icon=ft.Icons.HIDE_SOURCE, trailing=True, on_click=lambda e: self._request(SystemControl.COMMANDS["set_3d_off"]["uri"], {}, label="Выключить 3D")),
        ]
        return ft.Column(spacing=9, controls=controls)

    def _message_payload_dialog(self, title: str, uri: str, *, alert: bool) -> None:
        tf = ft.TextField(label="Сообщение", value="Сообщение", autofocus=True)

        def submit(_event: ft.Event) -> None:
            text = (tf.value or "").strip()
            self.page.pop_dialog()
            if not text:
                return

            def capture(resp: dict[str, Any]) -> None:
                if alert and self._ok(resp):
                    payload = resp.get("payload") or {}
                    alert_id = payload.get("alertId") or payload.get("id")
                    if alert_id is not None:
                        self.state.last_alert_id = str(alert_id)

            payload = {"message": text}
            if alert:
                payload["buttons"] = [{"label": "ОК"}]
            self._request(uri, payload, label=title, show_response=alert, after=capture)

        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                bgcolor=C.BG_ALT,
                title=ft.Text(title, color=C.TEXT),
                content=tf,
                actions=[
                    ft.TextButton("Отмена", on_click=lambda e: self.page.pop_dialog()),
                    ft.TextButton("Отправить", on_click=submit),
                ],
            )
        )

    def _close_alert(self, _e: ft.Event) -> None:
        if not self.state.last_alert_id:
            self._show_message(
                "Закрыть предупреждение",
                "Нет сохранённого alertId. Сначала создайте предупреждение из этого приложения.",
            )
            return
        self._request(
            SystemControl.COMMANDS["close_alert"]["uri"],
            {"alertId": self.state.last_alert_id},
            label="Закрыть предупреждение",
        )

    # ------------------------------------------------------------------
    # INPUTS
    # ------------------------------------------------------------------

    def _inputs_screen(self) -> ft.Control:
        options = []
        for d in self.state.inputs:
            key = str(d.get("id") or "")
            text = str(d.get("label") or key or "?")
            if key:
                options.append(ft.DropdownOption(key=key, text=text))

        def select(e: ft.Event) -> None:
            self.state.selected_input_id = e.control.value

        dd = ft.Dropdown(
            label="Входы",
            value=self.state.selected_input_id,
            hint_text="Выберите вход",
            color=C.TEXT,
            filled=True,
            fill_color="#5A101827",
            border_color=C.BORDER_ACTIVE,
            focused_border_color=C.CYAN,
            border_radius=16,
            options=options,
            on_select=select,
        )

        return ft.Column(
            spacing=15,
            controls=[
                glass_panel(
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Column(
                                spacing=5,
                                controls=[
                                    ft.Text("Статус", size=18, color=C.TEXT, weight=ft.FontWeight.W_600),
                                    ft.Text(f"Список входов: {self.state.inputs_status}", size=12, color=C.TEXT_2),
                                ],
                            ),
                            icon_disc(ft.Icons.INFO_OUTLINE),
                        ],
                    )
                ),
                glass_panel(
                    ft.Column(
                        spacing=13,
                        controls=[
                            dd,
                            ft.Row(
                                spacing=9,
                                controls=[
                                    ft.Container(
                                        expand=True,
                                        content=pill_button(
                                            "Переключить вход",
                                            icon=ft.Icons.INPUT,
                                            active=True,
                                            height=56,
                                            on_click=self._switch_input,
                                            disabled=not bool(self.state.selected_input_id),
                                        ),
                                    ),
                                    ft.Container(
                                        expand=True,
                                        content=pill_button(
                                            "Обновить список",
                                            icon=ft.Icons.REFRESH,
                                            height=56,
                                            on_click=lambda e: self._refresh_section_async("inputs"),
                                        ),
                                    ),
                                ],
                            ),
                        ],
                    )
                ),
            ],
        )

    def _switch_input(self, _e: ft.Event) -> None:
        if not self.state.selected_input_id:
            return
        self._request(
            SourceControl.COMMANDS["set_source"]["uri"],
            {"inputId": self.state.selected_input_id},
            label=f"Вход: {self.state.selected_input_id}",
        )

    # ------------------------------------------------------------------
    # RAW INPUT / IME
    # ------------------------------------------------------------------

    def _input_screen(self) -> ft.Control:
        text_field = ft.TextField(
            label="Текст для ТВ",
            hint_text="Введите текст",
            multiline=False,
            expand=True,
            border_color=C.BORDER_ACTIVE,
            focused_border_color=C.CYAN,
            border_radius=14,
        )

        def send_text(_e: ft.Event) -> None:
            value = (text_field.value or "").strip()
            if value:
                self._request(
                    InputControl.COMMANDS["type"]["uri"],
                    {"text": value, "replace": 0},
                    label="Ввод текста",
                )

        nav_names = [
            ("MENU", "Menu"),
            ("INFO", "Info"),
            ("EXIT", "Exit"),
            ("CC", "CC"),
            ("MUTE", "Mute"),
        ]

        digit_buttons = []
        for value in ["1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "0"]:
            digit_buttons.append(
                ft.Container(
                    width=52,
                    height=52,
                    border_radius=18,
                    border=border(),
                    gradient=glass_gradient(),
                    alignment=ft.Alignment.CENTER,
                    ink=True,
                    on_click=lambda e, v=value: self._pointer("ASTERISK" if v == "*" else v, v),
                    content=ft.Text(value, size=18, color=C.TEXT, weight=ft.FontWeight.W_500),
                )
            )

        return ft.Column(
            spacing=14,
            controls=[
                section_title("Ввод", "Pointer socket + IME"),
                glass_panel(
                    ft.Column(
                        spacing=10,
                        controls=[
                            ft.Row(
                                controls=[
                                    text_field,
                                    remote_circle(icon=ft.Icons.SEND, size=50, on_click=send_text),
                                ],
                            ),
                            ft.Row(
                                spacing=9,
                                controls=[
                                    ft.Container(
                                        expand=True,
                                        content=pill_button(
                                            "Удалить символ",
                                            icon=ft.Icons.BACKSPACE_OUTLINED,
                                            height=52,
                                            on_click=lambda e: self._request(InputControl.COMMANDS["delete"]["uri"], {"count": 1}, label="Удалить символ"),
                                        ),
                                    ),
                                    ft.Container(
                                        expand=True,
                                        content=pill_button(
                                            "Enter",
                                            icon=ft.Icons.KEYBOARD_RETURN,
                                            height=52,
                                            on_click=lambda e: self._pointer("ENTER", "Enter"),
                                        ),
                                    ),
                                ],
                            ),
                        ],
                    )
                ),
                glass_panel(
                    ft.Column(
                        spacing=10,
                        controls=[
                            ft.Text("Дополнительные клавиши", size=13, color=C.TEXT_2),
                            ft.Row(
                                wrap=True,
                                spacing=8,
                                run_spacing=8,
                                controls=[
                                    ft.Container(
                                        width=112,
                                        content=pill_button(
                                            label,
                                            height=48,
                                            on_click=lambda e, n=name, l=label: self._pointer(n, l),
                                        ),
                                    )
                                    for name, label in nav_names
                                ],
                            ),
                        ],
                    )
                ),
                glass_panel(
                    ft.Column(
                        spacing=10,
                        controls=[
                            ft.Text("Цифровые клавиши", size=13, color=C.TEXT_2),
                            ft.Row(wrap=True, spacing=8, run_spacing=8, controls=digit_buttons),
                        ],
                    )
                ),
                ft.Row(
                    spacing=9,
                    controls=[
                        ft.Container(expand=True, content=pill_button("Pointer move", icon=ft.Icons.OPEN_WITH, height=52, on_click=lambda e: self._pointer_vector_dialog("move"))),
                        ft.Container(expand=True, content=pill_button("Scroll", icon=ft.Icons.SWAP_VERT, height=52, on_click=lambda e: self._pointer_vector_dialog("scroll"))),
                    ],
                ),
            ],
        )

    def _pointer_vector_dialog(self, kind: str) -> None:
        tf = ft.TextField(label="dx dy", hint_text="10 20", autofocus=True)

        def submit(_e: ft.Event) -> None:
            raw = (tf.value or "").replace(",", " ").split()
            self.page.pop_dialog()
            if len(raw) < 2:
                return
            try:
                dx, dy = int(raw[0]), int(raw[1])
            except ValueError:
                return
            self.page.run_thread(self._pointer_vector_worker, kind, dx, dy)

        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                bgcolor=C.BG_ALT,
                title=ft.Text("Pointer move" if kind == "move" else "Scroll", color=C.TEXT),
                content=tf,
                actions=[
                    ft.TextButton("Отмена", on_click=lambda e: self.page.pop_dialog()),
                    ft.TextButton("Отправить", on_click=submit),
                ],
            )
        )

    def _pointer_vector_worker(self, kind: str, dx: int, dy: int) -> None:
        client = self.client
        if client is None or not client.paired:
            self.state.add_activity(kind, False, "Нет подключения")
            self.refresh_view()
            return
        if not client.pointer_connected:
            client.connect_pointer(timeout=8)
        if not client.pointer_connected:
            self.state.add_activity(kind, False, "Pointer socket недоступен")
            self.refresh_view()
            return
        if kind == "scroll":
            client.scroll(dx, dy)
        else:
            client.move(dx, dy)
        self.state.add_activity(kind, True, f"{dx} {dy}")
        self.refresh_view()

    # ------------------------------------------------------------------
    # ACTIVITY
    # ------------------------------------------------------------------

    def _activity_screen(self) -> ft.Control:
        if not self.state.activity:
            rows: list[ft.Control] = [
                glass_panel(
                    ft.Text("История команд пока пуста", size=13, color=C.TEXT_2),
                    padding=18,
                )
            ]
        else:
            rows = []
            for item in self.state.activity:
                rows.append(
                    glass_panel(
                        ft.Row(
                            spacing=11,
                            controls=[
                                icon_disc(
                                    ft.Icons.CHECK if item.ok else ft.Icons.CLOSE,
                                    size=38,
                                    icon_size=19,
                                    color=C.GREEN if item.ok else C.RED,
                                ),
                                ft.Column(
                                    expand=True,
                                    spacing=2,
                                    controls=[
                                        ft.Text(item.label, size=13, color=C.TEXT, weight=ft.FontWeight.W_500),
                                        ft.Text(item.detail, size=10.5, color=C.TEXT_3, max_lines=2),
                                    ],
                                ),
                                ft.Text(item.at, size=10, color=C.TEXT_3),
                            ],
                        ),
                        padding=10,
                    )
                )
        return ft.Column(
            spacing=10,
            controls=[section_title("Активность", "Последние команды и ошибки"), *rows],
        )

    # ------------------------------------------------------------------
    # SETTINGS
    # ------------------------------------------------------------------

    def _settings_screen(self) -> ft.Control:
        ip = ft.TextField(
            label="IP телевизора",
            value=self.state.tv_ip,
            hint_text="192.168.1.100",
            border_color=C.BORDER_ACTIVE,
            focused_border_color=C.CYAN,
            border_radius=14,
        )
        port = ft.TextField(
            label="WebSocket port",
            value=str(self.state.tv_port),
            keyboard_type=ft.KeyboardType.NUMBER,
            border_color=C.BORDER_ACTIVE,
            focused_border_color=C.CYAN,
            border_radius=14,
        )
        mac = ft.TextField(
            label="MAC для Wake-on-LAN (необязательно)",
            value=self.state.tv_mac,
            hint_text="AA:BB:CC:DD:EE:FF",
            border_color=C.BORDER_ACTIVE,
            focused_border_color=C.CYAN,
            border_radius=14,
        )

        async def save(_e: ft.Event) -> None:
            host = (ip.value or "").strip()
            try:
                port_value = int((port.value or "3000").strip())
            except ValueError:
                self._show_message("Настройки", "Порт должен быть числом")
                return
            mac_value = (mac.value or "").strip()

            await self.prefs.set("lg_remote.tv_ip", host)
            await self.prefs.set("lg_remote.tv_port", port_value)
            await self.prefs.set("lg_remote.tv_mac", mac_value)

            self.page.run_thread(
                self._connect_worker,
                ip=host,
                port=port_value,
                mac=mac_value or None,
            )

        return ft.Column(
            spacing=14,
            controls=[
                self._tv_list_section(),
                section_title("Ручная настройка", "Введите IP адрес вручную"),
                glass_panel(
                    ft.Column(
                        spacing=10,
                        controls=[ip, port, mac, pill_button("Сохранить и подключиться", icon=ft.Icons.WIFI, active=True, on_click=save)],
                    )
                ),
                glass_panel(
                    ft.Column(
                        spacing=8,
                        controls=[
                            ft.Text("Диагностика", size=16, color=C.TEXT, weight=ft.FontWeight.W_600),
                            status_pair("WebSocket", "подключён" if self.client and self.client.connected else "нет"),
                            status_pair("Pairing", "да" if self.client and self.client.paired else "нет"),
                            status_pair("Pointer socket", "подключён" if self.state.pointer_connected else "нет"),
                            status_pair("IP", self.state.tv_ip or "—"),
                            status_pair("Порт", str(self.state.tv_port)),
                        ],
                    )
                ),
                pill_button("Переподключиться", icon=ft.Icons.REFRESH, on_click=self._reconnect),
                pill_button("Включить через Wake-on-LAN", icon=ft.Icons.POWER_SETTINGS_NEW, icon_color=C.CYAN, on_click=self._wake_tv, disabled=not bool(self.state.tv_mac)),
                ft.Container(height=8),
                ft.ElevatedButton(
                    content=ft.Row(
                        alignment=ft.MainAxisAlignment.CENTER,
                        controls=[
                            ft.Icon(ft.Icons.DELETE_SWEEP),
                            ft.Text("Сбросить все подключения"),
                        ],
                    ),
                    height=52,
                    style=ft.ButtonStyle(
                        bgcolor="#332B1820",
                        color=C.RED,
                        shape=ft.RoundedRectangleBorder(radius=18),
                    ),
                    on_click=self._reset_all_connections,
                ),
            ],
        )

    def _tv_list_section(self) -> ft.Control:
        """Pull-to-refresh TV list. Pull down to start SSDP search."""
        _pulled = [False]

        def _on_scroll(e: ft.ScrollEvent) -> None:
            if e.pixels < -80 and not _pulled[0]:
                _pulled[0] = True
                self._discover_tvs_with_progress(e)
            if e.pixels >= 0:
                _pulled[0] = False

        tv_items: list[ft.Control] = [
            ft.Container(height=1),
        ]
        if self.state.discovery_in_progress:
            tv_items.append(
                ft.Row(
                    alignment=ft.MainAxisAlignment.CENTER,
                    controls=[
                        ft.ProgressRing(width=20, height=20, stroke_width=2, color=C.CYAN),
                        ft.Text("Поиск телевизоров в сети...", color=C.TEXT_2, size=13),
                    ],
                )
            )
        elif self.state.discovered_tvs:
            for tv in self.state.discovered_tvs:
                tv_ip_val = tv["ip"]
                tv_name = tv.get("name", tv_ip_val)
                is_current = tv_ip_val == self.state.tv_ip
                tv_items.append(
                    ft.Row(
                        controls=[
                            ft.Container(
                                content=pill_button(
                                    f"{tv_name} ({tv_ip_val})",
                                    icon=ft.Icons.TV if not is_current else ft.Icons.CHECK_CIRCLE,
                                    active=is_current,
                                    on_click=lambda _e, t=tv_ip_val: self._select_discovered_tv(t),
                                ),
                                expand=True,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.CLOSE,
                                icon_color=C.RED,
                                icon_size=18,
                                on_click=lambda _e, t=tv_ip_val: self._remove_discovered_tv(t),
                                tooltip="Удалить",
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    )
                )
        else:
            tv_items.append(
                ft.Text("Устройства не найдены", size=13, color=C.TEXT_3, text_align=ft.TextAlign.CENTER)
            )

        return glass_panel(
            ft.Column(
                spacing=6,
                controls=[
                    ft.Container(
                        height=280,
                        content=ft.ListView(
                            on_scroll=_on_scroll,
                            controls=tv_items,
                            expand=True,
                        ),
                    ),
                ],
            )
        )

    def _discover_tvs_with_progress(self, _e: ft.Event) -> None:
        """Manual discovery entry point — cancel any running search and start a new one."""
        print("[DISCOVER] Кнопка 'Найти телевизоры' нажата")

        if self.state.discovery_in_progress:
            print("[DISCOVER] Отмена предыдущего поиска")
            self._cancel_discovery()

        try:
            self.state.add_activity(
                "Запущен ручной поиск телевизоров",
                True,
            )
        except Exception:
            pass

        print("[DISCOVER] Запуск worker-потока для SSDP-поиска")
        self.refresh_view()
        self.page.run_thread(self._discover_tvs_worker, False)

    def _cancel_discovery(self) -> None:
        """Signal the running discovery worker to stop."""
        if self._discovery_cancel is not None and self._discovery_loop is not None:
            self._discovery_loop.call_soon_threadsafe(self._discovery_cancel.set)

    def _discover_tvs_worker(self, silent: bool = False) -> None:
        print("[DISCOVER] Worker запущен, silent =", silent)
        self.state.discovery_in_progress = True
        if not silent:
            self.state.add_activity("Поиск телевизоров", True, "Запуск SSDP обнаружения...")
        self.refresh_view()

        cancel = asyncio.Event()
        loop = asyncio.new_event_loop()
        self._discovery_cancel = cancel
        self._discovery_loop = loop

        import threading
        auto_cancel = threading.Timer(5.0, self._cancel_discovery)
        auto_cancel.daemon = True
        auto_cancel.start()

        try:
            from ssdp_discovery import discover_lg_tvs

            def _on_tv_found(tv: dict[str, str]) -> None:
                self.state.discovered_tvs = self._merge_discovered_tvs([tv])
                print(f"[DISCOVER] Найден ТВ: {tv.get('name')} ({tv.get('ip')}), обновление UI")
                self.refresh_view()

            print("[DISCOVER] Запуск discover_lg_tvs(timeout=5)")
            tvs = loop.run_until_complete(
                discover_lg_tvs(timeout=5, on_found=_on_tv_found, cancel_event=cancel)
            )
            if cancel.is_set():
                print("[DISCOVER] Поиск был отменён")
            else:
                print(f"[DISCOVER] SSDP вернул {len(tvs)} телевизоров: {tvs}")
                self.state.discovered_tvs = self._merge_discovered_tvs(tvs)
                self._save_discovered_tvs(self.state.discovered_tvs)
                if tvs:
                    self.state.add_activity("Поиск телевизоров", True, f"Найдено: {len(tvs)}")
                else:
                    self.state.add_activity("Поиск телевизоров", False, "Телевизоры не найдены")
        except Exception as exc:
            print(f"[DISCOVER] ОШИБКА в worker: {exc}")
            import traceback
            traceback.print_exc()
            self.state.add_activity("Поиск телевизоров", False, str(exc))
        finally:
            auto_cancel.cancel()
            print(f"[DISCOVER] Worker завершён. Итого найдено: {len(self.state.discovered_tvs)}")
            self.state.discovery_in_progress = False
            self._discovery_cancel = None
            self._discovery_loop = None
            loop.close()
            try:
                self.state.add_activity(
                    f"Поиск телевизоров завершён. Найдено: {len(self.state.discovered_tvs)}",
                    True,
                )
            except Exception:
                pass
            self.refresh_view()

    def _merge_discovered_tvs(self, fresh: list[dict[str, str]]) -> list[dict[str, str]]:
        """Merge SSDP results without losing saved metadata."""
        merged: dict[str, dict[str, str]] = {}
        for item in [*self.state.discovered_tvs, *fresh]:
            ip = item.get("ip")
            if ip:
                merged[ip] = {**merged.get(ip, {}), **item}
        return list(merged.values())

    def _save_discovered_tvs(self, tvs: list[dict[str, str]]) -> None:
        import json as _json
        import concurrent.futures
        try:
            with concurrent.futures.ThreadPoolExecutor() as pool:
                pool.submit(
                    lambda: __import__('asyncio').run(self.prefs.set("lg_remote.discovered_tvs", _json.dumps(tvs)))
                ).result(timeout=3)
        except Exception:
            pass

    def _save_tv_keys(self) -> None:
        import json as _json
        import concurrent.futures
        try:
            with concurrent.futures.ThreadPoolExecutor() as pool:
                pool.submit(
                    lambda: __import__('asyncio').run(self.prefs.set("lg_remote.tv_keys", _json.dumps(self.state.tv_keys)))
                ).result(timeout=3)
        except Exception:
            pass

    def _load_discovered_tvs(self) -> list[dict[str, str]]:
        import json as _json
        try:
            raw = self._discovered_tvs_raw
            if raw:
                return _json.loads(raw)
        except Exception:
            pass
        return []

    def _load_tv_keys(self) -> dict[str, str]:
        import json as _json
        try:
            raw = self._tv_keys_raw
            if raw:
                return _json.loads(raw)
        except Exception:
            pass
        return {}

    def _select_discovered_tv(self, tv_ip: str) -> None:
        if tv_ip == self.state.tv_ip and self.client and self.client.connected:
            return
        self.page.run_thread(self._select_discovered_tv_worker, tv_ip)

    def _select_discovered_tv_worker(self, tv_ip: str) -> None:
        if self.client is not None:
            self.client.close()
        selected = next(
            (tv for tv in self.state.discovered_tvs if tv.get("ip") == tv_ip),
            None,
        )

        connect_port = int(selected.get("port", self.state.tv_port or 3000)) if selected else self.state.tv_port
        connect_mac = selected.get("mac", "") if selected else ""

        self.state.connection_stage = "connecting"
        self.state.pointer_connected = False
        self.refresh_view()
        self._connect_worker(ip=tv_ip, port=connect_port, mac=connect_mac or None)

    def _remove_discovered_tv(self, tv_ip: str) -> None:
        self.page.run_thread(self._remove_discovered_tv_worker, tv_ip)

    def _remove_discovered_tv_worker(self, tv_ip: str) -> None:
        import asyncio as _aio
        import json as _json

        was_current = tv_ip == self.state.tv_ip

        if was_current and self.client is not None:
            self.client.close()
            self.client.forget_client_key()
            self.client = None

        # Remove TV from discovery cache.
        self.state.discovered_tvs = [
            tv for tv in self.state.discovered_tvs if tv.get("ip") != tv_ip
        ]
        await_set = [
            ("lg_remote.discovered_tvs", _json.dumps(self.state.discovered_tvs)),
        ]

        # Remove saved pairing key.
        if tv_ip in self.state.tv_keys:
            del self.state.tv_keys[tv_ip]
        await_set.append(("lg_remote.tv_keys", _json.dumps(self.state.tv_keys)))

        if was_current:
            # Clear all connection data, including manual connection fields.
            self.state.tv_ip = ""
            self.state.tv_mac = ""
            self.state.tv_port = 3000
            self.state.connection_stage = "not_configured"
            self.state.pointer_connected = False
            await_set.extend([
                ("lg_remote.tv_ip", ""),
                ("lg_remote.last_tv_ip", ""),
                ("lg_remote.tv_mac", ""),
                ("lg_remote.tv_port", 3000),
                ("lg_remote.discovered_tvs", json.dumps(
                    self.state.discovered_tvs
                )),
            ])

        for key, value in await_set:
            _aio.run(self.prefs.set(key, value))

        self.state.add_activity("Удаление ТВ", True, tv_ip)
        self.refresh_view()


    async def _reset_all_connections(self, e):
        """Full reset: remove saved TVs, keys and disable restoring deleted devices."""
        import json as _json

        try:
            if self.client:
                self.client.close()
                self.client = None
        except Exception:
            pass

        self.state.discovered_tvs = []
        self.state.tv_keys = {}
        self.state.tv_ip = ""
        self.state.tv_mac = ""
        self.state.tv_port = 3000
        self.state.last_tv_ip = ""
        self.state.connection_stage = "not_configured"
        self.state.pointer_connected = False

        values = {
            "lg_remote.tv_ip": "",
            "lg_remote.last_tv_ip": "",
            "lg_remote.tv_mac": "",
            "lg_remote.tv_port": 3000,
            "lg_remote.tv_keys": _json.dumps({}),
            "lg_remote.discovered_tvs": _json.dumps([]),
        }

        for key, value in values.items():
            await self.prefs.set(key, value)

        self.state.add_activity("Сброс подключений", True)
        self.refresh_view()


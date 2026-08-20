"""Async WebSocket client for the LG webOS TV (SSAP protocol).

Implements the connection handshake from the official webos api docs:
connect -> send "register" (reuse saved client-key or request pairing) ->
wait for "registered"/"response" to learn the client-key and save it.

The client runs its own asyncio event loop in a background thread, so it can
be used from synchronous Flet handlers via the blocking wrappers ``connect``
and ``request``.
"""

import asyncio
import concurrent.futures
import json
import logging
import os
import re
import socket
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import urlparse

import websockets

logger = logging.getLogger("tv_client")

# ── Coloured console logging for WebSocket traffic ───────────────────────────
_RESET = "\033[0m"
_SEND = "\033[32m"      # green   -> исходящие
_RECV = "\033[36m"      # cyan    -> входящие
_INFO = "\033[33m"      # yellow  -> служебные события
_ERR = "\033[31m"       # red     -> ошибки


def _console(kind: str, text: str) -> None:
    color = {"send": _SEND, "recv": _RECV, "info": _INFO, "err": _ERR}.get(kind, _INFO)
    print(f"{color}{text}{_RESET}", file=sys.stdout)


def _fmt(prefix: str, raw: Any) -> str:
    """Pretty-print JSON payloads; keep non-JSON (e.g. pointer) inline."""
    s = raw.strip() if isinstance(raw, str) else str(raw).strip()
    if s.startswith("{") or s.startswith("["):
        try:
            return f"{prefix}\n{json.dumps(json.loads(s), ensure_ascii=False, indent=2)}"
        except Exception:
            pass
    return f"{prefix} {s}"


def _log_send(payload: Any) -> None:
    _console("send", _fmt("SEND >>", payload))


def _log_recv(raw: Any) -> None:
    _console("recv", _fmt("RECV <<", raw))

REGISTER_ID = "register_0"
REGISTER_TIMEOUT = 12.0

POINTER_SOCKET_URI = "ssap://com.webos.service.networkinput/getPointerInputSocket"
POINTER_DEFAULT_PORT = 3001

SIGNATURE = (
    "eyJhbGdvcml0aG0iOiJSU0EtU0hBMjU2Iiwia2V5SWQiOiJ0ZXN0LXNpZ25pbm"
    "ctY2VydCIsInNpZ25hdHVyZVZlcnNpb24iOjF9.hrVRgjCwXVvE2OOSpDZ58hR"
    "+59aFNwYDyjQgKk3auukd7pcegmE2CzPCa0bJ0ZsRAcKkCTJrWo5iDzNhMBWRy"
    "aMOv5zWSrthlf7G128qvIlpMT0YNY+n/FaOHE73uLrS/g7swl3/qH/BGFG2Hu4"
    "RlL48eb3lLKqTt2xKHdCs6Cd4RMfJPYnzgvI4BNrFUKsjkcu+WD4OO2A27Pq1n"
    "50cMchmcaXadJhGrOqH5YmHdOCj5NSHzJYrsW0HPlpuAx/ECMeIZYDh6RMqaFM"
    "2DXzdKX9NmmyqzJ3o/0lkk/N97gfVRLW5hA29yeAwaCViZNCP8iC9aO0q9fQoj"
    "oa7NQnAtw=="
)

# Манифест для регистрации на LG webOS TV.
# CONTROL_MOUSE_AND_KEYBOARD в обоих массивах (permissions + signed.permissions)
# обязателен для getPointerInputSocket — без него TV отвечает 401.
MANIFEST = {
    "manifestVersion": 2,
    "appVersion": "1.1",
    "permissions": [
        "CONTROL_MOUSE_AND_KEYBOARD",
        "CONTROL_INPUT_JOYSTICK",
        "CONTROL_INPUT_TEXT",
        "CONTROL_POWER",
        "CONTROL_TV_POWER",
        "CONTROL_AUDIO",
        "CONTROL_DISPLAY",
        "CONTROL_TV_SCREEN",
        "CONTROL_TV_STANBY",
        "CONTROL_RECORDING",
        "CONTROL_BLUETOOTH",
        "CONTROL_TIMER_INFO",
        "CONTROL_FAVORITE_GROUP",
        "CONTROL_USER_INFO",
        "CONTROL_BOX_CHANNEL",
        "CONTROL_CHANNEL_GROUP",
        "CONTROL_CHANNEL_BLOCK",
        "LAUNCH",
        "LAUNCH_WEBAPP",
        "APP_TO_APP",
        "CLOSE",
        "TEST_OPEN",
        "TEST_PROTECTED",
        "TEST_SECURE",
        "READ_INSTALLED_APPS",
        "READ_RUNNING_APPS",
        "READ_APP_STATUS",
        "READ_CURRENT_CHANNEL",
        "READ_INPUT_DEVICE_LIST",
        "READ_NETWORK_STATE",
        "READ_TV_CHANNEL_LIST",
        "READ_TV_PROGRAM_INFO",
        "READ_TV_CURRENT_TIME",
        "READ_TV_ACR_AUTH_TOKEN",
        "READ_TV_CONTENT_STATE",
        "READ_POWER_STATE",
        "READ_COUNTRY_INFO",
        "READ_SETTINGS",
        "READ_RECORDING_STATE",
        "READ_RECORDING_LIST",
        "READ_RECORDING_SCHEDULE",
        "READ_STORAGE_DEVICE_LIST",
        "READ_UPDATE_INFO",
        "READ_NOTIFICATIONS",
        "READ_LGE_SDX",
        "READ_LGE_TV_INPUT_EVENTS",
        "WRITE_NOTIFICATION_TOAST",
        "WRITE_NOTIFICATION_ALERT",
        "WRITE_SETTINGS",
        "WRITE_RECORDING_LIST",
        "WRITE_RECORDING_SCHEDULE",
        "ADD_LAUNCHER_CHANNEL",
        "SET_CHANNEL_SKIP",
        "RELEASE_CHANNEL_SKIP",
        "DELETE_SELECT_CHANNEL",
        "SCAN_TV_CHANNELS",
        "STB_INTERNAL_CONNECTION",
        "SEARCH",
        "UPDATE_FROM_REMOTE_APP",
        "CONTROL_INPUT_MEDIA_RECORDING",
        "CONTROL_INPUT_MEDIA_PLAYBACK",
        "CHECK_BLUETOOTH_DEVICE",
        "CONTROL_WOL",
    ],
    "signatures": [{"signature": SIGNATURE, "signatureVersion": 1}],
    "signed": {
        "appId": "com.lge.test",
        "created": "20140509",
        "localizedAppNames": {"": "LG Remote App"},
        "localizedVendorNames": {"": "LG Electronics"},
        "serial": "2f930e2d2cfe083771f68e4fe7bb07",
        "vendorId": "com.lge",
        "permissions": [
            "TEST_SECURE",
            "CONTROL_INPUT_TEXT",
            "CONTROL_MOUSE_AND_KEYBOARD",
            "CONTROL_INPUT_JOYSTICK",
            "CONTROL_POWER",
            "CONTROL_TV_POWER",
            "CONTROL_AUDIO",
            "CONTROL_DISPLAY",
            "CONTROL_TV_SCREEN",
            "CONTROL_TV_STANBY",
            "CONTROL_RECORDING",
            "CONTROL_BLUETOOTH",
            "CONTROL_TIMER_INFO",
            "CONTROL_FAVORITE_GROUP",
            "CONTROL_USER_INFO",
            "CONTROL_BOX_CHANNEL",
            "CONTROL_CHANNEL_GROUP",
            "CONTROL_CHANNEL_BLOCK",
            "LAUNCH",
            "LAUNCH_WEBAPP",
            "APP_TO_APP",
            "CLOSE",
            "TEST_OPEN",
            "TEST_PROTECTED",
            "READ_INSTALLED_APPS",
            "READ_RUNNING_APPS",
            "READ_APP_STATUS",
            "READ_CURRENT_CHANNEL",
            "READ_INPUT_DEVICE_LIST",
            "READ_NETWORK_STATE",
            "READ_TV_CHANNEL_LIST",
            "READ_TV_PROGRAM_INFO",
            "READ_TV_CURRENT_TIME",
            "READ_TV_ACR_AUTH_TOKEN",
            "READ_TV_CONTENT_STATE",
            "READ_POWER_STATE",
            "READ_COUNTRY_INFO",
            "READ_SETTINGS",
            "READ_RECORDING_STATE",
            "READ_RECORDING_LIST",
            "READ_RECORDING_SCHEDULE",
            "READ_STORAGE_DEVICE_LIST",
            "READ_UPDATE_INFO",
            "READ_NOTIFICATIONS",
            "READ_LGE_SDX",
            "READ_LGE_TV_INPUT_EVENTS",
            "WRITE_NOTIFICATION_TOAST",
            "WRITE_NOTIFICATION_ALERT",
            "WRITE_SETTINGS",
            "WRITE_RECORDING_LIST",
            "WRITE_RECORDING_SCHEDULE",
            "ADD_LAUNCHER_CHANNEL",
            "SET_CHANNEL_SKIP",
            "RELEASE_CHANNEL_SKIP",
            "DELETE_SELECT_CHANNEL",
            "SCAN_TV_CHANNELS",
            "STB_INTERNAL_CONNECTION",
            "SEARCH",
            "UPDATE_FROM_REMOTE_APP",
            "CONTROL_INPUT_MEDIA_RECORDING",
            "CONTROL_INPUT_MEDIA_PLAYBACK",
            "CHECK_BLUETOOTH_DEVICE",
            "CONTROL_WOL",
        ],
    },
}


def default_key_file() -> str:
    return str(Path.home() / ".lg_remote" / "client_key.json")


def probe_ws(host: str, port: int, timeout: float = 2.0) -> bool:
    """Quick reachability check: open and close a WebSocket connection."""
    from websockets.sync.client import connect as sync_connect

    if not host:
        return False
    try:
        with sync_connect(f"ws://{host}:{port}", open_timeout=timeout):
            return True
    except Exception:
        return False


def wake_on_lan(mac: str, broadcast: str = "255.255.255.255", port: int = 9) -> None:
    """Send a Wake-on-LAN magic packet."""
    cleaned = re.sub(r"[^0-9A-Fa-f]", "", mac or "")
    if len(cleaned) != 12:
        raise ValueError("MAC-адрес должен содержать 12 hex-символов")
    mac_bytes = bytes.fromhex(cleaned)
    packet = b"\xff" * 6 + mac_bytes * 16
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(packet, (broadcast, port))


class TVClient:
    """SSAP client over WebSocket with pairing support."""

    def __init__(
        self,
        ip: str,
        port: int = 3000,
        client_key: str = "",
        client_key_file: Optional[str] = None,
        max_retries: int = 3,
    ) -> None:
        self.ip = ip
        self.port = port
        self.max_retries = max_retries
        self._client_key = client_key
        self.client_key_file = client_key_file or default_key_file()

        self.websocket: Any = None
        self.connected = False
        self.paired = False

        self.on_state_change: Optional[Callable[["TVClient"], None]] = None

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._listener_task: Optional[asyncio.Task] = None
        self._pending: dict[str, asyncio.Future] = {}
        self._counter = 0

        self._pointer_ws: Any = None
        self.pointer_connected = False
        self._pointer_lock = threading.Lock()

    # ── lifecycle ──────────────────────────────────────────────────────────
    def start(self) -> None:
        """Launch the background asyncio event loop."""
        if self._loop is None:
            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
            self._thread.start()

    def is_open(self) -> bool:
        ws = self.websocket
        if ws is None:
            return False
        state = getattr(ws, "state", None)
        if state is not None:
            try:
                return state.name == "OPEN"
            except AttributeError:
                pass
        return self.connected

    def connect(self, timeout: float = 15.0) -> bool:
        """Blocking connect + register. Returns True if the socket is up."""
        if self._loop is None:
            self.start()
        fut = asyncio.run_coroutine_threadsafe(self._connect_async(), self._loop)
        try:
            return bool(fut.result(timeout=timeout))
        except Exception:
            return False

    def close(self) -> None:
        loop = self._loop
        thread = self._thread
        if loop is not None:
            try:
                asyncio.run_coroutine_threadsafe(self._close_async(), loop).result(timeout=5)
            except Exception:
                pass
            try:
                loop.call_soon_threadsafe(loop.stop)
            except Exception:
                pass
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2)
        self._loop = None
        self._thread = None
        self.connected = False
        self.paired = False
        self.pointer_connected = False

    def forget_client_key(self) -> bool:
        """Remove the stored pairing key. Reconnect afterwards."""
        self._client_key = ""
        try:
            path = Path(self.client_key_file)
            if path.exists():
                path.unlink()
            self.paired = False
            return True
        except OSError as exc:
            logger.warning("Не удалось удалить client-key: %s", exc)
            return False

    @property
    def client_key(self) -> str:
        return self._client_key

    # ── commands ───────────────────────────────────────────────────────────
    def request(self, uri: str, payload: dict, timeout: float = 8.0) -> dict:
        """Blocking SSAP request/response. Returns the raw message dict."""
        if self._loop is None or not self.is_open():
            return {"type": "error", "error": {"code": "closed", "message": "Соединение закрыто"}}
        fut = asyncio.run_coroutine_threadsafe(self._request_async(uri, payload), self._loop)
        try:
            return fut.result(timeout=timeout)
        except (TimeoutError, concurrent.futures.TimeoutError):
            fut.cancel()
            return {"type": "error", "error": {"code": "timeout", "message": "Нет ответа от ТВ"}}
        except Exception as exc:
            return {"type": "error", "error": {"code": "request", "message": str(exc)}}

    # ── pointer / input socket (raw navigation) ────────────────────────────
    def connect_pointer(self, timeout: float = 10.0) -> bool:
        """Ask the TV for the input-socket path and connect to it (blocking)."""
        if self.pointer_connected:
            return True
        if not self._pointer_lock.acquire(blocking=False):
            return self.pointer_connected
        try:
            if self.pointer_connected:
                return True
            if self._loop is None:
                self.start()
            fut = asyncio.run_coroutine_threadsafe(self._connect_pointer_async(), self._loop)
            try:
                return bool(fut.result(timeout=timeout))
            except Exception:
                return False
        finally:
            self._pointer_lock.release()

    def pointer_send(self, data: str, timeout: float = 5.0) -> None:
        """Send a line-based command to the pointer socket."""
        if self._loop is None or self._pointer_ws is None:
            logger.warning("Pointer socket не подключён, команда пропущена: %s", data.strip())
            return
        frame = data.rstrip("\n") + "\n\n"
        _console("send", f"POINTER >> {frame.strip()}")
        fut = asyncio.run_coroutine_threadsafe(self._pointer_ws.send(frame), self._loop)
        try:
            fut.result(timeout=timeout)
        except Exception as exc:
            logger.warning("Ошибка отправки в pointer socket: %s", exc)

    def nav_button(self, name: str) -> None:
        """D-pad navigation: type:button\\nname:<name>\\n"""
        self.pointer_send(f"type:button\nname:{name}\n")

    def button(self, name: str) -> None:
        """Generic raw button push on the pointer socket (UP/DOWN/RED/1/...)."""
        self.pointer_send(f"type:button\nname:{name}\n")

    def click(self) -> None:
        """Click at the current pointer position: type:click\\n"""
        self.pointer_send("type:click\n")

    def move(self, dx: int, dy: int) -> None:
        """Move the pointer relatively by dx/dy."""
        self.pointer_send(f"type:move\ndx:{dx}\ndy:{dy}\ndown:0\n")

    def drag(self, dx: int, dy: int, down: int = 1) -> None:
        """Drag the pointer: type:move\\ndx:<dx>\\ndy:<dy>\\ndown:<down>\\n"""
        self.pointer_send(f"type:move\ndx:{dx}\ndy:{dy}\ndown:{down}\n")

    def scroll(self, dx: int, dy: int) -> None:
        """Scroll: type:scroll\\ndx:<dx>\\ndy:<dy>\\n"""
        self.pointer_send(f"type:scroll\ndx:{dx}\ndy:{dy}\n")

    def home(self) -> None:
        self.button("HOME")

    def back(self) -> None:
        self.button("BACK")

    def menu(self) -> None:
        self.button("MENU")

    def info(self) -> None:
        self.button("INFO")

    def dash(self) -> None:
        self.button("DASH")

    def exit(self) -> None:
        self.button("EXIT")

    def cc(self) -> None:
        self.button("CC")

    def number(self, n: int) -> None:
        self.button(str(n))

    def asterisk(self) -> None:
        self.button("ASTERISK")

    def color_key(self, name: str) -> None:
        self.button(name)

    def volume_up(self) -> None:
        self.button("VOLUMEUP")

    def volume_down(self) -> None:
        self.button("VOLUMEDOWN")

    def channel_up(self) -> None:
        self.button("CHANNELUP")

    def channel_down(self) -> None:
        self.button("CHANNELDOWN")

    def mute_raw(self) -> None:
        self.button("MUTE")

    def play(self) -> None:
        self.button("PLAY")

    def pause(self) -> None:
        self.button("PAUSE")

    def stop(self) -> None:
        self.button("STOP")

    def rewind(self) -> None:
        self.button("REWIND")

    def fast_forward(self) -> None:
        self.button("FASTFORWARD")

    def insert_text(self, text: str) -> dict:
        """SSAP: insert text in the focused input field."""
        return self.request("ssap://com.webos.service.ime/insertText",
                            {"text": text, "replace": 0})

    def delete_characters(self, count: int) -> dict:
        """SSAP: delete N characters in the focused input field."""
        return self.request("ssap://com.webos.service.ime/deleteCharacters",
                            {"count": int(count)})

    def send_enter(self) -> dict:
        """SSAP: confirm/enter key."""
        return self.request("ssap://com.webos.service.ime/sendEnterKey", {})

    # ── internals ──────────────────────────────────────────────────────────
    async def _connect_async(self) -> bool:
        if self.is_open():
            return True
        for attempt in range(self.max_retries):
            uri = f"ws://{self.ip}:{self.port}"
            logger.info("🔌 Подключение к %s (попытка %d/%d)", uri, attempt + 1, self.max_retries)
            try:
                self.websocket = await websockets.connect(uri, origin=None)
            except Exception as exc:
                logger.warning("Не удалось подключиться: %s", exc)
                await asyncio.sleep(1)
                continue

            self.connected = True
            self._listener_task = asyncio.create_task(self._listen())
            self._notify_state()
            # Ждём ответ на register: валидный ключ — мгновенный "response",
            # первый запуск — "registered" после подтверждения на ТВ, устаревший
            # ключ — error 401 (перерегистрация с manifest).
            await self._register()
            return True
        return False

    async def _register(self) -> dict | None:
        """Register on the TV and wait for the answer (up to REGISTER_TIMEOUT).

        Returns the register message, or None on timeout (the user has not yet
        accepted the pairing prompt — the socket stays open).
        """
        for _ in range(2):
            future = self._loop.create_future()
            self._pending[REGISTER_ID] = future
            reg_msg = json.dumps(self._build_register_msg())
            _log_send(reg_msg)
            await self.websocket.send(reg_msg)
            try:
                msg = await asyncio.wait_for(asyncio.shield(future), timeout=REGISTER_TIMEOUT)
            except asyncio.TimeoutError:
                self._pending.pop(REGISTER_ID, None)
                return None

            if msg.get("type") == "error":
                err = msg.get("error")
                if isinstance(err, dict):
                    code = err.get("code")
                elif isinstance(err, str):
                    code = err.split()[0] if err else None
                else:
                    code = None
                logger.warning("Регистрация отклонена: %s", msg)
                if str(code) == "401" and os.path.exists(self.client_key_file):
                    # Сохранённый ключ устарел/недействителен — сбрасываем и
                    # регистрируемся заново с manifest (pairing PROMPT).
                    try:
                        os.remove(self.client_key_file)
                    except OSError:
                        pass
                    self.paired = False
                    self._notify_state()
                    continue
                return msg
            self.paired = True
            self._notify_state()
            return msg
        return None

    def _build_register_msg(self) -> dict:
        payload = {
            "forcePairing": False,
            "pairingType": "PROMPT",
            "manifest": MANIFEST,
        }
        key = self._client_key
        if not key and os.path.exists(self.client_key_file):
            try:
                with open(self.client_key_file, "r", encoding="utf-8") as f:
                    key = json.load(f).get("client-key", "")
            except Exception:
                pass
        if key:
            payload["client-key"] = key
        return {"type": "register", "id": REGISTER_ID, "payload": payload}

    async def _request_async(self, uri: str, payload: dict) -> dict:
        self._counter += 1
        msg_id = f"cmd_{self._counter}"
        future = self._loop.create_future()
        self._pending[msg_id] = future
        msg = {"type": "request", "id": msg_id, "uri": uri, "payload": payload}
        _log_send(json.dumps(msg))
        try:
            await self.websocket.send(json.dumps(msg))
            return await future
        finally:
            self._pending.pop(msg_id, None)

    async def _connect_pointer_async(self) -> bool:
        # 1) Canonical way: ask the TV for the socket path.
        try:
            reply = await self._request_async(POINTER_SOCKET_URI, {})

            # Check for 401 — permissions are bound to the client-key at
            # pairing time.  If the old key was registered with a manifest
            # that lacked CONTROL_MOUSE_AND_KEYBOARD, we must re-register.
            err = reply.get("error")
            err_str = ""
            if isinstance(err, dict):
                err_str = str(err.get("message") or err.get("code") or "")
            elif isinstance(err, str):
                err_str = err
            if reply.get("type") == "error" and "401" in err_str:
                logger.warning("Pointer socket 401 — перерегистрация с обновлённым манифестом")
                if os.path.exists(self.client_key_file):
                    try:
                        os.remove(self.client_key_file)
                    except OSError:
                        pass
                self.paired = False
                await self._register()
                if not self.paired:
                    logger.warning("Перерегистрация не удалась — pointer socket недоступен")
                    return False
                # Retry after re-registration.
                reply = await self._request_async(POINTER_SOCKET_URI, {})

            path = (reply.get("payload") or {}).get("socketPath", "")
            if path:
                url = urlparse(path if "://" in path else f"ws://{path}")
                if not url.scheme:
                    url = urlparse(f"ws://{path}")
                host = url.hostname
                if host in ("127.0.0.1", "localhost", "0.0.0.0", None):
                    host = self.ip
                netloc = f"{host}:{url.port or POINTER_DEFAULT_PORT}"
                path_url = url._replace(netloc=netloc).geturl()
                # origin=None — как в pywebostv: ТВ может отклонить handshake из-за Origin.
                self._pointer_ws = await websockets.connect(path_url, origin=None)
                self.pointer_connected = True
                logger.info("Pointer socket подключён: %s", path_url)
                return True
        except Exception as exc:
            logger.warning("getPointerInputSocket: %s", exc)

        # 2) Fallback: many TVs expose the input socket on port 3001 directly.
        try:
            path_url = f"ws://{self.ip}:{POINTER_DEFAULT_PORT}/pointer"
            self._pointer_ws = await websockets.connect(path_url, origin=None)
            self.pointer_connected = True
            logger.info("Pointer socket подключён (fallback): %s", path_url)
            return True
        except Exception as exc:
            logger.warning("Не удалось подключиться к pointer socket: %s", exc)

        self._pointer_ws = None
        self.pointer_connected = False
        return False

    async def _listen(self) -> None:
        try:
            async for raw in self.websocket:
                _log_recv(raw)
                try:
                    msg = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    continue
                self._handle_message(msg)
        except Exception as exc:
            logger.warning("Соединение разорвано: %s", exc)
        finally:
            self.connected = False
            self.paired = False
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_result({"type": "error", "error": {"code": "closed", "message": "Соединение закрыто"}})
            self._pending.clear()
            if self._pointer_ws is not None:
                try:
                    await self._pointer_ws.close()
                except Exception:
                    pass
                self._pointer_ws = None
                self.pointer_connected = False
            self._notify_state()

    def _handle_message(self, msg: dict) -> None:
        mtype = msg.get("type")
        msg_id = msg.get("id")
        if mtype in ("response", "registered"):
            payload = msg.get("payload") or {}
            client_key = payload.get("client-key")
            if client_key:
                self._client_key = client_key
                self._save_client_key(client_key)
            if client_key or msg_id == REGISTER_ID or mtype == "registered":
                self.paired = True
                self._notify_state()
            fut = self._pending.pop(msg_id, None) if msg_id else None
            if fut is not None and not fut.done():
                fut.set_result(msg)
        elif mtype == "error":
            fut = self._pending.pop(msg_id, None) if msg_id else None
            if fut is not None and not fut.done():
                fut.set_result(msg)

    def _save_client_key(self, key: str) -> None:
        try:
            path = Path(self.client_key_file)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"client-key": key}), encoding="utf-8")
            logger.info("client-key сохранён в %s", path)
        except OSError as exc:
            logger.warning("Не удалось сохранить client-key: %s", exc)

    def _notify_state(self) -> None:
        if self.on_state_change is not None:
            try:
                self.on_state_change(self)
            except Exception as exc:
                logger.warning("on_state_change error: %s", exc)

    async def _close_async(self) -> None:
        if self.websocket is not None:
            try:
                await self.websocket.close()
            except Exception:
                pass
            self.websocket = None
        if self._listener_task is not None:
            self._listener_task.cancel()
            self._listener_task = None
        if self._pointer_ws is not None:
            try:
                await self._pointer_ws.close()
            except Exception:
                pass
            self._pointer_ws = None
            self.pointer_connected = False

import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI, WebSocket

app = FastAPI(title="Mock webOS TV")


@dataclass
class TVState:
    power: bool = True
    screen_on: bool = True
    standby_mode: str = "active"

    volume: int = 15
    mute: bool = False
    sound_output: str = "tv_speaker"

    current_channel: int = 1
    channels: list[dict] = field(default_factory=lambda: [
        {"channelId": "1", "name": "Первый канал", "number": "1"},
        {"channelId": "2", "name": "Россия 1", "number": "2"},
        {"channelId": "3", "name": "НТВ", "number": "3"},
        {"channelId": "4", "name": "СТС", "number": "4"},
        {"channelId": "5", "name": "ТНТ", "number": "5"},
    ])

    media_state: str = "stop"

    is_3d: bool = False

    inputs: list[dict] = field(default_factory=lambda: [
        {"id": "HDMI_1", "label": "HDMI 1", "type": "HDMI"},
        {"id": "HDMI_2", "label": "HDMI 2", "type": "HDMI"},
        {"id": "HDMI_3", "label": "HDMI 3", "type": "HDMI"},
        {"id": "COMPONENT", "label": "Component", "type": "COMPONENT"},
    ])
    current_input: str = "HDMI_1"

    foreground_app: str = "com.webos.app.home"
    apps: list[dict] = field(default_factory=lambda: [
        {"id": "com.webos.app.home", "title": "Home", "icon": "/usr/share/icons/home.png"},
        {"id": "com.webos.app.browser", "title": "Browser", "icon": "/usr/share/icons/browser.png"},
        {"id": "youtube.leanback.v4", "title": "YouTube", "icon": "/usr/share/icons/youtube.png"},
        {"id": "com.webos.app.settings", "title": "Settings", "icon": "/usr/share/icons/settings.png"},
        {"id": "com.webos.app.photos", "title": "Photos", "icon": "/usr/share/icons/photos.png"},
    ])

    ime_text: str = ""

    settings: dict = field(default_factory=lambda: {
        "picture": {
            "contrast": 50,
            "backlight": 80,
            "brightness": 50,
            "color": 50,
        },
        "sound": {
            "balance": 0,
            "eq": "standard",
        },
    })

    services: list[dict] = field(default_factory=lambda: [
        {"serviceName": "com.webos.service.tv", "version": "1.0"},
        {"serviceName": "com.webos.service.config", "version": "1.0"},
        {"serviceName": "com.webos.service.power", "version": "1.0"},
        {"serviceName": "com.webos.service.networkinput", "version": "1.0"},
        {"serviceName": "com.webos.service.ime", "version": "1.0"},
        {"serviceName": "com.webos.service.update", "version": "1.0"},
    ])

    sw_info: dict = field(default_factory=lambda: {
        "product_name": "LG Mock TV",
        "model_name": "OLED55C1MLB",
        "sw_type": "DTV",
        "major_ver": "03",
        "minor_ver": "30.71",
        "country": "RU",
        "language": "ru",
    })

    system_info: dict = field(default_factory=lambda: {
        "product_name": "LG Mock TV",
        "model_name": "OLED55C1MLB",
        "serial_number": "MOCK0000000001",
        "webos_version": "6.0",
        "firmware_version": "03.30.71",
    })

    alerts: dict = field(default_factory=dict)
    toasts: list[str] = field(default_factory=list)

    def ok(self, payload: Any = None) -> dict:
        return {"type": "response", "id": str(uuid.uuid4()), "payload": payload or {}}

    def error(self, error_code: str = "500", message: str = "Error") -> dict:
        return {"type": "error", "id": str(uuid.uuid4()), "error": {"code": error_code, "message": message}}


tv = TVState()


def handle(uri: str, payload: dict) -> dict:
    if not tv.power and uri not in (
        "ssap://com.webos.service.tvpower/power/getPowerState",
        "ssap://system/getSystemInfo",
        "ssap://com.webos.service.update/getCurrentSWInformation",
    ):
        return tv.error("401", "TV is powered off")

    match uri:
        # ---- Power ----
        case "ssap://system/turnOn":
            tv.power = True
            tv.screen_on = True
            return tv.ok({"state": "on"})

        case "ssap://system/turnOff":
            tv.power = False
            tv.screen_on = False
            return tv.ok({"state": "off"})

        case "ssap://com.webos.service.tvpower/power/getPowerState":
            return tv.ok({"state": "Active" if tv.power else "Off"})

        case "ssap://com.webos.service.tvpower/power/turnOffScreen":
            tv.screen_on = False
            return tv.ok({"state": "screenOff"})

        case "ssap://com.webos.service.tvpower/power/turnOnScreen":
            tv.screen_on = True
            return tv.ok({"state": "screenOn"})

        # ---- Audio ----
        case "ssap://audio/setVolume":
            tv.volume = max(0, min(100, payload.get("volume", tv.volume)))
            tv.mute = False
            return tv.ok({"volume": tv.volume, "mute": tv.mute})

        case "ssap://audio/setMute":
            tv.mute = payload.get("mute", not tv.mute)
            return tv.ok({"mute": tv.mute})

        case "ssap://audio/getStatus":
            return tv.ok({"volume": tv.volume, "mute": tv.mute, "soundOutput": tv.sound_output})

        case "ssap://audio/getVolume":
            return tv.ok({"volume": tv.volume})

        case "ssap://audio/volumeUp":
            tv.volume = min(100, tv.volume + 1)
            return tv.ok({"volume": tv.volume})

        case "ssap://audio/volumeDown":
            tv.volume = max(0, tv.volume - 1)
            return tv.ok({"volume": tv.volume})

        case "ssap://audio/changeSoundOutput":
            tv.sound_output = payload.get("output", tv.sound_output)
            return tv.ok({"output": tv.sound_output})

        # ---- Media controls ----
        case "ssap://media.controls/play":
            tv.media_state = "play"
            return tv.ok({"state": "play"})

        case "ssap://media.controls/stop":
            tv.media_state = "stop"
            return tv.ok({"state": "stop"})

        case "ssap://media.controls/pause":
            tv.media_state = "pause"
            return tv.ok({"state": "pause"})

        case "ssap://media.controls/rewind":
            return tv.ok({"state": "rewind"})

        case "ssap://media.controls/fastForward":
            return tv.ok({"state": "fastForward"})

        # ---- TV channels ----
        case "ssap://tv/channelUp":
            tv.current_channel = min(len(tv.channels), tv.current_channel + 1)
            return tv.ok({"channelId": str(tv.current_channel)})

        case "ssap://tv/channelDown":
            tv.current_channel = max(1, tv.current_channel - 1)
            return tv.ok({"channelId": str(tv.current_channel)})

        case "ssap://tv/openChannel":
            ch = payload.get("channelId", "1")
            tv.current_channel = int(ch) if ch.isdigit() else 1
            return tv.ok({"channelId": str(tv.current_channel)})

        case "ssap://tv/getCurrentChannel":
            ch = next((c for c in tv.channels if c["channelId"] == str(tv.current_channel)), tv.channels[0])
            return tv.ok(ch)

        case "ssap://tv/getChannelList":
            return tv.ok({"channelList": tv.channels})

        # ---- Inputs ----
        case "ssap://tv/getExternalInputList":
            return tv.ok({"inputList": tv.inputs})

        case "ssap://tv/switchInput":
            tv.current_input = payload.get("inputId", tv.current_input)
            return tv.ok({"inputId": tv.current_input})

        # ---- 3D ----
        case "ssap://com.webos.service.tv.display/set3DOn":
            tv.is_3d = True
            return tv.ok({"is3D": True})

        case "ssap://com.webos.service.tv.display/set3DOff":
            tv.is_3d = False
            return tv.ok({"is3D": False})

        # ---- Launcher / Apps ----
        case "ssap://system.launcher/launch" | "ssap://com.webos.applicationManager/launch":
            app_id = payload.get("id", "unknown")
            tv.foreground_app = app_id
            return tv.ok({"id": app_id, "launchPoint": {"id": app_id, "title": app_id}})

        case "ssap://system.launcher/close":
            tv.foreground_app = "com.webos.app.home"
            return tv.ok({"id": payload.get("id")})

        case "ssap://system.launcher/open":
            tv.foreground_app = "com.webos.app.browser"
            return tv.ok({"target": payload.get("target")})

        case "ssap://com.webos.applicationManager/listLaunchPoints":
            return tv.ok({"launchPoints": tv.apps})

        case "ssap://com.webos.applicationManager/listApps":
            return tv.ok({"apps": tv.apps})

        case "ssap://com.webos.applicationManager/getForegroundAppInfo":
            return tv.ok({"appId": tv.foreground_app})

        # ---- Notifications ----
        case "ssap://system.notifications/createToast":
            msg = payload.get("message", "")
            tv.toasts.append(msg)
            return tv.ok({"toastId": str(uuid.uuid4())})

        case "ssap://system.notifications/createAlert":
            alert_id = str(uuid.uuid4())
            tv.alerts[alert_id] = payload
            return tv.ok({"alertId": alert_id})

        case "ssap://system.notifications/closeAlert":
            alert_id = payload.get("alertId")
            tv.alerts.pop(alert_id, None)
            return tv.ok({"alertId": alert_id})

        # ---- IME / Input ----
        case "ssap://com.webos.service.ime/insertText":
            tv.ime_text += payload.get("text", "")
            return tv.ok({"text": tv.ime_text})

        case "ssap://com.webos.service.ime/sendEnterKey":
            return tv.ok()

        # ---- Network input (pointer) ----
        case "ssap://com.webos.service.networkinput/getPointerInputSocket":
            return tv.ok({"socketPath": "ws://127.0.0.1:9998/pointer"})

        # ---- System info ----
        case "ssap://system/getSystemInfo":
            return tv.ok(tv.system_info)

        case "ssap://com.webos.service.update/getCurrentSWInformation":
            return tv.ok(tv.sw_info)

        case "ssap://api/getServiceList":
            return tv.ok({"services": tv.services})

        # ---- Settings ----
        case "ssap://settings/getSystemSettings":
            cat = payload.get("category", "picture")
            keys = payload.get("keys", [])
            data = tv.settings.get(cat, {})
            if keys:
                data = {k: v for k, v in data.items() if k in keys}
            return tv.ok({"settings": data})

        case _:
            return tv.error("404", f"Unknown URI: {uri}")


@app.post("/ssap")
async def ssap_command(body: dict):
    uri = body.get("uri", "")
    payload = body.get("payload", {})
    return handle(uri, payload)


@app.get("/ssap")
async def ssap_command_get(uri: str = "", payload: str = "{}"):
    import json
    try:
        p = json.loads(payload)
    except json.JSONDecodeError:
        p = {}
    return handle(uri, p)


@app.websocket("/ssap")
async def ssap_websocket(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            msg = await ws.receive_json()
            uri = msg.get("uri", "")
            payload = msg.get("payload", {})
            response = handle(uri, payload)
            await ws.send_json(response)
    except Exception:
        pass


@app.get("/state")
async def get_state():
    return {
        "power": tv.power,
        "screen_on": tv.screen_on,
        "volume": tv.volume,
        "mute": tv.mute,
        "sound_output": tv.sound_output,
        "current_channel": tv.current_channel,
        "foreground_app": tv.foreground_app,
        "current_input": tv.current_input,
        "is_3d": tv.is_3d,
        "media_state": tv.media_state,
    }


@app.get("/")
def read_root():
    return {"status": "Mock webOS TV running", "docs": "/docs"}

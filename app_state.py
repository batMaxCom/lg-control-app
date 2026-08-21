from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class ActivityItem:
    at: str
    label: str
    ok: bool
    detail: str = ""


@dataclass(slots=True)
class RemoteState:
    active_section: str = "remote"
    active_bottom: str = "input"

    tv_ip: str = ""
    tv_port: int = 3000
    tv_mac: str = ""

    connection_stage: str = "not_configured"
    pointer_connected: bool = False

    power_text: str = "Неизвестно"
    volume: int = 0
    muted: bool | None = None
    audio_output: str = "—"

    channel_status: str = "—"
    current_channel: str = "—"

    apps: list[dict[str, Any]] = field(default_factory=list)
    apps_status: str = "—"

    inputs: list[dict[str, Any]] = field(default_factory=list)
    inputs_status: str = "—"
    selected_input_id: str | None = None

    last_alert_id: str | None = None
    last_response: str = ""
    busy: bool = False
    activity: list[ActivityItem] = field(default_factory=list)

    touch_mode: str = "move"

    discovered_tvs: list[dict[str, str]] = field(default_factory=list)
    last_tv_ip: str = ""
    discovery_in_progress: bool = False
    tv_keys: dict[str, str] = field(default_factory=dict)
    saved_tvs: list[dict[str, Any]] = field(default_factory=list)

    def add_activity(self, label: str, ok: bool, detail: str = "") -> None:
        self.activity.insert(
            0,
            ActivityItem(
                at=datetime.now().strftime("%H:%M:%S"),
                label=label,
                ok=ok,
                detail=detail,
            ),
        )
        del self.activity[40:]

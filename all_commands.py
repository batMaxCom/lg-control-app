import flet as ft


class WebOSControlBase:
    TAG = ""
    ICON = None
    COMMANDS: dict = {}


class PowerControl(WebOSControlBase):
    TAG = "Питание"
    ICON = ft.Icons.POWER_SETTINGS_NEW
    COMMANDS = {
        "turn_on": {"label": "Включить телевизор", "uri": "ssap://system/turnOn"},
        "turn_off": {"label": "Выключить телевизор", "uri": "ssap://system/turnOff"},
        "power_state": {"label": "Состояние питания",
                        "uri": "ssap://com.webos.service.tvpower/power/getPowerState"},
        "screen_off": {"label": "Выключить экран",
                       "uri": "ssap://com.webos.service.tvpower/power/turnOffScreen",
                       "payload": {"standbyMode": "active"}},
        "screen_on": {"label": "Включить экран",
                      "uri": "ssap://com.webos.service.tvpower/power/turnOnScreen",
                      "payload": {"standbyMode": "active"}},
    }


class AudioControl(WebOSControlBase):
    TAG = "Звук"
    ICON = ft.Icons.VOLUME_UP
    COMMANDS = {
        "get_status": {"label": "Получить статус звука", "uri": "ssap://audio/getStatus"},
        "get_volume": {"label": "Получить текущую громкость", "uri": "ssap://audio/getVolume"},
        "set_volume": {"label": "Установить громкость",
                       "uri": "ssap://audio/setVolume", "payload": {"volume": 15}},
        "volume_up": {"label": "Увеличить громкость", "uri": "ssap://audio/volumeUp"},
        "volume_down": {"label": "Уменьшить громкость", "uri": "ssap://audio/volumeDown"},
        "mute": {"label": "Заглушить звук", "uri": "ssap://audio/setMute", "payload": {"mute": True}},
        "unmute": {"label": "Включить звук", "uri": "ssap://audio/setMute", "payload": {"mute": False}},
        "get_audio_output": {"label": "Узнать аудиовыход", "uri": "ssap://audio/getSoundOutput"},
        "set_audio_output": {"label": "Установить аудиовыход",
                             "uri": "ssap://audio/changeSoundOutput",
                             "payload": {"output": "external_speaker"}},
    }


class MediaControl(WebOSControlBase):
    TAG = "Медиа"
    ICON = ft.Icons.PLAY_CIRCLE
    COMMANDS = {
        "play": {"label": "Воспроизведение", "uri": "ssap://media.controls/play"},
        "stop": {"label": "Остановить", "uri": "ssap://media.controls/stop"},
        "pause": {"label": "Пауза", "uri": "ssap://media.controls/pause"},
        "rewind": {"label": "Перемотка назад", "uri": "ssap://media.controls/rewind"},
        "fast_forward": {"label": "Перемотка вперёд", "uri": "ssap://media.controls/fastForward"},
    }


class ChannelControl(WebOSControlBase):
    TAG = "Каналы"
    ICON = ft.Icons.TV
    COMMANDS = {
        "channel_up": {"label": "Канал вверх", "uri": "ssap://tv/channelUp"},
        "channel_down": {"label": "Канал вниз", "uri": "ssap://tv/channelDown"},
        "set_channel": {"label": "Установить канал",
                        "uri": "ssap://tv/openChannel", "payload": {"channelId": "1"}},
        "get_current_channel": {"label": "Текущий канал", "uri": "ssap://tv/getCurrentChannel"},
        "channel_list": {"label": "Список каналов", "uri": "ssap://tv/getChannelList"},
        "get_current_program": {"label": "Текущая программа",
                                "uri": "ssap://tv/getChannelProgramInfo"},
    }


class ApplicationControl(WebOSControlBase):
    TAG = "Приложения"
    ICON = ft.Icons.APPS
    COMMANDS = {
        "list_apps": {"label": "Список приложений",
                      "uri": "ssap://com.webos.applicationManager/listApps"},
        "list_launch_points": {"label": "Список приложений (Launcher)",
                               "uri": "ssap://com.webos.applicationManager/listLaunchPoints"},
        "launch": {"label": "Запустить приложение",
                   "uri": "ssap://system.launcher/launch", "payload": {"id": "app.id"}},
        "launch_with_payload": {"label": "Запуск приложения с payload",
                                "uri": "ssap://com.webos.applicationManager/launch",
                                "payload": {"id": "app.id"}},
        "close": {"label": "Закрыть приложение",
                  "uri": "ssap://system.launcher/close", "payload": {"id": "app.id"}},
        "get_current": {"label": "Информация о текущем приложении",
                        "uri": "ssap://com.webos.applicationManager/getForegroundAppInfo"},
        "open_browser": {"label": "Открыть браузер по URL",
                         "uri": "ssap://system.launcher/open",
                         "payload": {"target": "https://example.com"}},
        "open_youtube_by_id": {"label": "Открыть YouTube по ID",
                               "uri": "ssap://system.launcher/launch",
                               "payload": {"id": "youtube.leanback.v4",
                                           "params": {"contentTarget": "http://www.youtube.com/tv?v=videoid"}}},
        "open_youtube_by_url": {"label": "Открыть YouTube по URL",
                                "uri": "ssap://system.launcher/launch",
                                "payload": {"id": "youtube.leanback.v4",
                                            "params": {"contentTarget": "http://youtube.com"}}},
    }


class SystemControl(WebOSControlBase):
    TAG = "Система"
    ICON = ft.Icons.SETTINGS
    COMMANDS = {
        "system_info": {"label": "Информация о системе", "uri": "ssap://system/getSystemInfo"},
        "software_info": {"label": "Информация о ПО",
                          "uri": "ssap://com.webos.service.update/getCurrentSWInformation"},
        "service_list": {"label": "Список сервисов", "uri": "ssap://api/getServiceList"},
        "picture_settings": {"label": "Настройки изображения",
                             "uri": "ssap://settings/getSystemSettings",
                             "payload": {"category": "picture",
                                         "keys": ["contrast", "backlight", "brightness", "color"]}},
        "show_toast": {"label": "Показать уведомление",
                       "uri": "ssap://system.notifications/createToast",
                       "payload": {"message": "Сообщение"}},
        "create_alert": {"label": "Показать предупреждение",
                         "uri": "ssap://system.notifications/createAlert",
                         "payload": {"message": "Сообщение", "buttons": [{"label": "ОК"}]}},
        "close_alert": {"label": "Закрыть предупреждение",
                        "uri": "ssap://system.notifications/closeAlert",
                        "payload": {"alertId": "123"}},
        "set_3d_on": {"label": "Включить 3D", "uri": "ssap://com.webos.service.tv.display/set3DOn"},
        "set_3d_off": {"label": "Выключить 3D", "uri": "ssap://com.webos.service.tv.display/set3DOff"},
    }


class SourceControl(WebOSControlBase):
    TAG = "Входы"
    ICON = ft.Icons.INPUT
    COMMANDS = {
        "list_sources": {"label": "Список входов", "uri": "ssap://tv/getExternalInputList"},
        "set_source": {"label": "Переключить вход",
                       "uri": "ssap://tv/switchInput", "payload": {"inputId": "HDMI_1"}},
    }


class InputControl(WebOSControlBase):
    TAG = "Ввод"
    ICON = ft.Icons.KEYBOARD
    COMMANDS = {
        "type": {"label": "Ввести текст",
                 "uri": "ssap://com.webos.service.ime/insertText",
                 "payload": {"text": "текст", "replace": 0}},
        "delete": {"label": "Удалить символы",
                   "uri": "ssap://com.webos.service.ime/deleteCharacters",
                   "payload": {"count": 1}},
        "enter": {"label": "Отправить Enter", "uri": "ssap://com.webos.service.ime/sendEnterKey"},
    }

    INPUT_COMMANDS = {
        "move": {"label": "Move", "command": [["type", "move"], ["dx", 0], ["dy", 0], ["down", 0]]},
        "click": {"label": "Click", "command": [["type", "click"]]},
        "scroll": {"label": "Scroll", "command": [["type", "scroll"], ["dx", 0], ["dy", 0]]},
        "up": {"label": "UP", "command": [["type", "button"], ["name", "UP"]]},
        "down": {"label": "DOWN", "command": [["type", "button"], ["name", "DOWN"]]},
        "left": {"label": "LEFT", "command": [["type", "button"], ["name", "LEFT"]]},
        "right": {"label": "RIGHT", "command": [["type", "button"], ["name", "RIGHT"]]},
        "ok": {"label": "OK", "command": [["type", "button"], ["name", "ENTER"]]},
        "home": {"label": "HOME", "command": [["type", "button"], ["name", "HOME"]]},
        "back": {"label": "BACK", "command": [["type", "button"], ["name", "BACK"]]},
        "menu": {"label": "MENU", "command": [["type", "button"], ["name", "MENU"]]},
        "info": {"label": "INFO", "command": [["type", "button"], ["name", "INFO"]]},
        "exit": {"label": "EXIT", "command": [["type", "button"], ["name", "EXIT"]]},
        "dash": {"label": "DASH", "command": [["type", "button"], ["name", "DASH"]]},
        "cc": {"label": "CC", "command": [["type", "button"], ["name", "CC"]]},
        "mute": {"label": "MUTE", "command": [["type", "button"], ["name", "MUTE"]]},
        "num_1": {"label": "1", "command": [["type", "button"], ["name", "1"]]},
        "num_2": {"label": "2", "command": [["type", "button"], ["name", "2"]]},
        "num_3": {"label": "3", "command": [["type", "button"], ["name", "3"]]},
        "num_4": {"label": "4", "command": [["type", "button"], ["name", "4"]]},
        "num_5": {"label": "5", "command": [["type", "button"], ["name", "5"]]},
        "num_6": {"label": "6", "command": [["type", "button"], ["name", "6"]]},
        "num_7": {"label": "7", "command": [["type", "button"], ["name", "7"]]},
        "num_8": {"label": "8", "command": [["type", "button"], ["name", "8"]]},
        "num_9": {"label": "9", "command": [["type", "button"], ["name", "9"]]},
        "num_0": {"label": "0", "command": [["type", "button"], ["name", "0"]]},
        "asterisk": {"label": "*", "command": [["type", "button"], ["name", "ASTERISK"]]},
        "red": {"label": "RED", "command": [["type", "button"], ["name", "RED"]]},
        "green": {"label": "GREEN", "command": [["type", "button"], ["name", "GREEN"]]},
        "yellow": {"label": "YELLOW", "command": [["type", "button"], ["name", "YELLOW"]]},
        "blue": {"label": "BLUE", "command": [["type", "button"], ["name", "BLUE"]]},
        "volume_up": {"label": "VOL+", "command": [["type", "button"], ["name", "VOLUMEUP"]]},
        "volume_down": {"label": "VOL-", "command": [["type", "button"], ["name", "VOLUMEDOWN"]]},
        "channel_up": {"label": "CH+", "command": [["type", "button"], ["name", "CHANNELUP"]]},
        "channel_down": {"label": "CH-", "command": [["type", "button"], ["name", "CHANNELDOWN"]]},
        "play": {"label": "PLAY", "command": [["type", "button"], ["name", "PLAY"]]},
        "pause": {"label": "PAUSE", "command": [["type", "button"], ["name", "PAUSE"]]},
        "stop": {"label": "STOP", "command": [["type", "button"], ["name", "STOP"]]},
        "rewind": {"label": "REWIND", "command": [["type", "button"], ["name", "REWIND"]]},
        "fastforward": {"label": "FF", "command": [["type", "button"], ["name", "FASTFORWARD"]]},
    }


_COMMAND_CLASSES = [
    PowerControl,
    AudioControl,
    MediaControl,
    ChannelControl,
    ApplicationControl,
    SystemControl,
    SourceControl,
]

TAG_ICONS = {cls.TAG: cls.ICON for cls in _COMMAND_CLASSES}

commands = []
for cls in _COMMAND_CLASSES:
    tag = cls.TAG
    for cmd_name, spec in cls.COMMANDS.items():
        commands.append((
            spec.get("label", cmd_name),
            spec["uri"],
            spec.get("payload", {}),
            tag,
        ))
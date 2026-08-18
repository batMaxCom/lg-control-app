import flet as ft

commands = [
    # Питание
    ("Включить телевизор", "ssap://system/turnOn", {}, "Питание"),
    ("Выключить телевизор", "ssap://system/turnOff", {}, "Питание"),
    ("Состояние питания", "ssap://com.webos.service.tvpower/power/getPowerState", {}, "Питание"),
    ("Выключить экран", "ssap://com.webos.service.tvpower/power/turnOffScreen", {"standbyMode": "active"}, "Питание"),
    ("Включить экран", "ssap://com.webos.service.tvpower/power/turnOnScreen", {"standbyMode": "active"}, "Питание"),

    # Звук
    ("Установить громкость", "ssap://audio/setVolume", {"volume": 15}, "Звук"),
    ("Включить/выключить звук", "ssap://audio/setMute", {"mute": True}, "Звук"),
    ("Получить статус звука", "ssap://audio/getStatus", {}, "Звук"),
    ("Получить текущую громкость", "ssap://audio/getVolume", {}, "Звук"),
    ("Увеличить громкость", "ssap://audio/volumeUp", {}, "Звук"),
    ("Уменьшить громкость", "ssap://audio/volumeDown", {}, "Звук"),
    ("Установить аудиовыход", "ssap://audio/changeSoundOutput", {"output": "external_speaker"}, "Звук"),
    ("Аудио выход", "ssap://com.webos.service.apiadapter/audio/getSoundOutput", {}, "Звук"),

    # Медиа
    ("Воспроизведение", "ssap://media.controls/play", {}, "Медиа"),
    ("Остановить", "ssap://media.controls/stop", {}, "Медиа"),
    ("Пауза", "ssap://media.controls/pause", {}, "Медиа"),
    ("Перемотка назад", "ssap://media.controls/rewind", {}, "Медиа"),
    ("Перемотка вперёд", "ssap://media.controls/fastForward", {}, "Медиа"),

    # Каналы
    ("Канал вверх", "ssap://tv/channelUp", {}, "Каналы"),
    ("Канал вниз", "ssap://tv/channelDown", {}, "Каналы"),
    ("Установить канал", "ssap://tv/openChannel", {"channelId": "1"}, "Каналы"),
    ("Текущий канал", "ssap://tv/getCurrentChannel", {}, "Каналы"),
    ("Список каналов", "ssap://tv/getChannelList", {}, "Каналы"),

    # Приложения
    ("Открыть браузер по URL", "ssap://system.launcher/open", {"target": "https://example.com"}, "Приложения"),
    ("Запустить приложение", "ssap://system.launcher/launch", {"id": "app.id"}, "Приложения"),
    ("Запуск приложения с payload", "ssap://com.webos.applicationManager/launch", {"id": "app.id"}, "Приложения"),
    ("Закрыть приложение", "ssap://system.launcher/close", {"id": "app.id"}, "Приложения"),
    ("Список приложений (Launcher)", "ssap://com.webos.applicationManager/listLaunchPoints", {}, "Приложения"),
    ("Список приложений", "ssap://com.webos.applicationManager/listApps", {}, "Приложения"),
    ("Информация о текущем приложении", "ssap://com.webos.applicationManager/getForegroundAppInfo", {}, "Приложения"),
    ("Открыть YouTube по ID", "ssap://system.launcher/launch", {"id": "youtube.leanback.v4", "params": {"contentTarget": "http://www.youtube.com/tv?v=videoid"}}, "Приложения"),
    ("Открыть YouTube по URL", "ssap://system.launcher/launch", {"id": "youtube.leanback.v4", "params": {"contentTarget": "http://youtube.com"}}, "Приложения"),

    # Система
    ("Информация о системе", "ssap://system/getSystemInfo", {}, "Система"),
    ("Информация о ПО", "ssap://com.webos.service.update/getCurrentSWInformation", {}, "Система"),
    ("Список сервисов", "ssap://api/getServiceList", {}, "Система"),
    ("Настройки изображения", "ssap://settings/getSystemSettings", {"category": "picture", "keys": ["contrast", "backlight", "brightness", "color"]}, "Система"),
    ("Показать уведомление", "ssap://system.notifications/createToast", {"message": "Сообщение"}, "Система"),
    ("Показать предупреждение", "ssap://system.notifications/createAlert", {"message": "Сообщение", "buttons": [{"label": "ОК"}]}, "Система"),
    ("Закрыть предупреждение", "ssap://system.notifications/closeAlert", {"alertId": "123"}, "Система"),
    ("Список входов", "ssap://tv/getExternalInputList", {}, "Система"),
    ("Переключить вход", "ssap://tv/switchInput", {"inputId": "HDMI_1"}, "Система"),
    ("Включить 3D", "ssap://com.webos.service.tv.display/set3DOn", {}, "Система"),
    ("Выключить 3D", "ssap://com.webos.service.tv.display/set3DOff", {}, "Система"),
    ("Ввести текст", "ssap://com.webos.service.ime/insertText", {"text": "текст"}, "Система"),
    ("Отправить Enter", "ssap://com.webos.service.ime/sendEnterKey", {}, "Система"),
    ("Получить socket курсора", "ssap://com.webos.service.networkinput/getPointerInputSocket", {}, "Система"),
]

TAG_ICONS = {
    "Питание": ft.Icons.POWER_SETTINGS_NEW,
    "Звук": ft.Icons.VOLUME_UP,
    "Медиа": ft.Icons.PLAY_CIRCLE,
    "Каналы": ft.Icons.TV,
    "Приложения": ft.Icons.APPS,
    "Система": ft.Icons.SETTINGS,
}

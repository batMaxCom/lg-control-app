# LG Remote — integrated Flet UI + webOS functionality

Это объединённая версия исходного `lg-control-app-main` и нового mobile-first UI.

## Что сохранено из функционального проекта

- SSAP/WebSocket pairing и сохранение `client-key`;
- Power / Audio / Media / Channels / Apps / System / Inputs;
- `getPointerInputSocket` и raw remote buttons;
- ввод текста через IME;
- запуск приложений;
- получение внешних входов;
- выбор аудиовыхода.

## Что добавлено / исправлено

- новый dark glass UI по утверждённому визуальному направлению;
- полноценный D-pad: `UP / DOWN / LEFT / RIGHT / ENTER`;
- pointer-команды и UI больше не смешиваются с `+/-` громкости;
- pointer frame завершается пустой строкой, `move` использует `dx/dy`;
- успешный register считается pairing даже если ТВ не возвращает client-key повторно;
- request timeout отменяет зависший future и очищает pending requests;
- отдельное состояние `connecting / pairing / connected / offline`;
- pointer socket подключается только после pairing;
- настройки IP/port/MAC сохраняются через Flet `SharedPreferences` — `.env` остаётся fallback;
- Wake-on-LAN при наличии `TV_MAC`;
- корректный `alertId`: закрывается alert, созданный самим приложением, вместо жёсткого `123`;
- выбор канала больше не зашит в `channelId=1`;
- история команд/ошибок;
- отдельная страница Input/IME;
- системные команды с ответом открывают читаемый response dialog.

## Важное про кнопку голоса

В исходном проекте нет Speech-to-Text. Визуальная кнопка микрофона сохранена, но не имитирует несуществующую функцию: она показывает пояснение. Это место для следующей интеграции системного Android/iOS speech recognition или отдельного STT.

## Запуск

```bash
uv sync
uv run flet run main.py
```

или через обычный venv/pip:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
flet run main.py
```

## Подключение

Можно использовать `.env`:

```env
TV_IP=192.168.1.100
TV_SERVER_PORT=3000
TV_MAC=AA:BB:CC:DD:EE:FF
```

Но для мобильного приложения удобнее открыть **Ещё → Подключение** и сохранить IP/port/MAC там.

При первом pairing подтвердите запрос на экране телевизора.

## Сборка Android

После проверки desktop-версии:

```bash
flet build apk
```

Перед релизом проверьте конкретную модель LG: часть SSAP/Luna endpoint'ов зависит от версии webOS и разрешений TV.

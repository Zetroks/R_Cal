# Проверенные пути серверов

Проверка 1 ноября 2026 года через SSH, без изменения служб и базы.
Реквизиты подключения находятся только в игнорируемом `creds.json`.

## Основной сервер (`main_server`)

- Проект: `/home/cal/r_cal`.
- Рабочая БД: `/home/cal/r_cal/CalendarServer/calendar.db`.
- Unit-файлы: `/home/cal/.config/systemd/user/`.
- `calendar-server.service`: active/running, рабочий каталог `/home/cal/r_cal`.
- `calendar-web.service`: active/running, рабочий каталог `/home/cal/r_cal`.
- `calendar-bot.service`: inactive/dead, старый рабочий каталог `/home/cal/r_cal`.

### Состояние схемы

Проверка выполнена через SQLite `mode=ro`, внутри read-транзакции.
Строки событий, пользователи, пароли и переменные окружения не выводились.
`PRAGMA quick_check`: `ok`. Alembic revision: `cbaea14ebe4b`.

Все колонки существующих таблиц, необходимые текущим SQLAlchemy-моделям,
присутствуют. Нет только новых таблиц `google_sync_jobs` и `event_archive`.
Текущий `create_all` создаст их при старте обновлённого API без изменения
существующих таблиц. Для этого выпуска отдельная миграция колонок не требуется.
Обновление сервера в ходе проверки не выполнялось.

В активных таблицах 90 событий с конкретными датами (`annual_events_new`)
и 52 ежегодных события (`daily_events`). Есть старые таблицы `annual_events`
(19 записей) и `annual_event_history` (3 записи). Их не удалять без отдельной
проверки содержимого и резервной копии: это не пустые артефакты.

История Alembic всё ещё неполна: формализацию baseline и последовательности
будущих обновлений следует сделать отдельно. Она не является обязательным
условием текущего обновления на этой установке.

## Сервер бота (`bot_server`)

После обновления реквизитов SSH-подключение проверено:

- Проект: `/opt/r_cal`.
- Пользователь службы: `botuser`.
- Unit: `/home/botuser/.config/systemd/user/calendar-bot.service`.
- Служба `calendar-bot.service`: active/running.
- Перед установкой самообновления коммит `82ccec0`, отслеживаемых локальных
  изменений нет. Это объясняет отсутствие новых команд архива.

Для повторной проверки:

```powershell
.\.venv\Scripts\python.exe -m scripts.discover_servers --server bot_server
```

## Повторная проверка схемы

```powershell
.\.venv\Scripts\python.exe -m scripts.inspect_remote_schema --database /home/cal/r_cal/CalendarServer/calendar.db --summary
```

SSH-ключи сохраняются в игнорируемом `.tmp_ssh/known_hosts` после сверки
с отпечатками, явно подтверждёнными владельцем. Секреты читаются кодом из
`creds.json` и не включаются в сообщения об ошибках.

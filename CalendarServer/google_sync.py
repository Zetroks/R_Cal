"""Синхронизация наших событий с Google Calendar (server-side).

Правила:
- Синкается только группа с google_sync_enabled; restricted-группы не
  выгружаются вообще (такие группы просто не включают).
- Цель: event_type.google_calendar_id или GOOGLE_TARGET_CALENDAR_ID из env.
- Связка хранится двусторонне: наша колонка google_event_id +
  extendedProperties.private.our_id ("annual:123") / our_version.
- Ограничения тестового билда (не чинить молча, а знать):
  - перенос ивента между календарями/группами патчит копию на старом
    месте (move не делаем), старый мусор не подчищаем;
  - all-day эвристика: start 00:00 + end 23:59(:59) или 00:00 следующего дня.
"""

import logging
import os
from datetime import date, datetime, time, timedelta

GOOGLE_TIMEZONE = os.environ.get("GOOGLE_TIMEZONE", "Europe/Moscow")
DEFAULT_TARGET_CALENDAR_ID = os.environ.get("GOOGLE_TARGET_CALENDAR_ID", "")

MIDNIGHT = time(0, 0)
END_OF_DAY = (time(23, 59), time(23, 59, 59))


def is_sync_enabled(event_type) -> bool:
    return bool(getattr(event_type, "google_sync_enabled", False))


def resolve_target_calendar(event_type) -> str | None:
    target = getattr(event_type, "google_calendar_id", None) or DEFAULT_TARGET_CALENDAR_ID
    return target.strip() if target and target.strip() else None


def _annual_is_allday(start: datetime, end: datetime) -> bool:
    return start.time() == MIDNIGHT and (
        end.time() in END_OF_DAY or (end.time() == MIDNIGHT and end.date() > start.date())
    )


def _allday_end_exclusive(end: datetime) -> str:
    if end.time() == MIDNIGHT:
        return end.date().isoformat()
    return (end.date() + timedelta(days=1)).isoformat()


def build_google_body(kind: str, fields: dict, event_type, event_id: int, version: int) -> dict:
    """Чистая функция маппинга (покрыта тестами). fields: title/url/start_date/end_date/day/month."""
    body: dict = {
        "summary": fields.get("title") or "(без названия)",
        "extendedProperties": {
            "private": {
                "our_id": f"{kind}:{event_id}",
                "our_version": str(version),
            }
        },
    }
    if fields.get("url"):
        body["description"] = fields["url"]

    if kind == "annual":
        start, end = fields["start_date"], fields["end_date"]
        if isinstance(start, str):
            start = datetime.fromisoformat(start)
        if isinstance(end, str):
            end = datetime.fromisoformat(end)
        if _annual_is_allday(start, end):
            body["start"] = {"date": start.date().isoformat()}
            body["end"] = {"date": _allday_end_exclusive(end)}
        else:
            body["start"] = {"dateTime": start.isoformat(), "timeZone": GOOGLE_TIMEZONE}
            body["end"] = {"dateTime": end.isoformat(), "timeZone": GOOGLE_TIMEZONE}
    elif kind == "daily":
        day = date(datetime.now().year, fields["month"], fields["day"])
        body["start"] = {"date": day.isoformat()}
        body["end"] = {"date": (day + timedelta(days=1)).isoformat()}
        body["recurrence"] = ["RRULE:FREQ=YEARLY"]
    else:
        raise ValueError(f"Unknown kind: {kind}")

    color_id = getattr(event_type, "google_color_id", None)
    if color_id:
        body["colorId"] = color_id
    visibility = getattr(event_type, "google_visibility", None)
    if visibility:
        body["visibility"] = visibility
    return body


def _service():
    from .google_auth import get_service

    return get_service()


def push_event(kind: str, obj, event_type) -> str:
    """Insert нового или patch существующего. Возвращает google_event_id."""
    target = resolve_target_calendar(event_type)
    if not target:
        raise RuntimeError("No target Google calendar (group calendar_id or GOOGLE_TARGET_CALENDAR_ID)")
    svc = _service()
    fields = {
        "title": obj.title,
        "url": getattr(obj, "url", None),
        "start_date": getattr(obj, "start_date", None),
        "end_date": getattr(obj, "end_date", None),
        "day": getattr(obj, "day", None),
        "month": getattr(obj, "month", None),
    }
    body = build_google_body(kind, fields, event_type, obj.id, obj.version or 0)
    gid = getattr(obj, "google_event_id", None)
    if gid:
        try:
            updated = svc.events().patch(calendarId=target, eventId=gid, body=body).execute()
            return updated["id"]
        except Exception as exc:
            if "404" not in str(exc) and "410" not in str(exc):
                raise
            logging.warning("Google event %s gone, re-inserting", gid)
    created = svc.events().insert(calendarId=target, body=body).execute()
    return created["id"]


def delete_google_event(calendar_id: str, google_event_id: str) -> bool:
    """Удаление копии в гугле. True если удалено/уже нет, False при ошибке сети/прав."""
    if not google_event_id:
        return True
    try:
        _service().events().delete(calendarId=calendar_id, eventId=google_event_id).execute()
        return True
    except Exception as exc:
        if "404" in str(exc) or "410" in str(exc):
            return True
        logging.exception("Google delete failed for %s", google_event_id)
        return False


def list_calendars() -> list:
    items = _service().calendarList().list().execute().get("items", [])
    return [
        {"id": c["id"], "summary": c.get("summary", ""), "primary": bool(c.get("primary", False))}
        for c in items
    ]

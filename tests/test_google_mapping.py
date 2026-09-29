"""Тесты маппинга наших событий -> Google Event (без сети)."""

from datetime import datetime
from types import SimpleNamespace

from CalendarServer.google_sync import build_google_body


def gtype(**kw):
    base = dict(
        google_calendar_id=None,
        google_color_id=None,
        google_visibility=None,
        google_sync_enabled=False,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_annual_timed():
    body = build_google_body(
        "annual",
        {"title": "Conf", "url": None,
         "start_date": datetime(2026, 10, 13, 12, 0),
         "end_date": datetime(2026, 10, 13, 14, 30)},
        gtype(), 5, 2,
    )
    assert body["start"] == {"dateTime": "2026-10-13T12:00:00", "timeZone": "Europe/Moscow"}
    assert body["end"] == {"dateTime": "2026-10-13T14:30:00", "timeZone": "Europe/Moscow"}
    assert "recurrence" not in body
    assert body["extendedProperties"]["private"] == {"our_id": "annual:5", "our_version": "2"}


def test_annual_allday():
    body = build_google_body(
        "annual",
        {"title": "Trip", "url": "http://x",
         "start_date": datetime(2026, 10, 10, 0, 0),
         "end_date": datetime(2026, 10, 13, 23, 59, 59)},
        gtype(), 6, 0,
    )
    assert body["start"] == {"date": "2026-10-10"}
    assert body["end"] == {"date": "2026-10-14"}  # exclusive
    assert body["description"] == "http://x"


def test_annual_midnight_end():
    body = build_google_body(
        "annual",
        {"title": "X", "url": None,
         "start_date": datetime(2026, 10, 10, 0, 0),
         "end_date": datetime(2026, 10, 12, 0, 0)},
        gtype(), 7, 0,
    )
    assert body["start"] == {"date": "2026-10-10"}
    assert body["end"] == {"date": "2026-10-12"}


def test_daily_yearly():
    body = build_google_body(
        "daily",
        {"title": "BD", "url": None, "day": 15, "month": 10},
        gtype(), 8, 1,
    )
    year = datetime.now().year
    assert body["start"] == {"date": f"{year}-10-15"}
    assert body["end"] == {"date": f"{year}-10-16"}
    assert body["recurrence"] == ["RRULE:FREQ=YEARLY"]
    assert body["extendedProperties"]["private"]["our_id"] == "daily:8"


def test_color_visibility_passthrough():
    body = build_google_body(
        "annual",
        {"title": "X", "url": None,
         "start_date": datetime(2026, 10, 13, 12, 0),
         "end_date": datetime(2026, 10, 13, 13, 0)},
        gtype(google_color_id="11", google_visibility="private"), 9, 0,
    )
    assert body["colorId"] == "11"
    assert body["visibility"] == "private"


def test_no_color_no_visibility_by_default():
    body = build_google_body(
        "annual",
        {"title": "X", "url": None,
         "start_date": datetime(2026, 10, 13, 12, 0),
         "end_date": datetime(2026, 10, 13, 13, 0)},
        gtype(), 10, 0,
    )
    assert "colorId" not in body
    assert "visibility" not in body
    assert "description" not in body

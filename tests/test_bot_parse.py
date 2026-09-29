"""Парсеры и рендер бота (без сети)."""

from datetime import datetime

from CalendarBot.bot import (append_data_field, parse_coords, parse_daily_input,
                             parse_dt_input, render_data_field)


def test_parse_dt_full():
    dt, t = parse_dt_input("05.10.2026 15:00", 2026)
    assert (dt, t) == (datetime(2026, 10, 5, 15, 0), True)


def test_parse_dt_short():
    dt, t = parse_dt_input("05.10 15:00", 2026)
    assert (dt, t) == (datetime(2026, 10, 5, 15, 0), True)


def test_parse_dt_date_only():
    dt, t = parse_dt_input("05.10", 2026)
    assert (dt, t) == (datetime(2026, 10, 5, 0, 0), False)


def test_parse_dt_iso():
    dt, t = parse_dt_input("2026-10-05 15:00", 2026)
    assert (dt, t) == (datetime(2026, 10, 5, 15, 0), True)


def test_parse_dt_bad():
    assert parse_dt_input("вчера", 2026) == (None, False)
    assert parse_dt_input("32.10", 2026) == (None, False)
    assert parse_dt_input("05.13", 2026) == (None, False)


def test_parse_daily():
    assert parse_daily_input("05.10") == (5, 10)
    assert parse_daily_input("29.02") == (29, 2)
    assert parse_daily_input("30.02") is None
    assert parse_daily_input("5") is None


def test_parse_coords():
    assert parse_coords("55.75, 37.61") == (55.75, 37.61)
    assert parse_coords("55.75 37.61") == (55.75, 37.61)
    assert parse_coords("hello") is None
    assert parse_coords("100, 10") is None


def test_render_url():
    html = render_data_field('{"URL": ["https://example.com/x"]}')
    assert '<a href="https://example.com/x">' in html


def test_render_geo():
    html = render_data_field('{"GEO": ["55.75, 37.61"]}')
    assert 'href="geo:55.75,37.61"' in html


def test_render_comment_and_legacy():
    assert "plain text" in render_data_field('{"COMMENT": ["plain text"]}')
    assert "legacy" in render_data_field("just legacy")
    assert render_data_field("") == ""
    assert render_data_field("restricted") == ""


def test_append():
    import json

    s = append_data_field("", "URL", "https://a.b")
    assert json.loads(s) == {"URL": ["https://a.b"]}
    s = append_data_field(s, "GEO", "1, 2")
    d = json.loads(s)
    assert d["URL"] == ["https://a.b"] and d["GEO"] == ["1, 2"]
    s = append_data_field("legacy", "URL", "https://a.b")
    d = json.loads(s)
    assert d["COMMENT"] == ["legacy"] and d["URL"] == ["https://a.b"]

"""Версии: формат и совместимость."""

import re

from CalendarService import version as v


def test_format():
    assert re.match(r"^\d{4}\.\d{2}\.\d{2}$", v.PROTOCOL)
    assert re.match(r"^\d{4}\.\d{2}\.\d{2}\.\d+$", v.BUILD)


def test_compatible():
    assert v.is_compatible("2026.09.30", "2026.09.29")
    assert v.is_compatible("2026.09.29", "2026.09.29")
    assert not v.is_compatible("2026.09.28", "2026.09.29")
    assert not v.is_compatible("", "2026.09.29")
    assert v.is_compatible("2026.09.29", "")

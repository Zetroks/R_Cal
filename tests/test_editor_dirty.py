"""Логика dirty-флагов редактора (без модальных диалогов и сети)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import datetime

import pytest
from PyQt5.QtWidgets import QApplication

from CalendarService import models
from CalendarService.db_cashe import cache
from CalendarDesktop import EventEditor as EE

app = QApplication.instance() or QApplication([])


class _NoopUpload:
    def enqueue(self, event):
        pass

    def enqueue_delete(self, event):
        pass


@pytest.fixture()
def panel(monkeypatch):
    monkeypatch.setattr(EE.UploadWorker, "get", classmethod(lambda cls: _NoopUpload()))
    cache.get().SetGroups([models.EventGroup(id=9, name="TEST", color="#fff", version=0)])
    cache.get().SetAccess({"IsAdmin": True})
    models.BaseEvent.set_access_resolver(cache.get().GetEventAccess)
    models.EventGroup.set_access_resolver(cache.get().GetGroupAccess)
    return EE.EventEditorPanel()


def _annual(id, title):
    return models.AnnualEvent(
        id=id, title=title, type_id=9, version=0,
        start_date=datetime(2026, 10, 1, 12, 0), end_date=datetime(2026, 10, 1, 13, 0))


def test_save_button_stays_red_until_save(panel):
    panel._add_to_box(panel.annual_box, _annual(1, "T"), EE.AnnualEventWidget)
    w = panel.annual_box.widget(0)
    assert not w._dirty
    assert w.save_btn.styleSheet() == ""
    w.title.setText("changed")
    assert w._dirty
    assert "red" in w.save_btn.styleSheet()
    assert panel.has_unsaved()
    w.save()
    assert not w._dirty
    assert w.save_btn.styleSheet() == ""
    assert not panel.has_unsaved()


def test_discard_restores(panel):
    panel._add_to_box(panel.annual_box, _annual(2, "orig"), EE.AnnualEventWidget)
    w = panel.annual_box.widget(0)
    w.title.setText("edited")
    assert panel.has_unsaved()
    panel.discard_all()
    assert w.title.text() == "orig"
    assert not w._dirty
    assert not panel.has_unsaved()


def test_new_event_is_dirty(panel):
    ev = models.DailyEvent(id=None, title="new", type_id=9, version=0, day=1, month=11)
    w = EE.DailyEventWidget(ev)
    assert w._dirty
    assert "red" in w.save_btn.styleSheet()

"""The upload must run outside the Qt GUI thread, including a slow API."""
import os
import threading
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QEventLoop, QTimer
from PyQt5.QtWidgets import QApplication
from CalendarDesktop.ThreadService import UploadWorker
from CalendarService import models, service


def test_upload_keeps_gui_responsive(monkeypatch):
    app = QApplication.instance() or QApplication([])
    main_thread = threading.get_ident()
    entered = threading.Event()
    release = threading.Event()
    calls = []
    ticks = []
    responses = []

    def post(self, endpoint, **kw):
        calls.append(threading.get_ident())
        entered.set()
        assert release.wait(2)
        return {"status": "created", "id": 10}

    monkeypatch.setattr(service.EventRepository, "POST", post)
    uploader = UploadWorker()
    event = models.DailyEvent(title="A", day=1, month=1, type_id=1)
    loop = QEventLoop()
    uploader.response_signal.connect(lambda *args: (responses.append(args), loop.quit()))

    def tick():
        ticks.append(entered.is_set())
        release.set()

    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(tick)
    timer.start(100)
    watchdog = QTimer()
    watchdog.setSingleShot(True)
    watchdog.timeout.connect(loop.quit)
    watchdog.start(3000)
    uploader.enqueue(event)
    loop.exec_()
    release.set()
    app.processEvents()
    assert responses and event.id == 10
    assert calls and calls[0] != main_thread
    assert ticks == [True]

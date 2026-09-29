from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QMainWindow, QHBoxLayout, QVBoxLayout, QToolTip
from PyQt5.QtWidgets import QWidget, QListView, QLabel, QMessageBox
from PyQt5.QtCore import QThread, Qt, QTimer

from datetime import datetime, timedelta, timezone

from .DispatchList import DispatchListWidget
from .Calendar import YearWidget
from .YearSwitcher import YearSwitcher
from CalendarService.models import BaseEvent, EventGroup
from .LegendWidget import LegendWidget
from .EventEditor import EventEditorPanel
from .ThreadService import InitWorker, PollWorker
from CalendarService import service
from CalendarService.db_cashe import cache



class MainWindow(QMainWindow):
    POLL_INTERVAL_MS = 5000
    WAKE_GAP_S = 120
    def __init__(self):
        super().__init__()
        QToolTip.setFont(QFont("Arial", 10))

        self.init_thread: QThread | None = None
        self.init_worker: InitWorker | None = None

        self.loading_label = QLabel("Загрузка данных...")
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.setCentralWidget(self.loading_label)

        self.start_init_load()

    def start_init_load(self):
        self.init_thread = QThread()
        self.init_worker = InitWorker()
        self.init_worker.moveToThread(self.init_thread)

        self.init_thread.started.connect(self.init_worker.run)  # type: ignore
        self.init_worker.finished.connect(self.on_init_loaded)  # type: ignore
        self.init_worker.failed.connect(self.on_init_failed)  # type: ignore

        self.init_thread.start()

    def on_init_loaded(self, groups, access):
        cache.get().SetGroups(groups)
        cache.get().SetAccess(access)
        BaseEvent.set_access_resolver(cache.get().GetEventAccess)
        EventGroup.set_access_resolver(cache.get().GetGroupAccess)

        self.build_ui()
        self.stop_init_load()

    def on_init_failed(self, message):
        self.loading_label.setText(f"Не удалось загрузить данные:\n{message}")
        self.stop_init_load()

    def stop_init_load(self):
        if self.init_thread is None:
            return
        self.init_thread.quit()
        self.init_thread.wait()
        self.init_thread.deleteLater()
        self.init_worker.deleteLater()
        self.init_thread = None
        self.init_worker = None

    def build_ui(self):
        _root = QWidget()
        self.setCentralWidget(_root)

        layout = QHBoxLayout(_root)
        left_layout = QVBoxLayout(_root)

        self.current_year = 2026
        self.year_switcher = YearSwitcher()
        self.year_switcher.set_year(self.current_year)
        self.year_switcher.step.connect(self.on_year_step)  # type: ignore
        left_layout.addWidget(self.year_switcher)

        self.legend = LegendWidget()
        self.legend.visibility_updated.connect(self.visibility_changed)  # type: ignore

        self.upload_status = DispatchListWidget()


        self.year = YearWidget(self.current_year)

        self.editor = EventEditorPanel()
        self.editor.on_data_changed.connect(self.data_changed)  # type: ignore

        for _calendar in self.year.calendars:
            _calendar.date_clicked.connect(self.on_date_clicked)  # type: ignore

        # layout.addWidget(self.legend, 1)
        left_layout.addWidget(self.legend)
        left_layout.addWidget(self.upload_status)
        layout.addLayout(left_layout, 1)
        layout.addWidget(self.year, 4)

        layout.addWidget(self.editor, 2)

        self.last_sync: str | None = None
        self._polling = False
        self._poll_thread: QThread | None = None
        self._poll_worker = None
        self._last_tick = None

        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.poll_once)  # type: ignore
        self.poll_timer.start(self.POLL_INTERVAL_MS)

    def on_year_step(self, delta: int):
        r = self.confirm_unsaved()
        if r == "cancel":
            return
        if r == "save":
            self.editor.save_all()
        elif r == "discard":
            self.editor.discard_all()
        self.set_year(self.current_year + delta)

    def set_year(self, year: int):
        self.current_year = year
        self.year_switcher.set_year(year)
        self.year.set_year(year)

    def confirm_unsaved(self) -> str:
        """'save' | 'discard' | 'cancel' | 'clean'."""
        if not hasattr(self, "editor") or not self.editor.has_unsaved():
            return "clean"
        r = QMessageBox.question(
            self, "Несохранённые изменения",
            "Есть несохранённые изменения. Сохранить их?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if r == QMessageBox.Save:
            return "save"
        if r == QMessageBox.Discard:
            return "discard"
        return "cancel"

    def on_date_clicked(self, day):
        r = self.confirm_unsaved()
        if r == "cancel":
            return
        if r == "save":
            self.editor.save_all()
        elif r == "discard":
            self.editor.discard_all()
        self.editor.load_day(day)

    def closeEvent(self, event):
        r = self.confirm_unsaved()
        if r == "cancel":
            event.ignore()
            return
        if r == "save":
            self.editor.save_all()
        event.accept()

    def poll_once(self):
        now = datetime.now(timezone.utc)
        if self._last_tick is not None:
            gap = (now - self._last_tick).total_seconds()
            if gap > self.WAKE_GAP_S:
                print(f"wake detected after {int(gap)}s, delta sync")
        self._last_tick = now
        if self._polling or not hasattr(self, "year"):
            return
        since = self.last_sync
        if since is None:
            since = (now - timedelta(seconds=60)).strftime("%Y-%m-%d %H:%M:%S")
        self._polling = True
        self._poll_thread = QThread()
        self._poll_worker = PollWorker(since, self.year.year)
        self._poll_worker.moveToThread(self._poll_thread)
        self._poll_thread.started.connect(self._poll_worker.run)  # type: ignore
        self._poll_worker.finished.connect(self.on_poll_result)  # type: ignore
        self._poll_worker.failed.connect(self.on_poll_failed)  # type: ignore
        self._poll_thread.start()

    def on_poll_result(self, data):
        self._stop_poll()
        if not isinstance(data, dict):
            return
        if data.get("full_reload"):
            self.last_sync = data.get("server_time", self.last_sync)
            self.year.start_show_year(self.year.year)
            return
        updates = data.get("updates", [])
        if updates:
            changed = self.year.apply_updates(updates)
            if changed and getattr(self.editor, "current_date", None) is not None \
                    and not self.editor.has_unsaved():
                self.editor.load_day(self.editor.current_date)
        ts = [u.get("ts") for u in updates if u.get("ts")]
        self.last_sync = max(ts) if ts else data.get("server_time", self.last_sync)

    def on_poll_failed(self, message):
        self._stop_poll()

    def _stop_poll(self):
        self._polling = False
        if self._poll_thread is None:
            return
        self._poll_thread.quit()
        self._poll_thread.wait()
        self._poll_thread.deleteLater()
        if self._poll_worker is not None:
            self._poll_worker.deleteLater()
        self._poll_thread = None
        self._poll_worker = None

    def data_changed(self):
        for _calendar in self.year.calendars:
            _calendar.invalidate_cache()

    def visibility_changed(self):
        for _calendar in self.year.calendars:
            _calendar.invalidate_cache()

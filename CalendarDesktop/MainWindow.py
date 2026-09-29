from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QMainWindow, QHBoxLayout, QVBoxLayout, QToolTip
from PyQt5.QtWidgets import QWidget, QListView, QLabel
from PyQt5.QtCore import QThread, Qt

from .DispatchList import DispatchListWidget
from .Calendar import YearWidget
from CalendarService.models import BaseEvent, EventGroup
from .LegendWidget import LegendWidget
from .EventEditor import EventEditorPanel
from .ThreadService import InitWorker
from CalendarService import service
from CalendarService.db_cashe import cache



class MainWindow(QMainWindow):
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

        self.legend = LegendWidget()
        self.legend.visibility_updated.connect(self.visibility_changed)  # type: ignore

        self.upload_status = DispatchListWidget()


        self.year = YearWidget(2026)

        self.editor = EventEditorPanel()
        self.editor.on_data_changed.connect(self.data_changed)  # type: ignore

        for _calendar in self.year.calendars:
            _calendar.date_clicked.connect(self.editor.load_day)  # type: ignore

        # layout.addWidget(self.legend, 1)
        left_layout.addWidget(self.legend)
        left_layout.addWidget(self.upload_status)
        layout.addLayout(left_layout, 1)
        layout.addWidget(self.year, 4)

        layout.addWidget(self.editor, 2)

    def data_changed(self):
        for _calendar in self.year.calendars:
            _calendar.invalidate_cache()

    def visibility_changed(self):
        for _calendar in self.year.calendars:
            _calendar.invalidate_cache()

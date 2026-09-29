from datetime import date

from PyQt5.QtWidgets import QWidget, QSplitter, QToolBox, QLineEdit, QDateEdit, QComboBox, QMessageBox, QDialog, \
    QDateTimeEdit
from PyQt5.QtWidgets import QPushButton, QVBoxLayout, QHBoxLayout
from PyQt5.QtCore import QDate, Qt, pyqtSignal, QSignalBlocker, QTimer

from CalendarService.dto_models import GROUP_ACCESS
from .MultiFields.MultiField import MultiField
from .ThreadService import UploadWorker
from .pydantic_modal import PydanticModal
from typing import List, Type
from CalendarService.db_cashe import cache

from CalendarService import models
from .pydantic_modal_widgets import CustomDateEdit


def clear_toolbox(box: QToolBox):
    while box.count():
        w = box.widget(0)
        box.removeItem(0)
        if w:
            w.deleteLater()


class EventEditorPanel(QWidget):
    on_data_changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        main_layout = QVBoxLayout(self)
        self.setMaximumSize(300, 9999)

        btn_layout = QHBoxLayout()

        if cache.get().has_editable_groups():
            self.add_daily_btn = QPushButton("+ Daily")
            self.add_annual_btn = QPushButton("+ Annual")

            btn_layout.addWidget(self.add_daily_btn)
            btn_layout.addWidget(self.add_annual_btn)
        # btn_layout.addStretch()

        main_layout.addLayout(btn_layout)

        splitter = QSplitter()

        self.daily_box = QToolBox()
        self.annual_box = QToolBox()

        splitter.addWidget(self.daily_box)
        splitter.addWidget(self.annual_box)

        main_layout.addWidget(splitter)

        # === connect ===
        if cache.get().has_editable_groups():
            self.add_daily_btn.clicked.connect(self.add_daily)  # type: ignore
            self.add_annual_btn.clicked.connect(self.add_annual)  # type: ignore

        self.current_date = None

    def update_toolbox_title(self, widget: QWidget, event: models.EventModel):
        for box in [self.daily_box, self.annual_box]:
            index = box.indexOf(widget)
            if index >= 0:
                box.setItemText(index, event.title or "(без названия)")
        self.on_data_changed.emit()  # type: ignore

    # noinspection PyUnusedLocal
    def delete_toolbox_entry(self, widget: QWidget, event: models.EventModel):
        for box in [self.daily_box, self.annual_box]:
            index = box.indexOf(widget)
            if index >= 0:
                box.removeItem(index)
        self.on_data_changed.emit()  # type: ignore

    def add_event(self, event_class: Type[models.EventModel], box: QToolBox, widget_class: Type[QWidget]):
        if not self.current_date:
            return
        dialog = PydanticModal(event_class, current_date=self.current_date)
        if dialog.exec_() == QDialog.Accepted:
            obj = dialog.get_data()
            if isinstance(obj, event_class):
                self._add_to_box(box, obj, widget_class)

    def add_daily(self):
        self.add_event(models.DailyEvent, self.daily_box, DailyEventWidget)

    def add_annual(self):
        self.add_event(models.AnnualEvent, self.annual_box, AnnualEventWidget)

    def _add_to_box(self, box: QToolBox, event: models.EventModel, widget_cls):
        w = widget_cls(event)
        w.on_event_changed.connect(self.update_toolbox_title)
        w.on_event_deleted.connect(self.delete_toolbox_entry)
        # w.on_title_changed = self.update_toolbox_title
        index = box.count()
        box.addItem(w, event.title if event.title else "(Без названия>)")
        box.setCurrentIndex(index)

    def load_day(self, day: date):
        year = cache.get().year_data.get(day.year, None)
        if year is None:
            return
        events = year.Events.get(day, None)
        if events is None:
            return
        clear_toolbox(self.daily_box)
        clear_toolbox(self.annual_box)

        self._fill_box(self.daily_box, events.daily, DailyEventWidget)
        self._fill_box(self.annual_box, events.annual, AnnualEventWidget)
        self.current_date = day

    def _fill_box(self, box: QToolBox, events, widget_cls):
        clear_toolbox(box)

        for e in events:
            self._add_to_box(box, e, widget_cls)

    def _iter_event_widgets(self):
        for box in (self.daily_box, self.annual_box):
            for i in range(box.count()):
                w = box.widget(i)
                if isinstance(w, BaseEventWidget):
                    yield w

    def has_unsaved(self) -> bool:
        return any(w._dirty for w in self._iter_event_widgets())

    def save_all(self):
        for w in self._iter_event_widgets():
            if w._dirty:
                w.save()

    def discard_all(self):
        for w in self._iter_event_widgets():
            if w._dirty:
                w.discard()


class BaseEventWidget(QWidget):
    # self, event
    on_event_changed = pyqtSignal(object, object)
    on_event_deleted = pyqtSignal(object, object)
    _edited_callbacks_schema_ = {
        QLineEdit : "textChanged",
        CustomDateEdit:"on_data_changed",
        MultiField:"on_data_changed",
        QComboBox:"currentIndexChanged",
        QDateEdit:"userDateChanged",
    }
    _loading_now_ = False

    def __init__(self, event=None, parent=None):
        super().__init__(parent)
        # self.on_title_changed = None
        self.event = event
        self._dirty = False
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(4, 0, 4, 0)
        self.layout.setAlignment(Qt.AlignTop)
        self.fields = self.GetFields()

        for field in self.fields:
            self.layout.addWidget(field)
            signal = getattr(field, self.__class__._edited_callbacks_schema_.get(field.__class__, ""), None)
            if signal is not None:
                signal.connect(self.some_field_changed)

        if self.event.get_access() >= GROUP_ACCESS.EDITOR:
            self.save_btn = QPushButton("Сохранить")
            self.save_btn.clicked.connect(self.save)  # type: ignore

            delete_btn = QPushButton("Удалить")
            delete_btn.clicked.connect(self.delete_event)  # type: ignore

            self.layout.addWidget(self.save_btn)
            self.layout.addWidget(delete_btn)

        if event:
            self._loading_now_ = True
            self.load(event)
            self._loading_now_ = False
            if event.id is None:
                self.mark_dirty()

        self.layout.addStretch()

    def some_field_changed(self):
        if not self._loading_now_:
            self.mark_dirty()

    def mark_dirty(self):
        self._dirty = True
        btn = getattr(self, "save_btn", None)
        if btn is not None:
            btn.setStyleSheet("background-color: red; color: white;")

    def clear_dirty(self):
        self._dirty = False
        btn = getattr(self, "save_btn", None)
        if btn is not None:
            btn.setStyleSheet("")

    def discard(self):
        self._loading_now_ = True
        try:
            self.load(self.event)
        finally:
            self._loading_now_ = False
        self.clear_dirty()
    def GetFields(self) -> List[QWidget]:
        return []

    @staticmethod
    def _fill_types(c_box: QComboBox):
        c_box.clear()
        for group in cache.get().groups_iterator():
            if group.get_access() >= GROUP_ACCESS.RESTRICTED:
                c_box.addItem(group.name, group.id)

    def save(self):
        self.event.invalidate_access()
        UploadWorker.get().enqueue(self.event)
        self._loading_now_ = True
        self.load(self.event)
        self._loading_now_ = False
        self.clear_dirty()
        self.on_event_changed.emit(self, self.event)  # type: ignore

    def delete_event(self):
        reply = QMessageBox.question(
            self,
            "Удаление",
            "Ты точно хочешь удалить это событие?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            UploadWorker.get().enqueue_delete(self.event)
            self.event_remove_from_cache(self.event)
            self.on_event_deleted.emit(self, self.event)  # type: ignore
            self.deleteLater()

    def load(self, event):
        pass

    def event_add_to_cache(self, event):
        if isinstance(event, models.AnnualEvent):
            for d in models.date_iterator(self.event.start_date, self.event.end_date):
                year = cache.get().year_data.get(d.year, None)
                if year is not None:
                    year.Months[d.month].Days[d.day].annual.append(self.event)
        elif isinstance(event, models.DailyEvent):
            for _, year in cache.get().year_data.items():
                if year is not None:
                    year.Months[self.event.month].Days[self.event.day].daily.append(self.event)

    def event_remove_from_cache(self, event):
        if isinstance(event, models.AnnualEvent):
            for d in models.date_iterator(self.event.start_date, self.event.end_date):
                year = cache.get().year_data.get(d.year, None)
                if year is not None:
                    container = year.Months[d.month].Days[d.day].annual
                    if self.event in container:
                        container.remove(self.event)
        elif isinstance(event, models.DailyEvent):
            for _, year in cache.get().year_data.items():
                if year is not None:
                    container = year.Months[self.event.month].Days[self.event.day].daily
                    if self.event in container:
                        container.remove(self.event)


class AnnualEventWidget(BaseEventWidget):
    def __init__(self, event: models.AnnualEvent = None, parent=None):
        self.title = QLineEdit()
        self.start = CustomDateEdit()
        self.end = CustomDateEdit()
        self.multi_field = MultiField()
        self.type = QComboBox()
        self._fill_types(self.type)
        super().__init__(event, parent)

    def GetFields(self) -> List[QWidget]:
        if self.event.get_access() >= GROUP_ACCESS.EDITOR:
            return [self.title, self.start, self.end, self.multi_field, self.type]
        else:
            return [self.title, self.start, self.end, self.multi_field]

    def load(self, event: models.AnnualEvent):
        self.title.setText(event.title or "")

        if event.start_date:
            self.start.setDateTime(event.start_date)

        if event.end_date:
            self.end.setDateTime(event.end_date)

        self.multi_field.SetValue(event.url)

        index = self.type.findData(event.type_id)
        if index >= 0:
            self.type.setCurrentIndex(index)

    def save(self):
        self.event_remove_from_cache(self.event)

        self.event.title = self.title.text()
        self.event.start_date = self.start.dateTime()
        self.event.end_date = self.end.dateTime()
        self.event.url = self.multi_field.serialize()
        self.event.type_id = self.type.currentData()

        self.event_add_to_cache(self.event)
        super().save()


class DailyEventWidget(BaseEventWidget):
    def __init__(self, event: models.DailyEvent = None, parent=None):

        self.title = QLineEdit()
        self.date = QDateEdit()
        self.date.setDisplayFormat("dd.MM")
        self.date.setCalendarPopup(True)
        self.type = QComboBox()
        self._fill_types(self.type)
        super().__init__(event, parent)

    def GetFields(self) -> List[QWidget]:
        if self.event.get_access() >= GROUP_ACCESS.EDITOR:
            return [self.title, self.date, self.type]
        else:
            return [self.title, self.date]

    def load(self, e: models.DailyEvent):
        self.title.setText(e.title or "")

        self.date.setDate(QDate(date.today().year, e.month, e.day))
        if e.type_id is not None:
            index = self.type.findData(e.type_id)
            if index >= 0:
                self.type.setCurrentIndex(index)

    def save(self):
        self.event_remove_from_cache(self.event)

        self.event.title = self.title.text()
        self.event.day = int(self.date.date().toString("dd"))
        self.event.month = int(self.date.date().toString("MM"))
        self.event.type_id = self.type.currentData()

        self.event_add_to_cache(self.event)

        super().save()

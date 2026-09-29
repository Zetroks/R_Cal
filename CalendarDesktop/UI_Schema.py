from dataclasses import dataclass
from datetime import time

from CalendarService import models
from PyQt5.QtWidgets import QLineEdit, QDateEdit, QWidget, QDateTimeEdit

from .MultiFields.MultiField import MultiField
from .pydantic_modal_widgets import QDateEditPopup, QTypeComboBox, QDateTimeEditPopup, CustomDateEdit
from typing import Callable, Any


@dataclass
class UISchema:
    hidden: bool = False
    widget: type | None = None
    label: str | None = None
    getter: Callable[[QWidget], Any] | None = None
    post_init_widget: Callable[[QWidget], Any] | None = None
    group: str | None = None


class WidgetTypeMissmatch(Exception): ...


def GetTypeCBData(widget: QWidget):
    if isinstance(widget, QTypeComboBox):
        return widget.currentData()
    raise WidgetTypeMissmatch()


def GetDEMonth(widget: QWidget):
    if isinstance(widget, QDateEdit):
        return widget.date().month()
    raise WidgetTypeMissmatch()


def GetDEDay(widget: QWidget):
    if isinstance(widget, QDateEdit):
        return widget.date().day()
    raise WidgetTypeMissmatch()


def PostInitStartDate(widget: QWidget):
    if isinstance(widget, (QDateTimeEdit, CustomDateEdit)):
        widget.setTime(time(0, 0))
    else:
        raise WidgetTypeMissmatch()


def PostInitEndDate(widget: QWidget):
    if isinstance(widget, (QDateTimeEdit, CustomDateEdit)):
        widget.setTime(time(23, 0))
    else:
        raise WidgetTypeMissmatch()

def GetMultiFieldData(widget) -> str:
    if isinstance(widget, MultiField):
        return widget.serialize()
    raise WidgetTypeMissmatch()

UI = {
    models.AnnualEvent: {
        "event_type": UISchema(hidden=True),
        "id": UISchema(hidden=True),
        "title": UISchema(widget=QLineEdit, label="Название"),
        "start_date": UISchema(widget=CustomDateEdit, label="Дата начала", post_init_widget=PostInitStartDate),
        "end_date": UISchema(widget=CustomDateEdit, label="Дата окончания", post_init_widget=PostInitEndDate),
        "url": UISchema(widget=MultiField, label="Доп поля", getter=GetMultiFieldData),
        "version": UISchema(hidden=True),
        "type_id": UISchema(widget=QTypeComboBox, getter=GetTypeCBData, label="Тип"),
        "sync_id": UISchema(hidden=True),
        "is_deleted": UISchema(hidden=True),
    },
    models.DailyEvent: {
        "event_type": UISchema(hidden=True),
        "id": UISchema(hidden=True),
        "title": UISchema(widget=QLineEdit, label="Название"),
        "day": UISchema(widget=QDateEditPopup, group="date", label="Дата", getter=GetDEDay),
        "month": UISchema(widget=QDateEditPopup, group="date", label="Дата", getter=GetDEMonth),
        "version": UISchema(hidden=True),
        "type_id": UISchema(widget=QTypeComboBox, getter=GetTypeCBData, label="Тип"),
        "sync_id": UISchema(hidden=True),
        "is_deleted": UISchema(hidden=True),
    }
}


from . import UI_Schema

from PyQt5.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QDateEdit,
    QSpinBox, QComboBox, QPushButton, QWidget, QDateTimeEdit
)
from PyQt5.QtCore import QDate, QDateTime
from pydantic import BaseModel
from datetime import date, datetime
from typing import Type

from ..pydantic_modal_widgets import CustomDateEdit


class PydanticModal(QDialog):
    def __init__(self, model_cls: type[BaseModel], instance: BaseModel | None = None, parent=None, current_date:date = None):
        super().__init__(parent)
        self.current_date = current_date
        self.model_cls = model_cls
        self.model_ui_schema = UI_Schema.UI.get(self.model_cls, {})
        self.instance = instance
        self.fields = {}
        self.unique_widgets = {}
        self.setWindowTitle(model_cls.__name__)

        self.layout = QFormLayout(self)

        self._build_form()
        self._add_buttons()


    def _build_form(self):
        for name, field in self.model_cls.model_fields.items():
            schema: UI_Schema.UISchema = self.model_ui_schema.get(name, None)
            if schema is None or schema.hidden:
                continue

            unique = schema.group
            title = schema.label or name
            widget = None
            if unique:
                if unique in self.unique_widgets:
                    self.fields[name] = self.unique_widgets[unique]
                else:
                    self.unique_widgets[unique] = self._create_widget(schema.widget)
                    widget = self.unique_widgets[unique]
                    if schema.post_init_widget:
                        schema.post_init_widget(widget)

            else:
                widget = self._create_widget(schema.widget)
                if schema.post_init_widget:
                    schema.post_init_widget(widget)

            if widget is None:
                continue

            self.fields[name] = widget
            self.layout.addRow(title, widget)

            # preload value
            # if self.instance:
            #     value = getattr(self.instance, name, None)
            #     if value is not None:
            #         self._set_value(widget, value, ui)

    def _create_widget(self, widget_class: Type[QWidget]|None) -> QWidget|None:
        if not widget_class:
            return None
        widget = widget_class()
        if isinstance(widget, QDateEdit):
            if self.current_date:
                widget.setDate(self.current_date)
        if isinstance(widget, QDateTimeEdit):
            if self.current_date:
                widget.setDateTime(datetime(self.current_date.year, self.current_date.month, self.current_date.day))
        if isinstance(widget, CustomDateEdit):
            widget.setDate(self.current_date)
        return widget


    @staticmethod
    def _set_value(widget, value):
        if isinstance(widget, QLineEdit):
            widget.setText(str(value))

        elif isinstance(widget, QDateEdit):
            if isinstance(value, date):
                widget.setDate(QDate(value.year, value.month, value.day))

        elif isinstance(widget, QSpinBox):
            widget.setValue(int(value))

        elif isinstance(widget, QComboBox):
            idx = widget.findText(str(value))
            if idx >= 0:
                widget.setCurrentIndex(idx)
        elif isinstance(widget, CustomDateEdit):
            widget.setDateTime(value)


    def get_data(self) -> BaseModel:
        data = {}

        for name, field in self.model_cls.model_fields.items():
            schema: UI_Schema.UISchema = self.model_ui_schema.get(name, None)
            if schema is None or schema.hidden:
                continue

            widget = self.fields[name]
            data[name] = self._read_value(widget, schema.getter)

        return self.model_cls(**data)

    @staticmethod
    def _read_value(widget, getter = None):
        if getter:
            return getter(widget)

        if isinstance(widget, QLineEdit):
            return widget.text()

        if isinstance(widget, QDateEdit):
            d = widget.date()
            return date(d.year(), d.month(), d.day())

        if isinstance(widget, QSpinBox):
            return widget.value()

        if isinstance(widget, QComboBox):
            return widget.currentText()

        if isinstance(widget, QDateTimeEdit):
            return widget.dateTime().toPyDateTime()

        if isinstance(widget, CustomDateEdit):
            return widget.dateTime()

        return None


    def _add_buttons(self):
        btn = QPushButton("OK")
        btn.clicked.connect(self.accept) # type: ignore
        self.layout.addRow(btn)
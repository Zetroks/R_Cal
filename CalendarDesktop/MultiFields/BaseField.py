from typing import Set, Tuple, Dict, Type, Iterator

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QToolButton, QApplication, QStyle

from ..AppStorage import AppStorage
from CalendarService.models import BaseEvent


class BaseField(QWidget):
    type_name = "BASE"
    action: str | None = None
    _registry_: Dict[str, Type['BaseField']] = {}
    icon = None
    on_data_changed = pyqtSignal()
    def __init__(self, value="", parent=None):
        super().__init__(parent)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        if self.__class__.action is not None:
            edit_button = QToolButton(self)
            edit_button.setToolTip(self.__class__.action)
#             edit_button.setToolTip("""
# <b>Add field</b><br>
# Создаёт новое поле в списке<br>
# <i>Ctrl+N</i>
# """)
            if self.icon is None:
                icon = QApplication.style().standardIcon(QStyle.SP_CommandLink)
            elif isinstance(self.icon, str):
                icon = QIcon(str(AppStorage().get_icon_path(self.icon)))
            else:
                icon = QApplication.style().standardIcon(QStyle.SP_CommandLink)

            edit_button.setIcon(icon)
            edit_button.setCursor(Qt.PointingHandCursor)
            edit_button.setAutoRaise(True)
            edit_button.clicked.connect(self.on_action)  # type: ignore
            edit_button.resize(20, 20)

            self.layout.addWidget(edit_button)

        self.editor = QLineEdit(value)
        self.editor.textEdited.connect(self.data_changed)# type: ignore
        self.layout.addWidget(self.editor)
    def data_changed(self):
        self.on_data_changed.emit() # type: ignore
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        t = getattr(cls, "type_name", None)
        if not t or t == "base":
            return

        if t in BaseField._registry_:
            raise ValueError(f"Duplicate field type: {t}")

        BaseField._registry_[t] = cls

    def get_value(self):
        return self.editor.text()

    def set_value(self, value: str):
        self.editor.setText(value)

    def on_action(self):
        pass

    @staticmethod
    def find_best_field_type(value:str) -> str:
        ret_type = BaseField.type_name
        ret_value = -1
        for field_type, field_class in BaseField.field_types_iterator():
            passed, confidence_value = field_class.perform_type_check(value)
            if passed:
                if confidence_value > ret_value:
                    ret_type = field_type
                    ret_value = confidence_value
        return ret_type


    @classmethod
    def field_types_iterator(cls) -> Iterator[Tuple[str, Type['BaseField']]]:
        for field_type, field_class in cls._registry_.items():
            yield field_type, field_class

    @staticmethod
    def perform_type_check(value) -> Tuple[bool, int]:
        return True, 0

    @classmethod
    def GetWidgetForType(cls, type_name: str) -> Type['BaseField']:
        return cls._registry_.get(type_name, cls)

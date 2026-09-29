import json

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPushButton, QHBoxLayout, QDialog, QLabel, QLineEdit

from .BaseField import BaseField

class AddFieldDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Add field")

        self.layout = QVBoxLayout(self)

        self.layout.addWidget(QLabel("Field type:"))

        self.input = QLineEdit()
        self.input.setPlaceholderText("url / geo / comment ...")
        self.layout.addWidget(self.input)

        btn_layout = QHBoxLayout()

        self.ok_btn = QPushButton("OK")
        self.cancel_btn = QPushButton("Cancel")

        btn_layout.addWidget(self.ok_btn)
        btn_layout.addWidget(self.cancel_btn)

        self.layout.addLayout(btn_layout)

        self.ok_btn.clicked.connect(self.accept)# type: ignore
        self.cancel_btn.clicked.connect(self.reject)# type: ignore

    def get_value(self):
        return self.input.text().strip()

class MultiField(QWidget):
    on_data_changed = pyqtSignal()
    def __init__(self, value: str = "", parent=None):
        super().__init__(parent)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 6, 0, 6)
        self.fields_container = QVBoxLayout()
        self.layout.addLayout(self.fields_container)

        self.add_btn = QPushButton("Add")
        self.add_btn.clicked.connect(self.add_field_dialog)# type: ignore
        self.layout.addWidget(self.add_btn)

        self.fields = []

    def data_changed(self):
        self.on_data_changed.emit()# type: ignore
    # -------- parsing --------
    def SetValue(self, value):
        while self.fields_container.count():
            item = self.fields_container.takeAt(0)

            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        # 2. очистить модель
        self.fields.clear()
        self.parse(value)

    def parse(self, value: str):
        if not value:
            return
        try:
            data = json.loads(value)
        except json.JSONDecodeError:
            data = {}
        for field_type, field_items in data.items():
            for field_item in field_items:
                self.add_field(field_type, field_item)


    # -------- UI creation --------
    def add_field(self, field_type: str, value=""):
        cls = BaseField.GetWidgetForType(field_type)

        field = cls(value)
        field.on_data_changed.connect(self.data_changed) # type: ignore
        self.fields.append((field_type, field))
        self.fields_container.addWidget(field)

        # ctrl+lmb hook
        # field.mousePressEvent = self._make_click_handler(field)

    def _make_click_handler(self, field):
        def handler(event):
            if event.modifiers() & Qt.ControlModifier and event.button() == Qt.LeftButton:
                field.on_ctrl_lmb()
            QWidget.mousePressEvent(field, event)
        return handler

    # -------- add menu --------
    def add_field_dialog(self):
        dialog = AddFieldDialog(self)

        if dialog.exec_() == QDialog.Accepted:
            field_value = dialog.get_value()
            if field_value:
                field_type = BaseField.find_best_field_type(field_value)

                self.add_field(field_type, field_value)
                self.data_changed()

    # -------- serialization --------
    def serialize(self) -> str:
        data = {}
        for field_type, field in self.fields:
            if field_type not in data:
                data[field_type] = []
            data[field_type].append(field.get_value())

        return json.dumps(data)
from PyQt5.QtWidgets import QScrollArea, QWidget, QVBoxLayout, QLabel

from CalendarService.models import BaseEvent


class DispatchListWidget(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWidgetResizable(True)

        # content widget
        self.content = QWidget()

        # vertical list
        self.layout = QVBoxLayout(self.content)

        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(4)

        # чтобы элементы прижимались вверх
        self.layout.addStretch()

        self.setWidget(self.content)

    def add_item(self, widget: QWidget):
        # вставляем перед stretch
        self.layout.insertWidget(
            self.layout.count() - 1,
            widget
        )

    def add_item_event(self, event:BaseEvent):
        self.add_item(QLabel(event.title))
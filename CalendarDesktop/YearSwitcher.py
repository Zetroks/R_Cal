"""Переключатель года: [◀] [ LCD ] [▶] над списком групп."""

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLCDNumber
from PyQt5.QtCore import pyqtSignal


class YearSwitcher(QWidget):
    step = pyqtSignal(int)  # +1 / -1

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.prev_btn = QPushButton("◀")
        self.prev_btn.setFixedSize(30, 30)
        self.prev_btn.clicked.connect(lambda: self.step.emit(-1))  # type: ignore

        self.lcd = QLCDNumber()
        self.lcd.setDigitCount(4)
        self.lcd.setSegmentStyle(QLCDNumber.Flat)
        self.lcd.setMinimumHeight(36)

        self.next_btn = QPushButton("▶")
        self.next_btn.setFixedSize(30, 30)
        self.next_btn.clicked.connect(lambda: self.step.emit(1))  # type: ignore

        layout.addWidget(self.prev_btn)
        layout.addWidget(self.lcd, 1)
        layout.addWidget(self.next_btn)

    def set_year(self, year: int):
        self.lcd.display(year)

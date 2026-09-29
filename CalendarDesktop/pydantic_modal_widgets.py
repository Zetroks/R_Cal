from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFontMetrics
from PyQt5.QtWidgets import QDateEdit, QComboBox, QDateTimeEdit, QWidget, QFormLayout, QHBoxLayout, QSpinBox, \
    QAbstractSpinBox, QLabel, QSizePolicy
from datetime import date, datetime, time

from CalendarService.dto_models import GROUP_ACCESS
from CalendarService.db_cashe import cache


class QDateEditPopup(QDateEdit):
    def __init__(self, parent=None, current_date: date = None):
        super().__init__(parent)
        self.setCalendarPopup(True)
        if current_date:
            self.setDate(current_date)


class QDateTimeEditPopup(QDateTimeEdit):
    def __init__(self, parent=None, current_date: date = None):
        super().__init__(parent)
        self.setCalendarPopup(True)
        if current_date:
            self.setDateTime(datetime(current_date.year, current_date.month, current_date.day))


class QTypeComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)

        for group in cache.get().groups_iterator():
            if group.get_access() >= GROUP_ACCESS.EDITOR:
                self.addItem(group.name, group.id)
            # types_access_iterator(ACCESS_OPERATION.HIGHER_THAN, ACCESS_ENUM.MEMBER)
            # _t = cache.get().group_id2groups[t]

class FixedWSpinBox(QSpinBox):
    def __init__(self, _max:int, parent=None, _min = 0):
        super().__init__(parent)
        self.setMinimum(_min)
        self.setMaximum(_max)
        self.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)

        w = QFontMetrics(self.font()).horizontalAdvance("0" * len(str(_max))) + 10
        self.setFixedWidth(w)

class CustomDateEdit(QWidget):
    on_data_changed = pyqtSignal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.colon = QLabel()
        self.colon.setText(":")
        self.colon.setContentsMargins(0, 0, 0, 0)
        self.colon.setMargin(0)
        self.colon.setIndent(0)
        self.colon.setMinimumWidth(0)
        self.colon.setSizePolicy(QSizePolicy.Policy.Fixed,
                                 QSizePolicy.Policy.Fixed)
        self.date = QDateEditPopup()
        self.hour = FixedWSpinBox(23)
        self.minute = FixedWSpinBox(59)
        self.date.dateChanged.connect(self.data_changed) # type: ignore
        self.hour.valueChanged.connect(self.data_changed) # type: ignore
        self.minute.valueChanged.connect(self.data_changed) # type: ignore
        self.layout.addWidget(self.date)
        self.layout.addWidget(self.hour)
        self.layout.addWidget(self.colon)
        self.layout.addWidget(self.minute)

    def data_changed(self):
        self.on_data_changed.emit() # type: ignore

    def setDateTime(self, dt: datetime):
        self.setDate(dt.date())
        self.setTime(dt.time())

    def setDate(self, d: date):
        self.date.setDate(d)

    def setTime(self, t: time):
        self.hour.setValue(t.hour)
        self.minute.setValue(t.minute)

    def dateTime(self) -> datetime:
        dt = self.date.dateTime().toPyDateTime()
        return dt.replace(hour=self.hour.value(), minute=self.minute.value())




from datetime import date, datetime, timedelta
from typing import List

from PyQt5.QtCore import Qt, QRect
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import QFrame

from CalendarService import models
from CalendarService.db_cashe import cache


class HintEvent:
    def __init__(self, *, from_event: models.BaseEvent = None, current: date):
        self.title = from_event.title
        self.start, self.end = from_event.getDatetimeRange(current)
        self.level = -1
        self.color = QColor(cache.get().get_event_group(from_event).color)
        self.textColor = self.get_text_color(self.color)
        self.group_name = cache.get().get_event_group(from_event).name

    def intersects(self, other: 'HintEvent') -> bool:
        return not (self.end < other.start or self.start > other.end)

    @staticmethod
    def get_text_color(bg_color: QColor) -> QColor:
        r = bg_color.red()
        g = bg_color.green()
        b = bg_color.blue()

        luminance = 0.299 * r + 0.587 * g + 0.114 * b

        return QColor(0, 0, 0) if luminance > 160 else QColor(255, 255, 255)

    def get_text(self):
        return f"{self.title}"
        # return f"{self.title} ({self.group_name})"


class DayHintWidget(QFrame):
    def __init__(self):
        super().__init__(None, Qt.ToolTip)
        self.setMinimumHeight(80)
        self._events: List[HintEvent] = []
        self.current_date: date | None = None
        self.day_start_datetime: datetime | None = None
        self.day_end_datetime: datetime | None = None

    def build_layout(self, events: models.DayEvents):
        self._events.clear()
        if events is None:
            return
        for event in [*events.daily, *events.annual]:
            self._events.append(HintEvent(from_event=event, current=self.current_date))

        self._events.sort(key=lambda x: x.start)

        levels: List[List[HintEvent]] = []

        for event in self._events:
            for level_idx, level in enumerate(levels):
                if not any(event.intersects(other) for other in level):
                    level.append(event)
                    event.level = level_idx
                    break
            else:
                levels.append([event])
                event.level = len(levels) - 1

    def set_events(self, events, current_date: date):
        self._events = []
        self.current_date = current_date
        self.day_start_datetime = datetime(current_date.year, current_date.month, current_date.day)
        self.day_end_datetime = self.day_start_datetime + timedelta(days=1)

        self.build_layout(events)
        self.update()
        self.adjustSize()


    def paintEvent(self, event):
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setBrush(QColor(255, 255, 255))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

        width = self.width()

        left_pad = 20
        right_pad = 20
        rect_round = 4
        overflow = right_pad + rect_round
        timeline_y = 20
        bar_h = 15
        usable_width = width - left_pad - right_pad
        if self._events:
            max_level = max(self._events, key = lambda x: x.level).level + 1
        else:
            max_level = 0
        height = timeline_y + 10 + max_level * (bar_h + 4)
        self.setFixedHeight(height)

        def time_to_x(dt):
            if dt < self.day_start_datetime:
                minutes = 0
            elif dt > self.day_end_datetime:
                minutes = 24 * 60
            else:
                minutes = dt.hour * 60 + dt.minute
            return left_pad + int(minutes / (24 * 60) * usable_width)

        grid_color = QColor(200, 200, 200, 80)
        painter.setPen(grid_color)
        for hour in range(25):
            x = left_pad + int(hour / 24 * usable_width)
            painter.drawLine(x, timeline_y - 5, x, height)
        painter.setPen(Qt.black)

        for hour in range(0, 25, 3):
            x = left_pad + int(hour / 24 * usable_width)
            painter.drawText(x - 10, timeline_y - 7, f"{hour:02d}:00")
        painter.drawLine(left_pad, timeline_y, width - right_pad, timeline_y)

        for ev in self._events:
            x1 = time_to_x(ev.start)
            x2 = time_to_x(ev.end)
            if ev.start < self.day_start_datetime:
                x1 -= overflow
            if ev.end > self.day_end_datetime:
                x2 += overflow

            y = timeline_y + 10 + ev.level * (bar_h + 4)
            rect = QRect(x1, y, x2 - x1, bar_h)
            painter.setBrush(ev.color)
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(rect, rect_round, rect_round)
            painter.setPen(ev.textColor)
            font = painter.font()
            font.setBold(True)
            painter.setFont(font)
            fm = painter.fontMetrics()
            title = ev.get_text()
            text = fm.elidedText(title, Qt.ElideRight, rect.width())
            painter.drawText(rect.adjusted(4, 0, -4, 0), Qt.AlignCenter, text)

        painter.setBrush(QColor(0,0,0,0))
        painter.setPen(QColor(0, 0, 0))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

        # for i, ev in enumerate(self._events):
        #     if isinstance(ev, models.DailyEvent):
        #         start = datetime(date.today().year, ev.month, ev.day)
        #         end = start + timedelta(hours=23, minutes=59, seconds=59)
        #     elif isinstance(ev, models.AnnualEvent):
        #         start = ev.start_date
        #         end = ev.end_date
        #     else:
        #         raise Exception
        #     color = QColor(cache.get().get_event_group(ev).color)
        #
        #     x1 = time_to_x(start)
        #     x2 = time_to_x(end)
        #     if start < self.day_start_datetime:
        #         x1 -= overflow
        #     if end > self.day_end_datetime:
        #         x2 += overflow
        #
        #     y = timeline_y + 10 + i * (bar_h + 4)
        #     rect = QRect(x1, y, x2 - x1, bar_h)
        #     painter.setBrush(color)
        #     painter.setPen(Qt.NoPen)
        #     painter.drawRoundedRect(rect, 4, 4)
        #     painter.setPen(self.get_text_color(color))
        #     font = painter.font()
        #     font.setBold(True)
        #     painter.setFont(font)
        #     fm = painter.fontMetrics()
        #     title = f"{ev.title} ({cache.get().get_event_group(ev).name})"
        #     text = fm.elidedText(title, Qt.ElideRight, rect.width())
        #     painter.drawText(rect.adjusted(4, 0, -4, 0), Qt.AlignCenter, text)

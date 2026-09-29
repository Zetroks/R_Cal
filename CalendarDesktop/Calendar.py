import calendar
from typing import List, Dict
from datetime import datetime, date, timedelta
from PyQt5.QtWidgets import QWidget, QGridLayout
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPainterPath, QFontMetrics, QPaintEvent, QMouseEvent
from PyQt5.QtCore import QRect, pyqtSignal, QPointF, QThread, QTimer, Qt, QPoint

from .CalendarDayHint import DayHintWidget
from CalendarService.db_cashe import cache
from .production_calendar import ProductionCalendar, DayType
from .VisibilityControl import VisibilityControl
from .ThreadService import CollectYearWorker, WorkerExistException
from CalendarService import models


class CalendarWidget(QWidget):
    date_clicked: pyqtSignal = pyqtSignal(date)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._grid_left = None
        self._grid_top = None
        self._cell_h = None
        self._cell_w = None

        self.current_date = datetime.now()
        self._month_days: List[List[date]] = []
        self._rows = 0
        self._cols = 0
        self.header_height = 20  # month row
        self.weekdays_height = 20  # Пн Вт ...
        self.week_number_width = 0
        self.year_data: models.YearEvents | None = None
        # self.day_data:Dict[date, DayDict] = {}
        self.day_layout: Dict[date, List[dict]] = {}
        self.setMouseTracking(True)
        self.production_calendar = None

        self._hint_widget = DayHintWidget()
        self._hovered_day: date | None = None
        self._hint_timer = QTimer(self)
        self._hint_timer.setSingleShot(True)
        self._hint_timer.timeout.connect(self.show_hint)  # type: ignore
        self._hover_pos: QPoint | None = None

    def build_month_layout(self):
        year = self.current_date.year
        month = self.current_date.month

        # === 1. collect all month events ===
        events = []

        cal = calendar.Calendar(firstweekday=0)

        self.year_data = cache.get().year_data.get(year, None)
        if self.year_data is None:
            return

        for week in cal.monthdatescalendar(year, month):
            for day in week:
                data = self.year_data.Events.get(day, None)
                if data is None:
                    continue

                for e in data.annual:
                    events.append(e)

                for e in data.daily:
                    events.append(e)

        # remove duplicates
        events = list({(type(e), e.id): e for e in events}.values())

        # === 2. normalize into ranges ===
        normalized = []

        for e in events:
            if not VisibilityControl.get().ShouldBeVisible(e.type_id):
                continue

            if isinstance(e, models.AnnualEvent):
                start = e.start_date.date()
                end = e.end_date.date()
            elif isinstance(e, models.DailyEvent):
                start = date(year, e.month, e.day)
                end = start
            else:
                raise ValueError(f"Unexpected event type: {type(e)}")

            normalized.append({
                "event": e,
                "start": start,
                "end": end,
                "color": cache.get().group_id2groups[e.type_id].color
            })

        # === 3. sort ===
        normalized.sort(key=lambda x: x["start"])

        # === 4. layout by levels ===
        levels = []

        def intersects(a, b):
            return not (a["end"] < b["start"] or a["start"] > b["end"])

        for ev in normalized:
            placed = False

            for level in levels:
                if not any(intersects(ev, other) for other in level):
                    level.append(ev)
                    placed = True
                    break

            if not placed:
                levels.append([ev])

        # === 5. days layout ===
        self.day_layout.clear()

        for level_index, level in enumerate(levels):
            for ev in level:
                d = ev["start"]
                while d <= ev["end"]:
                    if d not in self.day_layout:
                        self.day_layout[d] = []

                    self.day_layout[d].append({
                        "level": level_index,
                        "color": ev["color"],
                        "is_start": d == ev["start"],
                        "is_end": d == ev["end"]
                    })

                    d += timedelta(days=1)

    def invalidate_cache(self):
        self.build_month_layout()
        self.update()

    def show_month(self, dt: datetime):
        self.production_calendar = ProductionCalendar.get(dt.year)
        self.current_date = dt
        self.invalidate_cache()

    @staticmethod
    def draw_rect(painter: QPainter, rect: QRect) -> None:
        painter.setPen(Qt.black)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(rect)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)

        year = self.current_date.year
        month = self.current_date.month

        cal = calendar.Calendar(firstweekday=0)
        month_days = cal.monthdatescalendar(year, month)

        self._month_days = month_days
        self._rows = len(month_days)
        self._cols = 7

        grid_top = self.header_height + self.weekdays_height
        grid_left = self.week_number_width

        grid_w = self.width() - grid_left
        grid_h = self.height() - grid_top

        cell_w = grid_w // self._cols - 1
        cell_h = grid_h // self._rows

        self._cell_w = cell_w
        self._cell_h = cell_h
        self._grid_top = grid_top
        self._grid_left = grid_left

        # === 1. MOUTH ===
        month_name = self.current_date.strftime("%B %Y")
        rect = QRect(0, 0, cell_w * self._cols + grid_left, self.header_height)
        self.draw_rect(painter, rect)
        painter.drawText(rect, Qt.AlignCenter, month_name)

        # === 2. WEEKS ===

        weekdays = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

        for col in range(7):
            rect = QRect(
                grid_left + col * cell_w,
                self.header_height,
                cell_w,
                self.weekdays_height
            )
            self.draw_rect(painter, rect)
            painter.drawText(rect, Qt.AlignCenter, weekdays[col])

        # === 3. WEEK NUMBERS ===
        if self.week_number_width > 0:
            for row, week in enumerate(month_days):
                week_number = week[0].isocalendar()[1]

                rect = QRect(
                    0,
                    grid_top + row * cell_h,
                    self.week_number_width,
                    cell_h
                )
                self.draw_rect(painter, rect)
                painter.drawText(rect, Qt.AlignCenter, str(week_number))

        # === 4. GRID ===
        for row, week in enumerate(month_days):
            for col, day in enumerate(week):
                rect = QRect(
                    grid_left + col * cell_w,
                    grid_top + row * cell_h,
                    cell_w,
                    cell_h
                )

                self.draw_cell(painter, rect, day, month)
        corner_rect = QRect(0, self.header_height, self.week_number_width, self.weekdays_height)
        self.draw_rect(painter, corner_rect)

    def draw_cell(self, painter, rect: QRect, day: date, current_month: int):
        painter.save()

        if day.month == current_month:
            self.draw_cell_content(painter, rect, day)

        painter.setPen(QPen(Qt.black))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(rect)

        if day.month != current_month:
            painter.setOpacity(0.3)
            painter.setPen(Qt.black)
            painter.drawText(rect.adjusted(4, 4, -4, -4), Qt.AlignCenter | Qt.AlignCenter, str(day.day))
        else:
            if isinstance(self.production_calendar, ProductionCalendar):
                day_data = self.production_calendar.GetDayData(day.day, day.month)
                if day_data == DayType.HOLIDAY:
                    font = QFont("Arial", 12, QFont.Bold)
                elif day_data == DayType.SHORT:
                    font = QFont("Arial", 12)
                    font.setUnderline(True)
                else:
                    font = QFont("Arial", 12)
                self.draw_text(painter, rect, str(day.day), font)
                painter.setFont(font)

        painter.restore()

    def draw_text(self, painter: QPainter, rect: QRect, text: str, font: QFont):
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        painter.setPen(QPen(Qt.black, 3))
        painter.setBrush(QColor(255, 248, 240))

        font.setHintingPreference(QFont.PreferFullHinting)
        path = QPainterPath()

        fm = QFontMetrics(font)

        text_width = fm.horizontalAdvance(text)
        text_height = fm.height()

        x = rect.center().x() - text_width / 2
        y = rect.center().y() + text_height / 3

        path.addText(QPointF(x, y), font, text)

        # 1. contour
        painter.setPen(QPen(self.palette().color(self.backgroundRole()), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

        # 2. fill
        painter.setPen(Qt.NoPen)
        painter.setBrush(Qt.black)
        painter.drawPath(path)

    def mousePressEvent(self, event):
        if not hasattr(self, "_month_days"):
            return

        x = event.x()
        y = event.y()

        # === in calendar zone ===
        grid_left = self.week_number_width
        grid_top = self.header_height + self.weekdays_height

        x -= grid_left
        y -= grid_top

        if x < 0 or y < 0:
            return

        col = x // self._cell_w
        row = y // self._cell_h

        if 0 <= row < self._rows and 0 <= col < self._cols:
            clicked_date = self._month_days[row][col]
            self.date_clicked.emit(clicked_date)  # type: ignore

    def draw_cell_content(self, painter: QPainter, rect: QRect, day: date):
        if day == datetime.date(datetime.now()):
            self.fill_cell(painter, rect, QColor(255, 255, 0))

        layout = self.day_layout.get(day, [])

        stripe_h = 8
        padding = 4

        for item in layout:
            y = rect.top() + item["level"] * stripe_h

            left = rect.left()
            right = rect.right() + 1

            if item["is_start"]:
                left += padding

            if item["is_end"]:
                right -= padding

            painter.fillRect(
                QRect(left, y, right - left, stripe_h - 2),
                QColor(item["color"])
            )

    @staticmethod
    def fill_cell(painter: QPainter, rect: QRect, color: QColor):
        painter.save()
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.NoPen)
        painter.drawRect(rect)
        painter.restore()

    def get_day_at(self, pos: QPoint) -> date | None:
        x, y = pos.x(), pos.y()

        grid_left = self.week_number_width
        grid_top = self.header_height + self.weekdays_height

        x -= grid_left
        y -= grid_top

        if x < 0 or y < 0:
            self.setToolTip("")
            return None

        col = x // self._cell_w
        row = y // self._cell_h

        if 0 <= row < self._rows and 0 <= col < self._cols:
            return self._month_days[row][col]
        return None

    def show_hint(self):
        if self._hovered_day is None:
            return

        events = self.get_events_for_day(self._hovered_day)

        self._hint_widget.set_events(events, self._hovered_day)

        pos = self._hover_pos + QPoint(16, 16)

        self._hint_widget.move(pos)
        self._hint_widget.show()

    def show_hovered_day(self, hovered_day: date | None, pos: QPoint | None = None):
        # print(f"New hovered day: {hovered_day}, Old hovered day: {self._hovered_day} ")
        self._hovered_day = hovered_day
        self._hint_timer.stop()
        self._hint_widget.hide()

        if hovered_day is not None:
            self._hover_pos = pos
            self._hint_timer.start(500)

    def mouseMoveEvent(self, event: QMouseEvent):
        hovered_day = self.get_day_at(event.pos())
        if hovered_day != self._hovered_day:
            self.show_hovered_day(hovered_day, event.globalPos())

    def leaveEvent(self, event):
        self.show_hovered_day(None)

    def get_events_for_day(self, day: date) -> models.DayEvents | None:
        if self.year_data is None:
            return None
        return self.year_data.Events.get(day, None)


class YearWidget(QWidget):
    def do_show_year(self, year: models.YearEvents):
        cache.get().set_year_data(year.Year, year)
        for cal in self.calendars:
            cal.invalidate_cache()

    def start_show_year(self, year: int):
        self.collect_year_thread = QThread()
        try:
            worker = CollectYearWorker.get(year)
        except WorkerExistException:
            return  # TODO: add fail message

        worker.moveToThread(self.collect_year_thread)
        self.collect_year_thread.started.connect(worker.run)  # type: ignore
        worker.finished.connect(self.do_show_year)
        self.collect_year_thread.start()

    def __init__(self, year: int):
        self.collect_year_thread = None
        super().__init__()

        layout = QGridLayout(self)
        layout.setSpacing(5)

        self.calendars = []
        self.start_show_year(year)

        for month in range(1, 13):
            cal = CalendarWidget()
            cal.show_month(datetime(year, month, 1))

            row = (month - 1) // 4
            col = (month - 1) % 4

            layout.addWidget(cal, row, col)
            self.calendars.append(cal)

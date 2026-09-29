from PyQt5.QtWidgets import QHBoxLayout, QWidget, QVBoxLayout, QLabel, QFrame, QToolButton, QApplication, QStyle, \
    QDialog, QColorDialog, QPushButton, QSizePolicy, QLineEdit, QGridLayout
from PyQt5.QtGui import QPainter, QPen, QWindow, QColor
from PyQt5.QtCore import Qt, pyqtSignal

from CalendarService import dto_models
from CalendarService.dto_models import GROUP_ACCESS
from CalendarService.models import EventGroup
from .VisibilityControl import VisibilityControl
from CalendarService.db_cashe import cache



# ---------------------------------------------
# Заглушка под future sharing settings widget
# ---------------------------------------------

class GroupSharingWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setFrameShape(QFrame.Shape.StyledPanel)

        layout = QVBoxLayout(self)

        title = QLabel("Sharing settings")
        title.setStyleSheet("font-weight: bold;")

        layout.addWidget(title)

        # TODO:
        # future:
        # - members list
        # - roles
        # - invite links
        # - permissions
        # etc.

class ClickableColorPreview(QFrame):
    clicked = pyqtSignal()

    def __init__(self, color: str = "#ffffff", parent=None):
        super().__init__(parent)

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(28)

        self.set_color(color)

    def set_color(self, color: str):
        self.setStyleSheet(f"""
            QFrame {{
                background: {color};
                border: 1px solid #666;
                border-radius: 6px;
            }}
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

        super().mousePressEvent(event)

class GroupEditWidget(QDialog):
    def __init__(self, group: EventGroup, parent=None):
        super().__init__(parent)

        self.group = group

        self.server_name = group.name
        self.server_color = group.color

        self.local_name: str | None = None
        self.local_color: str | None = None

        self.setWindowTitle("Edit group")
        self.setModal(True)
        self.resize(700, 500)

        self.main_layout = QVBoxLayout(self)

        # =====================================================
        # Header
        # =====================================================

        self.grid = QGridLayout()

        self.grid.setColumnStretch(0, 0)
        self.grid.setColumnStretch(1, 1)
        self.grid.setColumnStretch(2, 1)

        self.grid.addWidget(QLabel(""), 0, 0)

        server_label = QLabel("SERVER")
        server_label.setStyleSheet("font-weight: bold;")

        local_label = QLabel("LOCAL")
        local_label.setStyleSheet("font-weight: bold;")

        self.grid.addWidget(server_label, 0, 1)
        self.grid.addWidget(local_label, 0, 2)

        # =====================================================
        # NAME
        # =====================================================

        self.grid.addWidget(QLabel("Name"), 1, 0)

        # ---------------- SERVER NAME ----------------

        self.server_name_edit = QLineEdit()
        self.server_name_edit.setText(self.server_name)

        self.grid.addWidget(self.server_name_edit, 1, 1)

        # ---------------- LOCAL NAME ----------------

        local_name_layout = QHBoxLayout()
        local_name_layout.setContentsMargins(0, 0, 0, 0)

        self.local_name_edit = QLineEdit()



        self.reset_local_name_button = QToolButton()
        icon = self.style().standardIcon(
            QStyle.StandardPixmap.SP_DialogResetButton
        )
        self.reset_local_name_button.setIcon(icon)
        self.reset_local_name_button.setFixedSize(24, 24)

        self.reset_local_name_button.setToolTip(
            "Reset local name"
        )
        self.reset_local_name_button.clicked.connect(
            self.reset_local_name
        )

        local_name_layout.addWidget(self.local_name_edit)
        local_name_layout.addWidget(self.reset_local_name_button)

        self.grid.addLayout(local_name_layout, 1, 2)

        # =====================================================
        # COLOR
        # =====================================================

        self.grid.addWidget(QLabel("Color"), 2, 0)

        # ---------------- SERVER COLOR ----------------

        server_color_layout = QHBoxLayout()
        server_color_layout.setContentsMargins(0, 0, 0, 0)

        self.server_color_preview = ClickableColorPreview(
            self.server_color
        )

        self.server_color_preview.clicked.connect(
            self.change_server_color
        )

        server_color_layout.addWidget(
            self.server_color_preview
        )


        self.grid.addLayout(server_color_layout, 2, 1)

        # ---------------- LOCAL COLOR ----------------

        local_color_layout = QHBoxLayout()
        local_color_layout.setContentsMargins(0, 0, 0, 0)

        self.local_color_preview = ClickableColorPreview(
            self.server_color
        )

        self.local_color_preview.clicked.connect(
            self.change_local_color
        )

        self.reset_local_color_button = QToolButton()
        icon = self.style().standardIcon(
            QStyle.StandardPixmap.SP_DialogResetButton
        )
        self.reset_local_color_button.setIcon(icon)
        self.reset_local_color_button.setFixedSize(24, 24)
        self.reset_local_color_button.setToolTip(
            "Reset local color"
        )
        self.reset_local_color_button.clicked.connect(
            self.reset_local_color
        )

        local_color_layout.addWidget(
            self.local_color_preview
        )
        local_color_layout.addWidget(
            self.reset_local_color_button
        )

        self.grid.addLayout(local_color_layout, 2, 2)

        self.main_layout.addLayout(self.grid)

        # =====================================================
        # Sharing
        # =====================================================

        self.sharing_widget = GroupSharingWidget()

        self.main_layout.addWidget(self.sharing_widget)

        # =====================================================
        # Bottom buttons
        # =====================================================

        buttons_layout = QHBoxLayout()

        buttons_layout.addStretch()

        self.cancel_button = QPushButton("Cancel")
        self.save_button = QPushButton("Save")

        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self.accept)

        buttons_layout.addWidget(self.cancel_button)
        buttons_layout.addWidget(self.save_button)

        self.main_layout.addLayout(buttons_layout)

        # =====================================================
        # Access update
        # =====================================================

        self.update_access()

    # =========================================================
    # ACCESS
    # =========================================================

    def can_edit_server_name(self) -> bool:
        """
        TODO:
        your logic
        """
        return False

    def can_edit_server_color(self) -> bool:
        """
        TODO:
        your logic
        """
        return False

    def update_access(self):
        self.server_name_edit.setEnabled(
            self.can_edit_server_name()
        )

    # =========================================================
    # LOCAL NAME
    # =========================================================

    def reset_local_name(self):
        self.local_name_edit.clear()

    # =========================================================
    # SERVER COLOR
    # =========================================================

    def change_server_color(self):
        color = QColorDialog.getColor(
            QColor(self.server_color),
            self,
        )

        if not color.isValid():
            return

        self.server_color = color.name()

        self.server_color_preview.set_color(
            self.server_color
        )

    # =========================================================
    # LOCAL COLOR
    # =========================================================

    def change_local_color(self):
        current = self.local_color or self.server_color

        color = QColorDialog.getColor(
            QColor(current),
            self,
        )

        if not color.isValid():
            return

        self.local_color = color.name()

        self.local_color_preview.set_color(
            self.local_color
        )

    def reset_local_color(self):
        self.local_color = None

        self.local_color_preview.set_color(
            self.server_color
        )


class ClickableFrame(QFrame):
    clicked = pyqtSignal(object)

    def __init__(self, parent=None, type_id=-1):
        super().__init__(parent)
        self._crossed = False
        self.type_id = type_id

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self)  # type: ignore
        super().mousePressEvent(event)

    def setCrossed(self, value: bool):
        self._crossed = value
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)

        if not self._crossed:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        pen = QPen(Qt.black, 2)
        painter.setPen(pen)

        painter.drawLine(0, 0, self.width(), self.height())
        painter.drawLine(self.width(), 0, 0, self.height())


class FakeGroup:
    def __init__(self, name, color):
        self.name = name
        self.color = color
        self.id = -1


class LegendWidget(QWidget):
    visibility_updated = pyqtSignal()

    def __init__(self):
        super().__init__()

        self.layout = QVBoxLayout(self)
        self.layout.setAlignment(Qt.AlignTop)
        self.setMaximumSize(150, 5000)
        self.refresh()

    def refresh(self):
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        types = cache.get().groups
        self.layout.addWidget(self._row(FakeGroup("Сегодня", "#FFFF00")))

        for group in cache.get().groups_iterator():
            self.layout.addWidget(self._row(group))

    def FrameClicked(self, frame: ClickableFrame):
        frame.setCrossed(not VisibilityControl.get().ToggleVisibility(frame.type_id))
        self.visibility_updated.emit()  # type: ignore

    def _row(self, group: EventGroup | FakeGroup):
        edit_button = None

        if isinstance(group, EventGroup) and group.get_access() >= GROUP_ACCESS.EDITOR:
            def on_edit_clicked():
                edit = GroupEditWidget(group, self)
                edit.setModal(True)
                result = edit.exec()
                print(result)
                print(f"click edit on event type: {group.id}")

            edit_button = QToolButton(self)
            icon = QApplication.style().standardIcon(QStyle.SP_FileDialogDetailedView)
            edit_button.setIcon(icon)
            edit_button.setCursor(Qt.PointingHandCursor)
            edit_button.setAutoRaise(True)
            edit_button.clicked.connect(on_edit_clicked)  # type: ignore
            edit_button.resize(20, 20)

        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(4, 2, 4, 2)

        box = ClickableFrame(type_id=group.id)
        if isinstance(group, EventGroup):
            box.clicked.connect(self.FrameClicked)  # type: ignore
        box.setFixedSize(14, 14)
        box.setStyleSheet(f"background-color: {group.color}; border-radius: 3px;")

        label = QLabel(group.name)

        h.addWidget(box)
        if edit_button:
            h.addWidget(edit_button)
        h.addWidget(label)
        h.addStretch()

        return w

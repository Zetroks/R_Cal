"""Окно входа в стиле WinSCP: слева список учётных записей, справа параметры.

Первая строка списка — «Новая учётная запись», остальные — сохранённые
сессии «user @ server». Успешный вход сохраняет/обновляет сессию.
"""

from PyQt5.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QCheckBox, QLabel,
    QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QDialogButtonBox, QPushButton,
)
from PyQt5.QtCore import QThread, QObject, pyqtSignal

from CalendarService.service import EventRepository
from .auth_store import AuthStore, DEFAULT_SERVER_URL

NEW_ROW_TEXT = "+ Новая учётная запись"


class LoginWorker(QObject):
    finished = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, server_url: str, username: str, password: str):
        super().__init__()
        self.server_url = server_url
        self.username = username
        self.password = password

    def run(self):
        try:
            EventRepository.configure(self.server_url, self.username, self.password)
            EventRepository.get().login(self.username, self.password)
        except Exception as exc:
            self.failed.emit(str(exc))  # type: ignore
            return
        self.finished.emit()  # type: ignore


class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Вход — Календарь")
        self.setMinimumSize(560, 320)
        self.setModal(True)

        self.store = AuthStore()
        self._thread: QThread | None = None
        self._worker: LoginWorker | None = None

        root = QHBoxLayout(self)

        # ---- слева: список учёток ----
        self.session_list = QListWidget()
        self.session_list.setMinimumWidth(220)
        self.session_list.currentRowChanged.connect(self.on_session_selected)  # type: ignore
        root.addWidget(self.session_list, 1)

        # ---- справа: параметры + кнопки ----
        right = QVBoxLayout()
        root.addLayout(right, 2)

        form = QFormLayout()
        self.server_edit = QLineEdit()
        self.server_edit.setPlaceholderText(DEFAULT_SERVER_URL)
        form.addRow("Сервер:", self.server_edit)

        self.user_edit = QLineEdit()
        form.addRow("Пользователь:", self.user_edit)

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.returnPressed.connect(self.start_login)  # type: ignore
        form.addRow("Пароль:", self.password_edit)

        self.remember_check = QCheckBox("Запомнить пароль")
        form.addRow("", self.remember_check)
        right.addLayout(form)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        right.addWidget(self.status_label)
        right.addStretch()

        btn_row = QHBoxLayout()
        self.login_btn = QPushButton("Войти")
        self.login_btn.setDefault(True)
        self.login_btn.clicked.connect(self.start_login)  # type: ignore
        self.delete_btn = QPushButton("Удалить")
        self.delete_btn.clicked.connect(self.delete_session)  # type: ignore
        cancel_btn = QPushButton("Отмена")
        cancel_btn.clicked.connect(self.reject)  # type: ignore
        btn_row.addWidget(self.login_btn)
        btn_row.addWidget(self.delete_btn)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        right.addLayout(btn_row)

        self.refresh_list()

    # ---------------- список ----------------

    def refresh_list(self, select_last: bool = True):
        self.session_list.clear()
        QListWidgetItem(NEW_ROW_TEXT, self.session_list)
        for s in self.store.sessions():
            item = QListWidgetItem(f"{s['username']} @ {s['server']}", self.session_list)
            item.setData(32, (s["server"], s["username"]))  # Qt.UserRole

        if select_last:
            last = self.store.last_session()
            row = 0
            if last is not None:
                for i in range(1, self.session_list.count()):
                    if self.session_list.item(i).data(32) == [last["server"], last["username"]] or \
                            tuple(self.session_list.item(i).data(32)) == (last["server"], last["username"]):
                        row = i
                        break
            self.session_list.setCurrentRow(row)
        else:
            self.session_list.setCurrentRow(0)

    def on_session_selected(self, row: int):
        if row <= 0:
            self.server_edit.setText(DEFAULT_SERVER_URL)
            self.user_edit.clear()
            self.password_edit.clear()
            self.remember_check.setChecked(False)
            self.delete_btn.setEnabled(False)
            return
        key = tuple(self.session_list.item(row).data(32))
        for s in self.store.sessions():
            if (s["server"], s["username"]) == key:
                self.server_edit.setText(s["server"])
                self.user_edit.setText(s["username"])
                self.password_edit.setText(s.get("password", ""))
                self.remember_check.setChecked(bool(s.get("remember")))
                break
        self.delete_btn.setEnabled(True)

    def delete_session(self):
        row = self.session_list.currentRow()
        if row <= 0:
            return
        server, username = tuple(self.session_list.item(row).data(32))
        self.store.forget_session(server, username)
        self.refresh_list(select_last=True)

    # ---------------- вход ----------------

    def start_login(self):
        server_url = self.server_edit.text().strip().rstrip("/")
        username = self.user_edit.text().strip()
        password = self.password_edit.text()

        if not server_url or not username or not password:
            self._set_status("Заполните сервер, пользователя и пароль.", error=True)
            return

        self._set_busy(True, "Подключение...")

        self._thread = QThread()
        self._worker = LoginWorker(server_url, username, password)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)  # type: ignore
        self._worker.finished.connect(self.on_login_ok)  # type: ignore
        self._worker.failed.connect(self.on_login_fail)  # type: ignore
        self._thread.start()

    def on_login_ok(self):
        self._stop_worker()
        self.store.save_session(
            self.server_edit.text(),
            self.user_edit.text(),
            self.password_edit.text(),
            self.remember_check.isChecked(),
        )
        self.accept()

    def on_login_fail(self, message: str):
        self._stop_worker()
        self._set_busy(False)
        self._set_status(f"Не удалось войти: {message}", error=True)

    # ---------------- helpers ----------------

    def _set_status(self, text: str, error: bool = False):
        self.status_label.setStyleSheet("color: red;" if error else "color: black;")
        self.status_label.setText(text)

    def _set_busy(self, busy: bool, text: str = ""):
        self.login_btn.setEnabled(not busy)
        self.delete_btn.setEnabled(not busy)
        self.session_list.setEnabled(not busy)
        self.server_edit.setEnabled(not busy)
        self.user_edit.setEnabled(not busy)
        self.password_edit.setEnabled(not busy)
        self.remember_check.setEnabled(not busy)
        self._set_status(text, error=False)

    def _stop_worker(self):
        if self._thread is None:
            return
        self._thread.quit()
        self._thread.wait()
        self._thread.deleteLater()
        if self._worker is not None:
            self._worker.deleteLater()
        self._thread = None
        self._worker = None

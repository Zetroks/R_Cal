"""Локальное хранилище учётных записей (вне репозитория).

Модель как в WinSCP: список сессий {server, username, password?}.
QSettings: Windows -> %APPDATA%/R_Cal/CalendarDesktop.ini,
Linux -> ~/.config/R_Cal/CalendarDesktop.conf.

Пароль хранится в пользовательском конфиге открытым текстом
(в git и в репо его нет). Для продакшена — переехать на keyring
(Windows Credential Vault / Secret Service).
"""

import json

from PyQt5.QtCore import QSettings

ORG_NAME = "R_Cal"
APP_NAME = "CalendarDesktop"

DEFAULT_SERVER_URL = "http://127.0.0.1:8001"
MAX_SESSIONS = 20


def _key(server: str, username: str) -> tuple:
    return ((server or "").strip().rstrip("/"), (username or "").strip())


class AuthStore:
    def __init__(self):
        self._s = QSettings(ORG_NAME, APP_NAME)

    # ---------------- сессии ----------------

    def sessions(self) -> list:
        """Список сессий [{server, username, password, remember}], свежие первые."""
        try:
            data = json.loads(self._s.value("sessions", "[]", type=str) or "[]")
        except (ValueError, TypeError):
            data = []
        return [d for d in data if isinstance(d, dict) and d.get("server") and d.get("username")]

    def _write(self, sessions: list):
        self._s.setValue("sessions", json.dumps(sessions[:MAX_SESSIONS], ensure_ascii=False))

    def save_session(self, server: str, username: str, password: str | None, remember: bool):
        server, username = _key(server, username)
        if not server or not username:
            return
        rest = [s for s in self.sessions() if _key(s.get("server"), s.get("username")) != (server, username)]
        entry = {
            "server": server,
            "username": username,
            "password": password if (remember and password) else "",
            "remember": bool(remember and password),
        }
        self._write([entry] + rest)
        self._s.setValue("last", json.dumps([server, username]))

    def forget_session(self, server: str, username: str):
        key = _key(server, username)
        self._write([s for s in self.sessions() if _key(s.get("server"), s.get("username")) != key])

    def last_session(self) -> dict | None:
        try:
            last = json.loads(self._s.value("last", "", type=str) or "null")
        except (ValueError, TypeError):
            last = None
        if isinstance(last, list) and len(last) == 2:
            for s in self.sessions():
                if _key(s.get("server"), s.get("username")) == (last[0], last[1]):
                    return s
        sessions = self.sessions()
        return sessions[0] if sessions else None

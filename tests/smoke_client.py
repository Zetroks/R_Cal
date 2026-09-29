"""Ручной smoke-тест десктоп-клиента (нужен живой сервер).

Запуск (из корня репо, сервер отдельно, например на 8011):
    $env:CAL_SERVER_URL="http://127.0.0.1:8011"
    $env:QT_QPA_PLATFORM="offscreen"
    .\\.venv\\Scripts\\python.exe tests/smoke_client.py

Проверяет, что MainWindow проходит фоновую загрузку
(groups + access) и строит UI: легенда, год, редактор.
"""

import os
import sys

os.environ.setdefault("CAL_SERVER_URL", "http://127.0.0.1:8001")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer

from CalendarDesktop.MainWindow import MainWindow
from CalendarDesktop.MultiFields.loader import load_all_fields


def main():
    load_all_fields()
    app = QApplication(sys.argv)
    w = MainWindow()
    w.resize(1500, 800)
    w.show()

    def check():
        built = hasattr(w, "legend") and hasattr(w, "year") and hasattr(w, "editor")
        print("SMOKE:", "BUILT" if built else "STILL_LOADING")
        if built:
            from CalendarService.db_cashe import cache

            print("SMOKE: groups =", len(cache.get().groups))
            print("SMOKE: calendars =", len(w.year.calendars))
        app.quit()

    QTimer.singleShot(25000, check)
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())

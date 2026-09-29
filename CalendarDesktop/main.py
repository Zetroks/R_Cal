import sys
from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox
from .MainWindow import MainWindow
from .LoginDialog import LoginDialog
from .MultiFields.loader import load_all_fields
from CalendarService import service as _service
from CalendarService import version as _version


def check_server_compatible() -> bool:
    try:
        info = _service.EventRepository.get().GET("/version")
    except Exception as exc:
        QMessageBox.critical(None, "Сервер недоступен",
                             f"Не удалось узнать версию сервера:\n{exc}")
        return False
    if not _version.is_compatible(_version.PROTOCOL, info.get("min_protocol", "")):
        QMessageBox.critical(
            None, "Нужно обновление",
            f"Клиент (протокол {_version.PROTOCOL}, сборка {_version.BUILD}) "
            f"несовместим с сервером (требуется протокол >= {info.get('min_protocol')}).\n\n"
            f"Скачай новую версию: {info.get('installer_url', '')}")
        return False
    return True


def run() -> int:
    load_all_fields()
    app = QApplication(sys.argv)

    login = LoginDialog()
    if login.exec_() != QDialog.Accepted:
        return 0

    if not check_server_compatible():
        return 1

    root = MainWindow()
    root.resize(1500, 800)
    root.show()

    return app.exec_()


if __name__ == "__main__":
    sys.exit(run())

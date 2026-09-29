import sys
from PyQt5.QtWidgets import QApplication, QDialog
from .MainWindow import MainWindow
from .LoginDialog import LoginDialog
from .MultiFields.loader import load_all_fields

if __name__ == "__main__":
    load_all_fields()
    app = QApplication(sys.argv)

    login = LoginDialog()
    if login.exec_() != QDialog.Accepted:
        sys.exit(0)

    root = MainWindow()
    root.resize(1500, 800)
    root.show()

    sys.exit(app.exec_())

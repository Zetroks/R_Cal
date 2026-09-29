import sys
from PyQt5.QtWidgets import QApplication
from ..MainWindow import MainWindow
from .MultiFields.loader import load_all_fields

if __name__ == "__main__":
    load_all_fields()
    app = QApplication(sys.argv)
    root = MainWindow()
    root.resize(1500, 800)
    root.show()

    sys.exit(app.exec_())

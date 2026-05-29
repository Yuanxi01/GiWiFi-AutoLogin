import sys
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont

from tray_app import MainWindow


def main():
    app = QApplication(sys.argv)

    # 全局字体抗锯齿
    font = QFont("Source Han Sans CN", 10, QFont.Weight.Medium)
    font.setStyleStrategy(QFont.PreferAntialias)
    font.setHintingPreference(QFont.PreferNoHinting)
    app.setFont(font)

    app.setQuitOnLastWindowClosed(False)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

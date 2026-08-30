import sys
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QFont

from tray_app import MainWindow
from config import load_config


def check_single_instance():
    """检查是否已有实例在运行"""
    import ctypes
    from ctypes import wintypes

    mutex_name = "GiWiFi_AutoLogin_Mutex"
    handle = ctypes.windll.kernel32.CreateMutexW(None, False, mutex_name)
    last_error = ctypes.windll.kernel32.GetLastError()

    ERROR_ALREADY_EXISTS = 183
    if last_error == ERROR_ALREADY_EXISTS:
        ctypes.windll.kernel32.CloseHandle(handle)
        return False
    return handle


def main():
    # 单实例检测
    mutex_handle = check_single_instance()
    if not mutex_handle:
        # 创建临时 QApplication 来显示消息框
        temp_app = QApplication(sys.argv)
        QMessageBox.warning(
            None,
            "GiWiFi 自动登录",
            "程序已在运行中，请勿重复打开！\n\n请检查系统托盘区域。",
            QMessageBox.StandardButton.Ok
        )
        sys.exit(0)

    app = QApplication(sys.argv)

    # 全局字体抗锯齿（带回退链：缺失字体时依序回退）
    font = QFont("Source Han Sans CN", 10, QFont.Weight.Medium)
    font.setFamilies([
        "Source Han Sans CN", "思源黑体", "Source Han Sans SC",
        "Microsoft YaHei UI", "微软雅黑", "Segoe UI",
    ])
    font.setStyleStrategy(QFont.PreferAntialias)
    font.setHintingPreference(QFont.PreferNoHinting)
    app.setFont(font)

    app.setQuitOnLastWindowClosed(False)

    # 读取配置，判断是否静默启动
    config = load_config()
    silent_start = config.get("silent_start", False)

    window = MainWindow()

    if silent_start:
        # 静默模式：不显示窗口，直接最小化到托盘
        window.hide()
    else:
        window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

import sys
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QFont

import tray_app
from tray_app import MainWindow
from config import load_config


def check_single_instance(force: bool = False):
    """
    检查是否已有实例在运行。

    force=True 时（重启自己拉起的那个进程）即使互斥体已存在也放行 ——
    否则老进程还没退干净，新进程会被自己的锁挡在门外。
    """
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.windll.kernel32
    # 必须显式声明返回值类型：默认按 c_int 处理，64 位下句柄会被截断，
    # 后面 CloseHandle 就会失败，锁一直挂着
    k32.CreateMutexW.restype = wintypes.HANDLE
    k32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    k32.CloseHandle.restype = wintypes.BOOL

    mutex_name = "GiWiFi_AutoLogin_Mutex"
    handle = k32.CreateMutexW(None, False, mutex_name)
    last_error = k32.GetLastError()

    ERROR_ALREADY_EXISTS = 183
    if last_error == ERROR_ALREADY_EXISTS and not force:
        k32.CloseHandle(handle)
        return False
    return handle


def install_excepthook():
    """
    把未捕获异常写进 giwifi.log。

    Qt 槽函数里抛的异常默认只打到 stderr —— 打包成窗口程序后 stderr 不可见，
    于是"点了没反应"这种问题根本查不到（例如 self.restart_app() 写错类导致的
    AttributeError 就被这样吞掉过一次）。挂上钩子后日志里能直接看到堆栈。
    """
    import traceback

    def _hook(exc_type, exc, tb):
        try:
            from logger import log as _log
            _log("未捕获异常:\n" + "".join(traceback.format_exception(exc_type, exc, tb)))
        except Exception:
            pass

    sys.excepthook = _hook


def main():
    install_excepthook()

    # 单实例检测
    restarted = "--restarted" in sys.argv
    mutex_handle = check_single_instance(force=restarted)
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

    # 把互斥锁句柄交给 tray_app：重启自己时要先放锁，否则新进程会被挡回去
    tray_app.MUTEX_HANDLE = mutex_handle

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

    code = app.exec()

    # 强制退出，不走解释器的正常关闭流程。
    # 原因：PySide6 在进程收尾时如果还有 QThread 对象存活（网络检测线程、
    # 登录线程、检查更新线程都可能刚好在跑），Qt 析构阶段会卡住不返回，
    # 表现就是「窗口消失了，但任务管理器里进程还在、托盘图标也跟着赖着」。
    # 这里所有该保存的东西（配置/流量/日志）在 quit_app 里已经落盘，
    # 直接 _exit 是安全的。
    from logger import log as _log
    _log(f"进程退出，返回码 {code}")
    os._exit(code)


if __name__ == "__main__":
    main()

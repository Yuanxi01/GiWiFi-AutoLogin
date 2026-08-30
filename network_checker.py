import time
from PySide6.QtCore import QThread, Signal

from login_worker import check_online


class NetworkChecker(QThread):
    status_changed = Signal(bool)
    login_needed = Signal(str)

    # 启动后 60 秒内使用更长超时，适应网络初始化
    _STARTUP_DURATION = 60
    _STARTUP_TIMEOUT = 15
    _NORMAL_TIMEOUT = 5
    # 登录信号冷却时间（秒），防止重复触发
    _LOGIN_COOLDOWN = 20

    def __init__(self, interval: int = 30, config_portal_url: str = ""):
        super().__init__()
        self.interval = interval
        self._running = True
        self._config_portal_url = config_portal_url
        self._last_login_trigger = 0.0
        self._startup_time = time.monotonic()

    def run(self):
        while self._running:
            # 启动阶段使用更长超时，等待网络就绪
            elapsed = time.monotonic() - self._startup_time
            timeout = self._STARTUP_TIMEOUT if elapsed < self._STARTUP_DURATION else self._NORMAL_TIMEOUT
            online, portal_url = check_online(timeout=timeout)
            self.status_changed.emit(online)

            if not online:
                # 使用检测到的 portal URL，或回退到配置中的 URL
                url = portal_url or self._config_portal_url
                if url:
                    now = time.monotonic()
                    if now - self._last_login_trigger >= self._LOGIN_COOLDOWN:
                        self._last_login_trigger = now
                        self.login_needed.emit(url)

            for _ in range(self.interval * 2):
                if not self._running:
                    return
                time.sleep(0.5)

    def stop(self):
        self._running = False

    def set_interval(self, interval: int):
        self.interval = interval

    def set_portal_url(self, url: str):
        """更新配置中的 portal URL"""
        self._config_portal_url = url

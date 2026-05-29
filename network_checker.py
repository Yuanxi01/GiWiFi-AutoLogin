import time
from PyQt5.QtCore import QThread, pyqtSignal

from login_worker import check_online


class NetworkChecker(QThread):
    status_changed = pyqtSignal(bool)
    login_needed = pyqtSignal(str)

    def __init__(self, interval: int = 30):
        super().__init__()
        self.interval = interval
        self._running = True
        self._was_online = True

    def run(self):
        while self._running:
            online, portal_url = check_online()
            self.status_changed.emit(online)

            if self._was_online and not online and portal_url:
                self.login_needed.emit(portal_url)

            self._was_online = online
            for _ in range(self.interval * 2):
                if not self._running:
                    return
                time.sleep(0.5)

    def stop(self):
        self._running = False

    def set_interval(self, interval: int):
        self.interval = interval

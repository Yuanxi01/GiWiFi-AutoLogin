import sys
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox,
    QSystemTrayIcon, QMenu, QAction, QMessageBox, QGroupBox,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QFont

from config import load_config, save_config
from autostart import is_autostart_enabled, enable_autostart, disable_autostart
from login_worker import login_giwifi, check_online, logout_giwifi, get_online_duration
from network_checker import NetworkChecker
from logger import log as file_log

APP_NAME = "GiWiFi自动登录软件（山东中医药大学）"
APP_VERSION = "1.0.0"
APP_AUTHOR = "YuanXi"


def create_icon(color: str = "#4CAF50") -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(color))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(4, 4, 56, 56)
    painter.setPen(QColor("white"))
    font = QFont("Arial", 24, QFont.Bold)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "W")
    painter.end()
    return QIcon(pixmap)


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.online = False
        self.init_ui()
        self.init_tray()
        self.init_checker()
        self.init_duration_timer()

    def init_ui(self):
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setFixedSize(400, 330)
        self.setWindowIcon(create_icon())

        layout = QVBoxLayout()

        # Status
        status_group = QGroupBox("网络状态")
        status_layout = QVBoxLayout()
        self.status_label = QLabel("检测中...")
        self.status_label.setFont(QFont("Microsoft YaHei", 12))
        self.status_label.setAlignment(Qt.AlignCenter)
        status_layout.addWidget(self.status_label)

        self.duration_label = QLabel("")
        self.duration_label.setFont(QFont("Microsoft YaHei", 10))
        self.duration_label.setAlignment(Qt.AlignCenter)
        self.duration_label.setStyleSheet("color: #666;")
        status_layout.addWidget(self.duration_label)

        status_group.setLayout(status_layout)
        layout.addWidget(status_group)

        # Credentials
        cred_group = QGroupBox("登录信息")
        cred_layout = QVBoxLayout()

        user_layout = QHBoxLayout()
        user_layout.addWidget(QLabel("账号:"))
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("请输入校园网账号")
        self.username_input.setText(self.config.get("username", ""))
        user_layout.addWidget(self.username_input)
        cred_layout.addLayout(user_layout)

        pass_layout = QHBoxLayout()
        pass_layout.addWidget(QLabel("密码:"))
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("请输入密码")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setText(self.config.get("password", ""))
        pass_layout.addWidget(self.password_input)
        cred_layout.addLayout(pass_layout)

        cred_group.setLayout(cred_layout)
        layout.addWidget(cred_group)

        # Buttons
        btn_layout = QHBoxLayout()

        self.save_btn = QPushButton("保存配置")
        self.save_btn.clicked.connect(self.save_config)
        btn_layout.addWidget(self.save_btn)

        self.login_btn = QPushButton("手动登录")
        self.login_btn.clicked.connect(self.manual_login)
        btn_layout.addWidget(self.login_btn)

        self.logout_btn = QPushButton("下线")
        self.logout_btn.clicked.connect(self.manual_logout)
        btn_layout.addWidget(self.logout_btn)

        layout.addLayout(btn_layout)

        # Checkboxes
        cb_layout = QHBoxLayout()

        self.autostart_cb = QCheckBox("开机自启动")
        self.autostart_cb.setChecked(is_autostart_enabled())
        self.autostart_cb.stateChanged.connect(self.toggle_autostart)
        cb_layout.addWidget(self.autostart_cb)

        self.auto_reconnect_cb = QCheckBox("掉线自动登录")
        self.auto_reconnect_cb.setChecked(self.config.get("auto_reconnect", True))
        self.auto_reconnect_cb.stateChanged.connect(self.toggle_auto_reconnect)
        cb_layout.addWidget(self.auto_reconnect_cb)

        layout.addLayout(cb_layout)

        # Version info
        version_label = QLabel(f"v{APP_VERSION}  |  {APP_AUTHOR}")
        version_label.setStyleSheet("color: #aaa; font-size: 10px;")
        version_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(version_label)

        # Log
        self.log_label = QLabel("")
        self.log_label.setStyleSheet("color: gray; font-size: 11px;")
        self.log_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.log_label)

        self.setLayout(layout)

    def init_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(create_icon())
        self.tray_icon.setToolTip(f"{APP_NAME} v{APP_VERSION}")

        tray_menu = QMenu()
        show_action = QAction("显示主窗口", self)
        show_action.triggered.connect(self.show_window)
        tray_menu.addAction(show_action)

        login_action = QAction("手动登录", self)
        login_action.triggered.connect(self.manual_login)
        tray_menu.addAction(login_action)

        logout_action = QAction("下线", self)
        logout_action.triggered.connect(self.manual_logout)
        tray_menu.addAction(logout_action)

        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self.quit_app)
        tray_menu.addAction(quit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.tray_activated)
        self.tray_icon.show()

    def init_checker(self):
        self.checker = NetworkChecker(self.config.get("check_interval", 10))
        self.checker.status_changed.connect(self.on_status_changed)
        self.checker.login_needed.connect(self.auto_login)
        self.checker.start()

    def init_duration_timer(self):
        self.duration_timer = QTimer(self)
        self.duration_timer.timeout.connect(self.update_duration)
        self.duration_timer.start(1000)

    def update_duration(self):
        logout_url = self.config.get("logout_url", "")
        if self.online and logout_url:
            duration = get_online_duration(logout_url)
            self.duration_label.setText(f"在线时长: {duration}")
            self.tray_icon.setToolTip(f"GiWiFi - 已连接 ({duration})")
        else:
            self.duration_label.setText("")

    def on_status_changed(self, online: bool):
        self.online = online
        if online:
            self.status_label.setText("已连接")
            self.status_label.setStyleSheet(
                "color: #4CAF50; font-size: 14px; font-weight: bold;"
            )
            self.tray_icon.setIcon(create_icon("#4CAF50"))
        else:
            self.status_label.setText("未连接")
            self.status_label.setStyleSheet(
                "color: #f44336; font-size: 14px; font-weight: bold;"
            )
            self.tray_icon.setIcon(create_icon("#f44336"))
            self.duration_label.setText("")

    def auto_login(self, portal_url: str):
        try:
            if not self.config.get("auto_reconnect", True):
                self.log("检测到断线，自动登录已关闭")
                return

            username = self.config.get("username", "")
            password = self.config.get("password", "")

            if not username or not password:
                self.log("未配置账号密码，无法自动登录")
                return

            self.log("检测到断线，正在自动登录...")
            success, msg, logout_url = login_giwifi(username, password, portal_url)
            self.log(msg)

            if success and logout_url:
                self.config["logout_url"] = logout_url
                save_config(self.config)
        except Exception as e:
            self.log(f"自动登录异常: {e}")

    def manual_login(self):
        try:
            username = self.username_input.text().strip()
            password = self.password_input.text().strip()

            if not username or not password:
                QMessageBox.warning(self, "提示", "请先输入账号和密码")
                return

            self.log("正在检测网络...")
            online, portal_url = check_online()

            if online:
                self.log("网络已连通，无需登录")
                return

            if not portal_url:
                portal_url = self.config.get("portal_url", "")
                self.log("未检测到认证页面，使用默认地址...")
            else:
                self.log("已获取认证页面，正在登录...")

            success, msg, logout_url = login_giwifi(username, password, portal_url)
            self.log(msg)

            if success and logout_url:
                self.config["logout_url"] = logout_url
                save_config(self.config)
        except Exception as e:
            self.log(f"手动登录异常: {e}")

    def manual_logout(self):
        try:
            logout_url = self.config.get("logout_url", "")
            if not logout_url:
                self.log("无下线信息，请先登录")
                return

            self.log("正在下线...")
            success, msg = logout_giwifi(logout_url)
            self.log(msg)

            if success:
                self.config.pop("logout_url", None)
                save_config(self.config)
        except Exception as e:
            self.log(f"下线异常: {e}")

    def save_config(self):
        self.config["username"] = self.username_input.text().strip()
        self.config["password"] = self.password_input.text().strip()
        save_config(self.config)
        self.checker.set_interval(self.config.get("check_interval", 10))
        self.log("配置已保存")

    def toggle_autostart(self, state):
        if state == Qt.Checked:
            enable_autostart()
            self.log("已启用开机自启动")
        else:
            disable_autostart()
            self.log("已禁用开机自启动")

    def toggle_auto_reconnect(self, state):
        self.config["auto_reconnect"] = (state == Qt.Checked)
        save_config(self.config)
        if state == Qt.Checked:
            self.log("已启用掉线自动登录")
        else:
            self.log("已禁用掉线自动登录")

    def log(self, text: str):
        self.log_label.setText(text)
        file_log(text)

    def show_window(self):
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_window()

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self.tray_icon.showMessage(
            APP_NAME,
            "程序已最小化到系统托盘，双击图标可恢复窗口",
            QSystemTrayIcon.Information,
            2000,
        )

    def quit_app(self):
        self.duration_timer.stop()
        self.checker.stop()
        self.checker.wait()
        self.tray_icon.hide()
        QApplication.quit()

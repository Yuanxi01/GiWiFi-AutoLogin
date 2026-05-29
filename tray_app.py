import sys
import os
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton,
    QSystemTrayIcon, QMenu, QMessageBox,
    QGraphicsDropShadowEffect,
)
from PySide6.QtCore import (
    Qt, QTimer, QPoint, QPointF, QRectF,
    QPropertyAnimation, QEasingCurve, Property, Signal,
)
from PySide6.QtGui import (
    QIcon, QPixmap, QPainter, QColor, QFont, QAction,
    QLinearGradient, QRadialGradient, QPainterPath, QPen,
)

from config import load_config, save_config
from autostart import is_autostart_enabled, enable_autostart, disable_autostart
from login_worker import login_giwifi, check_online, logout_giwifi, get_online_duration
from network_checker import NetworkChecker
from logger import log as file_log

APP_NAME = "GiWiFi自动登录"
APP_VERSION = "1.0.1"
APP_AUTHOR = "YuanXi"

# ── 配色 ──────────────────────────────────────────────
C_BG_TOP = QColor(0xE8, 0xF4, 0xFD)
C_BG_BOT = QColor(0xFF, 0xFF, 0xFF)
C_CARD = QColor(255, 255, 255, 140)
C_CARD_BORDER = QColor(255, 255, 255, 200)
C_PRIMARY = QColor(0x00, 0x7A, 0xFF)
C_PRIMARY_LIGHT = QColor(0x5A, 0xC8, 0xFA)
C_TEXT = QColor(0x1D, 0x1D, 0x1F)
C_TEXT_SEC = QColor(0x86, 0x86, 0x8B)
C_GREEN = QColor(0x34, 0xC7, 0x59)
C_RED = QColor(0xFF, 0x3B, 0x30)

# 全局字体 — 思源黑体 CN，笔画更粗更清晰
_FONT_FAMILY = "Source Han Sans CN"

def _make_font(size, weight=QFont.Weight.Normal):
    f = QFont(_FONT_FAMILY, size, weight)
    f.setStyleStrategy(QFont.PreferAntialias)
    f.setHintingPreference(QFont.PreferNoHinting)
    return f

APP_FONT = _make_font(10, QFont.Weight.Medium)
APP_FONT_BOLD = _make_font(10, QFont.Weight.DemiBold)
APP_FONT_TITLE = _make_font(11, QFont.Weight.Bold)
APP_FONT_BIG = _make_font(14, QFont.Weight.Bold)
APP_FONT_SMALL = _make_font(9, QFont.Weight.Medium)
APP_FONT_SEC = _make_font(10, QFont.Weight.Medium)


def create_icon(color: str = "#4CAF50") -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.NoPen)
    p.drawEllipse(4, 4, 56, 56)
    p.setPen(QColor("white"))
    p.setFont(QFont("Arial", 24, QFont.Weight.Bold))
    p.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "W")
    p.end()
    return QIcon(pixmap)


def lerp_color(c1: QColor, c2: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(
        int(c1.red() + (c2.red() - c1.red()) * t),
        int(c1.green() + (c2.green() - c1.green()) * t),
        int(c1.blue() + (c2.blue() - c1.blue()) * t),
        int(c1.alpha() + (c2.alpha() - c1.alpha()) * t),
    )


# ═══════════════════════════════════════════════════════
#  macOS 红绿灯按钮（自定义绘制，完美圆形）
# ═══════════════════════════════════════════════════════
class TrafficLight(QPushButton):
    def __init__(self, color: str, hover_color: str, parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self._hover_color = QColor(hover_color)
        self._hovered = False
        self.setFixedSize(14, 14)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def enterEvent(self, event):
        self._hovered = True
        self.update()

    def leaveEvent(self, event):
        self._hovered = False
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(self._hover_color if self._hovered else self._color)
        p.drawEllipse(1, 1, 12, 12)
        # 顶部高光
        hl = QRadialGradient(QPointF(5, 5), 6)
        hl.setColorAt(0, QColor(255, 255, 255, 80))
        hl.setColorAt(1, QColor(255, 255, 255, 0))
        p.setBrush(hl)
        p.drawEllipse(1, 1, 12, 12)
        p.end()


# ═══════════════════════════════════════════════════════
#  iOS 风格滑动开关
# ═══════════════════════════════════════════════════════
class ToggleSwitch(QWidget):
    toggled = Signal(bool)

    # 轨道: x=2, w=50 → 右边缘 x=52
    # 圆半径=10, 左侧中心 x=12 (circle_x=1), 右侧中心 x=42 (circle_x=31)
    _LEFT_X = 1.0
    _RIGHT_X = 31.0

    def __init__(self, text: str = "", checked: bool = False, parent=None):
        super().__init__(parent)
        self._text = text
        self._checked = checked
        self._circle_x = self._RIGHT_X if checked else self._LEFT_X
        self._bg_color = QColor(0x00, 0x7A, 0xFF) if checked else QColor(0xE0, 0xE0, 0xE0)
        self.setFixedSize(58 + (len(text) * 13 + 8 if text else 0), 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._anim = QPropertyAnimation(self, b"circle_x")
        self._anim.setDuration(280)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

        self._color_anim = QPropertyAnimation(self, b"bg_color")
        self._color_anim.setDuration(280)
        self._color_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

    def _get_circle_x(self):
        return self._circle_x

    def _set_circle_x(self, v):
        self._circle_x = v
        self.update()

    circle_x = Property(float, _get_circle_x, _set_circle_x)

    def _get_bg_color(self):
        return self._bg_color

    def _set_bg_color(self, c):
        self._bg_color = c
        self.update()

    bg_color = Property(QColor, _get_bg_color, _set_bg_color)

    def isChecked(self):
        return self._checked

    def setChecked(self, v: bool):
        self._checked = v
        target_x = self._RIGHT_X if v else self._LEFT_X
        target_c = QColor(0x00, 0x7A, 0xFF) if v else QColor(0xE0, 0xE0, 0xE0)
        self._anim.stop()
        self._anim.setStartValue(self._circle_x)
        self._anim.setEndValue(target_x)
        self._anim.start()
        self._color_anim.stop()
        self._color_anim.setStartValue(QColor(self._bg_color))
        self._color_anim.setEndValue(target_c)
        self._color_anim.start()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._checked = not self._checked
            self.setChecked(self._checked)
            self.toggled.emit(self._checked)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        track = QRectF(2, 4, 50, 22)
        tp = QPainterPath()
        tp.addRoundedRect(track, 11, 11)
        p.fillPath(tp, self._bg_color)

        # 圆形滑块 (直径 22, 半径 10)
        cx = self._circle_x + 11
        cy = 15.0
        r = 10.0

        p.setPen(Qt.NoPen)

        # 阴影（多层，营造立体感）
        for i in range(3, 0, -1):
            shadow = QRadialGradient(QPointF(cx, cy + i * 0.8), r + i * 1.5)
            shadow.setColorAt(0.5, QColor(0, 0, 0, 20 * i))
            shadow.setColorAt(1, QColor(0, 0, 0, 0))
            p.setBrush(shadow)
            p.drawEllipse(QPointF(cx, cy + i * 0.5), r + i, r + i)

        # 白色圆
        p.setBrush(QColor(255, 255, 255))
        p.drawEllipse(QPointF(cx, cy), r, r)

        # 顶部高光
        hl = QRadialGradient(QPointF(cx - 2, cy - 3), r)
        hl.setColorAt(0, QColor(255, 255, 255, 180))
        hl.setColorAt(0.4, QColor(255, 255, 255, 60))
        hl.setColorAt(1, QColor(255, 255, 255, 0))
        p.setBrush(hl)
        p.drawEllipse(QPointF(cx, cy), r, r)

        # 底部微暗（加强立体）
        bot = QRadialGradient(QPointF(cx + 1, cy + 4), r)
        bot.setColorAt(0, QColor(0, 0, 0, 0))
        bot.setColorAt(0.8, QColor(0, 0, 0, 0))
        bot.setColorAt(1, QColor(0, 0, 0, 15))
        p.setBrush(bot)
        p.drawEllipse(QPointF(cx, cy), r, r)

        # 文字
        if self._text:
            p.setPen(C_TEXT)
            p.setFont(APP_FONT)
            p.drawText(QRectF(60, 0, self.width() - 60, 30),
                       Qt.AlignmentFlag.AlignVCenter, self._text)

        p.end()


# ═══════════════════════════════════════════════════════
#  液态玻璃按钮（发光 hover + 回弹 press）
# ═══════════════════════════════════════════════════════
class GlassButton(QPushButton):
    def __init__(self, text: str, primary: bool = False, parent=None):
        super().__init__(text, parent)
        self._primary = primary
        self._hover_progress = 0.0
        self._press_scale = 1.0
        self._glow_color = QColor(0x00, 0x7A, 0xFF, 0) if primary else QColor(255, 255, 255, 0)

        self.setFixedHeight(38)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(APP_FONT_BOLD)

        # hover 动画
        self._hover_anim = QPropertyAnimation(self, b"hover_progress")
        self._hover_anim.setDuration(200)
        self._hover_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        # 回弹动画
        self._bounce_anim = QPropertyAnimation(self, b"press_scale")
        self._bounce_anim.setDuration(350)
        self._bounce_anim.setEasingCurve(QEasingCurve.Type.OutElastic)

    def _get_hp(self):
        return self._hover_progress

    def _set_hp(self, v):
        self._hover_progress = v
        self.update()

    hover_progress = Property(float, _get_hp, _set_hp)

    def _get_ps(self):
        return self._press_scale

    def _set_ps(self, v):
        self._press_scale = v
        self.update()

    press_scale = Property(float, _get_ps, _set_ps)

    def enterEvent(self, event):
        self._hover_anim.setStartValue(self._hover_progress)
        self._hover_anim.setEndValue(1.0)
        self._hover_anim.start()

    def leaveEvent(self, event):
        self._hover_anim.setStartValue(self._hover_progress)
        self._hover_anim.setEndValue(0.0)
        self._hover_anim.start()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._bounce_anim.stop()
            self._press_scale = 0.92
            self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._bounce_anim.setStartValue(0.92)
        self._bounce_anim.setEndValue(1.0)
        self._bounce_anim.start()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        # 应用回弹缩放
        p.translate(w / 2, h / 2)
        p.scale(self._press_scale, self._press_scale)
        p.translate(-w / 2, -h / 2)

        rect = QRectF(1, 1, w - 2, h - 2)
        path = QPainterPath()
        path.addRoundedRect(rect, 12, 12)

        if self._primary:
            # 主按钮：蓝色渐变
            grad = QLinearGradient(QPointF(0, 0), QPointF(w, 0))
            grad.setColorAt(0, QColor(0x00, 0x7A, 0xFF))
            grad.setColorAt(1, QColor(0x5A, 0xC8, 0xFA))
            p.fillPath(path, grad)

            # hover 发光
            if self._hover_progress > 0.01:
                glow = QRadialGradient(QPointF(w / 2, h / 2), max(w, h) * 0.7)
                glow.setColorAt(0, QColor(255, 255, 255, int(50 * self._hover_progress)))
                glow.setColorAt(1, QColor(255, 255, 255, 0))
                p.fillPath(path, glow)
        else:
            # 次按钮：玻璃态（加深底色和边框）
            bg = QColor(255, 255, 255, int(160 + 40 * self._hover_progress))
            p.fillPath(path, bg)

            # 底部微妙阴影线
            bottom_line = QPainterPath()
            bottom_line.moveTo(rect.x() + 12, rect.bottom())
            bottom_line.lineTo(rect.right() - 12, rect.bottom())
            p.setPen(QPen(QColor(0, 0, 0, 25), 1))
            p.drawPath(bottom_line)

            # 边框
            p.setPen(QPen(QColor(200, 210, 220, 180), 1))
            p.drawPath(path)

            # hover 发光
            if self._hover_progress > 0.01:
                glow = QRadialGradient(QPointF(w / 2, h / 2), max(w, h) * 0.6)
                glow.setColorAt(0, QColor(0x00, 0x7A, 0xFF, int(35 * self._hover_progress)))
                glow.setColorAt(1, QColor(0x00, 0x7A, 0xFF, 0))
                p.fillPath(path, glow)

        # 文字
        p.setPen(QColor("white") if self._primary else C_TEXT)
        p.setFont(self.font())
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text())

        p.end()


# ═══════════════════════════════════════════════════════
#  全局样式（输入框修复）
# ═══════════════════════════════════════════════════════
GLASS_STYLE = """
QLabel {
    color: #1D1D1F;
    background: transparent;
    border: none;
}
QLineEdit {
    background: rgba(255, 255, 255, 120);
    border: 1.5px solid rgba(200, 210, 220, 0.5);
    border-radius: 10px;
    padding: 6px 12px;
    font-size: 13px;
    color: #1D1D1F;
    min-height: 22px;
    selection-background-color: #007AFF;
}
QLineEdit:focus {
    border: 1.5px solid #007AFF;
    background: rgba(255, 255, 255, 180);
}
"""


# ═══════════════════════════════════════════════════════
#  主窗口
# ═══════════════════════════════════════════════════════
class MainWindow(QWidget):
    def _get_accent_alpha(self):
        return self._accent_alpha

    def _set_accent_alpha(self, val):
        self._accent_alpha = val

    accent_alpha = Property(float, _get_accent_alpha, _set_accent_alpha)

    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.online = False
        self._drag_pos = None
        self._radius = 18

        self._accent_alpha = 180.0
        self._current_accent = QColor(C_RED)

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(440, 420)
        self.setWindowIcon(create_icon())
        self.setStyleSheet(GLASS_STYLE)

        self._build_ui()
        self.init_tray()
        self.init_checker()
        self.init_duration_timer()
        self._init_animations()

    # ── 构建 UI ──────────────────────────────────────
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 28)

        self.container = QWidget()
        outer.addWidget(self.container)

        root = QVBoxLayout(self.container)
        root.setContentsMargins(22, 14, 22, 20)
        root.setSpacing(10)

        # ── 标题栏 ──
        title_bar = QHBoxLayout()
        title_bar.setContentsMargins(0, 0, 0, 4)

        self.btn_close = TrafficLight("#FF5F57", "#FF3B30")
        self.btn_close.clicked.connect(self.quit_app)
        self.btn_mini = TrafficLight("#FEBC2E", "#F5A623")
        self.btn_mini.clicked.connect(self.hide)
        lights = QHBoxLayout()
        lights.setSpacing(6)
        lights.addWidget(self.btn_close)
        lights.addWidget(self.btn_mini)
        title_bar.addLayout(lights)

        title_label = QLabel(APP_NAME)
        title_label.setFont(APP_FONT_TITLE)
        title_label.setStyleSheet("color:#1D1D1F;background:transparent")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_bar.addWidget(title_label, 1)

        ph = QWidget()
        ph.setFixedSize(36, 14)
        title_bar.addWidget(ph)
        root.addLayout(title_bar)

        # ── 状态卡片 ──
        self.status_card = QWidget()
        sc = QVBoxLayout(self.status_card)
        sc.setContentsMargins(16, 12, 16, 14)
        sc.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(10)

        dot_box = QWidget()
        dot_box.setFixedSize(20, 20)
        dl = QVBoxLayout(dot_box)
        dl.setContentsMargins(5, 5, 5, 5)
        self.status_dot = QLabel()
        self.status_dot.setFixedSize(10, 10)
        self._apply_dot_style(C_RED, 12)
        dl.addWidget(self.status_dot, 0, Qt.AlignmentFlag.AlignCenter)
        top.addWidget(dot_box)

        self.status_label = QLabel("检测中...")
        self.status_label.setFont(APP_FONT_BIG)
        self.status_label.setStyleSheet("color:#1D1D1F;background:transparent")
        top.addWidget(self.status_label)
        top.addStretch()

        self.duration_label = QLabel("")
        self.duration_label.setFont(APP_FONT_SEC)
        self.duration_label.setStyleSheet("color:#86868B;background:transparent")
        self.duration_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top.addWidget(self.duration_label)
        sc.addLayout(top)

        self.status_desc = QLabel("等待网络检测...")
        self.status_desc.setFont(APP_FONT_SMALL)
        self.status_desc.setStyleSheet("color:#86868B;background:transparent")
        sc.addWidget(self.status_desc)

        root.addWidget(self.status_card)

        # ── 登录卡片 ──
        self.cred_card = QWidget()
        cc = QVBoxLayout(self.cred_card)
        cc.setContentsMargins(16, 12, 16, 14)
        cc.setSpacing(10)

        def make_input_row(label_text, placeholder, echo_mode=None):
            row = QHBoxLayout()
            row.setSpacing(8)
            lbl = QLabel(label_text)
            lbl.setFont(APP_FONT_SEC)
            lbl.setFixedWidth(36)
            row.addWidget(lbl)
            inp = QLineEdit()
            inp.setPlaceholderText(placeholder)
            if echo_mode:
                inp.setEchoMode(echo_mode)
            row.addWidget(inp)
            return row, inp

        r1, self.username_input = make_input_row("账号", "请输入校园网账号")
        self.username_input.setText(self.config.get("username", ""))
        cc.addLayout(r1)

        r2, self.password_input = make_input_row("密码", "请输入密码", QLineEdit.EchoMode.Password)
        self.password_input.setText(self.config.get("password", ""))
        cc.addLayout(r2)

        root.addWidget(self.cred_card)

        # ── 按钮行 ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.login_btn = GlassButton("手动登录", primary=True)
        self.login_btn.clicked.connect(self.manual_login)
        btn_row.addWidget(self.login_btn)

        self.save_btn = GlassButton("保存配置")
        self.save_btn.clicked.connect(self.save_config)
        btn_row.addWidget(self.save_btn)

        self.logout_btn = GlassButton("下线")
        self.logout_btn.clicked.connect(self.manual_logout)
        btn_row.addWidget(self.logout_btn)

        root.addLayout(btn_row)

        # ── 开关行 ──
        sw_row = QHBoxLayout()
        sw_row.setSpacing(24)

        self.autostart_sw = ToggleSwitch("开机自启动", is_autostart_enabled())
        self.autostart_sw.toggled.connect(self.toggle_autostart)
        sw_row.addWidget(self.autostart_sw)

        self.auto_reconnect_sw = ToggleSwitch("掉线自动登录", self.config.get("auto_reconnect", True))
        self.auto_reconnect_sw.toggled.connect(self.toggle_auto_reconnect)
        sw_row.addWidget(self.auto_reconnect_sw)

        root.addLayout(sw_row)

        # ── 底部 ──
        bot = QHBoxLayout()
        self.log_label = QLabel("")
        self.log_label.setFont(APP_FONT_SMALL)
        self.log_label.setStyleSheet("color:#86868B;background:transparent")
        bot.addWidget(self.log_label, 1)

        ver = QLabel(f"v{APP_VERSION}  {APP_AUTHOR}")
        ver.setFont(APP_FONT_SMALL)
        ver.setStyleSheet("color:#AEAEB2;background:transparent")
        ver.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        bot.addWidget(ver)
        root.addLayout(bot)

    def _apply_dot_style(self, color: QColor, glow_r: float):
        self.status_dot.setStyleSheet(
            f"background:{color.name()};border-radius:5px;border:none"
        )
        # 复用已有效果，避免频繁创建导致抖动
        glow = self.status_dot.graphicsEffect()
        if glow is None or not isinstance(glow, QGraphicsDropShadowEffect):
            glow = QGraphicsDropShadowEffect(self.status_dot)
            glow.setOffset(0, 0)
            self.status_dot.setGraphicsEffect(glow)
        glow.setBlurRadius(int(glow_r))
        glow.setColor(color)

    # ── 动画 ──────────────────────────────────────────
    def _init_animations(self):
        self._color_anim = QPropertyAnimation(self, b"accent_alpha")
        self._color_anim.setDuration(600)
        self._color_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(400)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def showEvent(self, event):
        super().showEvent(event)
        self.setWindowOpacity(0.0)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.start()

    def _animate_accent(self, target: QColor):
        self._color_from = QColor(self._current_accent)
        self._color_to = target
        self._color_anim.stop()
        self._color_anim.setStartValue(0.0)
        self._color_anim.setEndValue(1.0)
        self._color_anim.start()

    # ── 绘制 ──────────────────────────────────────────
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        cw, ch = self.container.width(), self.container.height()
        cx, cy = self.container.pos().x(), self.container.pos().y()
        cr = QRectF(cx, cy, cw, ch)

        # 阴影
        for i in range(6, 0, -1):
            off = i * 3
            exp = i * 2.5
            a = int(18 * (7 - i) / 7)
            sr = cr.adjusted(-exp, -exp + off * 0.3, exp, exp + off)
            sp = QPainterPath()
            sp.addRoundedRect(sr, self._radius + exp, self._radius + exp)
            p.fillPath(sp, QColor(0, 0, 0, a))

        # 背景
        bg = QPainterPath()
        bg.addRoundedRect(cr, self._radius, self._radius)
        grad = QLinearGradient(QPointF(cx, cy), QPointF(cx, cy + ch))
        grad.setColorAt(0, C_BG_TOP)
        grad.setColorAt(1, C_BG_BOT)
        p.fillPath(bg, grad)
        p.fillPath(bg, QColor(255, 255, 255, 40))
        p.setPen(QPen(QColor(255, 255, 255, 160), 1))
        p.drawPath(bg)

        # 内部玻璃反光条（顶部高光）
        highlight = QRectF(cx + 20, cy + 1, cw - 40, 30)
        hp = QPainterPath()
        hp.addRoundedRect(highlight, 16, 16)
        hg = QLinearGradient(QPointF(cx, cy), QPointF(cx, cy + 30))
        hg.setColorAt(0, QColor(255, 255, 255, 60))
        hg.setColorAt(1, QColor(255, 255, 255, 0))
        p.fillPath(hp, hg)

        # 卡片
        for card in [self.status_card, self.cred_card]:
            self._paint_card(p, card)

        self._paint_accent(p, self.status_card)
        p.end()

    def _paint_card(self, p: QPainter, w: QWidget):
        pos = w.mapTo(self, QPoint(0, 0))
        r = QRectF(pos.x() - 2, pos.y() - 2, w.width() + 4, w.height() + 4)
        path = QPainterPath()
        path.addRoundedRect(r, 14, 14)

        # 多层玻璃效果
        p.fillPath(path, QColor(255, 255, 255, 30))  # 底层
        p.fillPath(path, C_CARD)  # 主体

        # 顶部高光
        top_hl = QRectF(r.x() + 10, r.y(), r.width() - 20, r.height() * 0.4)
        thp = QPainterPath()
        thp.addRoundedRect(top_hl, 14, 14)
        tg = QLinearGradient(QPointF(r.x(), r.y()), QPointF(r.x(), r.y() + r.height() * 0.4))
        tg.setColorAt(0, QColor(255, 255, 255, 50))
        tg.setColorAt(1, QColor(255, 255, 255, 0))
        p.fillPath(thp, tg)

        # 边框
        p.setPen(QPen(C_CARD_BORDER, 1))
        p.drawPath(path)

    def _paint_accent(self, p: QPainter, w: QWidget):
        t = self._accent_alpha / 180.0 if hasattr(self, '_color_from') else 1.0
        if hasattr(self, '_color_from') and hasattr(self, '_color_to'):
            self._current_accent = lerp_color(self._color_from, self._color_to, t)

        pos = w.mapTo(self, QPoint(0, 0))
        x, y = pos.x() - 2, pos.y() - 2
        bw = w.width() + 4

        br = QRectF(x + 14, y + 1, bw - 28, 3)
        bp = QPainterPath()
        bp.addRoundedRect(br, 1.5, 1.5)

        a = self._current_accent
        g = QLinearGradient(QPointF(br.left(), 0), QPointF(br.right(), 0))
        g.setColorAt(0, QColor(a.red(), a.green(), a.blue(), 30))
        g.setColorAt(0.5, a)
        g.setColorAt(1, QColor(a.red(), a.green(), a.blue(), 30))
        p.fillPath(bp, g)

    # ── 拖拽 ──────────────────────────────────────────
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and e.position().y() < 44:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            e.accept()

    def mouseMoveEvent(self, e):
        if self._drag_pos and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)
            e.accept()

    def mouseReleaseEvent(self, e):
        self._drag_pos = None

    # ── 托盘 ──────────────────────────────────────────
    def init_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(create_icon())
        self.tray_icon.setToolTip(f"{APP_NAME} v{APP_VERSION}")

        menu = QMenu()
        for text, slot in [
            ("显示主窗口", self.show_window),
            ("手动登录", self.manual_login),
            ("下线", self.manual_logout),
            ("退出", self.quit_app),
        ]:
            act = QAction(text, self)
            act.triggered.connect(slot)
            menu.addAction(act)

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(
            lambda r: self.show_window() if r == QSystemTrayIcon.ActivationReason.DoubleClick else None
        )
        self.tray_icon.show()

    # ── 网络 ──────────────────────────────────────────
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
        url = self.config.get("logout_url", "")
        if self.online and url:
            d = get_online_duration(url)
            self.duration_label.setText(f"在线时长: {d}")
            self.tray_icon.setToolTip(f"GiWiFi - 已连接 ({d})")
        else:
            self.duration_label.setText("")

    def on_status_changed(self, online: bool):
        self.online = online
        if online:
            self.status_label.setText("已连接")
            self.status_label.setStyleSheet("color:#34C759;background:transparent")
            self.tray_icon.setIcon(create_icon("#34C759"))
            self.status_desc.setText("网络已连通，可以正常上网")
            self.status_desc.setStyleSheet("color:#34C759;background:transparent")
            self._animate_accent(C_GREEN)
        else:
            self.status_label.setText("未连接")
            self.status_label.setStyleSheet("color:#FF3B30;background:transparent")
            self.tray_icon.setIcon(create_icon("#FF3B30"))
            self.status_desc.setText("未连接到网络，等待自动重连...")
            self.status_desc.setStyleSheet("color:#FF3B30;background:transparent")
            self.duration_label.setText("")
            self._animate_accent(C_RED)

    # ── 业务 ──────────────────────────────────────────
    def auto_login(self, portal_url: str):
        try:
            if not self.config.get("auto_reconnect", True):
                self.log("检测到断线，自动登录已关闭")
                return
            u, pw = self.config.get("username", ""), self.config.get("password", "")
            if not u or not pw:
                self.log("未配置账号密码，无法自动登录")
                return
            self.log("检测到断线，正在自动登录...")
            ok, msg, lu = login_giwifi(u, pw, portal_url)
            self.log(msg)
            if ok and lu:
                self.config["logout_url"] = lu
                save_config(self.config)
        except Exception as e:
            self.log(f"自动登录异常: {e}")

    def manual_login(self):
        try:
            u = self.username_input.text().strip()
            pw = self.password_input.text().strip()
            if not u or not pw:
                QMessageBox.warning(self, "提示", "请先输入账号和密码")
                return
            self.log("正在检测网络...")
            online, portal = check_online()
            if online:
                self.log("网络已连通，无需登录")
                return
            if not portal:
                portal = self.config.get("portal_url", "")
                self.log("未检测到认证页面，使用默认地址...")
            else:
                self.log("已获取认证页面，正在登录...")
            ok, msg, lu = login_giwifi(u, pw, portal)
            self.log(msg)
            if ok and lu:
                self.config["logout_url"] = lu
                save_config(self.config)
        except Exception as e:
            self.log(f"手动登录异常: {e}")

    def manual_logout(self):
        try:
            lu = self.config.get("logout_url", "")
            if not lu:
                self.log("无下线信息，请先登录")
                return
            self.log("正在下线...")
            ok, msg = logout_giwifi(lu)
            self.log(msg)
            if ok:
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

    def toggle_autostart(self, on: bool):
        if on:
            enable_autostart()
            self.log("已启用开机自启动")
        else:
            disable_autostart()
            self.log("已禁用开机自启动")

    def toggle_auto_reconnect(self, on: bool):
        self.config["auto_reconnect"] = on
        save_config(self.config)
        self.log(f"已{'启用' if on else '禁用'}掉线自动登录")

    def log(self, text: str):
        self.log_label.setText(text)
        file_log(text)

    def show_window(self):
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self.tray_icon.showMessage(
            APP_NAME, "程序已最小化到系统托盘，双击图标可恢复窗口",
            QSystemTrayIcon.MessageIcon.Information, 2000,
        )

    def quit_app(self):
        self.duration_timer.stop()
        self.checker.stop()
        self.checker.wait()
        self.tray_icon.hide()
        QApplication.quit()

import sys
import os
import math
import time
import psutil
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QDialog, QDialogButtonBox,
    QSystemTrayIcon, QMenu, QMessageBox, QTextEdit,
    QGraphicsDropShadowEffect,
)
from PySide6.QtCore import (
    Qt, QTimer, QPoint, QPointF, QRect, QRectF, QSize,
    QPropertyAnimation, QEasingCurve, Property, Signal,
    QSequentialAnimationGroup, QAbstractAnimation, QThread,
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
from diagnose import run_diagnosis

# 通知开关配置键
NOTIFY_ENABLED_KEY = "notify_enabled"
# 开机静默模式配置键
SILENT_START_KEY = "silent_start"
# 深色模式配置键（旧字段，保留兼容）
DARK_MODE_KEY = "dark_mode"
# 主题模式配置键：light / dark / auto（跟随系统）
THEME_MODE_KEY = "theme_mode"
# 今日流量统计配置键
TRAFFIC_DATE_KEY = "traffic_date"
TRAFFIC_SENT_KEY = "traffic_sent"
TRAFFIC_RECV_KEY = "traffic_recv"
# 今日掉线次数配置键
OFFLINE_DATE_KEY = "offline_date"
OFFLINE_COUNT_KEY = "offline_count"

APP_NAME = "GiWiFi自动登录"
APP_VERSION = "1.2.0"
APP_AUTHOR = "YuanXi"

# 检查更新：GitHub 最新 Release
UPDATE_API = "https://api.github.com/repos/Yuanxi01/GiWiFi-AutoLogin/releases/latest"

# ── 配色 ──────────────────────────────────────────────
# 设计系统：Minimalism & Swiss Style（ui-ux-pro-max 生成）
# 两套完整主题：白天模式「晴空白」 / 黑夜模式「深夜蓝」
# 全部语义色 token 化，正文对比度 ≥ 4.5:1

# 白天模式 · 晴空白：柔和冷灰蓝底 + 石板墨文字 + 靛蓝主色
LIGHT_THEME = {
    # 窗口
    "bg_top": QColor(0xF8, 0xFA, 0xFC),          # slate-50（非纯白底）
    "bg_bot": QColor(0xE6, 0xED, 0xF5),          # 柔和冷灰蓝
    "window_border": QColor(0xD8, 0xE2, 0xEC),
    "shadow": QColor(15, 23, 42, 36),
    # 卡片
    "card": QColor(255, 255, 255, 244),
    "card_border": QColor(0xE2, 0xE8, 0xF0),
    # 文字
    "text": QColor(0x0F, 0x17, 0x2A),            # slate-900
    "text_sec": QColor(0x47, 0x55, 0x69),        # slate-600
    "text_ter": QColor(0x64, 0x74, 0x8B),        # slate-500
    # 主色
    "primary": QColor(0x1D, 0x4E, 0xD8),         # blue-700
    "primary_hover": QColor(0x1E, 0x40, 0xAF),   # blue-800
    "focus_ring": QColor(29, 78, 216, 110),
    # 语义色
    "success": QColor(0x15, 0x80, 0x3D),         # green-700 文字
    "success_dot": QColor(0x22, 0xC5, 0x5E),     # green-500 圆点
    "danger": QColor(0xDC, 0x26, 0x26),          # red-600 文字
    "danger_dot": QColor(0xEF, 0x44, 0x44),
    # 控件
    "input_bg": QColor(255, 255, 255, 235),
    "input_border": QColor(0xC9, 0xD4, 0xE0),
    "input_focus_bg": QColor(255, 255, 255, 255),
    "surface": QColor(255, 255, 255, 240),       # 次按钮
    "surface_hover": QColor(0xEE, 0xF3, 0xF8),
    "track_off": QColor(0xC6, 0xD2, 0xDF),       # 开关关闭态轨道
    "divider": QColor(0xE6, 0xEC, 0xF3),
    "highlight": QColor(255, 255, 255, 110),
}

# 黑夜模式 · 深夜蓝：slate-900 夜空底 + 亮蓝主色 + 高亮状态色
DARK_THEME = {
    # 窗口
    "bg_top": QColor(0x0F, 0x17, 0x2A),          # slate-900
    "bg_bot": QColor(0x0A, 0x0F, 0x1E),          # 更深一档
    "window_border": QColor(51, 65, 85, 160),    # slate-700
    "shadow": QColor(0, 0, 0, 130),
    # 卡片
    "card": QColor(30, 41, 59, 235),             # slate-800
    "card_border": QColor(0x33, 0x41, 0x55),     # slate-700（暗色下清晰可见）
    # 文字
    "text": QColor(0xF8, 0xFA, 0xFC),            # slate-50
    "text_sec": QColor(0x94, 0xA3, 0xB8),        # slate-400
    "text_ter": QColor(0x8A, 0x99, 0xB0),
    # 主色
    "primary": QColor(0x25, 0x63, 0xEB),         # blue-600（白字 4.5:1）
    "primary_hover": QColor(0x3B, 0x82, 0xF6),   # blue-500
    "focus_ring": QColor(96, 165, 250, 150),
    # 语义色
    "success": QColor(0x4A, 0xDE, 0x80),         # green-400 文字（暗底高对比）
    "success_dot": QColor(0x22, 0xC5, 0x5E),
    "danger": QColor(0xF8, 0x71, 0x71),          # red-400 文字
    "danger_dot": QColor(0xEF, 0x44, 0x44),
    # 控件
    "input_bg": QColor(10, 16, 30, 235),         # 深一档内嵌输入框
    "input_border": QColor(0x33, 0x41, 0x55),
    "input_focus_bg": QColor(10, 16, 30, 255),
    "surface": QColor(37, 48, 70, 240),          # 次按钮（比卡片亮半档）
    "surface_hover": QColor(0x2E, 0x3B, 0x57),
    "track_off": QColor(0x3A, 0x47, 0x61),
    "divider": QColor(0x26, 0x32, 0x4A),
    "highlight": QColor(255, 255, 255, 16),
}

# 当前主题（默认白天模式）
CURRENT_THEME = LIGHT_THEME.copy()

# 主题切换过渡：进度由属性动画驱动（0→1），期间所有自绘控件取旧→新插值色
_TRANSITION_FROM = None
_TRANSITION_T = 1.0
APP_WIDTH, APP_HEIGHT = 440, 464


def theme_color(key: str) -> QColor:
    """当前主题色；切换过渡期间返回旧主题→新主题的插值色"""
    if _TRANSITION_FROM is None or _TRANSITION_T >= 1.0:
        return CURRENT_THEME[key]
    return lerp_color(_TRANSITION_FROM[key], CURRENT_THEME[key], _TRANSITION_T)


def set_transition_progress(t: float):
    global _TRANSITION_T
    _TRANSITION_T = max(0.0, min(1.0, t))


def get_theme_mode(cfg: dict) -> str:
    """主题模式：light / dark / auto；无新字段时兼容旧 dark_mode 布尔值"""
    mode = cfg.get(THEME_MODE_KEY)
    if mode in ("light", "dark", "auto"):
        return mode
    return "dark" if cfg.get(DARK_MODE_KEY, False) else "light"


def system_prefers_dark() -> bool:
    """读取 Windows「应用深色模式」系统设置（注册表）"""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        try:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return value == 0
        finally:
            winreg.CloseKey(key)
    except Exception:
        return False

# 固定颜色（不受主题影响）：托盘图标与窗口控制点
C_GREEN = QColor(0x22, 0xC5, 0x5E)
C_RED = QColor(0xEF, 0x44, 0x44)


def _rgba(c: QColor, alpha: int = None) -> str:
    """QColor → Qt QSS rgba() 字符串"""
    a = c.alpha() if alpha is None else alpha
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {a})"


def build_window_qss(t: dict) -> str:
    """由主题 token 生成全局 QSS（输入框 / 文字），替代硬编码色值"""
    return f"""
    QLabel {{
        color: {t['text'].name()};
        background: transparent;
        border: none;
    }}
    QLineEdit {{
        background: {_rgba(t['input_bg'])};
        border: 1.5px solid {t['input_border'].name()};
        border-radius: 8px;
        padding: 5px 12px;
        font-size: 13px;
        color: {t['text'].name()};
        min-height: 20px;
        selection-background-color: {t['primary'].name()};
    }}
    QLineEdit:focus {{
        border: 1.5px solid {t['primary'].name()};
        background: {_rgba(t['input_focus_bg'])};
    }}
    """

# 全局字体 — 思源黑体 CN，带系统回退链（缺失字体时依序回退，避免显示方框）
_FONT_FAMILY = "Source Han Sans CN"
_FONT_FALLBACKS = ["思源黑体", "Source Han Sans SC", "Microsoft YaHei UI", "微软雅黑", "Segoe UI"]

def _make_font(size, weight=QFont.Weight.Normal):
    f = QFont(_FONT_FAMILY, size, weight)
    f.setFamilies([_FONT_FAMILY] + _FONT_FALLBACKS)
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
        self._bg_color = QColor(theme_color("primary")) if checked else QColor(theme_color("track_off"))
        self.setFixedSize(58 + (len(text) * 13 + 8 if text else 0), 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # Q 弹回弹：滑块带轻微过冲再落位
        self._anim = QPropertyAnimation(self, b"circle_x")
        self._anim.setDuration(320)
        _back = QEasingCurve(QEasingCurve.Type.OutBack)
        _back.setOvershoot(1.0)
        self._anim.setEasingCurve(_back)

        self._color_anim = QPropertyAnimation(self, b"bg_color")
        self._color_anim.setDuration(250)
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

    def _track_color(self) -> QColor:
        """轨道色：点击动画期间用动画值，其余时候实时取主题色（随主题过渡自动插值）"""
        if self._color_anim.state() == QPropertyAnimation.State.Running:
            return self._bg_color
        return QColor(theme_color("primary") if self._checked else theme_color("track_off"))

    def setChecked(self, v: bool):
        self._checked = v
        target_x = self._RIGHT_X if v else self._LEFT_X
        target_c = QColor(theme_color("primary")) if v else QColor(theme_color("track_off"))
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
        p.fillPath(tp, self._track_color())

        # 圆形滑块 (直径 22, 半径 10)
        cx = self._circle_x + 11
        cy = 15.0
        r = 10.0

        p.setPen(Qt.NoPen)

        # 滑块柔和投影（单层，极简）
        shadow = QRadialGradient(QPointF(cx, cy + 1), r + 3)
        shadow.setColorAt(0.4, QColor(0, 0, 0, 45))
        shadow.setColorAt(1, QColor(0, 0, 0, 0))
        p.setBrush(shadow)
        p.drawEllipse(QPointF(cx, cy + 0.5), r + 2.5, r + 2.5)

        # 白色圆
        p.setBrush(QColor(255, 255, 255))
        p.drawEllipse(QPointF(cx, cy), r, r)

        # 顶部微高光
        hl = QRadialGradient(QPointF(cx - 2, cy - 3), r)
        hl.setColorAt(0, QColor(255, 255, 255, 140))
        hl.setColorAt(0.4, QColor(255, 255, 255, 40))
        hl.setColorAt(1, QColor(255, 255, 255, 0))
        p.setBrush(hl)
        p.drawEllipse(QPointF(cx, cy), r, r)

        # 文字
        if self._text:
            p.setPen(theme_color("text"))
            p.setFont(APP_FONT)
            p.drawText(QRectF(60, 0, self.width() - 60, 30),
                       Qt.AlignmentFlag.AlignVCenter, self._text)

        p.end()


# ═══════════════════════════════════════════════════════
#  主题模式选择器（白天 / 黑夜 / 跟随系统 三段控件）
# ═══════════════════════════════════════════════════════
class ThemeModeSelector(QWidget):
    modeChanged = Signal(str)

    _MODES = ["light", "dark", "auto"]
    _LABELS = ["白天", "黑夜", "跟随系统"]

    def __init__(self, mode: str = "light", parent=None):
        super().__init__(parent)
        if mode not in self._MODES:
            mode = "light"
        self._mode = mode
        self._index = self._MODES.index(mode)
        self._pos = float(self._index)  # 指示器滑动位置（单位：段）
        self.setFixedHeight(36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("主题模式：白天 / 黑夜 / 跟随系统深色")

        self._anim = QPropertyAnimation(self, b"indicator_pos")
        self._anim.setDuration(320)
        ec = QEasingCurve(QEasingCurve.Type.OutBack)
        ec.setOvershoot(1.0)
        self._anim.setEasingCurve(ec)

    def _get_pos(self):
        return self._pos

    def _set_pos(self, v):
        self._pos = v
        self.update()

    indicator_pos = Property(float, _get_pos, _set_pos)

    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str, animate: bool = True):
        if mode not in self._MODES:
            return
        target = self._MODES.index(mode)
        self._index = target
        self._mode = mode
        self._anim.stop()
        if animate and self._pos != float(target):
            self._anim.setStartValue(self._pos)
            self._anim.setEndValue(float(target))
            self._anim.start()
        else:
            self._pos = float(target)
        self.update()

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        seg_w = self.width() / 3.0
        idx = max(0, min(2, int(event.position().x() / seg_w)))
        if self._MODES[idx] != self._mode:
            self.set_mode(self._MODES[idx])
            self.modeChanged.emit(self._mode)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # 轨道
        track = QRectF(0.5, 0.5, w - 1, h - 1)
        tp = QPainterPath()
        tp.addRoundedRect(track, 10, 10)
        p.fillPath(tp, theme_color("input_bg"))
        p.setPen(QPen(theme_color("input_border"), 1))
        p.drawPath(tp)

        # 滑动指示器（Q 弹回弹）
        seg_w = w / 3.0
        pad = 3.0
        ind = QRectF(pad + self._pos * seg_w, pad, seg_w - pad * 2, h - pad * 2)
        ip = QPainterPath()
        ip.addRoundedRect(ind, 8, 8)
        p.fillPath(ip, theme_color("surface"))
        p.setPen(QPen(theme_color("input_border"), 1))
        p.drawPath(ip)

        # 三段文字
        for i, label in enumerate(self._LABELS):
            rect = QRectF(i * seg_w, 0, seg_w, h)
            if i == self._index:
                p.setPen(theme_color("primary"))
                p.setFont(APP_FONT_BOLD)
            else:
                p.setPen(theme_color("text_sec"))
                p.setFont(APP_FONT)
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)

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

        self.setFixedHeight(38)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(APP_FONT_BOLD)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)

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
        path.addRoundedRect(rect, 10, 10)

        if self._primary:
            # 主按钮：实色主色，hover 平滑过渡到 hover 色（200ms）
            fill = lerp_color(theme_color("primary"), theme_color("primary_hover"), self._hover_progress)
            p.fillPath(path, fill)
        else:
            # 次按钮：平面表面色 + 细边框，hover 微亮
            fill = lerp_color(theme_color("surface"), theme_color("surface_hover"), self._hover_progress)
            p.fillPath(path, fill)
            border = lerp_color(theme_color("input_border"), theme_color("text_ter"), self._hover_progress)
            p.setPen(QPen(border, 1))
            p.drawPath(path)

        # 键盘焦点环（可达性：焦点可见）
        if self.hasFocus():
            ring = QRectF(0.5, 0.5, w - 1, h - 1)
            ring_path = QPainterPath()
            ring_path.addRoundedRect(ring, 10, 10)
            p.setPen(QPen(theme_color("focus_ring"), 2))
            p.drawPath(ring_path)

        # 文字
        p.setPen(QColor("white") if self._primary else theme_color("text"))
        p.setFont(self.font())
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text())

        p.end()


# ═══════════════════════════════════════════════════════
#  设置图标按钮（自定义绘制齿轮）
# ═══════════════════════════════════════════════════════
class SettingsButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._hovered = False
        self.setFixedSize(20, 20)
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

        accent = theme_color("primary") if self._hovered else theme_color("text_ter")
        # 背景圆
        bg_color = QColor(accent.red(), accent.green(), accent.blue(), 38)
        border_color = QColor(accent.red(), accent.green(), accent.blue(), 102)
        p.setPen(QPen(border_color, 1))
        p.setBrush(bg_color)
        p.drawEllipse(1, 1, 18, 18)

        # 齿轮颜色
        gear_color = accent
        p.setPen(QPen(gear_color, 1.3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)

        cx, cy = 10.0, 10.0

        # 齿轮外圈（8个齿）
        outer_r = 7.0
        inner_r = 5.0
        teeth = 8
        angle_step = 360.0 / teeth

        path = QPainterPath()
        for i in range(teeth):
            angle1 = math.radians(i * angle_step - angle_step * 0.2)
            angle2 = math.radians(i * angle_step + angle_step * 0.2)
            angle3 = math.radians(i * angle_step + angle_step * 0.35)
            angle4 = math.radians((i + 1) * angle_step - angle_step * 0.35)

            if i == 0:
                path.moveTo(cx + inner_r * math.cos(angle1), cy + inner_r * math.sin(angle1))

            path.lineTo(cx + outer_r * math.cos(angle1), cy + outer_r * math.sin(angle1))
            path.lineTo(cx + outer_r * math.cos(angle2), cy + outer_r * math.sin(angle2))
            path.lineTo(cx + inner_r * math.cos(angle3), cy + inner_r * math.sin(angle3))
            path.lineTo(cx + inner_r * math.cos(angle4), cy + inner_r * math.sin(angle4))

        path.closeSubpath()
        p.drawPath(path)

        # 中心圆
        p.setBrush(gear_color)
        p.drawEllipse(QPointF(cx, cy), 2.5, 2.5)

        # 中心圆镂空
        p.setBrush(bg_color)
        p.drawEllipse(QPointF(cx, cy), 1.2, 1.2)

        p.end()


# ═══════════════════════════════════════════════════════
#  昼夜主题切换按钮（自绘太阳 / 月亮矢量图标）
#  白天模式显示月亮（点击进入黑夜），黑夜模式显示太阳
# ═══════════════════════════════════════════════════════
class ThemeToggleButton(QPushButton):
    def __init__(self, dark: bool = False, parent=None):
        super().__init__(parent)
        self._dark = dark
        self._hovered = False
        self.setFixedSize(20, 20)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("切换白天 / 黑夜模式")

    def set_dark(self, dark: bool):
        self._dark = dark
        self.update()

    def enterEvent(self, event):
        self._hovered = True
        self.update()

    def leaveEvent(self, event):
        self._hovered = False
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        accent = theme_color("primary") if self._hovered else theme_color("text_ter")
        bg_color = QColor(accent.red(), accent.green(), accent.blue(), 38)
        border_color = QColor(accent.red(), accent.green(), accent.blue(), 102)

        p.setPen(QPen(border_color, 1))
        p.setBrush(bg_color)
        p.drawEllipse(1, 1, 18, 18)

        p.setPen(Qt.NoPen)
        p.setBrush(accent)
        cx, cy = 10.0, 10.0

        if self._dark:
            # 太阳：中心圆 + 8 条光芒
            p.drawEllipse(QPointF(cx, cy), 3.2, 3.2)
            p.setPen(QPen(accent, 1.4, Qt.SolidLine, Qt.RoundCap))
            p.setBrush(Qt.NoBrush)
            for i in range(8):
                a = math.radians(i * 45)
                x1, y1 = cx + 5.0 * math.cos(a), cy + 5.0 * math.sin(a)
                x2, y2 = cx + 7.2 * math.cos(a), cy + 7.2 * math.sin(a)
                p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
        else:
            # 月亮：两圆相减得到月牙
            moon = QPainterPath()
            moon.addEllipse(QPointF(cx, cy), 6.0, 6.0)
            cut = QPainterPath()
            cut.addEllipse(QPointF(cx + 2.6, cy - 2.2), 5.2, 5.2)
            p.drawPath(moon.subtracted(cut))

        p.end()


# ═══════════════════════════════════════════════════════
#  日志查看器对话框
# ═══════════════════════════════════════════════════════
class LogViewerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("日志查看器")
        self.resize(600, 400)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._build_ui()
        self.load_logs()

    def _build_ui(self):
        # 主布局 - 留出阴影空间
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)

        # 容器
        self._container = QWidget()
        self._container.setObjectName("logViewerContainer")
        self._container.setStyleSheet(f"""
            #logViewerContainer {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {CURRENT_THEME['bg_top'].name()}, stop:1 {CURRENT_THEME['bg_bot'].name()});
                border-radius: 16px;
                border: 1px solid rgba({CURRENT_THEME['card_border'].red()},
                    {CURRENT_THEME['card_border'].green()},
                    {CURRENT_THEME['card_border'].blue()}, 220);
            }}
        """)
        outer.addWidget(self._container)

        layout = QVBoxLayout(self._container)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # 标题栏
        title_bar = QHBoxLayout()
        self.title_label = QLabel("日志查看器")
        self.title_label.setFont(APP_FONT_TITLE)
        self.title_label.setStyleSheet(f"color: {CURRENT_THEME['text'].name()}; background: transparent; border: none;")
        title_bar.addWidget(self.title_label)
        title_bar.addStretch()

        # 关闭按钮
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        danger = CURRENT_THEME["danger"]
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba({danger.red()}, {danger.green()}, {danger.blue()}, 38);
                border: 1px solid rgba({danger.red()}, {danger.green()}, {danger.blue()}, 76);
                border-radius: 12px;
                font-size: 12px;
                color: {danger.name()};
            }}
            QPushButton:hover {{
                background: rgba({danger.red()}, {danger.green()}, {danger.blue()}, 64);
            }}
        """)
        close_btn.clicked.connect(self.close)
        title_bar.addWidget(close_btn)
        layout.addLayout(title_bar)

        # 日志文本框（颜色全部来自主题 token）
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        t = CURRENT_THEME
        self.log_text.setStyleSheet(f"""
            QTextEdit {{
                background: {_rgba(t['input_bg'])};
                border: 1.5px solid {t['input_border'].name()};
                border-radius: 10px;
                padding: 8px;
                font-family: "Consolas", "Monaco", monospace;
                font-size: 12px;
                color: {t['text'].name()};
                selection-background-color: {t['primary'].name()};
            }}
        """)
        layout.addWidget(self.log_text)

        # 按钮行
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        refresh_btn = GlassButton("刷新")
        refresh_btn.clicked.connect(self.load_logs)
        btn_layout.addWidget(refresh_btn)

        clear_btn = GlassButton("清空日志")
        clear_btn.clicked.connect(self.clear_logs)
        btn_layout.addWidget(clear_btn)

        close_btn2 = GlassButton("关闭", primary=True)
        close_btn2.clicked.connect(self.close)
        btn_layout.addWidget(close_btn2)

        layout.addLayout(btn_layout)

        # 延迟创建阴影效果
        QTimer.singleShot(50, self._add_shadow)

    def _add_shadow(self):
        """添加阴影效果"""
        shadow = QGraphicsDropShadowEffect(self._container)
        shadow.setBlurRadius(25)
        shadow.setColor(QColor(0, 0, 0, 80))
        shadow.setOffset(0, 8)
        self._container.setGraphicsEffect(shadow)

    def load_logs(self):
        """加载日志文件"""
        try:
            log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "giwifi.log")
            if os.path.exists(log_file):
                with open(log_file, "r", encoding="utf-8") as f:
                    content = f.read()
                self.log_text.setText(content)
                # 滚动到底部
                scrollbar = self.log_text.verticalScrollBar()
                scrollbar.setValue(scrollbar.maximum())
            else:
                self.log_text.setText("日志文件不存在")
        except Exception as e:
            self.log_text.setText(f"读取日志失败: {e}")

    def clear_logs(self):
        """清空日志文件"""
        try:
            log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "giwifi.log")
            if os.path.exists(log_file):
                with open(log_file, "w", encoding="utf-8") as f:
                    f.write("")
                self.log_text.setText("日志已清空")
        except Exception as e:
            self.log_text.setText(f"清空日志失败: {e}")


# ═══════════════════════════════════════════════════════
#  检查更新（后台线程，查 GitHub 最新 Release）
# ═══════════════════════════════════════════════════════
class UpdateChecker(QThread):
    foundNew = Signal(str)   # 发现新版本
    upToDate = Signal()      # 已是最新

    def __init__(self, parent=None):
        super().__init__(parent)

    def run(self):
        import requests
        try:
            resp = requests.get(
                UPDATE_API, timeout=8,
                headers={"Accept": "application/vnd.github+json"},
            )
            tag = (resp.json().get("tag_name") or "").lstrip("v").strip()

            def ver_tuple(v):
                try:
                    return tuple(int(x) for x in v.split("."))
                except Exception:
                    return (0,)

            if tag and ver_tuple(tag) > ver_tuple(APP_VERSION):
                self.foundNew.emit(tag)
            else:
                self.upToDate.emit()
        except Exception as e:
            file_log(f"检查更新失败: {e}")
            self.upToDate.emit()  # 检查失败按最新处理，不打扰用户


# ═══════════════════════════════════════════════════════
#  断网诊断（后台线程）
# ═══════════════════════════════════════════════════════
class DiagnoseWorker(QThread):
    done = Signal(str)

    def __init__(self, portal_url: str, parent=None):
        super().__init__(parent)
        self._portal = portal_url

    def run(self):
        lines, _verdict = run_diagnosis(self._portal)
        self.done.emit("\n".join(lines))


# ═══════════════════════════════════════════════════════
#  设置对话框
# ═══════════════════════════════════════════════════════
class SettingsDialog(QDialog):
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config.copy()
        self.setWindowTitle("设置")
        self.setFixedSize(340, 350)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._build_ui()

    def _build_ui(self):
        # 主布局 - 留出阴影空间
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)

        # 容器
        self._container = QWidget()
        self._container.setObjectName("settingsContainer")
        self._container.setStyleSheet(f"""
            #settingsContainer {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {CURRENT_THEME['bg_top'].name()}, stop:1 {CURRENT_THEME['bg_bot'].name()});
                border-radius: 16px;
                border: 1px solid rgba({CURRENT_THEME['card_border'].red()},
                    {CURRENT_THEME['card_border'].green()},
                    {CURRENT_THEME['card_border'].blue()}, 220);
            }}
        """)
        outer.addWidget(self._container)

        layout = QVBoxLayout(self._container)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # 标题
        self.title_label = QLabel("设置")
        self.title_label.setFont(APP_FONT_TITLE)
        self.title_label.setStyleSheet(f"color: {CURRENT_THEME['text'].name()}; background: transparent; border: none;")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title_label)

        # 通知开关
        self.notify_switch = ToggleSwitch(
            "启用 Windows 通知",
            self.config.get(NOTIFY_ENABLED_KEY, False)
        )
        layout.addWidget(self.notify_switch)

        # 静默模式开关
        self.silent_start_switch = ToggleSwitch(
            "开机静默模式",
            self.config.get(SILENT_START_KEY, False)
        )
        layout.addWidget(self.silent_start_switch)

        # 主题模式选择（白天 / 黑夜 / 跟随系统）
        self.theme_selector = ThemeModeSelector(get_theme_mode(self.config))
        layout.addWidget(self.theme_selector)

        # 版本与检查更新
        ver_row = QHBoxLayout()
        self.version_label = QLabel(f"当前版本 v{APP_VERSION}")
        self.version_label.setFont(APP_FONT_SMALL)
        self.version_label.setStyleSheet(
            f"color: {CURRENT_THEME['text_sec'].name()}; background: transparent; border: none;")
        self.check_update_btn = GlassButton("检查更新")
        ver_row.addWidget(self.version_label)
        ver_row.addStretch()
        ver_row.addWidget(self.check_update_btn)
        layout.addLayout(ver_row)

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        ok_btn = GlassButton("确定", primary=True)
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)

        cancel_btn = GlassButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

        # 延迟创建阴影效果，避免首次打开卡顿
        QTimer.singleShot(50, self._add_shadow)

    def _add_shadow(self):
        """添加阴影效果"""
        shadow = QGraphicsDropShadowEffect(self._container)
        shadow.setBlurRadius(25)
        shadow.setColor(QColor(0, 0, 0, 80))
        shadow.setOffset(0, 8)
        self._container.setGraphicsEffect(shadow)

    def get_config(self) -> dict:
        self.config[NOTIFY_ENABLED_KEY] = self.notify_switch.isChecked()
        self.config[SILENT_START_KEY] = self.silent_start_switch.isChecked()
        mode = self.theme_selector.mode()
        self.config[THEME_MODE_KEY] = mode
        self.config[DARK_MODE_KEY] = (mode == "dark")  # 兼容旧字段
        return self.config

    def refresh_theme(self):
        """刷新对话框主题样式"""
        self._container.setStyleSheet(f"""
            #settingsContainer {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {CURRENT_THEME['bg_top'].name()}, stop:1 {CURRENT_THEME['bg_bot'].name()});
                border-radius: 16px;
                border: 1px solid rgba({CURRENT_THEME['card_border'].red()},
                    {CURRENT_THEME['card_border'].green()},
                    {CURRENT_THEME['card_border'].blue()}, 220);
            }}
        """)
        self.title_label.setStyleSheet(f"color: {CURRENT_THEME['text'].name()}; background: transparent; border: none;")


# ═══════════════════════════════════════════════════════
#  主窗口
# ═══════════════════════════════════════════════════════
class MainWindow(QWidget):
    def _get_accent_alpha(self):
        return self._accent_alpha

    def _set_accent_alpha(self, val):
        self._accent_alpha = val

    accent_alpha = Property(float, _get_accent_alpha, _set_accent_alpha)

    def _get_theme_t(self):
        return _TRANSITION_T

    def _set_theme_t(self, v):
        set_transition_progress(v)
        # 重绘窗口与全部自绘子控件，实现整窗颜色交叉淡化
        self.update()
        for w in self.findChildren(QWidget):
            w.update()

    theme_t = Property(float, _get_theme_t, _set_theme_t)

    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.online = False
        self._drag_pos = None
        self._radius = 18
        # 连接状态语义：pending(检测中) / online / offline
        self._status_state = "pending"

        self._accent_alpha = 180.0
        self._current_accent = QColor(CURRENT_THEME["danger_dot"])
        self._last_effective_dark = False

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(APP_WIDTH, APP_HEIGHT)
        self.setWindowIcon(create_icon())

        # 应用主题
        self._apply_theme()

        self._build_ui()
        self.init_tray()
        self.init_checker()
        self.init_duration_timer()
        self._init_animations()
        self._init_speed_checker()

        # 跟随系统深色模式：轮询注册表变化
        self._sys_theme_timer = QTimer(self)
        self._sys_theme_timer.timeout.connect(self._poll_system_theme)
        self._sys_theme_timer.start(3000)

        # 预创建设置对话框，避免首次打开卡顿
        self._settings_dialog = SettingsDialog(self.config, self)
        self._settings_dialog.check_update_btn.clicked.connect(self._manual_check_update)

        # 更新检查 / 断网诊断状态
        self._update_checker = None
        self._new_version = None
        self._diag_worker = None
        QTimer.singleShot(8000, self._auto_check_update)

    def _effective_dark(self) -> bool:
        """当前应生效的深色状态（auto 模式下读系统设置）"""
        mode = get_theme_mode(self.config)
        if mode == "auto":
            return system_prefers_dark()
        return mode == "dark"

    def _apply_theme(self):
        """应用当前主题；运行中切换时带 320ms 颜色淡化 + Q 弹脉冲"""
        global CURRENT_THEME, _TRANSITION_FROM
        is_dark = self._effective_dark()
        self._last_effective_dark = is_dark
        new_theme = (DARK_THEME if is_dark else LIGHT_THEME).copy()

        can_fade = hasattr(self, "_theme_anim") and new_theme is not CURRENT_THEME
        if can_fade:
            _TRANSITION_FROM = CURRENT_THEME
        CURRENT_THEME = new_theme
        self.setStyleSheet(build_window_qss(CURRENT_THEME))

        if can_fade:
            self._theme_anim.stop()
            self._theme_anim.setStartValue(0.0)
            self._theme_anim.setEndValue(1.0)
            self._theme_anim.start()
            self._pop_window()
        else:
            set_transition_progress(1.0)

        # 同步标题栏昼夜切换按钮
        if hasattr(self, "theme_btn"):
            self.theme_btn.set_dark(is_dark)

        # 按当前连接状态刷新状态区配色
        if hasattr(self, "status_label"):
            self._set_status_look(self._status_state, animate=False)
        self._apply_widget_styles()

    def toggle_theme(self):
        """标题栏昼夜切换：接管为明确的白天/黑夜模式（覆盖跟随系统）"""
        mode = "light" if self._effective_dark() else "dark"
        self.config[THEME_MODE_KEY] = mode
        self.config[DARK_MODE_KEY] = (mode == "dark")
        save_config(self.config)
        self._apply_theme()
        self.update()
        self.log("已切换至{}模式".format("黑夜" if mode == "dark" else "白天"))

    def _poll_system_theme(self):
        """跟随系统模式：轮询注册表，系统深色切换时自动换肤"""
        if get_theme_mode(self.config) != "auto":
            return
        if system_prefers_dark() != self._last_effective_dark:
            self.log("检测到系统深色模式变更，已自动切换主题")
            self._apply_theme()
            self.update()

    def _apply_widget_styles(self):
        """应用主题相关的控件内联样式"""
        if not hasattr(self, 'title_label'):
            return  # _build_ui 还未执行
        text_color = CURRENT_THEME["text"].name()
        sec_color = CURRENT_THEME["text_sec"].name()
        ter_color = CURRENT_THEME["text_ter"].name()

        self.title_label.setStyleSheet(f"color:{text_color};background:transparent")
        self.duration_label.setStyleSheet(f"color:{sec_color};background:transparent")
        self.speed_label.setStyleSheet(f"color:{sec_color};background:transparent")
        self.traffic_label.setStyleSheet(f"color:{ter_color};background:transparent")
        self.log_label.setStyleSheet(f"color:{sec_color};background:transparent")
        self.ver_label.setStyleSheet(f"color:{ter_color};background:transparent")

    def _set_status_look(self, state: str, animate: bool = True):
        """根据连接状态刷新状态区配色（文字 / 圆点 / 顶部强调条）"""
        t = CURRENT_THEME
        if state == "online":
            c_text, c_dot = t["success"], t["success_dot"]
        elif state == "offline":
            c_text, c_dot = t["danger"], t["danger_dot"]
        else:
            c_text, c_dot = t["text"], t["danger_dot"]

        self.status_label.setStyleSheet(f"color:{c_text.name()};background:transparent")
        self.status_desc.setStyleSheet(f"color:{c_text.name()};background:transparent")
        self._apply_dot_style(c_dot, 18)

        if animate and hasattr(self, "_color_anim"):
            self._animate_accent(c_dot)
        else:
            self._current_accent = QColor(c_dot)

    # ── 构建 UI ──────────────────────────────────────
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 28)

        self.container = QWidget()
        outer.addWidget(self.container)

        root = QVBoxLayout(self.container)
        root.setContentsMargins(22, 14, 22, 14)
        root.setSpacing(10)

        # ── 标题栏 ──
        title_bar = QHBoxLayout()
        title_bar.setContentsMargins(0, 0, 0, 6)

        # 左侧红绿灯
        self.btn_close = TrafficLight("#FF5F57", "#FF3B30")
        self.btn_close.clicked.connect(self.quit_app)
        self.btn_mini = TrafficLight("#FEBC2E", "#F5A623")
        self.btn_mini.clicked.connect(self.hide)
        lights_container = QWidget()
        lights = QHBoxLayout(lights_container)
        lights.setContentsMargins(0, 0, 0, 0)
        lights.setSpacing(6)
        lights.addWidget(self.btn_close)
        lights.addWidget(self.btn_mini)
        title_bar.addWidget(lights_container)

        # 中间标题
        self.title_label = QLabel(APP_NAME)
        self.title_label.setFont(APP_FONT_TITLE)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_bar.addWidget(self.title_label, 1)

        # 右侧昼夜切换 + 设置按钮
        self.theme_btn = ThemeToggleButton(self.config.get(DARK_MODE_KEY, False))
        self.theme_btn.clicked.connect(self.toggle_theme)

        self.settings_btn = SettingsButton()
        self.settings_btn.clicked.connect(self.show_settings)

        settings_container = QWidget()
        settings_layout = QHBoxLayout(settings_container)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.setSpacing(6)
        settings_layout.addWidget(self.theme_btn)
        settings_layout.addWidget(self.settings_btn)
        title_bar.addWidget(settings_container)

        root.addLayout(title_bar)

        # ── 状态卡片 ──
        self.status_card = QWidget()
        sc = QVBoxLayout(self.status_card)
        sc.setContentsMargins(16, 12, 16, 14)
        sc.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(10)

        dot_box = QWidget()
        dot_box.setFixedSize(20, 30)  # 与状态行同高，保证圆点与文字同行居中
        dl = QVBoxLayout(dot_box)
        dl.setContentsMargins(5, 4, 5, 6)  # 底部略厚：CJK 字形光学中心略高于行框中心
        self.status_dot = QLabel()
        self.status_dot.setFixedSize(10, 10)
        self._apply_dot_style(CURRENT_THEME["danger_dot"], 12)
        dl.addWidget(self.status_dot, 0, Qt.AlignmentFlag.AlignCenter)
        top.addWidget(dot_box, 0, Qt.AlignmentFlag.AlignVCenter)

        self.status_label = QLabel("检测中...")
        self.status_label.setFont(APP_FONT_BIG)
        self.status_label.setMinimumHeight(30)  # 防止布局挤压导致文字上下裁切
        self.status_label.setStyleSheet(f"color:{CURRENT_THEME['text'].name()};background:transparent")
        top.addWidget(self.status_label)
        top.addStretch()

        self.duration_label = QLabel("")
        self.duration_label.setFont(APP_FONT_SEC)
        self.duration_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top.addWidget(self.duration_label)
        sc.addLayout(top)

        self.status_desc = QLabel("等待网络检测...")
        self.status_desc.setFont(APP_FONT_SMALL)
        self.status_desc.setMinimumHeight(18)
        self.status_desc.setStyleSheet(f"color:{CURRENT_THEME['text_sec'].name()};background:transparent")
        sc.addWidget(self.status_desc)

        # 网速显示
        self.speed_label = QLabel("")
        self.speed_label.setFont(APP_FONT_SMALL)
        self.speed_label.setMinimumHeight(18)
        self.speed_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        sc.addWidget(self.speed_label)

        # 今日流量统计
        self.traffic_label = QLabel("")
        self.traffic_label.setFont(APP_FONT_SMALL)
        self.traffic_label.setMinimumHeight(18)
        self.traffic_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        sc.addWidget(self.traffic_label)

        root.addWidget(self.status_card)

        # ── 登录卡片 ──
        self.cred_card = QWidget()
        cc = QVBoxLayout(self.cred_card)
        cc.setContentsMargins(16, 12, 16, 14)  # 与状态卡完全一致的内边距
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

        self.diag_btn = GlassButton("诊断")
        self.diag_btn.clicked.connect(self.manual_diagnose)
        btn_row.addWidget(self.diag_btn)

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
        bot.addWidget(self.log_label, 1)

        self.ver_label = QLabel(f"v{APP_VERSION}  {APP_AUTHOR}")
        self.ver_label.setFont(APP_FONT_SMALL)
        self.ver_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        bot.addWidget(self.ver_label)
        root.addLayout(bot)

        # 应用主题相关的控件样式
        self._apply_widget_styles()

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

        # 主题切换：整窗颜色交叉淡化
        self._theme_anim = QPropertyAnimation(self, b"theme_t", self)
        self._theme_anim.setDuration(320)
        self._theme_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

        # 主题切换：Q 弹窗口脉冲（轻微压缩 → OutBack 回弹）
        self._pop_shrink = QPropertyAnimation(self, b"geometry", self)
        self._pop_shrink.setDuration(170)
        self._pop_shrink.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._pop_grow = QPropertyAnimation(self, b"geometry", self)
        self._pop_grow.setDuration(380)
        _pop_back = QEasingCurve(QEasingCurve.Type.OutBack)
        _pop_back.setOvershoot(1.2)
        self._pop_grow.setEasingCurve(_pop_back)
        self._pop_group = QSequentialAnimationGroup(self)
        self._pop_group.addAnimation(self._pop_shrink)
        self._pop_group.addAnimation(self._pop_grow)
        self._pop_group.finished.connect(self._on_pop_finished)
        self._pop_home = None

    def _pop_window(self):
        """窗口脉冲：先轻微压缩再 Q 弹回原位（需临时解除固定尺寸）"""
        if self._pop_group.state() == QAbstractAnimation.State.Running:
            return
        g = self.geometry()
        self._pop_home = QRect(g)
        small = QRect(QPoint(0, 0), QSize(int(g.width() * 0.955), int(g.height() * 0.955)))
        small.moveCenter(g.center())
        self.setMinimumSize(1, 1)
        self.setMaximumSize(16777215, 16777215)
        self._pop_shrink.setStartValue(g)
        self._pop_shrink.setEndValue(small)
        self._pop_grow.setStartValue(small)
        self._pop_grow.setEndValue(g)
        self._pop_group.start()

    def _on_pop_finished(self):
        if self._pop_home is not None:
            self.setFixedSize(APP_WIDTH, APP_HEIGHT)
            self.setGeometry(self._pop_home)
            self._pop_home = None

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

        # 单一柔和投影：多层极低透明度顺滑衰减（避免分层台阶感）
        token = theme_color("shadow")
        layers = 10
        for i in range(1, layers + 1):
            exp = i * 1.2
            a = int(token.alpha() * 0.25 * (1 - (i - 1) / layers))
            drop = i * 0.6  # 轻微下坠，模拟顶光
            sr = cr.adjusted(-exp, -exp + drop * 0.4, exp, exp + drop * 1.6)
            sp = QPainterPath()
            sp.addRoundedRect(sr, self._radius + exp, self._radius + exp)
            p.fillPath(sp, QColor(0, 0, 0, a))

        # 背景：垂直渐变 + 细边框（极简平面）
        bg = QPainterPath()
        bg.addRoundedRect(cr, self._radius, self._radius)
        grad = QLinearGradient(QPointF(cx, cy), QPointF(cx, cy + ch))
        grad.setColorAt(0, theme_color("bg_top"))
        grad.setColorAt(1, theme_color("bg_bot"))
        p.fillPath(bg, grad)
        p.setPen(QPen(theme_color("window_border"), 1))
        p.drawPath(bg)

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

        # 平面卡片：纯色填充 + 细边框（Swiss 极简，去掉玻璃渐变）
        p.fillPath(path, theme_color("card"))
        p.setPen(QPen(theme_color("card_border"), 1))
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
            ("断网诊断", self.manual_diagnose),
            ("查看日志", self.show_log_viewer),
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

    def show_log_viewer(self):
        """显示日志查看器"""
        dialog = LogViewerDialog(self)
        dialog.exec()

    # ── 网络 ──────────────────────────────────────────
    def init_checker(self):
        self.checker = NetworkChecker(
            self.config.get("check_interval", 10),
            self.config.get("portal_url", ""),
        )
        self.checker.status_changed.connect(self.on_status_changed)
        self.checker.login_needed.connect(self.auto_login)
        self.checker.start()

        # 登录重试机制
        self._login_retry_count = 0
        self._max_login_retries = 3
        self._login_retry_timer = QTimer(self)
        self._login_retry_timer.setSingleShot(True)
        self._login_retry_timer.timeout.connect(self._do_login_retry)

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

    def _init_speed_checker(self):
        """初始化网速检测器与今日流量统计"""
        self._last_bytes_sent = 0
        self._last_bytes_recv = 0
        # 今日流量：按日期重置，应用重启后延续当天的累计值
        today = time.strftime("%Y-%m-%d")
        if self.config.get(TRAFFIC_DATE_KEY) == today:
            self._day_sent = float(self.config.get(TRAFFIC_SENT_KEY, 0.0))
            self._day_recv = float(self.config.get(TRAFFIC_RECV_KEY, 0.0))
        else:
            self._day_sent = 0.0
            self._day_recv = 0.0
            self._persist_traffic()
        # 今日掉线次数：按日期重置，重启延续
        if self.config.get(OFFLINE_DATE_KEY) == today:
            self._offline_count = int(self.config.get(OFFLINE_COUNT_KEY, 0))
        else:
            self._offline_count = 0
            self.config[OFFLINE_DATE_KEY] = today
            self.config[OFFLINE_COUNT_KEY] = 0
            save_config(self.config)
        self._traffic_ticks = 0
        self._speed_timer = QTimer(self)
        self._speed_timer.timeout.connect(self._update_speed)
        self._speed_timer.start(2000)  # 每2秒检测一次
        self._update_speed()  # 立即检测一次

    def _update_speed(self):
        """更新网速显示与今日流量统计"""
        try:
            # 跨零点重置今日流量
            if time.strftime("%Y-%m-%d") != self.config.get(TRAFFIC_DATE_KEY):
                self._day_sent = 0.0
                self._day_recv = 0.0
                self._persist_traffic()

            net_io = psutil.net_io_counters()
            current_sent = net_io.bytes_sent
            current_recv = net_io.bytes_recv

            if self._last_bytes_sent > 0 and self._last_bytes_recv > 0:
                delta_sent = max(current_sent - self._last_bytes_sent, 0)
                delta_recv = max(current_recv - self._last_bytes_recv, 0)
                upload_speed = delta_sent / 2.0
                download_speed = delta_recv / 2.0

                # 累计今日流量
                self._day_sent += delta_sent
                self._day_recv += delta_recv

                # 每 15 次采样（约 30 秒）持久化一次
                self._traffic_ticks += 1
                if self._traffic_ticks >= 15:
                    self._traffic_ticks = 0
                    self._persist_traffic()

                # 更新界面
                upload_str = self._format_speed(upload_speed)
                download_str = self._format_speed(download_speed)
                self.speed_label.setText(f"↑{upload_str} ↓{download_str}")

                # 更新托盘 tooltip
                if self.online:
                    url = self.config.get("logout_url", "")
                    today = f"今日 ↑{self._format_amount(self._day_sent)} ↓{self._format_amount(self._day_recv)}"
                    if url:
                        d = get_online_duration(url)
                        self.tray_icon.setToolTip(f"GiWiFi - 已连接 ({d})\n↑{upload_str} ↓{download_str}\n{today}")
                    else:
                        self.tray_icon.setToolTip(f"GiWiFi - 已连接\n↑{upload_str} ↓{download_str}\n{today}")

            self._last_bytes_sent = current_sent
            self._last_bytes_recv = current_recv
            self._update_traffic_label()
        except Exception:
            pass

    def _update_traffic_label(self):
        """刷新状态卡上的今日流量/掉线统计行"""
        if not hasattr(self, "traffic_label"):
            return
        text = "今日流量  ↑{} · ↓{}".format(
            self._format_amount(self._day_sent),
            self._format_amount(self._day_recv),
        )
        n = getattr(self, "_offline_count", 0)
        if n > 0:
            text += f"  ·  掉线 {n} 次"
        self.traffic_label.setText(text)

    def _persist_traffic(self):
        """把今日流量与掉线次数写入配置文件"""
        self.config[TRAFFIC_DATE_KEY] = time.strftime("%Y-%m-%d")
        self.config[TRAFFIC_SENT_KEY] = float(self._day_sent)
        self.config[TRAFFIC_RECV_KEY] = float(self._day_recv)
        self.config[OFFLINE_DATE_KEY] = time.strftime("%Y-%m-%d")
        self.config[OFFLINE_COUNT_KEY] = int(getattr(self, "_offline_count", 0))
        save_config(self.config)

    @staticmethod
    def _format_amount(n: float) -> str:
        """流量总量格式化（B/KB/MB/GB）"""
        if n < 1024:
            return f"{n:.0f}B"
        if n < 1024 ** 2:
            return f"{n / 1024:.1f}KB"
        if n < 1024 ** 3:
            return f"{n / 1024 ** 2:.1f}MB"
        return f"{n / 1024 ** 3:.2f}GB"

    def _format_speed(self, speed_bytes: float) -> str:
        """格式化速度显示"""
        if speed_bytes < 1024:
            return f"{speed_bytes:.0f}B/s"
        elif speed_bytes < 1024 * 1024:
            return f"{speed_bytes / 1024:.1f}KB/s"
        else:
            return f"{speed_bytes / (1024 * 1024):.1f}MB/s"

    def on_status_changed(self, online: bool):
        # 只在状态真正变化时更新 UI 和发送通知
        if self.online == online:
            return

        self.online = online
        if online:
            self._status_state = "online"
            self.status_label.setText("已连接")
            self.tray_icon.setIcon(create_icon("#22C55E"))
            self.status_desc.setText("网络已连通，可以正常上网")
            self._set_status_look("online")
            self.notify("网络已连接", "校园网连接正常",
                        QSystemTrayIcon.MessageIcon.Information)
        else:
            self._status_state = "offline"
            self.status_label.setText("未连接")
            self.tray_icon.setIcon(create_icon("#EF4444"))
            self.status_desc.setText("未连接到网络，等待自动重连...")
            self.duration_label.setText("")
            # 今日掉线次数 +1（跨零点自动重置）
            today = time.strftime("%Y-%m-%d")
            if self.config.get(OFFLINE_DATE_KEY) != today:
                self.config[OFFLINE_DATE_KEY] = today
                self._offline_count = 0
            self._offline_count = getattr(self, "_offline_count", 0) + 1
            self.config[OFFLINE_COUNT_KEY] = self._offline_count
            save_config(self.config)
            self._set_status_look("offline")
            self.notify("网络断开", "校园网连接已断开，正在尝试自动重连...",
                        QSystemTrayIcon.MessageIcon.Warning)

    # ── 业务 ──────────────────────────────────────────
    def auto_login(self, portal_url: str):
        try:
            if not self.config.get("auto_reconnect", True):
                self.log("检测到断线，自动登录已关闭")
                self.notify("网络断开", "检测到断线，但自动登录已关闭",
                            QSystemTrayIcon.MessageIcon.Warning)
                return
            u, pw = self.config.get("username", ""), self.config.get("password", "")
            if not u or not pw:
                self.log("未配置账号密码，无法自动登录")
                self.notify("自动登录失败", "未配置账号密码，请先填写并保存",
                            QSystemTrayIcon.MessageIcon.Warning)
                return
            self._login_retry_count = 0
            self._login_portal_url = portal_url
            self.log("检测到断线，正在自动登录...")
            ok, msg, lu = login_giwifi(u, pw, portal_url)
            self.log(msg)
            if ok:
                self._on_auto_login_success(lu)
            else:
                self._schedule_login_retry(msg)
        except Exception as e:
            self.log(f"自动登录异常: {e}")
            self._schedule_login_retry(str(e))

    def _on_auto_login_success(self, logout_url=None):
        """自动登录成功处理"""
        self._login_retry_count = 0
        self._login_retry_timer.stop()
        self.notify("自动登录成功", "网络已恢复连接",
                    QSystemTrayIcon.MessageIcon.Information)
        if logout_url:
            self.config["logout_url"] = logout_url
            save_config(self.config)

    def _schedule_login_retry(self, reason: str):
        """安排登录重试"""
        self._login_retry_count += 1
        if self._login_retry_count < self._max_login_retries:
            self.log(f"自动登录失败（第{self._login_retry_count}次），5秒后重试: {reason}")
            self._login_retry_timer.start(5000)
        else:
            self.log(f"自动登录已重试{self._max_login_retries}次，均失败: {reason}")
            self.notify("自动登录失败", f"重试{self._max_login_retries}次后仍失败",
                        QSystemTrayIcon.MessageIcon.Warning)
            self._login_retry_count = 0

    def _do_login_retry(self):
        """执行登录重试"""
        if not self.config.get("auto_reconnect", True):
            return
        # 检查是否已经恢复连接
        if self.online:
            self._login_retry_count = 0
            return
        u, pw = self.config.get("username", ""), self.config.get("password", "")
        if not u or not pw:
            return
        portal = getattr(self, '_login_portal_url', '') or self.config.get("portal_url", "")
        if not portal:
            self.log("重试失败: 无可用的认证地址")
            return
        try:
            self.log(f"正在重试自动登录（第{self._login_retry_count + 1}次）...")
            ok, msg, lu = login_giwifi(u, pw, portal)
            self.log(msg)
            if ok:
                self._on_auto_login_success(lu)
            else:
                self._schedule_login_retry(msg)
        except Exception as e:
            self.log(f"重试登录异常: {e}")
            self._schedule_login_retry(str(e))

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
                self.notify("网络正常", "当前已连接网络，无需登录",
                            QSystemTrayIcon.MessageIcon.Information)
                return
            if not portal:
                portal = self.config.get("portal_url", "")
                self.log("未检测到认证页面，使用默认地址...")
            else:
                self.log("已获取认证页面，正在登录...")
            ok, msg, lu = login_giwifi(u, pw, portal)
            self.log(msg)
            if ok:
                self.notify("登录成功", "已成功连接到校园网",
                            QSystemTrayIcon.MessageIcon.Information)
                if lu:
                    self.config["logout_url"] = lu
                    save_config(self.config)
            else:
                self.notify("登录失败", msg,
                            QSystemTrayIcon.MessageIcon.Warning)
        except Exception as e:
            self.log(f"手动登录异常: {e}")
            self.notify("登录异常", str(e),
                        QSystemTrayIcon.MessageIcon.Critical)

    def manual_logout(self):
        try:
            lu = self.config.get("logout_url", "")
            if not lu:
                self.log("无下线信息，请先登录")
                self.notify("无法下线", "没有下线信息，请先登录",
                            QSystemTrayIcon.MessageIcon.Warning)
                return
            self.log("正在下线...")
            ok, msg = logout_giwifi(lu)
            self.log(msg)
            if ok:
                self.notify("下线成功", "已断开校园网连接",
                            QSystemTrayIcon.MessageIcon.Information)
                self.config.pop("logout_url", None)
                save_config(self.config)
            else:
                self.notify("下线失败", msg,
                            QSystemTrayIcon.MessageIcon.Warning)
        except Exception as e:
            self.log(f"下线异常: {e}")
            self.notify("下线异常", str(e),
                        QSystemTrayIcon.MessageIcon.Critical)

    def save_config(self):
        self.config["username"] = self.username_input.text().strip()
        self.config["password"] = self.password_input.text().strip()
        save_config(self.config)
        self.checker.set_interval(self.config.get("check_interval", 10))
        self.checker.set_portal_url(self.config.get("portal_url", ""))
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

    # ── 检查更新 ──────────────────────────────────────
    def _auto_check_update(self):
        """启动 8 秒后静默检查一次更新"""
        self._start_update_checker(silent=True)

    def _manual_check_update(self):
        """设置面板「检查更新」按钮"""
        self._start_update_checker(silent=False)

    def _start_update_checker(self, silent: bool):
        if self._update_checker is not None and self._update_checker.isRunning():
            return
        if not silent:
            self._settings_dialog.version_label.setText("正在检查更新...")
        self._update_checker = UpdateChecker(self)
        self._update_checker.foundNew.connect(
            lambda v: self._on_update_found(v, silent))
        self._update_checker.upToDate.connect(
            lambda: self._on_update_ok(silent))
        self._update_checker.start()

    def _on_update_found(self, version: str, silent: bool):
        self._new_version = version
        if hasattr(self, "_settings_dialog"):
            self._settings_dialog.version_label.setText(
                f"发现新版本 v{version}，请到 GitHub Release 下载")
        self.log(f"发现新版本 v{version}，请到 GitHub Release 页面下载")
        self.notify("发现新版本", f"v{version} 已发布，请到 GitHub Release 页面下载更新",
                    QSystemTrayIcon.MessageIcon.Information, 5000)

    def _on_update_ok(self, silent: bool):
        if not silent and hasattr(self, "_settings_dialog"):
            self._settings_dialog.version_label.setText(f"当前已是最新版本 v{APP_VERSION}")
        self.log("检查更新: 已是最新版本")

    # ── 断网诊断 ──────────────────────────────────────
    def manual_diagnose(self):
        """一键诊断掉线原因（网卡/网关/认证系统/外网）"""
        if self._diag_worker is not None and self._diag_worker.isRunning():
            return
        self.diag_btn.setEnabled(False)
        self.diag_btn.setText("诊断中...")
        self.log("正在执行断网诊断...")
        portal = self.config.get("portal_url", "")
        self._diag_worker = DiagnoseWorker(portal, self)
        self._diag_worker.done.connect(self._on_diagnosis_done)
        self._diag_worker.start()

    def _on_diagnosis_done(self, report: str):
        self.diag_btn.setEnabled(True)
        self.diag_btn.setText("诊断")
        self.log("断网诊断完成")
        box = QMessageBox(self)
        box.setWindowTitle("断网诊断")
        box.setText(report)
        box.setStyleSheet(f"QLabel {{ color: {CURRENT_THEME['text'].name()}; }}")
        box.exec()

    def show_settings(self):
        """显示设置对话框"""
        # 每次打开前更新配置
        self._settings_dialog.config = self.config.copy()
        self._settings_dialog.refresh_theme()
        self._settings_dialog.notify_switch.setChecked(
            self.config.get(NOTIFY_ENABLED_KEY, False)
        )
        self._settings_dialog.silent_start_switch.setChecked(
            self.config.get(SILENT_START_KEY, False)
        )
        self._settings_dialog.theme_selector.set_mode(
            get_theme_mode(self.config), animate=False
        )

        if self._settings_dialog.exec() == QDialog.DialogCode.Accepted:
            self.config = self._settings_dialog.get_config()
            save_config(self.config)
            # 应用深色模式
            self._apply_theme()
            self.update()
            self.log("设置已保存")

    def log(self, text: str):
        self.log_label.setText(text)
        file_log(text)

    def notify(self, title: str, text: str, icon=QSystemTrayIcon.MessageIcon.Information, duration: int = 3000):
        """发送 Windows toast 通知（根据设置决定是否发送）"""
        if self.config.get(NOTIFY_ENABLED_KEY, False):
            self.tray_icon.showMessage(title, text, icon, duration)

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
        try:
            self._persist_traffic()  # 退出前保存今日流量
        except Exception:
            pass
        self.duration_timer.stop()
        self._login_retry_timer.stop()
        self.checker.stop()
        self.checker.wait()
        self.tray_icon.hide()
        QApplication.quit()

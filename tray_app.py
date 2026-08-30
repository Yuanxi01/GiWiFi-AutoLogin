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
# 使用场景配置键：auto（自动判断）/ school（校园）/ home（家庭）
SCENE_MODE_KEY = "scene_mode"

APP_NAME = "GiWiFi自动登录"
APP_VERSION = "1.3.0"
APP_AUTHOR = "YuanXi"

# 检查更新：GitHub 最新 Release
UPDATE_API = "https://api.github.com/repos/Yuanxi01/GiWiFi-AutoLogin/releases/latest"


def get_scene_mode(cfg: dict) -> str:
    """使用场景：auto（自动判断在校）/ school（校园）/ home（家庭）"""
    mode = cfg.get(SCENE_MODE_KEY)
    return mode if mode in ("auto", "school", "home") else "auto"


def portal_reachable(portal_url: str, timeout: int = 3) -> bool:
    """校园网认证页是否可达：可达说明当前在学校网络里"""
    import requests
    try:
        requests.get(portal_url or "http://172.27.253.230/gportal/web/login", timeout=timeout)
        return True  # 任意 HTTP 响应都算可达（含 302/403）
    except Exception:
        return False

# ── 配色 / 主题 ─────────────────────────────────────────
# 默认主题（晴空白 / 深夜蓝）已原样收编至 themes/default.py，视觉零改动；
# 液态玻璃主题（可选）在 themes/liquid_glass.py，由设置面板「主题风格」切换。
# 切换采用「写入配置 + 重启生效」：WA_TranslucentBackground 仅在窗口 show 前
# 设置才有效，运行中热切换会导致透明失效（取舍说明见 themes/theme_manager.py）。
from themes import ThemeManager, THEME_DEFAULT, THEME_GLASS
from themes.default import LIGHT_THEME, DARK_THEME, build_window_qss
import themes.liquid_glass as _glass

# 主题家族：default（原有样式，零改动启动） / liquid_glass（液态玻璃，需重启生效）
THEME_FAMILY = "default"

# 当前主题（默认白天模式）
CURRENT_THEME = LIGHT_THEME.copy()


def is_glass() -> bool:
    """当前是否为液态玻璃主题家族"""
    return THEME_FAMILY == "liquid_glass"

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


def _resource_path(name: str) -> str:
    """资源文件路径：onefile 解包目录 / exe 目录 / 源码目录依次查找"""
    bases = []
    if getattr(sys, "_MEIPASS", None):
        bases.append(sys._MEIPASS)
    bases.append(os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
                 else os.path.dirname(os.path.abspath(__file__)))
    for base in bases:
        p = os.path.join(base, name)
        if os.path.exists(p):
            return p
    return os.path.join(bases[-1], name)


def create_icon(color: str = "#34C759") -> QIcon:
    """应用图标：叶片图标 + 右下角状态小圆点（在线绿/离线红/检测中灰）"""
    try:
        base = QPixmap(_resource_path("app_icon.png"))
        if not base.isNull():
            size = 64
            pm = QPixmap(size, size)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            p.setRenderHint(QPainter.Antialiasing)
            p.drawPixmap(0, 0, size, size, base)
            # 状态小圆点（右下角，白描边保证浅色背景可见）
            p.setBrush(QColor(color))
            p.setPen(QPen(Qt.white, 3))
            p.drawEllipse(QPoint(size - 13, size - 13), 8, 8)
            p.end()
            return QIcon(pm)
    except Exception:
        pass
    # 兜底：资源缺失时回退到旧版自绘图标
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(4, 4, 56, 56)
    p.setPen(QColor("white"))
    p.setFont(QFont("Arial", 24, QFont.Weight.Bold))
    p.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "W")
    p.end()
    return QIcon


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
        # 玻璃主题：48×28 iOS 胶囊（选中态 #34C759，由 _paint_glass_track 绘制）
        if THEME_FAMILY == "liquid_glass":
            self._LEFT_X = 3.0
            self._RIGHT_X = 23.0
        self._circle_x = self._RIGHT_X if checked else self._LEFT_X
        self._bg_color = QColor(theme_color("primary")) if checked else QColor(theme_color("track_off"))
        if THEME_FAMILY == "liquid_glass":
            self.setFixedSize(48 + (len(text) * 13 + 8 if text else 0), 30)
        else:
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

    def _paint_glass_track(self, event):
        """液态玻璃：48×28 iOS 胶囊开关（选中态 #34C759，滑块带位移动画）"""
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        track = QRectF(1, 1, 48, 28)
        tp = QPainterPath()
        tp.addRoundedRect(track, 14, 14)
        if self._checked:
            p.fillPath(tp, QColor("#34C759"))
        else:
            p.fillPath(tp, QColor(255, 255, 255, 45))
            p.setPen(QPen(QColor(255, 255, 255, 70), 1))
            p.drawPath(tp)
        # 滑块（复用 circle_x 位移动画）
        cx = self._circle_x + 12
        cy = 15.0
        p.setPen(Qt.PenStyle.NoPen)
        shadow = QRadialGradient(QPointF(cx, cy + 1), 14)
        shadow.setColorAt(0.4, QColor(0, 0, 0, 50))
        shadow.setColorAt(1, QColor(0, 0, 0, 0))
        p.setBrush(shadow)
        p.drawEllipse(QPointF(cx, cy + 0.5), 13.5, 13.5)
        p.setBrush(QColor("white"))
        p.drawEllipse(QPointF(cx, cy), 12, 12)
        if self._text:
            p.setPen(QColor("#F4F7FB"))
            p.setFont(APP_FONT)
            p.drawText(QRectF(56, 0, self.width() - 56, 30),
                       Qt.AlignmentFlag.AlignVCenter, self._text)
        p.end()

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
        if THEME_FAMILY == "liquid_glass":
            self._paint_glass_track(event)
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        dark = theme_color("text").red() > 128  # 经典家族的深浅主题

        # ── 内凹轨道（Neumorphism 凹槽：上沿压暗、下沿提亮）──
        track = QRectF(2, 4, 50, 22)
        tp = QPainterPath()
        tp.addRoundedRect(track, 11, 11)
        p.fillPath(tp, QColor("#E2E8F2") if not dark else QColor(9, 14, 26))
        p.save()
        p.setClipRect(QRectF(track.x(), track.y(), track.width(), track.height() / 2))
        p.setPen(QPen(QColor(0, 0, 0, 38) if not dark else QColor(0, 0, 0, 150), 2))
        p.drawPath(tp)
        p.restore()
        p.save()
        p.setClipRect(QRectF(track.x(), track.y() + track.height() / 2,
                             track.width(), track.height() / 2))
        p.setPen(QPen(QColor(255, 255, 255, 220) if not dark else QColor(255, 255, 255, 26), 2))
        p.drawPath(tp)
        p.restore()

        # ── 浮起滑块（投影 + 立体高光；选中态为品牌蓝）──
        cx = self._circle_x + 11
        cy = 15.0
        r = 10.0
        p.setPen(Qt.PenStyle.NoPen)

        shadow = QRadialGradient(QPointF(cx, cy + 1.5), r + 4)
        shadow.setColorAt(0.35, QColor(0, 0, 0, 70) if not dark else QColor(0, 0, 0, 160))
        shadow.setColorAt(1, QColor(0, 0, 0, 0))
        p.setBrush(shadow)
        p.drawEllipse(QPointF(cx, cy + 0.5), r + 3, r + 3)

        knob = QRadialGradient(QPointF(cx - r * 0.35, cy - r * 0.4), r * 1.9)
        if self._checked:
            knob.setColorAt(0, QColor(0x5E, 0x8A, 0xF5) if not dark else QColor(0x3B, 0x82, 0xF6))
            knob.setColorAt(1, QColor(0x2F, 0x5F, 0xD0) if not dark else QColor(0x1D, 0x4E, 0xD8))
            ring = QColor(255, 255, 255, 70) if not dark else QColor(0, 0, 0, 60)
        else:
            knob.setColorAt(0, QColor(255, 255, 255) if not dark else QColor(0xD8, 0xDF, 0xEA))
            knob.setColorAt(1, QColor(0xEC, 0xF0, 0xF7) if not dark else QColor(0x9A, 0xA6, 0xBC))
            ring = QColor(0, 0, 0, 30) if not dark else QColor(0, 0, 0, 90)
        p.setBrush(knob)
        p.drawEllipse(QPointF(cx, cy), r, r)
        p.setPen(QPen(ring, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), r, r)

        # 文字
        if self._text:
            p.setPen(theme_color("text"))
            p.setFont(APP_FONT)
            p.drawText(QRectF(60, 0, self.width() - 60, 30),
                       Qt.AlignmentFlag.AlignVCenter, self._text)

        p.end()
        p.end()


# ═══════════════════════════════════════════════════════
#  液态玻璃按钮（仅液态玻璃主题使用；经典主题继续用 GlassButton）
#  三层自绘：半透明基底 + 顶部白色高光渐变 + 1.2px 白描边
#  胶囊造型（圆角 = 高度一半，高 44px），悬浮变亮 / 按压下沉回弹
# ═══════════════════════════════════════════════════════
class LiquidGlassButton(QPushButton):
    def __init__(self, text: str, primary: bool = False, parent=None):
        super().__init__(text, parent)
        self._primary = primary      # 主按钮基底稍亮
        self._danger = False         # 红色玻璃变体（「下线」按钮）
        self._hover_progress = 0.0   # 悬浮进度 0..1（220ms OutCubic）
        self._press_t = 0.0          # 按压进度 0..1（下沉/缩放由此派生）
        self.setFixedHeight(_glass.BUTTON_HEIGHT)  # 44px，胶囊圆角 = 高度一半
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(APP_FONT_BOLD)

        # 悬浮：220ms OutCubic 变亮
        self._hover_anim = QPropertyAnimation(self, b"hover_progress")
        self._hover_anim.setDuration(220)
        self._hover_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        # 按压：260ms OutBack 弹性回弹（下沉 2px + 缩放 0.98 复位）
        self._press_anim = QPropertyAnimation(self, b"press_t")
        self._press_anim.setDuration(260)
        self._press_anim.setEasingCurve(QEasingCurve.Type.OutBack)

    # ── 动画属性 ─────────────────────────────────────
    def _get_hover(self):
        return self._hover_progress

    def _set_hover(self, v):
        self._hover_progress = max(0.0, min(1.0, v))
        self.update()

    hover_progress = Property(float, _get_hover, _set_hover)

    def _get_press(self):
        return self._press_t

    def _set_press(self, v):
        self._press_t = max(0.0, min(1.0, v))
        self.update()

    press_t = Property(float, _get_press, _set_press)

    def set_danger(self, on: bool):
        """红色玻璃变体（用于「下线」等警示动作）"""
        self._danger = on
        self.update()

    # ── 交互 ─────────────────────────────────────────
    def enterEvent(self, event):
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_progress)
        self._hover_anim.setEndValue(1.0)
        self._hover_anim.start()

    def leaveEvent(self, event):
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_progress)
        self._hover_anim.setEndValue(0.0)
        self._hover_anim.start()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_anim.stop()
            self._press_anim.setStartValue(self._press_t)
            self._press_anim.setEndValue(1.0)
            self._press_anim.start()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        # 松开：OutBack 弹性回弹（先弹出过冲再落回 0）
        self._press_anim.stop()
        self._press_anim.setStartValue(self._press_t)
        self._press_anim.setEndValue(0.0)
        self._press_anim.start()
        super().mouseReleaseEvent(event)

    # ── 绘制 ─────────────────────────────────────────
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # 按压派生量：下沉 2px + 缩放 0.98
        sink = _glass.BUTTON_PRESS_SINK_PX * self._press_t
        scale = 1.0 - (1.0 - _glass.BUTTON_PRESS_SCALE) * self._press_t
        p.translate(w / 2, h / 2)
        p.scale(scale, scale)
        p.translate(-w / 2, -h / 2 + sink)

        hv = self._hover_progress
        rect = QRectF(1, 1, w - 2, h - 2)
        path = QPainterPath()
        path.addRoundedRect(rect, h * _glass.BUTTON_RADIUS_RATIO, h * _glass.BUTTON_RADIUS_RATIO)

        # 第 1 层：半透明基底（悬浮动态加深；危险动作用红色玻璃）
        if self._danger:
            base_a = 110 + int(40 * hv)
            p.fillPath(path, QColor(255, 59, 48, base_a))
        else:
            base_a = _glass.BUTTON_BASE_ALPHA + int(
                (_glass.BUTTON_BASE_HOVER_ALPHA - _glass.BUTTON_BASE_ALPHA) * hv)
            p.fillPath(path, QColor(255, 255, 255, base_a))

        # 第 2 层：顶部白色高光渐变（上浓下淡，玻璃的"高光带"）
        hl = QLinearGradient(QPointF(0, 0), QPointF(0, h * 0.55))
        top_a = int(_glass.BUTTON_HIGHLIGHT_ALPHA * (0.55 + 0.45 * hv))
        hl.setColorAt(0.0, QColor(255, 255, 255, top_a))
        hl.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillPath(path, hl)

        # 第 3 层：1.2px 白描边（悬浮增亮）
        border_a = _glass.BUTTON_BORDER_ALPHA + int(
            (_glass.BUTTON_BORDER_HOVER_ALPHA - _glass.BUTTON_BORDER_ALPHA) * hv)
        if self._danger:
            p.setPen(QPen(QColor(255, 150, 143, border_a), 1.2))
        else:
            p.setPen(QPen(QColor(255, 255, 255, border_a), 1.2))
        p.drawPath(path)

        # 文字（白色粗体，保证玻璃上对比度）
        p.setPen(QColor("white"))
        p.setFont(self.font())
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text())
        p.end()



# ═══════════════════════════════════════════════════════
#  通用三段选择器（白天 / 黑夜 / 跟随系统；也用于场景选择）
# ═══════════════════════════════════════════════════════
class ThemeModeSelector(QWidget):
    modeChanged = Signal(str)

    def __init__(self, mode: str = "light", modes=None, labels=None,
                 tooltip: str = "", parent=None):
        super().__init__(parent)
        self._MODES = modes or ["light", "dark", "auto"]
        self._LABELS = labels or ["白天", "黑夜", "跟随系统"]
        if mode not in self._MODES:
            mode = self._MODES[0]
        self._mode = mode
        self._index = self._MODES.index(mode)
        self._pos = float(self._index)  # 指示器滑动位置（单位：段）
        self.setFixedHeight(36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tooltip or " / ".join(self._LABELS))

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
        seg_w = self.width() / len(self._MODES)  # 按模式数量分段（2 段/3 段通用）
        idx = max(0, min(len(self._MODES) - 1, int(event.position().x() / seg_w)))
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
        seg_w = w / len(self._MODES)  # 按模式数量分段（2 段/3 段通用）
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
class _DraggableDialogMixin:
    """无边框弹窗拖动：按住空白处/标签文字即可移动窗口（子控件不受影响）"""

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_offset = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            e.accept()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if getattr(self, "_drag_offset", None) is not None and (e.buttons() & Qt.LeftButton):
            self.move(e.globalPosition().toPoint() - self._drag_offset)
            e.accept()
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._drag_offset = None
        super().mouseReleaseEvent(e)


class LogViewerDialog(_DraggableDialogMixin, QDialog):
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
        if is_glass():
            # 液态玻璃：容器半透明白，背景由 DWM Acrylic 提供
            self._container.setStyleSheet(
                "#logViewerContainer { background: rgba(15, 23, 42, 150); "
                "border-radius: 16px; border: 1px solid rgba(255, 255, 255, 70); }")
        else:
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

    def showEvent(self, event):
        super().showEvent(event)
        # 液态玻璃主题：纯透明（与主窗口一致，不再申请 DWM backdrop）
        pass

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
#  场景模式选择器（自动判断 / 校园 / 家庭）
# ═══════════════════════════════════════════════════════
class SceneModeSelector(ThemeModeSelector):
    def __init__(self, mode: str = "auto", parent=None):
        super().__init__(
            mode,
            modes=["auto", "school", "home"],
            labels=["自动判断", "校园", "家庭"],
            tooltip="使用场景：自动判断是否在校园网；家庭网络下暂停校园网自动登录",
            parent=parent,
        )


# ═══════════════════════════════════════════════════════
#  场景探测（后台线程：认证页可达 = 在学校）
# ═══════════════════════════════════════════════════════
class SceneCheckWorker(QThread):
    done = Signal(bool)

    def __init__(self, portal_url: str, parent=None):
        super().__init__(parent)
        self._portal = portal_url

    def run(self):
        self.done.emit(portal_reachable(self._portal))


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
class SettingsDialog(_DraggableDialogMixin, QDialog):
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config.copy()
        self.setWindowTitle("设置")
        self.setFixedSize(340, 448)
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

        # 使用场景（自动判断 / 校园 / 家庭）
        self.scene_label = QLabel("使用场景")
        self.scene_label.setFont(APP_FONT_SMALL)
        self.scene_label.setStyleSheet(
            f"color: {CURRENT_THEME['text_sec'].name()}; background: transparent; border: none;")
        layout.addWidget(self.scene_label)
        self.scene_selector = SceneModeSelector(get_scene_mode(self.config))
        layout.addWidget(self.scene_selector)

        # 主题模式选择（白天 / 黑夜 / 跟随系统）
        theme_label = QLabel("主题模式（经典风格下生效）")
        theme_label.setFont(APP_FONT_SMALL)
        theme_label.setStyleSheet(
            f"color: {CURRENT_THEME['text_sec'].name()}; background: transparent; border: none;")
        layout.addWidget(theme_label)
        self.theme_selector = ThemeModeSelector(get_theme_mode(self.config))
        layout.addWidget(self.theme_selector)

        # 主题风格（经典 / 液态玻璃）——写入配置，重启生效
        family_label = QLabel("主题风格")
        family_label.setFont(APP_FONT_SMALL)
        family_label.setStyleSheet(
            f"color: {CURRENT_THEME['text_sec'].name()}; background: transparent; border: none;")
        layout.addWidget(family_label)
        self.family_selector = ThemeModeSelector(
            self.config.get("theme", THEME_DEFAULT),
            modes=[THEME_DEFAULT, THEME_GLASS],
            labels=["经典", "液态玻璃"],
            tooltip="液态玻璃为 Windows 11 毛玻璃效果；切换写入配置，重启后生效",
        )
        self.family_selector.modeChanged.connect(self._on_family_changed)
        layout.addWidget(self.family_selector)

        # 分隔呼吸
        layout.addSpacing(6)

        # 版本与检查更新（独立一行，不再与按钮挤在一起）
        ver_row = QHBoxLayout()
        ver_row.setSpacing(10)
        self.version_label = QLabel(f"当前版本 v{APP_VERSION}")
        self.version_label.setFont(APP_FONT_SMALL)
        self.version_label.setStyleSheet(
            f"color: {CURRENT_THEME['text_sec'].name()}; background: transparent; border: none;")
        self.check_update_btn = GlassButton("检查更新")
        self.check_update_btn.setFixedHeight(30)
        self.check_update_btn.setFixedWidth(108)
        ver_row.addWidget(self.version_label)
        ver_row.addStretch()
        ver_row.addWidget(self.check_update_btn)
        layout.addLayout(ver_row)

        # 按钮（统一高度，左右等宽）
        layout.addSpacing(6)
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        ok_btn = GlassButton("确定", primary=True)
        ok_btn.setFixedHeight(36)
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)

        cancel_btn = GlassButton("取消")
        cancel_btn.setFixedHeight(36)
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

    def showEvent(self, event):
        super().showEvent(event)
        # 液态玻璃主题：纯透明（与主窗口一致，不再申请 DWM backdrop）
        pass

    def get_config(self) -> dict:
        self.config[NOTIFY_ENABLED_KEY] = self.notify_switch.isChecked()
        self.config[SILENT_START_KEY] = self.silent_start_switch.isChecked()
        mode = self.theme_selector.mode()
        self.config[THEME_MODE_KEY] = mode
        self.config[DARK_MODE_KEY] = (mode == "dark")  # 兼容旧字段
        self.config[SCENE_MODE_KEY] = self.scene_selector.mode()
        self.config["theme"] = self.family_selector.mode()  # 主题家族（重启生效）
        return self.config

    def _on_family_changed(self, family: str):
        """主题风格切换：写入配置 + 提示重启
        （WA_TranslucentBackground 仅在窗口 show 前设置才有效，
        运行中热切换会导致毛玻璃透明失效，因此采用重启方案）"""
        ThemeManager.save_family(self.config, family)
        save_config(self.config)
        QMessageBox.information(
            self, "主题风格已保存",
            f"主题风格已切换为「{'液态玻璃' if family == THEME_GLASS else '经典'}」，"
            "重启软件后生效。\n\n"
            "（毛玻璃依托系统窗口合成，运行中直接切换会导致透明失效，"
            "因此需要重启一次软件；已自动保存，随时可切回「经典」。）")

    def refresh_theme(self):
        """刷新对话框主题样式"""
        if is_glass():
            # 液态玻璃：容器半透明白，背景由 DWM Acrylic 提供
            self._container.setStyleSheet(
                "#settingsContainer { background: rgba(15, 23, 42, 140); "
                "border-radius: 16px; border: 1px solid rgba(255, 255, 255, 70); }")
        else:
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
        sec = CURRENT_THEME["text_sec"].name()
        self.scene_label.setStyleSheet(f"color: {sec}; background: transparent; border: none;")
        self.version_label.setStyleSheet(f"color: {sec}; background: transparent; border: none;")


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
        # 主题家族：default（原有样式，零改动）/ liquid_glass（液态玻璃，重启生效）
        global THEME_FAMILY
        self.theme_manager = ThemeManager()
        THEME_FAMILY = self.theme_manager.load_family(self.config)
        # 把 theme 键固化进主配置：否则周期性的 _persist_traffic 整体写盘
        # 会把设置面板刚写入的 theme 字段覆盖回默认（真实踩过的坑）
        self.config.setdefault("theme", THEME_FAMILY)
        self._backdrop_applied = False
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
        self.setWindowIcon(create_icon("#9AA3AF"))  # 检测中：灰色状态点

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
        self._settings_dialog.scene_selector.modeChanged.connect(self._on_scene_mode_changed)

        # 更新检查 / 断网诊断 / 场景状态
        self._update_checker = None
        self._new_version = None
        self._diag_worker = None
        self._scene_worker = None
        self._auto_at_school = None  # None=未探测, True=在学校, False=在家
        QTimer.singleShot(8000, self._auto_check_update)
        QTimer.singleShot(1500, self._poll_scene)

        # 场景自动探测：每 5 分钟一次（仅 auto 模式生效）
        self._scene_timer = QTimer(self)
        self._scene_timer.timeout.connect(self._poll_scene)
        self._scene_timer.start(5 * 60 * 1000)

    def _effective_dark(self) -> bool:
        """当前应生效的深色状态（auto 模式下读系统设置）"""
        mode = get_theme_mode(self.config)
        if mode == "auto":
            return system_prefers_dark()
        return mode == "dark"

    def _apply_theme(self):
        """应用当前主题；运行中切换时带 320ms 颜色淡化 + Q 弹脉冲（仅经典主题）"""
        global CURRENT_THEME, _TRANSITION_FROM
        if is_glass():
            # 液态玻璃：CURRENT_THEME 换成玻璃语义色（key 与默认主题一致）；
            # QSS 先 setStyleSheet("") 清空再套玻璃版，避免两套样式残留叠加
            CURRENT_THEME = _glass.GLASS_THEME.copy()
            is_dark = self._effective_dark()  # 仅用于昼夜按钮图标同步（玻璃配色固定白色文字）
            self.setStyleSheet("")
            self.setStyleSheet(_glass.GLASS_QSS)
        else:
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
        # 按钮工厂：经典主题用 GlassButton；液态玻璃主题用 LiquidGlassButton
        btn_cls = LiquidGlassButton if THEME_FAMILY == "liquid_glass" else GlassButton
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.login_btn = btn_cls("手动登录", primary=True)
        self.login_btn.clicked.connect(self.manual_login)
        btn_row.addWidget(self.login_btn)

        self.save_btn = btn_cls("保存配置")
        self.save_btn.clicked.connect(self.save_config)
        btn_row.addWidget(self.save_btn)

        self.logout_btn = btn_cls("下线")
        self.logout_btn.clicked.connect(self.manual_logout)
        if THEME_FAMILY == "liquid_glass":
            self.logout_btn.set_danger(True)  # 下线：红色玻璃变体
        btn_row.addWidget(self.logout_btn)

        self.diag_btn = btn_cls("诊断")
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
        # 液态玻璃主题：纯透明方案（不申请 DWM backdrop）。
        # 原因：WA_TranslucentBackground 的 WS_EX_LAYERED 窗口与
        # DWM SystemBackdrop(Mica) 组合时，系统会渲染成深色底（用户看到的黑背景）。
        # 纯透明 = 直接透出桌面，玻璃按钮/卡片悬浮其上，效果干净自然。
        # ThemeManager.apply_backdrop 保留，供后续 DirectComposition 方案使用。
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

        if is_glass():
            # 液态玻璃：背景交由 DWM 毛玻璃（Mica）绘制，
            # Qt 侧只画一层极淡白色蒙层 + 细白描边，让系统模糊透出来
            veil = QPainterPath()
            veil.addRoundedRect(cr, self._radius, self._radius)
            p.fillPath(veil, QColor(15, 23, 42, 60))
            p.setPen(QPen(QColor(255, 255, 255, 60), 1))
            p.drawPath(veil)
            for card in [self.status_card, self.cred_card]:
                self._paint_card(p, card)
            self._paint_accent(p, self.status_card)
            p.end()
            return

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

        if is_glass():
            # 玻璃卡片：半透明白基底 + 细白描边（背景由 DWM 毛玻璃提供）
            p.fillPath(path, QColor(255, 255, 255, 20))
            p.setPen(QPen(QColor(255, 255, 255, 70), 1))
            p.drawPath(path)
            return

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
        self.tray_icon.setIcon(create_icon("#9AA3AF"))  # 检测中：灰色状态点
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

                # 更新托盘 tooltip（家庭模式附加标识）
                if self.online:
                    url = self.config.get("logout_url", "")
                    today = f"今日 ↑{self._format_amount(self._day_sent)} ↓{self._format_amount(self._day_recv)}"
                    if not self._scene_school_active():
                        today += "\n🏠 家庭模式（暂停校园网自动登录）"
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
            if self._scene_school_active():
                self.notify("网络断开", "校园网连接已断开，正在尝试自动重连...",
                            QSystemTrayIcon.MessageIcon.Warning)
            else:
                self.notify("网络已断开", "当前为家庭网络，不会自动登录校园网",
                            QSystemTrayIcon.MessageIcon.Information)
        # 场景可能改变状态描述文案（家庭模式）
        self._apply_scene()

    # ── 业务 ──────────────────────────────────────────
    def auto_login(self, portal_url: str):
        try:
            if not self._scene_school_active():
                self.log("当前为家庭网络模式，跳过校园网自动登录")
                return
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
        if not self._scene_school_active():
            return  # 家庭网络模式：不重试校园网登录
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
            if not self._scene_school_active():
                QMessageBox.information(
                    self, "提示",
                    "当前是家庭网络环境，无需登录校园网。\n\n"
                    "如果确实在学校，请到 设置 → 使用场景 选择「校园」或「自动判断」。")
                return
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

    # ── 使用场景（在校 / 在家）─────────────────────────
    def _scene_school_active(self) -> bool:
        """校园网功能是否应处于启用状态"""
        mode = get_scene_mode(self.config)
        if mode == "school":
            return True
        if mode == "home":
            return False
        return self._auto_at_school is not False  # auto：未检出前默认按在校处理

    def _apply_scene(self, announce: bool = False):
        """按当前场景刷新状态描述与提示"""
        active = self._scene_school_active()
        if hasattr(self, "status_desc"):
            if not active:
                self.status_desc.setText(
                    "家庭网络：已暂停校园网自动登录" if self.online
                    else "未连接网络（家庭模式：不自动登录校园网）")
            else:
                self.status_desc.setText(
                    "网络已连通，可以正常上网" if self.online
                    else "未连接到网络，等待自动重连...")
        if announce:
            self.log("场景切换 → " + ("校园网模式（自动登录已启用）" if active
                                    else "家庭网络模式（校园网自动登录已暂停）"))

    def _poll_scene(self):
        """auto 模式下探测认证页可达性，判断是否在学校"""
        if get_scene_mode(self.config) != "auto":
            return
        if self._scene_worker is not None and self._scene_worker.isRunning():
            return
        portal = self.config.get("portal_url", "")
        self._scene_worker = SceneCheckWorker(portal, self)
        self._scene_worker.done.connect(self._on_scene_detected)
        self._scene_worker.start()

    def _on_scene_detected(self, at_school: bool):
        first = self._auto_at_school is None
        changed = (at_school != self._auto_at_school) and not first
        self._auto_at_school = at_school
        if first or changed:
            self._apply_scene(announce=not first)

    def _on_scene_mode_changed(self, mode: str):
        self.config[SCENE_MODE_KEY] = mode
        save_config(self.config)
        self._apply_scene(announce=True)

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
        self._settings_dialog.scene_selector.set_mode(
            get_scene_mode(self.config), animate=False
        )
        self._settings_dialog.family_selector.set_mode(
            self.config.get("theme", THEME_DEFAULT), animate=False
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

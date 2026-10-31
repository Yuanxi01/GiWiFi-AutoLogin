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
    Qt, QTimer, QPoint, QPointF, QRect, QRectF, QSize, QSizeF,
    QPropertyAnimation, QEasingCurve, Property, Signal,
    QSequentialAnimationGroup, QParallelAnimationGroup, QAbstractAnimation, QThread,
    QProcess,
)
from PySide6.QtGui import (
    QIcon, QPixmap, QPainter, QColor, QFont, QAction, QBrush,
    QLinearGradient, QRadialGradient, QConicalGradient, QPainterPath, QPen,
)

from config import load_config, save_config
from autostart import is_autostart_enabled, enable_autostart, disable_autostart
from login_worker import login_giwifi, check_online, logout_giwifi, get_online_duration
from network_checker import NetworkChecker
from logger import log as file_log, LOG_FILE
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
# 多账户列表配置键
ACCOUNTS_KEY = "accounts"
# 关闭窗口时的行为：False=收进托盘（默认） / True=直接退出
QUIT_ON_CLOSE_KEY = "quit_on_close"

APP_NAME = "GiWiFi自动登录"
APP_VERSION = "1.4.0"
APP_AUTHOR = "YuanXi"

# 检查更新：GitHub 最新 Release
UPDATE_API = "https://api.github.com/repos/Yuanxi01/GiWiFi-AutoLogin/releases/latest"
UPDATE_PAGE = "https://github.com/Yuanxi01/GiWiFi-AutoLogin/releases/latest"


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
# 切换采用「写入配置 + 重启生效」：WA_TranslucentBackground 仅在窗口 show 前
# 设置才有效，运行中热切换会导致透明失效（取舍说明见 themes/theme_manager.py）。
from themes import ThemeManager, THEME_DEFAULT, THEME_AURORA, THEME_INNOVATE
from themes import UI_DEFAULT, UI_AURORA, UI_INNOVATE
from themes.default import LIGHT_THEME, DARK_THEME, build_window_qss
from themes.aurora import AURORA_LIGHT, AURORA_DARK, build_aurora_qss
from themes.innovate import INNOVATE_LIGHT, INNOVATE_DARK, build_innovate_qss

# 主题家族：innovate（蓝白创新，默认）/ default（经典）/ aurora（极光）
THEME_FAMILY = "default"

# 当前主题（默认白天模式）
CURRENT_THEME = LIGHT_THEME.copy()


def is_aurora() -> bool:
    """当前是否为「极光」主题家族"""
    return THEME_FAMILY == THEME_AURORA


def is_innovate() -> bool:
    """当前是否为「蓝白创新」主题家族"""
    return THEME_FAMILY == THEME_INNOVATE


def theme_ui() -> dict:
    """当前主题的 UI 结构参数（圆角 / 卡片间距 / 装饰类型）"""
    if is_aurora():
        return UI_AURORA
    if is_innovate():
        return UI_INNOVATE
    return UI_DEFAULT


def card_radius() -> int:
    return theme_ui()["card_radius"]


FAMILY_LABELS = {
    THEME_DEFAULT: "经典",
    THEME_INNOVATE: "蓝白创新",
    THEME_AURORA: "极光",
}

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
# 注：9pt 在 125% 缩放 + 思源黑体下会把汉字字头裁掉（实测 10pt 正常），
# 所以「小字」也统一用 10pt，靠颜色和字重区分层级。
APP_FONT_SMALL = _make_font(10, QFont.Weight.Medium)
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
    try:
        file_log(f"图标资源不可用，使用兜底图标（找过 {_resource_path('app_icon.png')}）")
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
    # 注意：这里必须 return QIcon(pixmap)。
    # 之前写成 `return QIcon`（返回了类对象本身），一旦走到兜底分支，
    # setWindowIcon() 就会抛 "called with wrong argument types: ObjectType"，
    # 整个窗口初始化直接崩掉 —— 表现就是"重启后程序没了"。
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
#  连接状态圆点（呼吸光晕 + 状态切换时扩散涟漪）
#  思路参考 GitHub 上 Qt 涟漪按钮的通行做法（QPropertyAnimation 驱动
#  进度值，paintEvent 里按进度画半径/透明度），这里全部自写，不引入
#  任何 GPL 依赖。
# ═══════════════════════════════════════════════════════
class StatusDot(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        # 宽度留够 28px：涟漪最远要扩到 r≈13，20px 宽会被控件边界裁掉
        self.setFixedSize(28, 30)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        self._color = QColor(0xEF, 0x44, 0x44)
        self._online = False
        self._phase = 0.0          # 呼吸相位（由主窗口统一驱动）
        self._ripple_t = 1.0       # 1.0 = 涟漪已结束

        self._ripple_anim = QPropertyAnimation(self, b"ripple_t", self)
        self._ripple_anim.setDuration(720)
        self._ripple_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    # ── 动画属性 ─────────────────────────────────────
    def _get_ripple(self):
        return self._ripple_t

    def _set_ripple(self, v):
        self._ripple_t = max(0.0, min(1.0, v))
        self.update()

    ripple_t = Property(float, _get_ripple, _set_ripple)

    # ── 外部接口 ─────────────────────────────────────
    def set_color(self, color: QColor):
        self._color = QColor(color)
        self.update()

    def set_state(self, state: str):
        """状态变化时才放涟漪：主题切换等场景重复调用不会乱闪"""
        was_online = self._online
        self._online = (state == "online")
        if self._online and not was_online:
            self.burst()
        self.update()

    def burst(self):
        self._ripple_anim.stop()
        self._ripple_anim.setStartValue(0.0)
        self._ripple_anim.setEndValue(1.0)
        self._ripple_anim.start()

    def tick(self, dt: float):
        if self._online:
            self._phase = (self._phase + dt) % (2 * math.pi * 1000)
            self.update()

    def is_animating(self) -> bool:
        return (self._online
                or self._ripple_anim.state() == QAbstractAnimation.State.Running)

    # ── 绘制 ─────────────────────────────────────────
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cx, cy = 12.0, 15.0
        r = 5.0
        c = self._color

        # 在线时：一圈缓慢呼吸的光晕（约 2.4 秒一个周期）
        if self._online:
            k = 0.5 + 0.5 * math.sin(self._phase * 0.26)
            halo_r = 9.5 + 3.0 * k
            halo = QRadialGradient(QPointF(cx, cy), halo_r)
            halo.setColorAt(0.0, QColor(c.red(), c.green(), c.blue(), 130 + int(50 * k)))
            halo.setColorAt(0.45, QColor(c.red(), c.green(), c.blue(), 52))
            halo.setColorAt(1.0, QColor(c.red(), c.green(), c.blue(), 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(halo)
            p.drawEllipse(QPointF(cx, cy), halo_r, halo_r)

        # 刚连上时：从圆点扩散出去的一圈涟漪（最远 r=13，正好落在控件内）
        if self._ripple_t < 1.0:
            t = self._ripple_t
            ring_r = r + 8.0 * t
            alpha = int(190 * (1.0 - t) ** 1.3)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(c.red(), c.green(), c.blue(), alpha), 2.2))
            p.drawEllipse(QPointF(cx, cy), ring_r, ring_r)

        # 圆点本体
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c)
        p.drawEllipse(QPointF(cx, cy), r, r)
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

    def _paint_aurora_track(self):
        """极光主题：iOS 风格实心轨道（选中填主色 + 白色滑块），比经典凹槽更干净"""
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        track = QRectF(2, 4, 50, 22)
        tp = QPainterPath()
        tp.addRoundedRect(track, 11, 11)
        p.fillPath(tp, theme_color("primary_fill") if self._checked
                   else theme_color("track_off"))

        # 滑块位置：把 1→31 的动画值映射成 13→41 的圆心（左右各留 2px 内缩）
        progress = (self._circle_x - self._LEFT_X) / (self._RIGHT_X - self._LEFT_X)
        progress = max(0.0, min(1.0, progress))
        cx = 13.0 + progress * 28.0
        cy = 15.0
        r = 9.0

        shadow = QRadialGradient(QPointF(cx, cy + 1.2), r + 4)
        shadow.setColorAt(0.35, QColor(0, 0, 0, 60))
        shadow.setColorAt(1, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(shadow)
        p.drawEllipse(QPointF(cx, cy + 0.5), r + 3, r + 3)

        p.setBrush(QColor("#FFFFFF"))
        p.drawEllipse(QPointF(cx, cy), r, r)

        if self._text:
            p.setPen(theme_color("text"))
            p.setFont(APP_FONT)
            p.drawText(QRectF(60, 0, self.width() - 60, 30),
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
        if is_aurora():
            self._paint_aurora_track()
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
            if is_aurora():
                # 极光主题：滑块跟随主题主色，避免和粉彩盘撞色
                base = theme_color("primary_fill")
                knob.setColorAt(0, lerp_color(base, QColor(255, 255, 255), 0.35))
                knob.setColorAt(1, lerp_color(base, QColor(0, 0, 0), 0.18))
                ring = QColor(255, 255, 255, 70) if not dark else QColor(0, 0, 0, 70)
            else:
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


# ═══════════════════════════════════════════════════════
#  「蓝白创新」按钮
#  观感对照 Rev-RoastedDuck/Qt-RoastedDuck-Widgets 的按钮分类：
#    · 微光/流光 → 一条高光带周期性扫过按钮面
#    · 波纹      → 点击时从落点扩散一圈
#    · 简易      → 悬浮/按下的颜色渐变与位移
#  实现全部自己写（对方是 GPLv3，不复制代码）
# ═══════════════════════════════════════════════════════
class ShimmerButton(QPushButton):
    def __init__(self, text: str, primary: bool = False, danger: bool = False, parent=None):
        super().__init__(text, parent)
        self._primary = primary
        self._danger = danger
        self._hover_progress = 0.0
        self._press_t = 0.0
        self._ripple_t = 1.0
        self._ripple_x = 0.0
        self._ripple_y = 0.0
        self._phase = 0.0          # 扫光相位，由主窗口统一驱动
        self._focus_by_keyboard = False

        self.setFixedHeight(theme_ui()["btn_height"])
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(APP_FONT_BOLD)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)

        self._hover_anim = QPropertyAnimation(self, b"hover_progress", self)
        self._hover_anim.setDuration(180)
        self._hover_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._press_anim = QPropertyAnimation(self, b"press_t", self)
        self._press_anim.setDuration(220)
        self._press_anim.setEasingCurve(QEasingCurve.Type.OutBack)

        self._ripple_anim = QPropertyAnimation(self, b"ripple_t", self)
        self._ripple_anim.setDuration(420)
        self._ripple_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    # ── 动画属性 ─────────────────────────────────────
    def _get_hover(self):
        return self._hover_progress

    def _set_hover(self, v):
        self._hover_progress = v
        self.update()

    hover_progress = Property(float, _get_hover, _set_hover)

    def _get_press(self):
        return self._press_t

    def _set_press(self, v):
        self._press_t = v
        self.update()

    press_t = Property(float, _get_press, _set_press)

    def _get_ripple(self):
        return self._ripple_t

    def _set_ripple(self, v):
        self._ripple_t = v
        self.update()

    ripple_t = Property(float, _get_ripple, _set_ripple)

    def set_phase(self, phase: float):
        """主窗口每帧推一次相位，扫光才会动"""
        self._phase = phase
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

    def focusInEvent(self, event):
        reason = event.reason()
        self._focus_by_keyboard = reason in (
            Qt.FocusReason.TabFocusReason, Qt.FocusReason.BacktabFocusReason,
            Qt.FocusReason.ShortcutFocusReason,
        )
        super().focusInEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position()
            self._ripple_x, self._ripple_y = pos.x(), pos.y()
            self._ripple_anim.stop()
            self._ripple_anim.setStartValue(0.0)
            self._ripple_anim.setEndValue(1.0)
            self._ripple_anim.start()
            self._press_anim.stop()
            self._press_anim.setStartValue(self._press_t)
            self._press_anim.setEndValue(1.0)
            self._press_anim.start()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
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
        hv = self._hover_progress
        pressed = self._press_t

        # 按下：整体下沉 1px 并缩到 0.97
        sink = 1.2 * pressed
        scale = 1.0 - 0.03 * pressed
        p.translate(w / 2, h / 2)
        p.scale(scale, scale)
        p.translate(-w / 2, -h / 2 + sink)

        rect = QRectF(0.8, 0.8, w - 1.6, h - 1.6)
        radius = min(h / 2, 12.0)
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)

        filled = self._primary or self._danger

        if filled:
            base = theme_color("danger_dot") if self._danger else theme_color("primary_fill")
            top = lerp_color(base.lighter(112), QColor(255, 255, 255), 0.10 * hv)
            bottom = base.darker(112 + int(6 * hv))
            g = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            g.setColorAt(0.0, top)
            g.setColorAt(0.55, base)
            g.setColorAt(1.0, bottom)
            p.fillPath(path, g)
        else:
            # 次按钮：白面（描边同样放到内高光之后）
            surf = lerp_color(theme_color("surface"), theme_color("surface_hover"), hv)
            p.fillPath(path, surf)

        # 顶沿内高光：一条 1px 亮线 + 上亮下暗的竖向渐变，做出厚度
        p.save()
        p.setClipPath(path)
        rim = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        if filled:
            rim.setColorAt(0.0, QColor(255, 255, 255, 110))
            rim.setColorAt(0.10, QColor(255, 255, 255, 40))
            rim.setColorAt(0.45, QColor(255, 255, 255, 0))
            rim.setColorAt(1.0, QColor(0, 0, 0, 30))
        else:
            rim.setColorAt(0.0, QColor(255, 255, 255, 180))
            rim.setColorAt(0.12, QColor(255, 255, 255, 70))
            rim.setColorAt(0.5, QColor(255, 255, 255, 0))
            rim.setColorAt(1.0, QColor(0, 0, 0, 12))
        p.fillRect(rect, rim)

        # 扫光：一条斜向高光带按相位从左扫到右（微光/流光的观感）
        if filled:
            t = (self._phase * 0.36) % 1.0      # 约 2.5 秒扫一遍
            band = w * 0.5
            x = -band + (w + 2 * band) * t
            sg = QLinearGradient(x, rect.top(), x + band, rect.bottom())
            sg.setColorAt(0.0, QColor(255, 255, 255, 0))
            sg.setColorAt(0.5, QColor(255, 255, 255, 62))
            sg.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.fillRect(rect, sg)
        p.restore()

        # 次按钮描边：放在高光之后，且半像素内缩，避免上边缘被盖住
        if not filled:
            border = lerp_color(theme_color("input_border"), theme_color("primary"), hv)
            stroke = QPainterPath()
            stroke.addRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius - 0.5, radius - 0.5)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(border, 1.2))
            p.drawPath(stroke)

        # 点击波纹
        if self._ripple_t < 1.0:
            t = self._ripple_t
            p.save()
            p.setClipPath(path)
            base = theme_color("on_primary") if filled else theme_color("primary")
            alpha = int(90 * (1.0 - t) ** 1.1)
            rr = (max(w, h) * 1.15) * t
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(base.red(), base.green(), base.blue(), alpha))
            p.drawEllipse(QPointF(self._ripple_x, self._ripple_y), rr, rr)
            p.restore()

        # 键盘焦点环：同 GlassButton，只在 Tab 导航时画，整圈留在控件内
        if self.hasFocus() and self._focus_by_keyboard:
            ring = rect.adjusted(0.75, 0.75, -0.75, -0.75)
            rp = QPainterPath()
            rp.addRoundedRect(ring, radius - 0.75, radius - 0.75)
            fp = QColor(theme_color("focus_ring"))
            fp.setAlpha(180)
            p.setPen(QPen(fp, 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(rp)

        p.setPen(theme_color("on_primary") if filled else theme_color("text"))
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
        # 选中块：浅色主题用纯白，深色主题用比轨道亮两档的面色，
        # 否则深色下轨道和选中块几乎同色，看不出选的是哪个
        surf = theme_color("surface")
        if surf.lightness() < 110:
            thumb = surf.lighter(142)
        else:
            thumb = QColor(255, 255, 255)
        p.fillPath(ip, thumb)
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
#  通用按钮（发光 hover + 回弹 press + 点击波纹）
# ═══════════════════════════════════════════════════════
class GlassButton(QPushButton):
    def __init__(self, text: str, primary: bool = False, parent=None):
        super().__init__(text, parent)
        self._primary = primary
        self._hover_progress = 0.0
        self._press_scale = 1.0
        # 点击水波纹：记录按下的位置与进度
        self._ripple_t = 1.0          # 1.0 = 已结束
        self._ripple_x = 0.0
        self._ripple_y = 0.0

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

        # 水波纹动画
        self._ripple_anim = QPropertyAnimation(self, b"ripple_t", self)
        self._ripple_anim.setDuration(460)
        self._ripple_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        # 是否由键盘拿到焦点（只有这种才画焦点环）
        self._focus_by_keyboard = False

    def _get_ripple(self):
        return self._ripple_t

    def _set_ripple(self, v):
        self._ripple_t = v
        self.update()

    ripple_t = Property(float, _get_ripple, _set_ripple)

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

    def focusInEvent(self, event):
        # Tab / Shift+Tab 才算键盘聚焦；鼠标点进来不画环
        reason = event.reason()
        self._focus_by_keyboard = reason in (
            Qt.FocusReason.TabFocusReason, Qt.FocusReason.BacktabFocusReason,
            Qt.FocusReason.ShortcutFocusReason,
        )
        super().focusInEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._bounce_anim.stop()
            self._press_scale = 0.92
            # 水波纹起点 = 鼠标位置
            pos = event.position()
            self._ripple_x, self._ripple_y = pos.x(), pos.y()
            self._ripple_anim.stop()
            self._ripple_anim.setStartValue(0.0)
            self._ripple_anim.setEndValue(1.0)
            self._ripple_anim.start()
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
            # 极光主题再叠一层极淡的垂直渐变，避免大色块太平
            if is_aurora():
                # 极光：横向 蓝 → 蓝紫 渐变（深色下是 淡蓝 → 淡紫，配深色文字）
                g_left = lerp_color(theme_color("primary_fill"),
                                    theme_color("primary_hover"), self._hover_progress)
                g_right = lerp_color(theme_color("primary2"),
                                     theme_color("primary_hover"), self._hover_progress)
                grad_btn = QLinearGradient(rect.topLeft(), rect.topRight())
                grad_btn.setColorAt(0, g_left)
                grad_btn.setColorAt(1, g_right)
                p.fillPath(path, grad_btn)
            else:
                # 经典：主色带一点上亮下暗的纵向渐变，实色块太"平"了
                # 用 primary_fill 而不是 primary：深色主题里 primary 是"文字色"（偏浅），
                # 拿它当填充会让按钮发灰、白字看不清
                top_c = lerp_color(theme_color("primary_fill").lighter(112),
                                   theme_color("primary_hover"), self._hover_progress)
                bot_c = lerp_color(theme_color("primary_fill").darker(106),
                                   theme_color("primary_hover"), self._hover_progress)
                grad_btn = QLinearGradient(rect.topLeft(), rect.bottomLeft())
                grad_btn.setColorAt(0, top_c)
                grad_btn.setColorAt(1, bot_c)
                p.fillPath(path, grad_btn)
        else:
            # 次按钮：平面表面色（描边放到内高光之后画，见下面的说明）
            fill = lerp_color(theme_color("surface"), theme_color("surface_hover"), self._hover_progress)
            p.fillPath(path, fill)

        # 内高光 + 底部内阴影：给按钮一点厚度（上沿一条亮线，下沿压暗）
        p.save()
        p.setClipPath(path)
        rim = QLinearGradient(rect.topLeft(), QRectF(rect).bottomLeft())
        if self._primary:
            rim.setColorAt(0.0, QColor(255, 255, 255, 92))
            rim.setColorAt(0.08, QColor(255, 255, 255, 40))
            rim.setColorAt(0.5, QColor(255, 255, 255, 0))
            rim.setColorAt(0.88, QColor(0, 0, 0, 0))
            rim.setColorAt(1.0, QColor(0, 0, 0, 26))
        else:
            rim.setColorAt(0.0, QColor(255, 255, 255, 168))
            rim.setColorAt(0.10, QColor(255, 255, 255, 64))
            rim.setColorAt(0.45, QColor(255, 255, 255, 0))
            rim.setColorAt(1.0, QColor(0, 0, 0, 14))
        p.fillRect(rect, rim)
        p.restore()

        # 描边必须画在内高光之后：否则顶部那道白色高光会盖住上边框的 1px，
        # 看起来像"上边缘被啃掉一小条"。同时按半像素内缩，1px 线才落在像素格上。
        if not self._primary:
            border = lerp_color(theme_color("input_border"), theme_color("text_ter"), self._hover_progress)
            stroke = QPainterPath()
            stroke.addRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 9.5, 9.5)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(border, 1))
            p.drawPath(stroke)

        # 点击水波纹：裁在按钮形状里，从点击点向外扩散后淡出
        if self._ripple_t < 1.0:
            t = self._ripple_t
            p.save()
            p.setClipPath(path)
            base = theme_color("on_primary") if self._primary else theme_color("primary")
            alpha = int(96 * (1.0 - t) ** 1.1)
            ripple_r = (max(w, h) * 1.15) * t
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(base.red(), base.green(), base.blue(), alpha))
            p.drawEllipse(QPointF(self._ripple_x, self._ripple_y), ripple_r, ripple_r)
            p.restore()

        # 键盘焦点环：只在用 Tab 导航时画（鼠标点按不画），并且整圈都落在控件内，
        # 否则 2px 笔画的半像素会被控件边界裁掉，看着像"边框缺一截"
        if self.hasFocus() and self._focus_by_keyboard:
            ring = rect.adjusted(0.75, 0.75, -0.75, -0.75)
            ring_path = QPainterPath()
            ring_path.addRoundedRect(ring, 9.4, 9.4)
            fp = QColor(theme_color("focus_ring"))
            fp.setAlpha(180)
            p.setPen(QPen(fp, 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(ring_path)

        # 文字
        p.setPen(theme_color("on_primary") if self._primary else theme_color("text"))
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
        self._angle = 0.0
        self.setFixedSize(20, 20)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("设置")

        # 齿轮旋转：悬浮转 90°，点一下再转半圈
        self._anim = QPropertyAnimation(self, b"gear_angle", self)
        self._anim.setDuration(420)
        self._anim.setEasingCurve(QEasingCurve.Type.OutBack)

    def _get_angle(self):
        return self._angle

    def _set_angle(self, v):
        self._angle = v
        self.update()

    gear_angle = Property(float, _get_angle, _set_angle)

    def _spin_to(self, target: float, duration: int = 420,
                 curve=QEasingCurve.Type.OutBack):
        self._anim.stop()
        self._anim.setDuration(duration)
        self._anim.setEasingCurve(curve)
        self._anim.setStartValue(self._angle)
        self._anim.setEndValue(target)
        self._anim.start()

    def enterEvent(self, event):
        self._hovered = True
        self._spin_to(90.0)
        self.update()

    def leaveEvent(self, event):
        self._hovered = False
        self._spin_to(0.0, 300, QEasingCurve.Type.OutCubic)
        self.update()

    def mousePressEvent(self, event):
        # 点击额外转半圈，给一个"咔哒"的反馈
        self._spin_to(self._angle + 180.0, 380, QEasingCurve.Type.OutCubic)
        super().mousePressEvent(event)

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
        # 只让齿轮转，背景圆不转
        p.save()
        p.translate(cx, cy)
        p.rotate(self._angle)
        p.translate(-cx, -cy)

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

        p.restore()
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
        self._angle = 0.0
        self.setFixedSize(20, 20)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("切换白天 / 黑夜模式")

        self._anim = QPropertyAnimation(self, b"icon_angle", self)
        self._anim.setDuration(380)
        self._anim.setEasingCurve(QEasingCurve.Type.OutBack)

    def _get_angle(self):
        return self._angle

    def _set_angle(self, v):
        self._angle = v
        self.update()

    icon_angle = Property(float, _get_angle, _set_angle)

    def set_dark(self, dark: bool):
        if dark != self._dark:
            # 日月切换时转半圈，图标"翻"过去
            self._anim.stop()
            self._anim.setStartValue(self._angle)
            self._anim.setEndValue(self._angle + 180.0)
            self._anim.start()
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
        p.save()
        p.translate(cx, cy)
        p.rotate(self._angle)
        p.translate(-cx, -cy)

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

        p.restore()
        p.end()


# ═══════════════════════════════════════════════════════
#  账号切换按钮（账号输入框右侧的小箭头）
# ═══════════════════════════════════════════════════════
class AccountMenuButton(QPushButton):
    """点开已保存账户列表；自绘圆角小方钮 + 下箭头"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hovered = False
        self.setFixedSize(28, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setToolTip("切换已保存的账户")

    def enterEvent(self, event):
        self._hovered = True
        self.update()

    def leaveEvent(self, event):
        self._hovered = False
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        bg = theme_color("surface_hover") if self._hovered else theme_color("surface")
        p.setBrush(bg)
        p.setPen(QPen(theme_color("input_border"), 1))
        p.drawRoundedRect(QRectF(0.5, 0.5, 27, 27), 8, 8)

        color = theme_color("primary") if self._hovered else theme_color("text_sec")
        p.setPen(QPen(color, 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        chevron = QPainterPath()
        chevron.moveTo(10.0, 12.0)
        chevron.lineTo(14.0, 16.0)
        chevron.lineTo(18.0, 12.0)
        p.drawPath(chevron)
        p.end()


# ═══════════════════════════════════════════════════════
#  密码可见性按钮（小眼睛：点击在明文 / 密文之间切换）
# ═══════════════════════════════════════════════════════
class EyeButton(QPushButton):
    """眼睛图标，选中（按下）态表示正在显示明文密码"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hovered = False
        self.setCheckable(True)
        self.setFixedSize(28, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setToolTip("显示 / 隐藏密码")

    def enterEvent(self, event):
        self._hovered = True
        self.update()

    def leaveEvent(self, event):
        self._hovered = False
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        bg = theme_color("surface_hover") if (self._hovered or self.isChecked()) else theme_color("surface")
        p.setBrush(bg)
        p.setPen(QPen(theme_color("input_border"), 1))
        p.drawRoundedRect(QRectF(0.5, 0.5, 27, 27), 8, 8)

        color = theme_color("primary") if self.isChecked() else theme_color("text_sec")
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(color, 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))

        # 眼形：上下两段贝塞尔弧
        eye = QPainterPath()
        eye.moveTo(7.5, 14.0)
        eye.cubicTo(9.5, 9.8, 18.5, 9.8, 20.5, 14.0)
        eye.cubicTo(18.5, 18.2, 9.5, 18.2, 7.5, 14.0)
        p.drawPath(eye)

        # 瞳孔
        p.setBrush(color)
        p.drawEllipse(QPointF(14.0, 14.0), 2.4, 2.4)

        # 隐藏态：斜杠（先画一道白色底衬，避免和瞳孔糊在一起）
        if not self.isChecked():
            p.setPen(QPen(theme_color("surface"), 3.0, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(9.0, 19.0), QPointF(19.0, 9.0))
            p.setPen(QPen(color, 1.5, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(9.0, 19.0), QPointF(19.0, 9.0))
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

    def showEvent(self, event):
        super().showEvent(event)
        # 弹出动效：从下方 14px 处上滑 + 淡入（窗口尺寸固定，只能动位置和透明度）
        home = self.pos()
        self.move(home.x(), home.y() + 14)
        self.setWindowOpacity(0.0)
        slide = QPropertyAnimation(self, b"pos", self)
        slide.setDuration(200)
        slide.setStartValue(QPoint(home.x(), home.y() + 14))
        slide.setEndValue(home)
        slide.setEasingCurve(QEasingCurve.Type.OutCubic)
        fade = QPropertyAnimation(self, b"windowOpacity", self)
        fade.setDuration(170)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        group = QParallelAnimationGroup(self)
        group.addAnimation(slide)
        group.addAnimation(fade)
        self._pop_anim = group   # 持引用，防 GC
        group.start()

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
        """加载日志文件（用 logger 里的绝对路径：打包成 onefile 后 __file__ 在临时目录）"""
        try:
            log_file = LOG_FILE
            if os.path.exists(log_file):
                with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                self.log_text.setText(content)
                # 滚动到底部
                scrollbar = self.log_text.verticalScrollBar()
                scrollbar.setValue(scrollbar.maximum())
            else:
                self.log_text.setText(f"日志文件不存在\n{log_file}")
        except Exception as e:
            self.log_text.setText(f"读取日志失败: {e}")

    def clear_logs(self):
        """清空日志文件"""
        try:
            log_file = LOG_FILE
            if os.path.exists(log_file):
                with open(log_file, "w", encoding="utf-8") as f:
                    f.write("")
                self.log_text.setText("日志已清空")
            else:
                self.log_text.setText("日志文件不存在，无需清空")
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
    upToDate = Signal(str)   # 已是最新（携带远端版本号，可能为空）
    failed = Signal(str)     # 检查失败（网络/限流/接口异常），带上原因

    def __init__(self, parent=None):
        super().__init__(parent)

    def run(self):
        import requests

        def ver_tuple(v):
            try:
                return tuple(int(x) for x in v.split("."))
            except Exception:
                return (0,)

        try:
            resp = requests.get(
                UPDATE_API, timeout=8,
                headers={"Accept": "application/vnd.github+json"},
            )
        except Exception as e:
            file_log(f"检查更新失败(网络): {e}")
            self.failed.emit(f"网络不通，检查不了更新：{type(e).__name__}")
            return

        # 403 多半是 GitHub 的 IP 限流（匿名每小时 60 次）
        if resp.status_code == 403:
            file_log("检查更新失败: GitHub 限流 403")
            self.failed.emit("GitHub 接口限流（403），过一会儿再试")
            return
        if resp.status_code != 200:
            file_log(f"检查更新失败: HTTP {resp.status_code}")
            self.failed.emit(f"接口返回 HTTP {resp.status_code}")
            return

        try:
            data = resp.json()
        except Exception as e:
            self.failed.emit(f"返回内容解析失败：{e}")
            return

        tag = (data.get("tag_name") or "").lstrip("v").strip()
        if not tag:
            # 仓库还没发过 Release，按"已是最新"处理，但记一笔
            file_log("检查更新: 远端还没有 Release")
            self.upToDate.emit("")
            return

        if ver_tuple(tag) > ver_tuple(APP_VERSION):
            self.foundNew.emit(tag)
        else:
            self.upToDate.emit(tag)


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
#  登录线程（一次登录最坏要等两个 10s 超时，放主线程会卡界面）
# ═══════════════════════════════════════════════════════
class LoginWorker(QThread):
    resultReady = Signal(object)  # {"ok", "msg", "logout_url", "already"}

    def __init__(self, username: str, password: str, portal_url: str,
                 verify_online: bool = False, parent=None):
        super().__init__(parent)
        self._username = username
        self._password = password
        self._portal_url = portal_url
        self._verify_online = verify_online

    def run(self):
        result = {"ok": False, "msg": "", "logout_url": None, "already": False}
        try:
            portal = self._portal_url
            if self._verify_online:
                online, detected = check_online()
                if online:
                    result.update(ok=True, already=True, msg="网络已连通，无需登录")
                    self.resultReady.emit(result)
                    return
                if detected:
                    portal = detected
            ok, msg, logout_url = login_giwifi(self._username, self._password, portal)
            result.update(ok=ok, msg=msg, logout_url=logout_url)
        except Exception as e:
            result["msg"] = f"登录异常: {e}"
        self.resultReady.emit(result)


# ═══════════════════════════════════════════════════════
#  设置对话框
# ═══════════════════════════════════════════════════════
class SettingsDialog(_DraggableDialogMixin, QDialog):
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config.copy()
        self.setWindowTitle("设置")
        # 只锁宽度，高度按内容自适应：行数一变（加主题/场景选择器）就不至于把
        # 底部的「当前版本」压到裁字
        self.setFixedWidth(368)   # 宽一点：四个主题分段才不会把「蓝白创新」挤变形
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._build_ui()
        self.adjustSize()
        self.setFixedHeight(self.sizeHint().height())

    def showEvent(self, event):
        super().showEvent(event)
        # 弹出动效：从下方 14px 处上滑 + 淡入（窗口尺寸固定，只能动位置和透明度）
        home = self.pos()
        self.move(home.x(), home.y() + 14)
        self.setWindowOpacity(0.0)
        slide = QPropertyAnimation(self, b"pos", self)
        slide.setDuration(200)
        slide.setStartValue(QPoint(home.x(), home.y() + 14))
        slide.setEndValue(home)
        slide.setEasingCurve(QEasingCurve.Type.OutCubic)
        fade = QPropertyAnimation(self, b"windowOpacity", self)
        fade.setDuration(170)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        group = QParallelAnimationGroup(self)
        group.addAnimation(slide)
        group.addAnimation(fade)
        self._pop_anim = group   # 持引用，防 GC
        group.start()

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
        layout.setContentsMargins(20, 16, 20, 18)
        layout.setSpacing(12)

        # 标题
        self.title_label = QLabel("设置")
        self.title_label.setFont(APP_FONT_TITLE)
        self.title_label.setStyleSheet(
            f"color: {CURRENT_THEME['text'].name()}; background: transparent; border: none;")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setMinimumHeight(24)
        layout.addWidget(self.title_label)

        # ── 版式：分组卡片 + 左右两列对齐 ──
        # 左列标签统一从卡片内边距起排，右列控件统一贴右边，行高一致
        # 这些控件的配色统一由 _apply_settings_colors() 刷，切换昼夜才不会留下旧颜色
        self._group_boxes = []
        self._row_labels = []
        self._section_labels = []

        def group_box() -> tuple:
            box = QWidget()
            box.setObjectName("settingsGroup")
            self._group_boxes.append(box)
            lay = QVBoxLayout(box)
            lay.setContentsMargins(14, 10, 14, 12)
            lay.setSpacing(6)
            return box, lay

        def section_label(text: str, store: bool = False) -> QLabel:
            lb = QLabel(text)
            lb.setFont(APP_FONT_SMALL)
            lb.setMinimumHeight(18)
            if store:
                self._section_labels.append(lb)
            return lb

        def switch_row(text: str, switch: ToggleSwitch) -> QHBoxLayout:
            row = QHBoxLayout()
            row.setContentsMargins(0, 3, 0, 3)
            row.setSpacing(10)
            lb = QLabel(text)
            lb.setFont(APP_FONT_SEC)
            lb.setMinimumHeight(18)
            self._row_labels.append(lb)
            row.addWidget(lb, 1)
            row.addWidget(switch, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return row

        # ── 第一组：三个开关（标签左、开关右，开关右边全部对齐）──
        box1, g1 = group_box()
        self.notify_switch = ToggleSwitch("", self.config.get(NOTIFY_ENABLED_KEY, False))
        self.silent_start_switch = ToggleSwitch("", self.config.get(SILENT_START_KEY, False))
        self.quit_on_close_switch = ToggleSwitch("", self.config.get(QUIT_ON_CLOSE_KEY, False))
        self.quit_on_close_switch.setToolTip("关掉时点 ✕ / Alt+F4 只是收进托盘")
        g1.addLayout(switch_row("启用 Windows 通知", self.notify_switch))
        g1.addLayout(switch_row("开机静默模式", self.silent_start_switch))
        g1.addLayout(switch_row("关闭窗口即退出", self.quit_on_close_switch))

        self.log_btn = GlassButton("查看")
        self.log_btn.setFixedHeight(26)
        self.log_btn.setFixedWidth(64)
        self.log_btn.setToolTip("打开运行日志窗口")
        self.log_btn.clicked.connect(self._open_log_viewer)
        g1.addLayout(switch_row("运行日志", self.log_btn))
        layout.addWidget(box1)

        # ── 第二组：三个选择器（标签在上、控件整行，左右边与卡片对齐）──
        box2, g2 = group_box()
        self.scene_label = section_label("使用场景", store=True)
        g2.addWidget(self.scene_label)
        self.scene_selector = SceneModeSelector(get_scene_mode(self.config))
        g2.addWidget(self.scene_selector)

        g2.addSpacing(6)
        g2.addWidget(section_label("主题模式（白天 / 黑夜）", store=True))
        self.theme_selector = ThemeModeSelector(get_theme_mode(self.config))
        g2.addWidget(self.theme_selector)

        g2.addSpacing(6)
        g2.addWidget(section_label("主题风格", store=True))
        self.family_selector = ThemeModeSelector(
            ThemeManager.load_family(self.config),
            modes=[THEME_INNOVATE, THEME_DEFAULT, THEME_AURORA],
            labels=["蓝白创新", "经典", "极光"],
            tooltip="蓝白创新 = Material 按钮 + 流光描边；切换写入配置，重启后生效",
        )
        self.family_selector.modeChanged.connect(self._on_family_changed)
        g2.addWidget(self.family_selector)
        layout.addWidget(box2)

        # ── 版本行：左文字、右按钮，与上面卡片的左右边对齐 ──
        ver_row = QHBoxLayout()
        ver_row.setContentsMargins(2, 0, 2, 0)
        ver_row.setSpacing(10)
        self.version_label = section_label(f"当前版本 v{APP_VERSION}", store=True)
        self.check_update_btn = GlassButton("检查更新")
        self.check_update_btn.setFixedHeight(28)
        self.check_update_btn.setFixedWidth(96)
        ver_row.addWidget(self.version_label, 1)
        ver_row.addWidget(self.check_update_btn, 0, Qt.AlignmentFlag.AlignRight)
        layout.addLayout(ver_row)

        # ── 底部按钮：等宽、等高 ──
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.setContentsMargins(2, 0, 2, 0)

        ok_btn = GlassButton("确定", primary=True)
        ok_btn.setFixedHeight(34)
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)

        cancel_btn = GlassButton("取消")
        cancel_btn.setFixedHeight(34)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

        self._apply_settings_colors()

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
        self.config[SCENE_MODE_KEY] = self.scene_selector.mode()
        self.config[QUIT_ON_CLOSE_KEY] = self.quit_on_close_switch.isChecked()
        self.config["theme"] = self.family_selector.mode()  # 主题家族（重启生效）
        return self.config

    def _on_family_changed(self, family: str):
        """主题风格切换：写入配置 + 提示重启
        （WA_TranslucentBackground 仅在窗口 show 前设置才有效，
        运行中热切换会导致毛玻璃透明失效，因此采用重启方案）"""
        ThemeManager.save_family(self.config, family)
        save_config(self.config)
        label = FAMILY_LABELS.get(family, family)
        file_log(f"主题风格切换为「{label}」，弹出重启提示")

        dlg = RestartPromptDialog(label, self)
        code = dlg.exec()
        file_log(f"重启提示返回 {code}（Accepted={int(QDialog.DialogCode.Accepted)}）")

        if code == QDialog.DialogCode.Accepted:
            # 注意：restart_app 在 MainWindow 上，不在本对话框里。
            # 以前这里写的是 self.restart_app()，触发 AttributeError 被吞掉，
            # 表现就是"点了立即重启毫无反应"。
            target = self.parent()
            if target is None or not hasattr(target, "restart_app"):
                for wd in QApplication.topLevelWidgets():
                    if hasattr(wd, "restart_app"):
                        target = wd
                        break
            if target is not None and hasattr(target, "restart_app"):
                # 关键：把对话框当前的所有设置写回主窗口并落盘。
                # 不写的话，restart_app() 里 save_config(self.config) 用的是主窗口那份
                # 【旧】配置，会把刚保存的主题家族又覆盖回去 —— 表现为"重启了但主题没变"。
                try:
                    target.config.update(self.get_config())
                    # 以本次切换的家族为准（get_config 读的是选择器，理论上一致，
                    # 但显式写一遍更稳，避免选择器状态没同步时又写回旧值）
                    target.config["theme"] = family
                    save_config(target.config)
                    file_log(f"重启前已写回配置，主题={target.config.get('theme')}")
                except Exception as e:
                    file_log(f"重启前写回配置失败: {e}")
                target.restart_app()
            else:
                file_log("重启失败：找不到主窗口的 restart_app")

    def _open_log_viewer(self):
        """从设置里打开日志窗口（真正的实现在主窗口上）"""
        target = self.parent()
        if target is None or not hasattr(target, "show_log_viewer"):
            # 兜底：父窗口没设或不是主窗口时，找一遍顶层窗口
            for wd in QApplication.topLevelWidgets():
                if hasattr(wd, "show_log_viewer"):
                    target = wd
                    break
        if target is not None and hasattr(target, "show_log_viewer"):
            target.show_log_viewer()

    def _apply_settings_colors(self):
        """按当前主题刷新分组卡与各类文字的颜色（切昼夜后必须重刷）"""
        t = CURRENT_THEME
        group_qss = f"""
            #settingsGroup {{
                background: rgba({t['surface'].red()}, {t['surface'].green()},
                                 {t['surface'].blue()}, 170);
                border: 1px solid rgba({t['card_border'].red()}, {t['card_border'].green()},
                                       {t['card_border'].blue()}, 140);
                border-radius: 12px;
            }}
            #settingsGroup QLabel {{
                color: {t['text'].name()};
                background: transparent;
                border: none;
            }}
        """
        for box in getattr(self, "_group_boxes", ()):
            box.setStyleSheet(group_qss)
        for lb in getattr(self, "_row_labels", ()):
            lb.setStyleSheet(f"color: {t['text'].name()}; background: transparent; border: none;")
        for lb in getattr(self, "_section_labels", ()):
            lb.setStyleSheet(f"color: {t['text_sec'].name()}; background: transparent; border: none;")

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
        self._apply_settings_colors()


# ═══════════════════════════════════════════════════════
#  通用信息对话框（检查更新结果、提示等）
#  比 QMessageBox 更贴合本程序的风格，也更容易带上"打开下载页"这类动作
# ═══════════════════════════════════════════════════════
class InfoDialog(_DraggableDialogMixin, QDialog):
    def __init__(self, title: str, body: str, parent=None,
                 action_text: str = "", action=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedWidth(340)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)

        box = QWidget()
        box.setObjectName("infoBox")
        box.setStyleSheet(f"""
            #infoBox {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {CURRENT_THEME['bg_top'].name()}, stop:1 {CURRENT_THEME['bg_bot'].name()});
                border-radius: 16px;
                border: 1px solid rgba({CURRENT_THEME['card_border'].red()},
                    {CURRENT_THEME['card_border'].green()},
                    {CURRENT_THEME['card_border'].blue()}, 220);
            }}
        """)
        outer.addWidget(box)

        lay = QVBoxLayout(box)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(10)

        lb_title = QLabel(title)
        lb_title.setFont(APP_FONT_TITLE)
        lb_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lb_title.setStyleSheet(f"color:{CURRENT_THEME['text'].name()};background:transparent;")
        lay.addWidget(lb_title)

        lb_body = QLabel(body)
        lb_body.setFont(APP_FONT)
        lb_body.setWordWrap(True)
        lb_body.setMinimumHeight(40)
        lb_body.setStyleSheet(f"color:{CURRENT_THEME['text_sec'].name()};background:transparent;")
        lay.addWidget(lb_body)

        lay.addSpacing(4)
        row = QHBoxLayout()
        row.setSpacing(10)
        if action_text and action:
            act = GlassButton(action_text)
            act.setFixedHeight(34)
            act.clicked.connect(lambda: (action(), self.accept()))
            row.addWidget(act)
        ok = GlassButton("知道了", primary=True)
        ok.setFixedHeight(34)
        ok.clicked.connect(self.accept)
        row.addWidget(ok)
        lay.addLayout(row)

        self.adjustSize()
        self.setFixedHeight(self.sizeHint().height())

        shadow = QGraphicsDropShadowEffect(box)
        shadow.setBlurRadius(25)
        shadow.setColor(QColor(0, 0, 0, 80))
        shadow.setOffset(0, 8)
        box.setGraphicsEffect(shadow)


# ═══════════════════════════════════════════════════════
#  重启提示（切换主题后）
#  比 QMessageBox 更贴合本程序的自绘风格，并提供「立即重启」
# ═══════════════════════════════════════════════════════
class RestartPromptDialog(_DraggableDialogMixin, QDialog):
    def __init__(self, family_label: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("主题风格已保存")
        self.setFixedWidth(340)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)

        box = QWidget()
        self._box = box
        box.setObjectName("restartBox")
        box.setStyleSheet(f"""
            #restartBox {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {CURRENT_THEME['bg_top'].name()}, stop:1 {CURRENT_THEME['bg_bot'].name()});
                border-radius: 16px;
                border: 1px solid rgba({CURRENT_THEME['card_border'].red()},
                    {CURRENT_THEME['card_border'].green()},
                    {CURRENT_THEME['card_border'].blue()}, 220);
            }}
        """)
        outer.addWidget(box)

        lay = QVBoxLayout(box)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(10)

        title = QLabel("主题风格已保存")
        title.setFont(APP_FONT_TITLE)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"color:{CURRENT_THEME['text'].name()};background:transparent;")
        lay.addWidget(title)

        body = QLabel(
            f"已切换为「{family_label}」。\n"
            "需要重启软件后生效。"
        )
        body.setFont(APP_FONT)
        body.setWordWrap(True)
        body.setMinimumHeight(46)
        body.setStyleSheet(f"color:{CURRENT_THEME['text_sec'].name()};background:transparent;")
        lay.addWidget(body)

        lay.addSpacing(4)
        row = QHBoxLayout()
        row.setSpacing(10)
        self.btn_later = GlassButton("稍后手动重启")
        self.btn_later.setFixedHeight(34)
        self.btn_later.clicked.connect(self.reject)
        self.btn_now = GlassButton("立即重启", primary=True)
        self.btn_now.setFixedHeight(34)
        self.btn_now.clicked.connect(self.accept)
        row.addWidget(self.btn_later)
        row.addWidget(self.btn_now)
        lay.addLayout(row)

        self.adjustSize()
        self.setFixedHeight(self.sizeHint().height())

        # 窗口阴影：这个提示框之前是"平贴"在背景上的，加上投影才有浮起来的感觉。
        # 外面留了 20px 外边距，正好给模糊半径留出空间。
        shadow = QGraphicsDropShadowEffect(self._box)
        shadow.setBlurRadius(25)
        shadow.setColor(QColor(0, 0, 0, 80))
        shadow.setOffset(0, 8)
        self._box.setGraphicsEffect(shadow)


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
        # 主题家族：innovate（蓝白创新，默认）/ default（经典）/ aurora（极光）
        global THEME_FAMILY
        self.theme_manager = ThemeManager()
        THEME_FAMILY = self.theme_manager.load_family(self.config)
        # 把 theme 键固化进主配置：否则周期性的 _persist_traffic 整体写盘
        # 会把设置面板刚写入的 theme 字段覆盖回默认（真实踩过的坑）
        self.config.setdefault("theme", THEME_FAMILY)
        self._backdrop_applied = False
        self.online = False
        self._drag_pos = None
        # 圆角由主题的 UI 参数决定（经典 18 / 极光 20 / 玻璃 26）
        self._radius = theme_ui()["win_radius"]
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

        # 动效总驱动：20fps。只在「极光光晕要流动」或「状态点要呼吸/涟漪」时
        # 才触发重绘，静止时这个定时器只是空转一次判断，几乎不吃 CPU
        self._fx_phase = 0.0
        self._fx_timer = QTimer(self)
        self._fx_timer.setInterval(60)   # 16fps：动效够顺，又比 20fps 省约 1/4 CPU
        self._fx_timer.timeout.connect(self._tick_fx)
        self._fx_timer.start()

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
        """应用当前主题；经典 / 极光家族切换时带 320ms 颜色淡化 + Q 弹脉冲"""
        global CURRENT_THEME, _TRANSITION_FROM
        is_dark = self._effective_dark()
        # 记录实际生效的深浅状态：玻璃分支以前漏了这句，
        # 导致「跟随系统」面板每 3 秒误判一次主题变更、反复重刷并刷日志
        self._last_effective_dark = is_dark

        if is_aurora():
            new_theme = (AURORA_DARK if is_dark else AURORA_LIGHT).copy()
            qss = build_aurora_qss(new_theme)
        elif is_innovate():
            new_theme = (INNOVATE_DARK if is_dark else INNOVATE_LIGHT).copy()
            qss = build_innovate_qss(new_theme)
        else:
            new_theme = (DARK_THEME if is_dark else LIGHT_THEME).copy()
            qss = build_window_qss(new_theme)

        can_fade = hasattr(self, "_theme_anim") and new_theme is not CURRENT_THEME
        if can_fade:
            _TRANSITION_FROM = CURRENT_THEME
        CURRENT_THEME = new_theme
        self.setStyleSheet(qss)

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
        # 圆点状态：online 才呼吸，刚从离线切到在线时放一圈涟漪
        self.status_dot.set_state(state)

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

        # 两张内容卡放进同一个容器：玻璃主题把间距设成 0，两块合并成一整块
        # 大玻璃面板（中间一条分隔线），经典 / 极光则是 10px 分开的独立卡片
        ui = theme_ui()
        self.cards_host = QWidget()
        cards_layout = QVBoxLayout(self.cards_host)
        cards_layout.setContentsMargins(0, 0, 0, 0)
        cards_layout.setSpacing(ui["card_gap"])

        # ── 标题栏 ──
        title_bar = QHBoxLayout()
        title_bar.setContentsMargins(0, 0, 0, 6)

        # 左侧红绿灯：红 = 退出程序，黄 = 收进托盘
        self.btn_close = TrafficLight("#FF5F57", "#FF3B30")
        self.btn_close.setToolTip("退出程序")
        # 用 singleShot 把退出推迟到按钮事件派发之外，避免在按钮内部事件循环里
        # 直接 quit 导致偶发不生效
        self.btn_close.clicked.connect(lambda: QTimer.singleShot(0, self.quit_app))
        self.btn_mini = TrafficLight("#FEBC2E", "#F5A623")
        self.btn_mini.setToolTip("最小化到系统托盘")
        self.btn_mini.clicked.connect(self.fade_out_to_tray)
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
        sc.setContentsMargins(*ui["card_pad"])
        sc.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(10)

        self.status_dot = StatusDot()
        self.status_dot.set_color(CURRENT_THEME["danger_dot"])
        top.addWidget(self.status_dot, 0, Qt.AlignmentFlag.AlignVCenter)

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

        cards_layout.addWidget(self.status_card)

        # ── 登录卡片 ──
        self.cred_card = QWidget()
        cc = QVBoxLayout(self.cred_card)
        cc.setContentsMargins(*ui["card_pad"])  # 与状态卡完全一致的内边距
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
            row.addWidget(inp, 1)
            return row, inp

        # 账号行：输入框右侧挂一个下拉箭头，点开就是已保存账户列表
        r1, self.username_input = make_input_row("账号", "请输入校园网账号")
        self.username_input.setText(self.config.get("username", ""))
        self.account_btn = AccountMenuButton()
        self.account_btn.clicked.connect(self.show_account_menu)
        r1.addWidget(self.account_btn)
        cc.addLayout(r1)

        # 密码行：右侧小眼睛，点一下看明文
        r2, self.password_input = make_input_row("密码", "请输入密码", QLineEdit.EchoMode.Password)
        self.password_input.setText(self.config.get("password", ""))
        self.eye_btn = EyeButton()
        self.eye_btn.toggled.connect(self.toggle_password_visible)
        r2.addWidget(self.eye_btn)
        cc.addLayout(r2)

        cards_layout.addWidget(self.cred_card)
        root.addWidget(self.cards_host)

        # ── 按钮行 ──
        # 每个主题用自己的按钮实现：
        #   经典 / 极光 → GlassButton      蓝白创新 → ShimmerButton
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        if is_innovate():
            self.login_btn = ShimmerButton("手动登录", primary=True)
            self.save_btn = ShimmerButton("保存配置")
            self.logout_btn = ShimmerButton("下线", danger=True)
            self.diag_btn = ShimmerButton("诊断")
        else:
            self.login_btn = GlassButton("手动登录", primary=True)
            self.save_btn = GlassButton("保存配置")
            self.logout_btn = GlassButton("下线")
            self.diag_btn = GlassButton("诊断")

        self.login_btn.clicked.connect(self.manual_login)
        self.save_btn.clicked.connect(self.on_save_clicked)
        self.logout_btn.clicked.connect(self.manual_logout)
        self.diag_btn.clicked.connect(self.manual_diagnose)
        for _btn in (self.login_btn, self.save_btn, self.logout_btn, self.diag_btn):
            btn_row.addWidget(_btn)

        # 蓝白创新：这些按钮的扫光要跟着主窗口的动效相位走
        self._fx_buttons = [self.login_btn, self.save_btn, self.logout_btn, self.diag_btn]

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
        self.log_label.setMinimumHeight(18)  # 同上：避免 9pt 被压到 12px 裁字
        bot.addWidget(self.log_label, 1)

        self.ver_label = QLabel(f"v{APP_VERSION}  {APP_AUTHOR}")
        self.ver_label.setFont(APP_FONT_SMALL)
        self.ver_label.setMinimumHeight(18)
        self.ver_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        bot.addWidget(self.ver_label)
        root.addLayout(bot)

        # 应用主题相关的控件样式
        self._apply_widget_styles()

    def _apply_dot_style(self, color: QColor, glow_r: float = 18):
        """状态圆点配色（glow_r 保留参数兼容旧调用）"""
        self.status_dot.set_color(color)

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

    # ── 动效驱动 ──────────────────────────────────────
    def _tick_fx(self):
        """20fps 动效驱动：极光/玻璃动态装饰 + 状态点呼吸，按需重绘"""
        self._fx_phase += 0.066
        if not self.isVisible():
            return  # 收在托盘里就不画了，别白烧 CPU
        if is_aurora():
            self.update()
        if is_innovate():
            self.update()
            for btn in getattr(self, "_fx_buttons", ()):
                if hasattr(btn, "set_phase"):
                    btn.set_phase(self._fx_phase)
        if hasattr(self, "status_dot") and self.status_dot.is_animating():
            self.status_dot.tick(0.066)

    def fade_out_to_tray(self):
        """淡出后收进托盘（关闭 / 最小化按钮共用），比直接消失自然"""
        if not self.isVisible():
            self.hide()
            return
        fade = QPropertyAnimation(self, b"windowOpacity", self)
        fade.setDuration(180)
        fade.setStartValue(self.windowOpacity())
        fade.setEndValue(0.0)
        fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        fade.finished.connect(self._after_fade_out)
        self._fade_out_anim = fade  # 持有引用，防止被 GC
        fade.start()

    def _after_fade_out(self):
        self.hide()
        self.setWindowOpacity(1.0)  # 复位，下次 show 才能正常淡入

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
        # 注意：_paint_accent 里用的是 _accent_alpha / 180.0，
        # 所以动画终点必须是 180（以前写成 1.0，导致强调条永远停在起始色：
        # 断线红→在线绿根本过渡不过去，一直是红的）
        self._color_anim.setStartValue(0.0)
        self._color_anim.setEndValue(180.0)
        self._color_anim.start()

    # ── 绘制 ──────────────────────────────────────────
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        c = self.container
        cr = QRectF(c.x(), c.y(), c.width(), c.height())
        bg = QPainterPath()
        bg.addRoundedRect(cr, self._radius, self._radius)

        self._soft_window_shadow(p, cr)
        self._paint_flat_bg(p, cr, bg)
        self._paint_decor(p, cr, bg)
        p.setPen(QPen(theme_color("window_border"), 1))
        p.drawPath(bg)
        for card in (self.status_card, self.cred_card):
            self._paint_card(p, card)
        self._paint_button_shadows(p)
        self._paint_accent(p, self.status_card)
        p.end()

    # ── 通用绘制零件 ──────────────────────────────────
    def _soft_window_shadow(self, p: QPainter, cr: QRectF):
        """窗口外投影：多层极低透明度顺滑衰减，避免分层台阶感"""
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

    def _soft_shadow(self, p: QPainter, rect: QRectF, radius: float,
                     color: QColor, spread: float = 4.0, dy: float = 2.0,
                     layers: int = 6):
        """给面板 / 按钮垫一层柔和投影（不收笔，调用方自己画边）"""
        p.save()
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(layers, 0, -1):
            k = i / layers
            exp = spread * k
            a = int(color.alpha() * (1 - k) * 0.55)
            if a <= 0:
                continue
            sr = rect.adjusted(-exp, -exp + dy * k, exp, exp + dy * k)
            sp = QPainterPath()
            sp.addRoundedRect(sr, radius + exp * 0.7, radius + exp * 0.7)
            p.fillPath(sp, QColor(color.red(), color.green(), color.blue(), a))
        p.restore()

    def _paint_button_shadows(self, p: QPainter):
        """按钮的投影只能由父窗口代画（子控件画不出自己的矩形之外）"""
        for name in ("login_btn", "save_btn", "logout_btn", "diag_btn"):
            btn = getattr(self, name, None)
            if btn is None or not btn.isVisible():
                continue
            pos = btn.mapTo(self, QPoint(0, 0))
            r = QRectF(pos.x() + 1, pos.y() + 1, btn.width() - 2, btn.height() - 2)
            if is_innovate():
                # Material 高度：更深、更散、往下坠一点
                radius, color, spread, dy = min(r.height() / 2, 12), QColor(24, 60, 140, 92), 6.0, 3.6
            else:
                radius, color, spread, dy = 10, QColor(0, 0, 0, 62), 4.5, 3.0
            self._soft_shadow(p, r, radius, color, spread=spread, dy=dy, layers=5)

    def _paint_flat_bg(self, p: QPainter, cr: QRectF, bg: QPainterPath):
        """经典 / 极光的背景：垂直渐变 + （极光）漂移光晕"""
        grad = QLinearGradient(QPointF(cr.left(), cr.top()), QPointF(cr.left(), cr.bottom()))
        grad.setColorAt(0, theme_color("bg_top"))
        grad.setColorAt(1, theme_color("bg_bot"))
        p.fillPath(bg, grad)

        if is_aurora():
            t = self._fx_phase
            p.save()
            p.setClipPath(bg)
            g1x = cr.right() - 30 + math.sin(t) * 62
            g1y = cr.top() + 10 + math.cos(t * 0.75) * 42
            k1 = 0.78 + 0.22 * math.sin(t * 0.9)
            glow = QRadialGradient(QPointF(g1x, g1y), cr.height() * 0.62)
            c1 = theme_color("glow")
            glow.setColorAt(0, QColor(c1.red(), c1.green(), c1.blue(), int(c1.alpha() * k1)))
            glow.setColorAt(0.55, QColor(c1.red(), c1.green(), c1.blue(), int(c1.alpha() * k1 * 0.35)))
            glow.setColorAt(1, QColor(0, 0, 0, 0))
            p.fillRect(cr, glow)

            g2x = cr.left() + 14 + math.cos(t * 0.6) * 48
            g2y = cr.bottom() + 6 + math.sin(t * 0.9) * 40
            k2 = 0.78 + 0.22 * math.cos(t * 0.7)
            glow2 = QRadialGradient(QPointF(g2x, g2y), cr.height() * 0.5)
            c2 = theme_color("glow2")
            glow2.setColorAt(0, QColor(c2.red(), c2.green(), c2.blue(), int(c2.alpha() * k2)))
            glow2.setColorAt(0.55, QColor(c2.red(), c2.green(), c2.blue(), int(c2.alpha() * k2 * 0.35)))
            glow2.setColorAt(1, QColor(0, 0, 0, 0))
            p.fillRect(cr, glow2)
            p.restore()

    def _paint_decor(self, p: QPainter, cr: QRectF, bg: QPainterPath):
        """各主题的专属装饰元素（区别不只靠配色）"""
        decor = theme_ui()["decor"]
        if decor == "aurora":
            # 顶部一条极淡的 mauve → blue 光带，像极光垂落的边缘
            p.save()
            p.setClipPath(bg)
            band = QLinearGradient(QPointF(cr.left(), 0), QPointF(cr.right(), 0))
            c1 = theme_color("glow")
            c2 = theme_color("glow2")
            band.setColorAt(0.0, QColor(c1.red(), c1.green(), c1.blue(), 0))
            band.setColorAt(0.30, QColor(c1.red(), c1.green(), c1.blue(), min(240, int(c1.alpha() * 2.2))))
            band.setColorAt(0.66, QColor(c2.red(), c2.green(), c2.blue(), min(240, int(c2.alpha() * 2.0))))
            band.setColorAt(1.0, QColor(c2.red(), c2.green(), c2.blue(), 0))
            p.fillRect(QRectF(cr.left(), cr.top(), cr.width(), 5.0), band)
            p.restore()
        elif decor == "hairline":
            # 经典：标题栏下方一根极细的分隔线，给扁平版式一点结构
            y = cr.top() + 44
            g = QLinearGradient(QPointF(cr.left() + 12, 0), QPointF(cr.right() - 12, 0))
            base = theme_color("divider")
            g.setColorAt(0.0, QColor(base.red(), base.green(), base.blue(), 0))
            g.setColorAt(0.5, base)
            g.setColorAt(1.0, QColor(base.red(), base.green(), base.blue(), 0))
            p.setPen(QPen(QBrush(g), 1))
            p.drawLine(QPointF(cr.left() + 12, y), QPointF(cr.right() - 12, y))

    # ── 卡片 ──────────────────────────────────────────
    def _paint_card(self, p: QPainter, w: QWidget):
        pos = w.mapTo(self, QPoint(0, 0))
        r = QRectF(pos.x() - 2, pos.y() - 2, w.width() + 4, w.height() + 4)
        radius = card_radius()
        path = QPainterPath()
        path.addRoundedRect(r, radius, radius)

        # 卡片自身的柔和投影：让内容块浮在窗口底色之上
        shadow = QColor(0, 0, 0, 54 if not is_aurora() else 44)
        self._soft_shadow(p, r, radius, shadow, spread=4, dy=3)

        p.fillPath(path, theme_color("card"))

        # 顶部内高光（薄透镜感）
        p.save()
        p.setClipPath(path)
        hl = QLinearGradient(QPointF(r.left(), r.top()),
                             QPointF(r.left(), r.top() + r.height() * 0.5))
        hl.setColorAt(0.0, theme_color("highlight"))
        hl.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillRect(r, hl)
        p.restore()

        p.setBrush(Qt.BrushStyle.NoBrush)
        if is_aurora():
            gb = QLinearGradient(r.topLeft(), r.bottomRight())
            c1 = theme_color("glow")
            c2 = theme_color("glow2")
            gb.setColorAt(0.0, QColor(c1.red(), c1.green(), c1.blue(), 120))
            gb.setColorAt(1.0, QColor(c2.red(), c2.green(), c2.blue(), 120))
            p.setPen(QPen(QBrush(gb), 1))
            p.drawPath(path)
        elif is_innovate():
            # 底层先给一圈淡描边，再叠一条绕卡片旋转的流光（锥形渐变描边）
            p.setPen(QPen(theme_color("card_border"), 1))
            p.drawPath(path)

            c1 = theme_color("glow")
            c2 = theme_color("glow2")
            a1, a2 = c1.alpha(), c2.alpha()
            cg = QConicalGradient(r.center(), (self._fx_phase * 26) % 360)
            cg.setColorAt(0.00, QColor(c1.red(), c1.green(), c1.blue(), int(a1 * 0.10)))
            cg.setColorAt(0.13, QColor(c1.red(), c1.green(), c1.blue(), a1))
            cg.setColorAt(0.32, QColor(c2.red(), c2.green(), c2.blue(), int(a2 * 0.22)))
            cg.setColorAt(0.60, QColor(c2.red(), c2.green(), c2.blue(), int(a2 * 0.18)))
            cg.setColorAt(0.82, QColor(c2.red(), c2.green(), c2.blue(), a2))
            cg.setColorAt(1.00, QColor(c1.red(), c1.green(), c1.blue(), int(a1 * 0.10)))
            inner = QPainterPath()
            inner.addRoundedRect(r.adjusted(0.9, 0.9, -0.9, -0.9), radius - 0.9, radius - 0.9)
            p.setPen(QPen(QBrush(cg), 1.8))
            p.drawPath(inner)
        else:
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
            ("退出", lambda: QTimer.singleShot(0, self.quit_app)),
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

        # 登录走后台线程，这里只是占位引用
        self._login_worker = None

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
    def _start_login(self, username: str, password: str, portal_url: str,
                     source: str, verify_online: bool = False) -> bool:
        """把登录丢给后台线程（source: auto / retry / manual），界面不再假死"""
        if self._login_worker is not None and self._login_worker.isRunning():
            self.log("上一次登录还在进行中，本次跳过")
            return False
        # 上一轮的线程已经结束：主动回收，避免窗口下越挂越多
        if self._login_worker is not None:
            self._login_worker.deleteLater()
            self._login_worker = None
        self._login_worker = LoginWorker(username, password, portal_url,
                                         verify_online=verify_online, parent=self)
        self._login_worker.resultReady.connect(
            lambda result, s=source: self._on_login_result(result, s))
        self._login_worker.start()
        return True

    def _on_login_result(self, result: dict, source: str):
        """后台登录线程回来后的统一处理"""
        msg = result.get("msg", "")
        if msg:
            self.log(msg)

        if result.get("already"):
            self.notify("网络正常", msg or "当前已连接网络，无需登录",
                        QSystemTrayIcon.MessageIcon.Information)
            return

        if result.get("ok"):
            logout_url = result.get("logout_url")
            if logout_url:
                self.config["logout_url"] = logout_url
                save_config(self.config)
            self._login_retry_count = 0
            self._login_retry_timer.stop()
            if source == "manual":
                self.notify("登录成功", "已成功连接到校园网",
                            QSystemTrayIcon.MessageIcon.Information)
            else:
                self.notify("自动登录成功", "网络已恢复连接",
                            QSystemTrayIcon.MessageIcon.Information)
            return

        if source == "manual":
            self.notify("登录失败", msg or "登录失败",
                        QSystemTrayIcon.MessageIcon.Warning)
        else:
            self._schedule_login_retry(msg)

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
            self._start_login(u, pw, portal_url, "auto")
        except Exception as e:
            self.log(f"自动登录异常: {e}")
            self._schedule_login_retry(str(e))

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
        self.log(f"正在重试自动登录（第{self._login_retry_count + 1}次）...")
        self._start_login(u, pw, portal, "retry")

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
            self.log("正在检测网络并登录...")
            # 检测可达性和登录一起丢到后台线程，避免界面卡住
            self._start_login(u, pw, self.config.get("portal_url", ""),
                              "manual", verify_online=True)
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

    def on_save_clicked(self):
        """「保存配置」按钮：写入当前账号密码，并顺手把它加进账户列表"""
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()
        self.config["username"] = username
        self.config["password"] = password
        if username:
            self._upsert_account(username, password)
        save_config(self.config)
        self.checker.set_interval(self.config.get("check_interval", 10))
        self.checker.set_portal_url(self.config.get("portal_url", ""))
        self.log("配置已保存" + ("（账号已加入列表）" if username else ""))

    # ── 多账户 ────────────────────────────────────────
    def _upsert_account(self, username: str, password: str):
        """新增 / 覆盖一个账户（密码在内存里是明文，落盘时由 config 统一加密）"""
        accounts = [a for a in self.config.get(ACCOUNTS_KEY, [])
                    if a.get("username") != username]
        accounts.append({"username": username, "password": password})
        self.config[ACCOUNTS_KEY] = accounts

    def _styled_menu(self) -> QMenu:
        """跟随当前主题的弹出菜单样式"""
        t = CURRENT_THEME
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background: {t['card'].name()};
                border: 1px solid {t['card_border'].name()};
                border-radius: 10px;
                padding: 6px;
                color: {t['text'].name()};
                font-size: 13px;
            }}
            QMenu::item {{
                padding: 7px 20px 7px 12px;
                border-radius: 6px;
                background: transparent;
            }}
            QMenu::item:selected {{
                background: {t['surface_hover'].name()};
                color: {t['text'].name()};
            }}
            QMenu::item:disabled {{
                color: {t['text_ter'].name()};
            }}
            QMenu::separator {{
                height: 1px;
                background: {t['divider'].name()};
                margin: 5px 8px;
            }}
            QMenu::indicator {{ width: 0px; }}
        """)
        return menu

    def show_account_menu(self):
        """账号右侧小箭头：列出已保存账户 + 保存 / 删除当前账号"""
        accounts = self.config.get(ACCOUNTS_KEY, [])
        current = self.username_input.text().strip()

        menu = self._styled_menu()
        if accounts:
            for acc in accounts:
                name = acc.get("username", "")
                prefix = "✓ " if name == current else "　 "
                act = menu.addAction(f"{prefix}{name}")
                act.triggered.connect(
                    lambda _checked=False, u=name: self.switch_account(u))
        else:
            act = menu.addAction("还没有保存的账户")
            act.setEnabled(False)

        menu.addSeparator()
        save_act = menu.addAction("保存当前账号")
        save_act.triggered.connect(lambda _checked=False: self.save_current_account())
        if current:
            del_act = menu.addAction(f"删除 {current}")
            del_act.triggered.connect(
                lambda _checked=False, u=current: self.delete_account(u))

        menu.exec(self.account_btn.mapToGlobal(
            QPoint(0, self.account_btn.height() + 6)))

    def switch_account(self, username: str):
        """切换账户：自动把对应的密码填进密码框"""
        for acc in self.config.get(ACCOUNTS_KEY, []):
            if acc.get("username") == username:
                password = acc.get("password", "")
                self.username_input.setText(username)
                self.password_input.setText(password)
                self.config["username"] = username
                self.config["password"] = password
                save_config(self.config)
                self.log(f"已切换到账户 {username}")
                return
        self.log(f"未找到账户 {username}")

    def save_current_account(self) -> bool:
        """把输入框里的账号密码存进账户列表"""
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()
        if not username:
            QMessageBox.warning(self, "提示", "请先填写账号")
            return False
        self._upsert_account(username, password)
        self.config["username"] = username
        self.config["password"] = password
        save_config(self.config)
        self.log(f"账户 {username} 已保存（密码已加密存储）")
        return True

    def delete_account(self, username: str):
        """从列表里删除一个账户；删的正好是当前账号时清空输入框"""
        before = self.config.get(ACCOUNTS_KEY, [])
        after = [a for a in before if a.get("username") != username]
        if len(after) == len(before):
            return
        self.config[ACCOUNTS_KEY] = after
        if self.config.get("username") == username:
            self.config["username"] = ""
            self.config["password"] = ""
            self.username_input.clear()
            self.password_input.clear()
        save_config(self.config)
        self.log(f"已删除账户 {username}")

    def toggle_password_visible(self, visible: bool):
        """小眼睛：明文 / 密文切换"""
        self.password_input.setEchoMode(
            QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password)

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
        # 已经有一次检查在跑：手动点击时给个明确提示，别静默忽略
        if self._update_checker is not None and self._update_checker.isRunning():
            if not silent:
                self._settings_dialog.version_label.setText("正在检查中，请稍候…")
            return

        if not silent:
            self._settings_dialog.version_label.setText("正在检查更新...")
            self._set_update_btn(checking=True)

        self._update_checker = UpdateChecker(self)
        self._update_checker.foundNew.connect(
            lambda v: self._on_update_found(v, silent))
        self._update_checker.upToDate.connect(
            lambda tag: self._on_update_ok(tag, silent))
        self._update_checker.failed.connect(
            lambda msg: self._on_update_failed(msg, silent))
        self._update_checker.start()

    def _set_update_btn(self, checking: bool):
        """检查期间按钮变成"检查中…"并禁用，结束后恢复"""
        btn = getattr(self._settings_dialog, "check_update_btn", None)
        if btn is None:
            return
        btn.setEnabled(not checking)
        btn.setText("检查中…" if checking else "检查更新")

    def _on_update_found(self, version: str, silent: bool):
        self._set_update_btn(checking=False)
        self._new_version = version
        if hasattr(self, "_settings_dialog"):
            self._settings_dialog.version_label.setText(
                f"发现新版本 v{version}，请到 GitHub Release 下载")
        self.log(f"发现新版本 v{version}，请到 GitHub Release 页面下载")
        self.notify("发现新版本", f"v{version} 已发布，请到 GitHub Release 页面下载更新",
                    QSystemTrayIcon.MessageIcon.Information, 5000)

    def _on_update_ok(self, tag: str, silent: bool):
        self._set_update_btn(checking=False)
        if hasattr(self, "_settings_dialog"):
            self._settings_dialog.version_label.setText(f"当前已是最新版本 v{APP_VERSION}")
        self.log(f"检查更新: 已是最新版本（远端 {('v' + tag) if tag else '无 Release'}）")
        if not silent:
            body = f"当前已是最新版本 v{APP_VERSION}。"
            if tag:
                body += f"\n远端最新发布为 v{tag}，不高于本地版本。"
            else:
                body += "\n远端仓库还没有发布任何 Release。"
            InfoDialog("检查更新", body, self._settings_dialog).exec()

    def _on_update_failed(self, msg: str, silent: bool):
        self._set_update_btn(checking=False)
        if hasattr(self, "_settings_dialog"):
            self._settings_dialog.version_label.setText("检查更新失败，详见日志")
        self.log(f"检查更新失败: {msg}")
        if not silent:
            InfoDialog("检查更新失败", msg + "\n\n可以稍后重试，或手动到 GitHub 查看发布页。",
                       self._settings_dialog,
                       action_text="打开发布页",
                       action=lambda: __import__("webbrowser").open(UPDATE_PAGE)).exec()

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
        self._settings_dialog.quit_on_close_switch.setChecked(
            self.config.get(QUIT_ON_CLOSE_KEY, False)
        )
        self._settings_dialog.theme_selector.set_mode(
            get_theme_mode(self.config), animate=False
        )
        self._settings_dialog.scene_selector.set_mode(
            get_scene_mode(self.config), animate=False
        )
        self._settings_dialog.family_selector.set_mode(
            ThemeManager.load_family(self.config), animate=False
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
        """关窗口 / Alt+F4：默认收进托盘，可在设置里改成直接退出"""
        if self.config.get(QUIT_ON_CLOSE_KEY, False):
            self.log("窗口关闭 → 按设置直接退出")
            event.accept()
            self.quit_app()
            return
        self.log("窗口关闭 → 收进系统托盘（可在设置里改成直接退出）")
        event.ignore()
        self.fade_out_to_tray()
        self.tray_icon.showMessage(
            APP_NAME, "程序已最小化到系统托盘，双击图标可恢复窗口",
            QSystemTrayIcon.MessageIcon.Information, 2000,
        )

    def _spawn_new_instance(self) -> bool:
        """
        拉起一个新的自己。三种方式依次尝试，任何一种成功就返回 True：
          1) subprocess + DETACHED_PROCESS（独立进程，最可控）
          2) os.startfile（等价于资源管理器里双击）
          3) QProcess.startDetached
        每种方式的成败都写日志，出问题能直接从 giwifi.log 看出来。
        """
        frozen = getattr(sys, "frozen", False)
        prog = sys.executable
        if frozen:
            args = ["--restarted"]
            cwd = os.path.dirname(os.path.abspath(sys.executable))
        else:
            args = [os.path.abspath(sys.argv[0]), "--restarted"]
            cwd = os.getcwd()
        file_log(f"重启：尝试拉起 {prog} {args}")

        # 关键：先摘掉 PyInstaller 传下来的解包目录变量（_MEIxxxx / _PYI_*）。
        # 不清的话子进程会「复用」父进程那个已解包目录，而父进程随后就退出，
        # 目录一消失，子进程读 app_icon.png 之类的资源就会失败 ——
        # 实测表现就是"重启出来的进程启动即崩"。
        stashed = {k: v for k, v in os.environ.items()
                   if k.startswith("_MEI") or k.startswith("_PYI")}
        for k in stashed:
            os.environ.pop(k, None)
        try:
            # 方式 1：subprocess + DETACHED_PROCESS（独立进程，不随父进程退出）
            try:
                import subprocess
                DETACHED_PROCESS = 0x00000008
                subprocess.Popen([prog] + args, cwd=cwd, close_fds=True,
                                 creationflags=DETACHED_PROCESS)
                file_log("重启：subprocess 已启动")
                return True
            except Exception as e:
                file_log(f"重启：subprocess 失败 - {e}")

            # 方式 2：ShellExecute（等价于双击；带不了参数）
            if frozen:
                try:
                    os.startfile(prog)
                    file_log("重启：ShellExecute 已启动")
                    return True
                except Exception as e:
                    file_log(f"重启：ShellExecute 失败 - {e}")

            # 方式 3：QProcess.startDetached（返回 (bool, pid) 元组）
            try:
                res = QProcess.startDetached(prog, args, cwd)
                ok = bool(res[0]) if isinstance(res, tuple) else bool(res)
                file_log(f"重启：QProcess 返回 {ok}")
                return ok
            except Exception as e:
                file_log(f"重启：QProcess 失败 - {e}")
            return False
        finally:
            os.environ.update(stashed)

    def restart_app(self):
        """重启自身：先放掉单实例互斥锁 → 拉起新进程 → 退出当前进程"""
        self.log("restart_app 进入")
        try:
            self._persist_traffic()
            save_config(self.config)
        except Exception:
            pass

        # 不先放锁的话，新进程会被单实例检测挡回去（提示"已在运行"）
        handle = globals().get("MUTEX_HANDLE")
        if handle:
            try:
                import ctypes
                ctypes.windll.kernel32.CloseHandle(handle)
            except Exception:
                pass
            globals()["MUTEX_HANDLE"] = None

        ok = self._spawn_new_instance()

        if not ok:
            file_log("重启失败：没能拉起新进程，请手动启动")
            return

        file_log("正在重启程序...")
        # 先把窗口和托盘图标藏掉再退出：否则 os._exit 之后窗口会以白/黑方块的形式
        # 在屏幕上挂一两秒（DWM 还拿着最后一帧），看起来像"卡住未响应"。
        # hide() 走的是原生 ShowWindow，不依赖事件循环，立刻生效。
        for wd in QApplication.topLevelWidgets():
            try:
                if wd.isVisible():
                    wd.hide()
            except Exception:
                pass
        try:
            self.tray_icon.hide()
        except Exception:
            pass

        # 直接结束本进程，不等 Qt 事件循环自己退。
        # 原因：点「立即重启」时正套着「设置」和「重启提示」两层模态对话框，
        # QApplication.quit() 不一定能把这两个嵌套事件循环都掀掉，
        # 表现就是"程序没重开也关不掉"。配置和流量在上面已经落盘了。
        os._exit(0)

    def quit_app(self):
        """真正退出程序（红点按钮 / 托盘菜单「退出」/ 设置里开了「关闭即退出」）"""
        if getattr(self, "_quitting", False):
            return  # 防止连点两次走两遍
        self._quitting = True
        self.log("正在退出程序...")

        try:
            self._persist_traffic()  # 退出前保存今日流量
        except Exception:
            pass

        # 把所有定时器停掉，避免退出过程中还在回调
        for name in ("duration_timer", "_login_retry_timer", "_speed_timer",
                     "_fx_timer", "_sys_theme_timer", "_scene_timer"):
            timer = getattr(self, name, None)
            if timer is not None:
                try:
                    timer.stop()
                except Exception:
                    pass

        # 等待后台线程，全部带上限：以前 checker.wait() 没上限，
        # 正好卡在一次网络检测里时界面会僵住（最长十几秒）
        try:
            self.checker.stop()
            self.checker.wait(600)
        except Exception:
            pass
        if getattr(self, "_login_worker", None) is not None and self._login_worker.isRunning():
            self._login_worker.wait(600)

        try:
            self.tray_icon.hide()
        except Exception:
            pass

        file_log("程序退出")
        QApplication.quit()

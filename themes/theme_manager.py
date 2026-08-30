# -*- coding: utf-8 -*-
"""
themes/theme_manager.py —— 主题管理器（加载 / 切换 / 持久化 / DWM 毛玻璃）

职责
----
1. 主题家族持久化：config["theme"] = "default" | "liquid_glass"，
   读写复用项目现有的 config.load_config / save_config，重启后记住选择。
2. DWM 原生毛玻璃应用与移除（仅液态玻璃主题使用）：
   - 首选：Win11 DwmSetWindowAttribute + DWMWA_SYSTEMBACKDROP_TYPE
     （主窗口 2 = Mica，弹窗 3 = Acrylic），并设置
     DWMWA_USE_IMMERSIVE_DARK_MODE(20) 保证玻璃上的白字可读。
   - 降级 1：DWM 不可用/调用失败 → SetWindowCompositionAttribute +
     ACCENT_ENABLE_ACRYLICBLURBEHIND（Win10/Win11 均可）。
   - 降级 2：两者都失败 → 保持默认主题外观（本模块返回 "none"，
     由调用方回退默认渲染），全程不抛异常、不闪退。
3. 移除毛玻璃：把 DWMWA_SYSTEMBACKDROP_TYPE 设为 DWMSBT_NONE(1)、
   ACCENT_POLICY 设为 ACCENT_DISABLED(0)，彻底清除系统层残留。
   （注意：需求原文写「设回 0」——0 是 DWMSBT_AUTO 交给系统决定，
   真正彻底关闭应使用 1 = DWMSBT_NONE，此处按语义实现。）

切换流程（重要）
----------------
WA_TranslucentBackground 只能在窗口 show 之前设置，运行中直接切换
主题会导致透明失效。因此本项目的切换策略为：
    设置面板修改「主题风格」 → ThemeManager.save_family() 写入
    config["theme"] → 弹窗提示「重启生效」 → 用户重启 →
    main.py 启动时 load_family() 读回 → 主窗口按新家族构建。
运行期不做 DWM 热切换，杜绝黑块/透明失效；窗口销毁时系统层
毛玻璃随 hwnd 自动回收，无残留。
"""
import ctypes
import sys
from ctypes import wintypes

from themes.default import THEME_DEFAULT
from themes.liquid_glass import THEME_GLASS

# ── DWM 常量 ─────────────────────────────────────────────
DWMWA_USE_IMMERSIVE_DARK_MODE = 20     # BOOL：深色模式（白字可读）
DWMWA_SYSTEMBACKDROP_TYPE = 38         # Win11 22H2+ 系统级毛玻璃
DWMWA_WINDOW_CORNER_PREFERENCE = 33    # Win11 圆角偏好
DWMWCP_ROUND = 2                       # 系统圆角

# SYSTEMBACKDROP 取值（注意：NONE = 1，AUTO = 0）
DWMSBT_AUTO = 0
DWMSBT_NONE = 1
DWMSBT_MAINWINDOW = 2                  # Mica（主窗口）
DWMSBT_TRANSIENTWINDOW = 3             # Acrylic（弹窗）

# SetWindowCompositionAttribute（降级方案）常量
ACCENT_DISABLED = 0
ACCENT_ENABLE_ACRYLICBLURBEHIND = 4
WCA_ACCENT_POLICY = 19

_IS_WIN11 = None  # 延迟探测缓存


def _win_build() -> int:
    try:
        return sys.getwindowsversion().build  # type: ignore[attr-defined]
    except Exception:
        return 0


def is_win11() -> bool:
    """Windows 11（build ≥ 22000）才支持 DWMWA_SYSTEMBACKDROP_TYPE"""
    global _IS_WIN11
    if _IS_WIN11 is None:
        _IS_WIN11 = _win_build() >= 22000
    return _IS_WIN11


class _ACCENT_POLICY(ctypes.Structure):
    _fields_ = [
        ("AccentState", ctypes.c_uint),
        ("AccentFlags", ctypes.c_uint),
        ("GradientColor", ctypes.c_uint),  # AABBGGRR
        ("AnimationId", ctypes.c_int),
    ]


class _WINDOWCOMPOSITIONATTRIBDATA(ctypes.Structure):
    _fields_ = [
        ("Attribute", ctypes.c_int),
        ("Data", ctypes.POINTER(_ACCENT_POLICY)),
        ("SizeOfData", ctypes.c_size_t),
    ]


def _hwnd_of(widget) -> int:
    try:
        return int(widget.winId())
    except Exception:
        return 0


# ── ThemeManager ─────────────────────────────────────────
class ThemeManager:
    """主题家族的加载 / 切换 / 持久化 + DWM 毛玻璃应用与移除"""

    BACKDROP_MICA = "mica"          # 主窗口：DWM Mica
    BACKDROP_ACRYLIC = "acrylic"    # 弹窗：DWM Acrylic
    BACKDROP_COMPOSITION = "composition"  # 降级：SetWindowCompositionAttribute
    BACKDROP_NONE = "none"          # 降级到底：不启用毛玻璃（回退默认外观）

    def __init__(self):
        self.last_method = self.BACKDROP_NONE  # 最近一次实际生效的毛玻璃方式

    # ── 持久化 ───────────────────────────────────────
    @staticmethod
    def load_family(cfg: dict) -> str:
        """从配置读取主题家族，非法值回退 default（默认主题零改动启动）"""
        family = cfg.get("theme", THEME_DEFAULT)
        return family if family in (THEME_DEFAULT, THEME_GLASS) else THEME_DEFAULT

    @staticmethod
    def save_family(cfg: dict, family: str) -> None:
        """写入 config["theme"]（由调用方负责 save_config 落盘 + 提示重启）"""
        if family in (THEME_DEFAULT, THEME_GLASS):
            cfg["theme"] = family

    # ── DWM 毛玻璃（含降级链路）──────────────────────
    def apply_backdrop(self, widget, kind: str = BACKDROP_MICA) -> str:
        """
        给窗口/弹窗套系统级毛玻璃。返回实际生效方式：
        "mica" / "acrylic" / "composition" / "none"
        降级链路：DWM SystemBackdrop → SetWindowCompositionAttribute
        → none（调用方回退默认主题外观）。全程 try/except，绝不抛异常。
        """
        hwnd = _hwnd_of(widget)
        self.last_method = self.BACKDROP_NONE
        if not hwnd:
            return self.last_method

        # Win11 首选：DWMWA_SYSTEMBACKDROP_TYPE
        if is_win11():
            try:
                dwm = ctypes.windll.dwmapi
                # 统一使用 DWMSBT_TRANSIENTWINDOW(3) = 系统级 Acrylic 高斯模糊。
                # 之前主窗口用 DWMSBT_MAINWINDOW(2)=Mica，它是「壁纸染色」而非模糊，
                # 叠加深色模式后呈现为接近黑色的底（用户反馈难看）。
                backdrop = DWMSBT_TRANSIENTWINDOW  # 3 = Acrylic 高斯模糊
                value = ctypes.c_int(backdrop)
                hr = dwm.DwmSetWindowAttribute(
                    wintypes.HWND(hwnd),
                    DWMWA_SYSTEMBACKDROP_TYPE,
                    ctypes.byref(value),
                    ctypes.sizeof(value),
                )
                if hr == 0:
                    # 深色模式标志：保证玻璃上的白色文字可读
                    dark = ctypes.c_int(1)
                    dwm.DwmSetWindowAttribute(
                        wintypes.HWND(hwnd),
                        DWMWA_USE_IMMERSIVE_DARK_MODE,
                        ctypes.byref(dark),
                        ctypes.sizeof(dark),
                    )
                    # Win11 圆角（无边框窗口系统级圆角，毛玻璃随窗口形状）
                    corner = ctypes.c_int(DWMWCP_ROUND)
                    dwm.DwmSetWindowAttribute(
                        wintypes.HWND(hwnd),
                        DWMWA_WINDOW_CORNER_PREFERENCE,
                        ctypes.byref(corner),
                        ctypes.sizeof(corner),
                    )
                    self.last_method = self.BACKDROP_MICA if kind == self.BACKDROP_MICA \
                        else self.BACKDROP_ACRYLIC
                    return self.last_method
            except Exception:
                pass  # DWM 失败 → 降级到 SetWindowCompositionAttribute

        # 降级：SetWindowCompositionAttribute + Acrylic（Win10 也可用）
        try:
            user32 = ctypes.windll.user32
            accent = _ACCENT_POLICY()
            accent.AccentState = ACCENT_ENABLE_ACRYLICBLURBEHIND
            # GradientColor 为 AABBGGRR；浅灰蓝底 + 半透明
            accent.GradientColor = 0x99F5EFE8
            accent.AccentFlags = 2
            data = _WINDOWCOMPOSITIONATTRIBDATA()
            data.Attribute = WCA_ACCENT_POLICY
            data.Data = ctypes.pointer(accent)
            data.SizeOfData = ctypes.sizeof(accent)
            if user32.SetWindowCompositionAttribute(wintypes.HWND(hwnd), ctypes.byref(data)):
                self.last_method = self.BACKDROP_COMPOSITION
                return self.last_method
        except Exception:
            pass

        # 降级到底：不启用毛玻璃，调用方回退默认主题外观
        return self.last_method

    @staticmethod
    def clear_backdrop(widget) -> None:
        """
        彻底移除系统层毛玻璃（切回默认主题时调用，防残留）：
        - DWM SystemBackdrop 设回 DWMSBT_NONE(1)
        - ACCENT_POLICY 设回 ACCENT_DISABLED(0)
        本项目切换采用「重启生效」方案，窗口销毁时 hwnd 连同系统属性
        一起回收，因此正常流程不会调用本方法；保留以备测试与强制清理。
        """
        hwnd = _hwnd_of(widget)
        if not hwnd:
            return
        try:
            dwm = ctypes.windll.dwmapi
            value = ctypes.c_int(DWMSBT_NONE)  # 彻底关闭（而非 AUTO=0）
            dwm.DwmSetWindowAttribute(
                wintypes.HWND(hwnd),
                DWMWA_SYSTEMBACKDROP_TYPE,
                ctypes.byref(value),
                ctypes.sizeof(value),
            )
        except Exception:
            pass
        try:
            user32 = ctypes.windll.user32
            accent = _ACCENT_POLICY()
            accent.AccentState = ACCENT_DISABLED
            data = _WINDOWCOMPOSITIONATTRIBDATA()
            data.Attribute = WCA_ACCENT_POLICY
            data.Data = ctypes.pointer(accent)
            data.SizeOfData = ctypes.sizeof(accent)
            user32.SetWindowCompositionAttribute(wintypes.HWND(hwnd), ctypes.byref(data))
        except Exception:
            pass

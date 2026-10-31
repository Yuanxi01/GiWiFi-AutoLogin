# -*- coding: utf-8 -*-
"""
themes/aurora.py —— 「极光」主题（第三个主题家族）

配色来源
--------
Catppuccin（https://github.com/catppuccin/catppuccin，MIT 协议）：
  - 浅色 = Latte 风味（唯一浅色盘）
  - 深色 = Mocha 风味（最经典的深色盘）
两套盘都是 26 色成套设计，色彩之间互相协调，正文对比度均 ≥ 4.5:1。

视觉特征（与「经典」的区别）
--------------------------
1. 柔和粉彩配色 + 紫/蓝双色径向光晕（paintEvent 里的 aurora 分支绘制）
2. 卡片 / 窗口圆角更大（窗口 20px、卡片 16px）
3. 主按钮在深色下用「浅底 + 深字」（Catppuccin 的惯用做法），
   因此新增 primary_fill / on_primary 两个 token 供按钮取色

token 键与 default.py / innovate.py 完全一致，tray_app 里所有读
CURRENT_THEME[key] 的既有代码无需分支即可自动适配。
"""
from PySide6.QtGui import QColor

THEME_AURORA = "aurora"

# UI 结构参数：极光主题——中等圆角、渐变顶带 + 漂移光晕
UI_AURORA = {
    "win_radius": 20,
    "card_radius": 16,
    "card_gap": 10,
    "card_merged": False,
    "btn_height": 38,
    "decor": "aurora",
    "card_pad": (16, 12, 16, 14),
}


def _rgba(c: QColor, alpha: int = None) -> str:
    a = c.alpha() if alpha is None else alpha
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {a})"


# ── 浅色 · Catppuccin Latte（页面底色掺薰衣草紫，拉开和「经典」的距离）──
AURORA_LIGHT = {
    # 窗口（Latte base 掺入 mauve/lavender 的淡紫调）
    "bg_top": QColor(0xF4, 0xF0, 0xFC),
    "bg_bot": QColor(0xE7, 0xE3, 0xF7),
    "window_border": QColor(0xDA, 0xD4, 0xEF),
    "shadow": QColor(76, 62, 120, 40),
    # 卡片
    "card": QColor(255, 255, 255, 250),
    "card_border": QColor(0xE8, 0xE3, 0xF8),
    # 文字
    "text": QColor(0x4C, 0x4F, 0x69),            # Latte text
    "text_sec": QColor(0x6C, 0x6F, 0x85),        # subtext0
    "text_ter": QColor(0x8C, 0x8F, 0xA1),        # overlay1
    # 主色（蓝 → 蓝紫渐变按钮）
    "primary": QColor(0x1E, 0x66, 0xF5),         # Latte blue
    "primary_hover": QColor(0x72, 0x87, 0xFD),   # lavender（更亮一档）
    "primary_fill": QColor(0x2F, 0x6B, 0xF3),
    "primary2": QColor(0x6C, 0x5B, 0xF0),        # 渐变终点（蓝紫）
    "on_primary": QColor(255, 255, 255),
    "focus_ring": QColor(30, 102, 245, 110),
    # 语义色
    "success": QColor(0x40, 0xA0, 0x2B),         # Latte green
    "success_dot": QColor(0x40, 0xA0, 0x2B),
    "danger": QColor(0xD2, 0x0F, 0x39),          # Latte red
    "danger_dot": QColor(0xD2, 0x0F, 0x39),
    # 控件
    "input_bg": QColor(255, 255, 255, 242),
    "input_border": QColor(0xC9, 0xC4, 0xE4),    # 带紫调的描边
    "input_focus_bg": QColor(255, 255, 255, 255),
    "surface": QColor(0xEC, 0xE8, 0xFA),         # 次按钮
    "surface_hover": QColor(0xE0, 0xDB, 0xF5),
    "track_off": QColor(0xD4, 0xCE, 0xEC),
    "divider": QColor(0xE8, 0xE3, 0xF8),
    "highlight": QColor(255, 255, 255, 130),
    # 光晕（极光效果专用）
    "glow": QColor(0x88, 0x39, 0xEF, 68),        # mauve 光晕
    "glow2": QColor(0x1E, 0x66, 0xF5, 52),       # blue 光晕
}

# ── 深色 · Catppuccin Mocha ─────────────────────────────
AURORA_DARK = {
    # 窗口（base → crust）
    "bg_top": QColor(0x1E, 0x1E, 0x2E),          # Mocha base
    "bg_bot": QColor(0x11, 0x11, 0x1B),          # Mocha crust
    "window_border": QColor(0x45, 0x47, 0x5A),   # surface1
    "shadow": QColor(0, 0, 0, 150),
    # 卡片
    "card": QColor(0x2A, 0x2B, 0x3D, 240),       # base/surface0 之间
    "card_border": QColor(0x45, 0x47, 0x5A),     # surface1
    # 文字
    "text": QColor(0xCD, 0xD6, 0xF4),            # Mocha text
    "text_sec": QColor(0xBA, 0xC2, 0xDE),        # subtext1
    "text_ter": QColor(0x93, 0x99, 0xB2),        # overlay2
    # 主色（蓝）/ 按钮填充 / 按钮文字
    "primary": QColor(0x89, 0xB4, 0xFA),         # Mocha blue（做文字/强调）
    "primary_hover": QColor(0xA6, 0xC8, 0xFF),
    "primary_fill": QColor(0x89, 0xB4, 0xFA),    # 浅底按钮
    "primary2": QColor(0xB4, 0xBE, 0xFE),        # lavender：渐变终点（蓝 → 淡紫）
    "on_primary": QColor(0x1E, 0x1E, 0x2E),      # 浅底按钮上用深字
    "focus_ring": QColor(137, 180, 250, 150),
    # 语义色
    "success": QColor(0xA6, 0xE3, 0xA1),         # Mocha green
    "success_dot": QColor(0xA6, 0xE3, 0xA1),
    "danger": QColor(0xF3, 0x8B, 0xA8),          # Mocha red
    "danger_dot": QColor(0xF3, 0x8B, 0xA8),
    # 控件
    "input_bg": QColor(0x11, 0x11, 0x1B, 235),
    "input_border": QColor(0x58, 0x5B, 0x70),    # surface2
    "input_focus_bg": QColor(0x11, 0x11, 0x1B, 255),
    "surface": QColor(0x31, 0x32, 0x44, 240),    # surface0
    "surface_hover": QColor(0x45, 0x47, 0x5A),
    "track_off": QColor(0x45, 0x47, 0x5A),
    "divider": QColor(0x31, 0x32, 0x44),
    "highlight": QColor(255, 255, 255, 18),
    # 光晕
    "glow": QColor(0xCB, 0xA6, 0xF7, 62),        # mauve 光晕
    "glow2": QColor(0x89, 0xB4, 0xFA, 46),       # blue 光晕
}


def build_aurora_qss(t: dict) -> str:
    """极光主题的全局 QSS（比经典主题更圆的输入框、更柔和的边框）"""
    return f"""
    QLabel {{
        color: {t['text'].name()};
        background: transparent;
        border: none;
    }}
    QLineEdit {{
        background: {_rgba(t['input_bg'])};
        border: 1.5px solid {t['input_border'].name()};
        border-radius: 10px;
        padding: 5px 12px;
        font-size: 13px;
        color: {t['text'].name()};
        min-height: 20px;
        selection-background-color: {t['primary'].name()};
        selection-color: {t['on_primary'].name()};
    }}
    QLineEdit:focus {{
        border: 1.5px solid {t['primary'].name()};
        background: {_rgba(t['input_focus_bg'])};
    }}
    """

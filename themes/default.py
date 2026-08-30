# -*- coding: utf-8 -*-
"""
themes/default.py —— 默认主题（原样式收编）

用途：把 tray_app.py 原有的「晴空白（白天）/ 深夜蓝（黑夜）」两套配色
与全局 QSS 构建函数**原样搬运**到这里，视觉零改动。
tray_app.py 通过 `from themes.default import LIGHT_THEME, DARK_THEME,
build_window_qss` 继续使用，行为与收编前完全一致。

本文件不做任何视觉调整；调整默认主题外观请保持谨慎（会影响老用户）。
"""
from PySide6.QtGui import QColor

THEME_DEFAULT = "default"


def _rgba(c: QColor, alpha: int = None) -> str:
    """QColor → Qt QSS rgba() 字符串"""
    a = c.alpha() if alpha is None else alpha
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {a})"

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

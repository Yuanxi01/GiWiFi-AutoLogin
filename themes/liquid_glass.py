# -*- coding: utf-8 -*-
"""
themes/liquid_glass.py —— 液态玻璃主题（可选，Windows 11 毛玻璃）

设计：
- 背景交由 DWM 原生毛玻璃（主窗口 Mica / 弹窗 Acrylic，见 theme_manager.py），
  Qt 侧只画「半透明白色蒙层 + 细白描边」，让系统模糊透出来。
- GLASS_THEME 的 key 与 default.py 的 LIGHT_THEME/DARK_THEME 完全一致，
  因此 tray_app 里所有读 CURRENT_THEME 的既有代码（状态色、圆点、强调条等）
  无需分支即可自动适配玻璃配色。
- 文字统一白色/浅色系，保证在毛玻璃上的对比度。

调参：玻璃浓度改 GLASS_THEME["card"]/input_bg 的 alpha；
按钮玻璃浓度改 BUTTON_BASE_ALPHA / 高光改 BUTTON_HIGHLIGHT_ALPHA。
"""
from PySide6.QtGui import QColor

THEME_GLASS = "liquid_glass"

# ── 语义色（key 与 default 主题一致）─────────────────
GLASS_THEME = {
    # 窗口（玻璃模式下 bg_* 仅用于弹窗容器等以 rgba 输出的场景，带 alpha）
    "bg_top": QColor(15, 23, 42, 140),
    "bg_bot": QColor(15, 23, 42, 110),
    "window_border": QColor(255, 255, 255, 60),
    "shadow": QColor(0, 0, 0, 60),
    # 卡片（玻璃卡片：半透明白 + 白描边）
    "card": QColor(255, 255, 255, 26),
    "card_border": QColor(255, 255, 255, 70),
    # 文字（白色 / 浅色系）
    "text": QColor(0xF4, 0xF7, 0xFB),
    "text_sec": QColor(0xE2, 0xEA, 0xF4, 214),
    "text_ter": QColor(0xD5, 0xDF, 0xEB, 190),
    # 主色（玻璃模式下选中/强调色）
    "primary": QColor(0x34, 0xC7, 0x59),         # iOS 绿（开关选中态同源）
    "primary_hover": QColor(0x2F, 0xB3, 0x50),
    "focus_ring": QColor(255, 255, 255, 120),
    # 语义色
    "success": QColor(0x5A, 0xE0, 0x7A),
    "success_dot": QColor(0x34, 0xC7, 0x59),
    "danger": QColor(0xFF, 0x8A, 0x80),
    "danger_dot": QColor(0xFF, 0x59, 0x48),
    # 控件
    "input_bg": QColor(255, 255, 255, 26),
    "input_border": QColor(255, 255, 255, 95),
    "input_focus_bg": QColor(255, 255, 255, 42),
    "surface": QColor(255, 255, 255, 36),
    "surface_hover": QColor(255, 255, 255, 55),
    "track_off": QColor(255, 255, 255, 45),
    "divider": QColor(255, 255, 255, 36),
    "highlight": QColor(255, 255, 255, 26),
}

# ── 玻璃 QSS（与默认主题 QSS 完全隔离，切换时先 setStyleSheet("") 清空）──
GLASS_QSS = f"""
    QLabel {{
        color: {GLASS_THEME['text'].name()};
        background: transparent;
        border: none;
    }}
    QLineEdit {{
        background: rgba({GLASS_THEME['input_bg'].red()}, {GLASS_THEME['input_bg'].green()}, {GLASS_THEME['input_bg'].blue()}, {GLASS_THEME['input_bg'].alpha()});
        border: 1px solid rgba({GLASS_THEME['input_border'].red()}, {GLASS_THEME['input_border'].green()}, {GLASS_THEME['input_border'].blue()}, {GLASS_THEME['input_border'].alpha()});
        border-radius: 8px;
        padding: 5px 12px;
        font-size: 13px;
        color: {GLASS_THEME['text'].name()};
        min-height: 20px;
        selection-background-color: {GLASS_THEME['primary'].name()};
    }}
    QLineEdit:focus {{
        border: 1px solid rgba(255, 255, 255, 150);
        background: rgba(255, 255, 255, {GLASS_THEME['input_focus_bg'].alpha()});
    }}
"""

# ── 按钮玻璃参数（LiquidGlassButton 使用）────────────
BUTTON_HEIGHT = 44                 # 胶囊高度（圆角 = 高度一半）
BUTTON_BASE_ALPHA = 18             # 半透明基底白色 alpha（悬浮时动态加深）
BUTTON_BASE_HOVER_ALPHA = 36       # 悬浮目标 alpha
BUTTON_HIGHLIGHT_ALPHA = 55        # 顶部白色高光渐变峰值
BUTTON_BORDER_ALPHA = 150          # 1.2px 白描边 alpha
BUTTON_BORDER_HOVER_ALPHA = 210
BUTTON_PRESS_SINK_PX = 2           # 按压下沉像素
BUTTON_PRESS_SCALE = 0.98          # 按压缩放
BUTTON_RADIUS_RATIO = 0.5          # 胶囊圆角 = 高度一半

# 玻璃卡片圆角与描边
CARD_RADIUS = 14
CARD_BORDER_PX = 1

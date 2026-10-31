# -*- coding: utf-8 -*-
"""
themes/innovate.py —— 「蓝白创新」主题

定位
----
以「经典」的蓝白为底，但整套按钮换成 Material 风格的高度/动效体系，
参考 GitHub 上 Rev-RoastedDuck/Qt-RoastedDuck-Widgets 的按钮分类
（波纹按钮 / 流光按钮 / 微光按钮 / 开关按钮）与「流光展示卡片」，
**按其视觉特征自行实现**（该仓库是 GPLv3，代码未复制，仅借鉴观感）：

- 主按钮：纵向渐变 + 顶沿内高光 + 投影 + 周期性扫光（微光/流光的观感）
- 次按钮：白面 + 细描边 + 投影，hover 时描边与底色染主色
- 危险按钮：红色渐变，同样带扫光
- 卡片：1.5px 的**流动渐变描边**（锥形渐变绕卡片缓慢旋转，即"流光卡片"）
- 开关：实心轨道 + 白色滑块（iOS 观感）

token 键与 default.py 完全一致，tray_app 里读 CURRENT_THEME[key] 的旧代码无缝适配。
"""
from PySide6.QtGui import QColor

THEME_INNOVATE = "innovate"

# ── 配色：亮版（蓝白）────────────────────────────────
INNOVATE_LIGHT = {
    "bg_top": QColor(0xF7, 0xFA, 0xFF),
    "bg_bot": QColor(0xE7, 0xF0, 0xFE),
    "window_border": QColor(0xD3, 0xE2, 0xF7),
    "shadow": QColor(30, 64, 175, 46),
    # 卡片
    "card": QColor(255, 255, 255, 252),
    "card_border": QColor(0xDC, 0xE8, 0xF8),
    # 文字
    "text": QColor(0x0B, 0x1B, 0x33),
    "text_sec": QColor(0x4A, 0x5C, 0x74),
    "text_ter": QColor(0x7C, 0x8C, 0xA3),
    # 主色：亮蓝 → 青（扫光与流光都用这两个）
    "primary": QColor(0x1D, 0x5B, 0xFF),
    "primary_hover": QColor(0x3D, 0x74, 0xFF),
    "primary_fill": QColor(0x1D, 0x5B, 0xFF),
    "primary2": QColor(0x22, 0xC3, 0xE6),
    "on_primary": QColor(255, 255, 255),
    "focus_ring": QColor(29, 91, 255, 110),
    # 语义色
    "success": QColor(0x0E, 0x9F, 0x6E),
    "success_dot": QColor(0x10, 0xB9, 0x81),
    "danger": QColor(0xE0, 0x24, 0x24),
    "danger_dot": QColor(0xF0, 0x52, 0x52),
    # 控件
    "input_bg": QColor(255, 255, 255, 244),
    "input_border": QColor(0xC8, 0xD9, 0xEE),
    "input_focus_bg": QColor(255, 255, 255, 255),
    "surface": QColor(0xEE, 0xF4, 0xFD),
    "surface_hover": QColor(0xDF, 0xEA, 0xFB),
    "track_off": QColor(0xC8, 0xD9, 0xEE),
    "divider": QColor(0xE3, 0xED, 0xFA),
    "highlight": QColor(255, 255, 255, 130),
    # 流光描边 / 扫光
    "glow": QColor(0x22, 0xC3, 0xE6, 150),
    "glow2": QColor(0x1D, 0x5B, 0xFF, 150),
}

# ── 配色：暗版（深海军蓝 + 青）────────────────────────
INNOVATE_DARK = {
    "bg_top": QColor(0x0E, 0x1B, 0x2E),
    "bg_bot": QColor(0x0A, 0x12, 0x20),
    "window_border": QColor(0x1E, 0x33, 0x50),
    "shadow": QColor(0, 0, 0, 150),
    # 卡片
    "card": QColor(0x13, 0x21, 0x36, 242),
    "card_border": QColor(0x22, 0x38, 0x57),
    # 文字
    "text": QColor(0xEA, 0xF2, 0xFF),
    "text_sec": QColor(0x9B, 0xB0, 0xCC),
    "text_ter": QColor(0x72, 0x89, 0xA8),
    # 主色
    "primary": QColor(0x5B, 0x93, 0xFF),
    "primary_hover": QColor(0x7C, 0xAB, 0xFF),
    "primary_fill": QColor(0x2F, 0x6B, 0xFF),
    "primary2": QColor(0x22, 0xD3, 0xEE),
    "on_primary": QColor(255, 255, 255),
    "focus_ring": QColor(91, 147, 255, 150),
    # 语义色
    "success": QColor(0x34, 0xD3, 0x99),
    "success_dot": QColor(0x34, 0xD3, 0x99),
    "danger": QColor(0xF8, 0x71, 0x71),
    "danger_dot": QColor(0xF8, 0x71, 0x71),
    # 控件
    "input_bg": QColor(0x0A, 0x16, 0x26, 236),
    "input_border": QColor(0x2C, 0x46, 0x6B),
    "input_focus_bg": QColor(0x0A, 0x16, 0x26, 255),
    "surface": QColor(0x1A, 0x2B, 0x43),
    "surface_hover": QColor(0x25, 0x3A, 0x58),
    "track_off": QColor(0x22, 0x39, 0x5A),
    "divider": QColor(0x1B, 0x2E, 0x47),
    "highlight": QColor(255, 255, 255, 22),
    "glow": QColor(0x22, 0xD3, 0xEE, 170),
    "glow2": QColor(0x5B, 0x93, 0xFF, 170),
}

# ── UI 结构参数 ───────────────────────────────────────
UI_INNOVATE = {
    "win_radius": 20,
    "card_radius": 16,
    "card_gap": 10,
    "card_merged": False,
    "btn_height": 40,
    "decor": "flow",        # 卡片流动渐变描边
    "card_pad": (16, 12, 16, 14),
}


def build_innovate_qss(t: dict) -> str:
    """蓝白创新的全局 QSS：输入框更圆、聚焦时染主色"""
    def rgba(c: QColor, alpha: int = None) -> str:
        a = c.alpha() if alpha is None else alpha
        return f"rgba({c.red()}, {c.green()}, {c.blue()}, {a})"

    return f"""
    QLabel {{
        color: {t['text'].name()};
        background: transparent;
        border: none;
    }}
    QLineEdit {{
        background: {rgba(t['input_bg'])};
        border: 1.5px solid {t['input_border'].name()};
        border-radius: 10px;
        padding: 6px 12px;
        font-size: 13px;
        color: {t['text'].name()};
        min-height: 20px;
        selection-background-color: {t['primary'].name()};
        selection-color: {t['on_primary'].name()};
    }}
    QLineEdit:focus {{
        border: 1.5px solid {t['primary'].name()};
        background: {rgba(t['input_focus_bg'])};
    }}
    """

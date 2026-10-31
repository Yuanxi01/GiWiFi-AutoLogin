# -*- coding: utf-8 -*-
"""
themes —— 主题包

每个主题 = 一套配色 token + 一套 UI 结构参数（圆角 / 卡片间距 / 装饰元素），
所以三个主题不只是换颜色，布局质感和装饰也不同。

- themes.default      经典（晴空白 / 深夜蓝，扁平瑞士风）
- themes.aurora       极光（Catppuccin Latte / Mocha + 漂移光晕）
- themes.innovate     蓝白创新（Blue/White + Material 按钮 + 流光描边）
- themes.ThemeManager 主题加载/切换/持久化 + DWM 毛玻璃应用与移除
"""
from themes.theme_manager import ThemeManager
from themes.default import THEME_DEFAULT, UI_DEFAULT
from themes.aurora import THEME_AURORA, UI_AURORA
from themes.innovate import THEME_INNOVATE, UI_INNOVATE

__all__ = [
    "ThemeManager",
    "THEME_DEFAULT", "THEME_AURORA", "THEME_INNOVATE",
    "UI_DEFAULT", "UI_AURORA", "UI_INNOVATE",
]

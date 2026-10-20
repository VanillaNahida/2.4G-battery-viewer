# -*- coding: utf-8 -*-
"""theme.py —— 主题（跟随系统 / 浅色 / 深色）"""

from __future__ import annotations

from qfluentwidgets import Theme, setTheme

from device_battery.core.config import THEME_CHOICES   # 选项只有一份定义

__all__ = ["THEME_CHOICES", "apply_theme"]


def apply_theme(name: str) -> None:
    if name == "light":
        setTheme(Theme.LIGHT)
    elif name == "dark":
        setTheme(Theme.DARK)
    else:
        setTheme(Theme.AUTO)      # 跟随系统深浅色

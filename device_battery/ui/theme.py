# -*- coding: utf-8 -*-
"""theme.py —— 主题（跟随系统 / 浅色 / 深色）"""

from __future__ import annotations

from qfluentwidgets import Theme, setTheme

THEME_CHOICES = [("auto", "跟随系统"), ("light", "浅色"), ("dark", "深色")]


def apply_theme(name: str) -> None:
    if name == "light":
        setTheme(Theme.LIGHT)
    elif name == "dark":
        setTheme(Theme.DARK)
    else:
        setTheme(Theme.AUTO)      # 跟随系统深浅色

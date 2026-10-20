# -*- coding: utf-8 -*-
"""fonts.py —— 字体加载与应用

* 启动时把 `assets/fonts/` 里的字体（默认 MiSans）注册到 Qt；
* 界面字体可自定义（`ui.font`），托盘图标数字字体可单独设置（`tray.font`）；
* 用户还可以「加载字体文件…」，文件路径记在 `fonts.extra_files`，下次启动自动注册。

字体改动后尽量当场生效：改写所有已存在控件的 QFont 家族，同时更新
qfluentwidgets 的默认字体链（之后新建的控件也用它）。
"""

from __future__ import annotations

import os
from typing import Iterable

from PyQt5.QtGui import QFont, QFontDatabase
from PyQt5.QtWidgets import QApplication

from .paths import ASSETS_DIR

FONT_DIR = ASSETS_DIR / "fonts"
FONT_SUFFIXES = (".ttf", ".otf", ".ttc", ".otc")

# 默认字体（找不到 MiSans 时按这个顺序回落）
DEFAULT_FAMILY = "MiSans"
FALLBACK_FAMILIES = ["Microsoft YaHei UI", "Microsoft YaHei",
                     "Segoe UI", "PingFang SC", "Noto Sans CJK SC"]

# 本进程里「默认字体链」曾经用过的家族，改字体时据此判断哪些控件要跟着改
_known_defaults: set[str] = set(FALLBACK_FAMILIES) | {DEFAULT_FAMILY}

_registered: dict[str, str] = {}     # 字体文件绝对路径 -> family
_app_families: list[str] = []       # assets/fonts 里注册进来的 family


# --------------------------------------------------------------------------
# 注册字体文件
# --------------------------------------------------------------------------
def register_font_file(path) -> str:
    """把一个字体文件注册到 Qt，返回它的 family 名；失败返回空串。"""
    target = os.path.abspath(str(path))
    if not target or not os.path.isfile(target):
        return ""
    if target in _registered:
        return _registered[target]
    font_id = QFontDatabase.addApplicationFont(target)
    if font_id < 0:
        return ""
    families = QFontDatabase.applicationFontFamilies(font_id) or []
    family = families[0] if families else ""
    if family:
        _registered[target] = family
    return family


def load_default_fonts() -> list[str]:
    """注册 `assets/fonts/` 下的所有字体，返回 family 列表。"""
    out: list[str] = []
    if not FONT_DIR.is_dir():
        return out
    for item in sorted(FONT_DIR.iterdir()):
        if item.suffix.lower() in FONT_SUFFIXES:
            family = register_font_file(item)
            if family and family not in out:
                out.append(family)
    for family in out:
        if family not in _app_families:
            _app_families.append(family)
        _known_defaults.add(family)
    return out


def app_families() -> list[str]:
    """随程序一起分发的字体 family（MiSans 的 ttf 可能叫 "MiSans Medium"）。"""
    return list(_app_families)


# --------------------------------------------------------------------------
# 可用字体
# --------------------------------------------------------------------------
def available_families() -> list[str]:
    """系统 + 应用内注册的全部字体 family（去重、去掉 @ 开头的竖排别名）。"""
    try:
        families = list(QFontDatabase.families())
    except Exception:
        try:
            families = list(QFontDatabase().families())
        except Exception:
            families = []
    seen: dict[str, None] = {}
    for name in families:
        if not name or name.startswith("@"):
            continue
        seen.setdefault(name, None)
    return sorted(seen, key=lambda s: s.lower())


def family_exists(name: str) -> bool:
    if not name:
        return False
    if name in _registered.values():
        return True
    return name in available_families()


def resolve_family(name: str) -> str:
    """把配置里的字体名解析成实际可用的 family；不可用返回空串（回落默认链）。"""
    name = (name or "").strip()
    if not name:
        return ""
    if family_exists(name):
        return name
    # assets/fonts 里的 MiSans 字体族名可能是 "MiSans Medium" / "MiSans Semibold"，
    # 系统没装 MiSans 时按前缀认领，保证默认字体照样生效。
    lowered = name.lower()
    for family in _app_families:
        if family.lower().startswith(lowered):
            return family
    return ""


def families_for(name: str) -> list[str]:
    """生成 QFont 用的 family 链：选中的字体 + 随包字体 + 系统回退链。"""
    resolved = resolve_family(name)
    chain: list[str] = []
    if resolved:
        chain.append(resolved)
    if DEFAULT_FAMILY not in chain:
        chain.append(DEFAULT_FAMILY)
    chain.extend(_app_families)
    chain.extend(sorted(_known_defaults, key=lambda s: s.lower()))
    out: list[str] = []
    for fam in chain:
        if fam not in out:
            out.append(fam)
    return out


# --------------------------------------------------------------------------
# 应用字体
# --------------------------------------------------------------------------
def _apply_qf_widgets_chain(families: list[str]) -> None:
    """更新 qfluentwidgets 的默认字体链（save=False：不写它的 config/config.json）。"""
    try:
        from qfluentwidgets.common.font import setFontFamilies
        setFontFamilies(families, save=False)
    except Exception:
        pass


def _rebase_widget_fonts(families: list[str]) -> None:
    """把已经创建出来的控件换到新字体（保留原来的字号 / 字重 / 斜体）。"""
    app = QApplication.instance()
    if app is None:
        return
    for widget in app.allWidgets():
        try:
            font = widget.font()
        except Exception:
            continue
        current = list(font.families()) or [font.family()]
        if not set(current) & _known_defaults:
            # 控件自己指定了别的字体，不强行改
            continue
        new_font = QFont(font)
        new_font.setFamilies(families)
        widget.setFont(new_font)
        widget.update()


def apply_ui_font(name: str, *, restyle: bool = True) -> str:
    """应用界面字体，返回实际生效的 family（空串表示回落到默认链）。"""
    resolved = resolve_family(name)
    chain = families_for(resolved)

    _apply_qf_widgets_chain(chain)

    app = QApplication.instance()
    if app is not None:
        font = QFont()
        font.setFamilies(chain)
        app.setFont(font)

    if restyle:
        _rebase_widget_fonts(chain)
    return resolved


def icon_font_family(name: str, fallbacks: Iterable[str] = ()) -> str:
    """自绘图标用的字体 family（找不到就按顺序回退到系统字体）。"""
    resolved = resolve_family(name)
    if resolved:
        return resolved
    for fam in list(fallbacks) + FALLBACK_FAMILIES:
        if family_exists(fam):
            return fam
    return "Segoe UI"


def load_extra_fonts(paths: Iterable[str]) -> list[str]:
    """注册用户自定义字体文件，返回 family 列表。"""
    out: list[str] = []
    for path in paths:
        family = register_font_file(path)
        if family and family not in out:
            out.append(family)
    return out


def font_file_label(path: str) -> str:
    """UI 里显示字体文件用短名字。"""
    return os.path.basename(str(path)) if path else ""

# -*- coding: utf-8 -*-
"""icon_render.py —— 用 QPainter 画托盘图标

三种形态（用户可在设置里选）：
    number  电量数字直接画在图标上（数字尽量占满图标）
    ring    环形进度 + 环内数字；**没走到的部分是透明的**，不画深色底圈
    icon    只画设备图形，不画数字

颜色按电量分级：>=60 绿 / 30-59 黄 / <30 红（与界面一致）。
结果按 (mode, level, kind, font) 缓存，避免重复绘制。
"""

from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

from device_battery.devices import (KIND_GAMEPAD, KIND_HEADSET,
                                    KIND_KEYBOARD, KIND_MOUSE)

from ..ui.paint import contrast_outline, draw_centered_text, fit_font

# 覆盖 Windows 各种 DPI 下托盘实际请求的尺寸（150% 取 24、200% 取 32）
SIZES = (16, 20, 24, 28, 32, 40, 48, 64, 96, 128, 256)

COLOR_GOOD = "#5DDC8A"          # 正常：绿
COLOR_MID = "#F5A623"           # 偏低：橙黄
COLOR_LOW = "#FF5252"           # 很低：红
COLOR_UNKNOWN = "#969BA4"

_default_family = "Segoe UI"

# 颜色阈值（设置里可改）：<= red_at 红，<= orange_at 橙黄，其余绿
_orange_at = 30
_red_at = 20

_cache: dict[tuple, QIcon] = {}


def set_level_thresholds(orange_at: int, red_at: int) -> None:
    """设置「橙 / 红」阈值（低电量变色）。改了颜色，缓存要清掉重画。"""
    global _orange_at, _red_at
    red_at = min(max(1, int(red_at)), 99)
    orange_at = min(max(red_at + 1, int(orange_at)), 100)
    if (orange_at, red_at) == (_orange_at, _red_at):
        return
    _orange_at, _red_at = orange_at, red_at
    clear_cache()


def level_thresholds() -> tuple[int, int]:
    return _orange_at, _red_at


def level_color(level: Optional[int]) -> str:
    if level is None:
        return COLOR_UNKNOWN
    if level <= _red_at:
        return COLOR_LOW
    if level <= _orange_at:
        return COLOR_MID
    return COLOR_GOOD


def level_text(level: Optional[int]) -> str:
    if level is None:
        return "--"
    return str(level)


def set_font_family(family: str) -> None:
    """设置图标里数字用的字体（托盘字体可单独配置）。"""
    global _default_family
    family = (family or "").strip()
    if not family or family == _default_family:
        return
    _default_family = family
    clear_cache()


def font_family() -> str:
    return _default_family


def _stroke(size: int) -> float:
    return max(1.0, size / 15.0)


def _paint_number(p: QPainter, size: int, level: Optional[int]) -> None:
    """数字直接铺满图标（比按字数估算的做法大一大截）。"""
    color = QColor(level_color(level))
    rect = QRectF(size * 0.04, size * 0.02, size * 0.92, size * 0.96)
    text = level_text(level)
    font = fit_font(_default_family, text, rect.width(), rect.height() * 0.94)
    outline = contrast_outline(color) if level is not None else None
    draw_centered_text(p, rect, text, font, color, outline, _stroke(size))


def _paint_ring(p: QPainter, size: int, level: Optional[int],
                show_text: bool = True) -> None:
    """环形进度：只画走过的弧，缺口保持透明；show_text=False 时只画环。"""
    ring_w = max(1.5, size * 0.095)
    margin = ring_w / 2.0 + max(0.5, size * 0.035)
    box = QRectF(margin, margin, size - 2 * margin, size - 2 * margin)

    color = QColor(level_color(level))
    if level is None:
        # 电量未知：一圈半透明灰环（不是深色实心圈）
        unknown = QColor(color)
        unknown.setAlpha(150)
        p.setPen(QPen(unknown, ring_w))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(box)
    else:
        span = int(-360 * 16 * max(0, min(100, level)) / 100.0)
        p.setPen(QPen(color, ring_w, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        p.drawArc(box, 90 * 16, span)

    if not show_text:
        return

    inner = box.adjusted(ring_w, ring_w, -ring_w, -ring_w)
    text = level_text(level)
    # 三位数（100）按宽度收；一两位数字可以更高一点，但左右留出与环的间隙
    height_factor = 0.86 if len(text) <= 2 else 0.80
    font = fit_font(_default_family, text,
                    inner.width() * 0.82, inner.height() * height_factor)
    # 环里的数字不描边：缺口是透明的，描边反而会糊住环
    draw_centered_text(p, inner, text, font, color)


def _paint_icon(p: QPainter, size: int, kind: str) -> None:
    """画设备图形（鼠标 / 键盘 / 耳机 / 手柄 / 其它）。"""
    pen = QPen(QColor("#D8DCE3"), max(1.2, size / 14.0))
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(QColor(40, 44, 50, 235))

    m = size * 0.16
    w = size - 2 * m
    if kind == KIND_MOUSE:
        body = QRectF(m + w * 0.18, m, w * 0.64, w)
        p.drawRoundedRect(body, w * 0.32, w * 0.32)
        p.drawLine(int(size / 2), int(m + w * 0.08),
                   int(size / 2), int(m + w * 0.34))
    elif kind == KIND_KEYBOARD:
        body = QRectF(m, m + w * 0.22, w, w * 0.56)
        p.drawRoundedRect(body, w * 0.12, w * 0.12)
        for row in range(2):
            for col in range(4):
                cx = body.left() + w * (0.16 + col * 0.22)
                cy = body.top() + w * (0.16 + row * 0.24)
                p.drawRect(QRectF(cx, cy, w * 0.1, w * 0.1))
    elif kind == KIND_HEADSET:
        band = QRectF(m + w * 0.06, m, w * 0.88, w * 0.9)
        p.drawArc(band, 0, 180 * 16)
        pad = w * 0.24
        p.drawRoundedRect(QRectF(m + w * 0.02, m + w * 0.42, pad, pad), 3, 3)
        p.drawRoundedRect(QRectF(m + w - pad - w * 0.02, m + w * 0.42, pad, pad),
                          3, 3)
    elif kind == KIND_GAMEPAD:
        body = QRectF(m, m + w * 0.24, w, w * 0.5)
        p.drawRoundedRect(body, w * 0.26, w * 0.26)
        r = w * 0.09
        p.drawEllipse(QRectF(m + w * 0.22 - r, m + w * 0.49 - r, 2 * r, 2 * r))
        p.drawEllipse(QRectF(m + w * 0.72 - r, m + w * 0.49 - r, 2 * r, 2 * r))
    else:
        p.drawEllipse(QRectF(m, m, w, w))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#D8DCE3"))
        p.drawEllipse(QRectF(size * 0.42, size * 0.42, size * 0.16, size * 0.16))


def render(mode: str, level: Optional[int], kind: str = "") -> QIcon:
    """按形态生成托盘图标（带缓存）。"""
    key = (mode, level, kind, _default_family)
    cached = _cache.get(key)
    if cached is not None:
        return cached

    icon = QIcon()
    for size in SIZES:
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        try:
            if mode == "ring":
                _paint_ring(p, size, level)
            elif mode == "ring_only":
                _paint_ring(p, size, level, show_text=False)
            elif mode == "icon":
                _paint_icon(p, size, kind)
            else:
                _paint_number(p, size, level)
        finally:
            p.end()
        icon.addPixmap(pix)

    _cache[key] = icon
    return icon


def clear_cache() -> None:
    _cache.clear()

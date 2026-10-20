# -*- coding: utf-8 -*-
"""icon_render.py —— 用 QPainter 画托盘图标

三种形态（用户可在设置里选）：
    number  电量数字直接画在图标上
    ring    圆环进度 + 环内数字
    icon    只画设备图形，不画数字

颜色按电量分级：>=60 绿 / 30-59 黄 / <30 红（与界面一致）。
结果按 (mode, level, kind) 缓存，避免重复绘制。
"""

from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap

from device_battery.devices import (KIND_GAMEPAD, KIND_HEADSET,
                                    KIND_KEYBOARD, KIND_MOUSE)

SIZES = (16, 24, 32, 48, 64, 128)

COLOR_GOOD = "#5DDC8A"
COLOR_MID = "#F5C451"
COLOR_LOW = "#FF6B6B"
COLOR_UNKNOWN = "#969BA4"
OUTLINE = QColor(16, 17, 19, 200)

_cache: dict[tuple, QIcon] = {}


def level_color(level: Optional[int]) -> str:
    if level is None:
        return COLOR_UNKNOWN
    if level >= 60:
        return COLOR_GOOD
    if level >= 30:
        return COLOR_MID
    return COLOR_LOW


def level_text(level: Optional[int]) -> str:
    if level is None:
        return "--"
    return str(level)


def _draw_text(p: QPainter, size: int, text: str, color: QColor,
               rect: QRectF = None) -> None:
    """画描边文字（保证在浅色/深色任务栏上都看得清）。"""
    area = rect or QRectF(0, 0, size, size)
    font = QFont("Segoe UI")
    font.setBold(True)
    px = int(min(area.width() / max(len(text), 1) * 0.95, area.height() * 0.92))
    font.setPixelSize(max(6, px))
    p.setFont(font)

    path = None
    from PyQt5.QtGui import QPainterPath
    path = QPainterPath()
    path.addText(area.center().x() - px * len(text) * 0.3,
                 area.center().y() + px * 0.35, font, text)

    p.setPen(QPen(OUTLINE, max(1.0, size / 16.0)))
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    p.drawPath(path)


def _paint_number(p: QPainter, size: int, level: Optional[int]) -> None:
    _draw_text(p, size, level_text(level), QColor(level_color(level)))


def _paint_ring(p: QPainter, size: int, level: Optional[int]) -> None:
    color = QColor(level_color(level))
    ring_w = max(2.0, size / 8.0)
    margin = ring_w / 2.0 + max(1.0, size / 32.0)
    box = QRectF(margin, margin, size - 2 * margin, size - 2 * margin)

    p.setPen(QPen(OUTLINE, ring_w + 1.0))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(box)
    p.setPen(QPen(QColor(60, 64, 70, 220), ring_w))
    p.drawEllipse(box)

    if level is not None:
        p.setPen(QPen(color, ring_w, Qt.SolidLine, Qt.RoundCap))
        # Qt 角度：1/16 度，从 3 点方向逆时针；这里从 12 点顺时针画进度
        span = int(-360 * 16 * max(0, min(100, level)) / 100.0)
        p.drawArc(box, 90 * 16, span)

    inner = QRectF(margin + ring_w, margin + ring_w,
                   size - 2 * (margin + ring_w), size - 2 * (margin + ring_w))
    _draw_text(p, size, level_text(level), color, inner)


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
    key = (mode, level, kind)
    cached = _cache.get(key)
    if cached is not None:
        return cached

    icon = QIcon()
    for size in SIZES:
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing, True)
        try:
            if mode == "ring":
                _paint_ring(p, size, level)
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

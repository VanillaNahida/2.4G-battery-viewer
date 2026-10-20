# -*- coding: utf-8 -*-
"""paint.py —— 自绘用的小工具（文字适配、居中绘制）

托盘图标（16~256 px）和界面里的环形电量都要求「数字尽量大且不出框」，
所以字体大小按 QFontMetricsF 实测宽度 / 上伸高度算，而不是按字数估算。
"""

from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import (QColor, QFont, QFontMetricsF, QPainter, QPainterPath,
                         QPen)


def fit_font(family: str, text: str, max_w: float, max_h: float,
             *, bold: bool = True, min_px: int = 5) -> QFont:
    """在 max_w x max_h 的框内，把 text 撑到尽可能大的字号。"""
    text = text or "0"
    font = QFont(family)
    font.setBold(bold)
    font.setPixelSize(100)          # 先按 100 px 量，再按比例缩放
    metrics = QFontMetricsF(font)
    width = max(1.0, metrics.horizontalAdvance(text))
    cap = max(1.0, metrics.ascent())
    scale = min(max_w / width, max_h / cap)
    font.setPixelSize(max(int(min_px), int(round(100.0 * scale))))
    return font


def draw_centered_text(painter: QPainter, rect: QRectF, text: str,
                       font: QFont, color: QColor,
                       outline: Optional[QColor] = None,
                       outline_width: float = 0.0) -> None:
    """在 rect 里居中画一行字（可带描边，保证在任意背景上都看得清）。"""
    if not text:
        return
    metrics = QFontMetricsF(font)
    width = metrics.horizontalAdvance(text)
    x = rect.center().x() - width / 2.0
    y = rect.center().y() + (metrics.ascent() - metrics.descent()) / 2.0

    path = QPainterPath()
    path.addText(x, y, font, text)

    if outline is not None and outline_width > 0:
        pen = QPen(outline, outline_width)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

    painter.setPen(Qt.NoPen)
    painter.setBrush(color)
    painter.drawPath(path)


def contrast_outline(color: QColor) -> QColor:
    """给亮色文字配一层淡描边：亮色配深描边，暗色配浅描边。"""
    luminance = (0.299 * color.red() + 0.587 * color.green()
                 + 0.114 * color.blue())
    if luminance >= 128:
        return QColor(0, 0, 0, 110)
    return QColor(255, 255, 255, 120)

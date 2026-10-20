# -*- coding: utf-8 -*-
"""widgets.py —— 界面里用到的自绘小控件

* BatteryRing：环形电量条，环内直接写百分比（主界面可切成这种显示方式）
* ElidedLabel：长度超出可用宽度时自动省略的标签（防止内容把窗口撑爆）
"""

from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import QRectF, QSize, Qt
from PyQt5.QtGui import QColor, QPainter, QPen
from PyQt5.QtWidgets import QLabel, QSizePolicy, QWidget
from qfluentwidgets import qconfig
from qfluentwidgets.common.font import setFont as qset_font
from qfluentwidgets.common.config import isDarkTheme

from ..tray.icon_render import level_color
from .paint import contrast_outline, draw_centered_text, fit_font


def _theme_disconnector(connection):
    """安全断开主题信号（退出时 QConfig 可能已经先被销毁）。"""
    def handler() -> None:
        try:
            qconfig.themeChanged.disconnect(connection)
        except Exception:
            pass
    return handler


class ElidedLabel(QLabel):
    """单行标签，宽度不够时用省略号收尾（不会撑大窗口）。

    直接继承 QLabel 而不是 FluentLabelBase：后者的字符分发式 __init__
    遇到子类会自递归。字体与颜色在这里按 Fluent 的规范补上，并跟随主题。
    """

    def __init__(self, text: str = "", parent: QWidget = None,
                 mode: Qt.TextElideMode = Qt.ElideRight):
        super().__init__(parent)
        self._full_text = ""
        self._mode = mode
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        try:
            qset_font(self, 12)
        except Exception:
            pass
        self._light_color = QColor(0, 0, 0, 158)
        self._dark_color = QColor(255, 255, 255, 168)
        self._apply_color()
        try:
            connection = qconfig.themeChanged.connect(self._apply_color)
            self.destroyed.connect(
                _theme_disconnector(connection))
        except Exception:
            pass
        self.setText(text or "")

    # ---- 文本 ---------------------------------------------------------
    def setText(self, text: str) -> None:      # noqa: N802 (Qt 命名)
        self._full_text = text or ""
        self.setToolTip(self._full_text)
        self._refresh()

    def fullText(self) -> str:
        return self._full_text

    def resizeEvent(self, event) -> None:      # noqa: N802
        super().resizeEvent(event)
        self._refresh()

    def changeEvent(self, event) -> None:      # noqa: N802
        super().changeEvent(event)
        self._refresh()

    def _refresh(self) -> None:
        metrics = self.fontMetrics()
        available = max(0, self.width() - 2)
        super().setText(metrics.elidedText(self._full_text, self._mode,
                                           available))

    def _apply_color(self) -> None:
        color = self._dark_color if isDarkTheme() else self._light_color
        self.setStyleSheet(
            f"QLabel{{color:{color.name(QColor.HexArgb)}}}")


class BatteryRing(QWidget):
    """环形电量条：外圈进度 + 环内百分比数字。"""

    def __init__(self, parent: QWidget = None, diameter: int = 96,
                 thickness: int = 9):
        super().__init__(parent)
        self._level: Optional[int] = None
        self._diameter = diameter
        self._thickness = thickness
        self._font_family = "Segoe UI"
        self.setFixedSize(diameter, diameter)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        try:
            connection = qconfig.themeChanged.connect(self.update)
            self.destroyed.connect(
                _theme_disconnector(connection))
        except Exception:
            pass

    # ---- 属性 ---------------------------------------------------------
    def set_level(self, level: Optional[int]) -> None:
        # 数值没变也要重画：颜色阈值可能在设置里被改过
        self._level = level
        self.update()

    def set_font_family(self, family: str) -> None:
        if family and family != self._font_family:
            self._font_family = family
            self.update()

    def sizeHint(self) -> QSize:               # noqa: N802
        return QSize(self._diameter, self._diameter)

    # ---- 绘制 ---------------------------------------------------------
    def paintEvent(self, event) -> None:        # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        try:
            self._paint(painter)
        finally:
            painter.end()

    def _paint(self, painter: QPainter) -> None:
        outer = min(self.width(), self.height())
        thickness = max(4.0, self._thickness * outer / float(self._diameter))
        margin = thickness / 2.0 + outer * 0.03
        box = QRectF(margin, margin, outer - 2 * margin, outer - 2 * margin)

        track = (QColor(255, 255, 255, 40) if isDarkTheme()
                 else QColor(0, 0, 0, 26))
        painter.setPen(QPen(track, thickness))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(box)

        color = QColor(level_color(self._level))
        if self._level is not None:
            span = int(-360 * 16 * max(0, min(100, self._level)) / 100.0)
            painter.setPen(QPen(color, thickness, Qt.SolidLine, Qt.RoundCap))
            painter.drawArc(box, 90 * 16, span)

        text = "--" if self._level is None else str(self._level)
        inner = box.adjusted(thickness, thickness, -thickness, -thickness)
        font = fit_font(self._font_family, text,
                        inner.width() * 0.98, inner.height() * 0.94)
        draw_centered_text(painter, inner, text, font, color,
                           contrast_outline(color), max(1.0, outer / 46.0))


__all__ = ["BatteryRing", "ElidedLabel"]

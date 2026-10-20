# -*- coding: utf-8 -*-
"""cards.py —— 设备卡片

只保留必要信息：设备图标、设备名、状态（充电中 / 放电中 / 未连接）、电量。

电量有两种显示方式（设置里可切换）：
    ring  右侧环形电量，百分比写在环内
    bar   右侧大号百分比 + 卡片底部通栏进度条

布局全部使用「可压缩」的控件（省略号标签 / 弹性宽度），
窗口拉窄时不会把内容顶出边界。
"""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget)
from qfluentwidgets import (CaptionLabel, CardWidget, ProgressBar,
                            StrongBodyLabel, SubtitleLabel)

from device_battery.devices import Reading

from ..tray import icon_render
from .widgets import BatteryRing, ElidedLabel


def _status_text(r: Reading) -> str:
    """卡片上那一行状态：优先充电状态，其次连接方式（蓝牙 / 2.4G）。"""
    if not r.online:
        return "未连接"
    if r.level is None:
        return r.error or "读不到电量"
    if r.charging is True:
        return "充电中"
    if r.charging is False:
        return "放电中"
    info = r.info
    if info is not None and info.transport:
        # 单独一个 "2.4G" 看不出是什么意思；带上字段名，
        # 手柄这种分不清有线/无线的设备会显示 "连接方式：2.4G/有线连接"。
        return f"连接方式：{info.transport}"
    return ""


class DeviceCard(CardWidget):
    """一张设备卡片。"""

    RING_SIZE = 76

    def __init__(self, parent: QWidget = None, style: str = "ring"):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self._style = style

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 12)
        root.setSpacing(10)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(14)
        root.addLayout(top)

        self._icon = StrongBodyLabel(self)
        self._icon.setFixedSize(40, 40)
        self._icon.setAlignment(Qt.AlignCenter)
        self._icon.setStyleSheet("background: transparent;")
        top.addWidget(self._icon, 0, Qt.AlignVCenter)

        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(2)
        top.addLayout(text, 1)

        self._name = SubtitleLabel("设备", self)
        self._name.setWordWrap(True)
        self._name.setMinimumWidth(0)
        text.addWidget(self._name)

        self._status = ElidedLabel("", self)
        self._status.setMinimumWidth(0)
        text.addWidget(self._status)

        top.addStretch(0)

        # 右侧电量：环形 / 百分比 + 底部进度条
        self._ring = BatteryRing(self, diameter=self.RING_SIZE, thickness=8)
        top.addWidget(self._ring, 0, Qt.AlignVCenter)

        self._level = StrongBodyLabel("--", self)
        self._level.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._level.setMinimumWidth(76)
        font = self._level.font()
        font.setPixelSize(26)
        font.setBold(True)
        self._level.setFont(font)
        top.addWidget(self._level, 0, Qt.AlignVCenter)

        self._bar = ProgressBar(self)
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setFixedHeight(8)
        root.addWidget(self._bar)

        self.set_style(style)

    # ---- 形态 ---------------------------------------------------------
    def set_style(self, style: str) -> None:
        self._style = "bar" if style == "bar" else "ring"
        is_ring = self._style == "ring"
        self._ring.setVisible(is_ring)
        self._level.setVisible(not is_ring)
        self._bar.setVisible(not is_ring)
        # 固定高度：卡片长短一致，列表看起来才整齐
        self.setFixedHeight(104 if is_ring else 92)
        self.updateGeometry()

    def set_font_family(self, family: str) -> None:
        self._ring.set_font_family(family)

    # ---- 数据刷新 -----------------------------------------------------
    def update_reading(self, r: Reading) -> None:
        info = r.info
        name = info.name if info else r.key
        kind = info.kind if info else ""
        self._name.setText(name)

        self._status.setText(_status_text(r))

        self._icon.setPixmap(
            icon_render.render("icon", None, kind).pixmap(36, 36))

        if r.online and r.level is not None:
            color = icon_render.level_color(r.level)
            self._level.setText(f"{r.level}%")
            self._level.setStyleSheet(f"color: {color};")
            self._bar.setValue(r.level)
            # 进度条跟着电量变色（绿 / 黄 / 红），和托盘、环形保持一套配色
            self._bar.setCustomBarColor(color, color)
            self._ring.set_level(r.level)
        else:
            self._level.setText("--")
            self._level.setStyleSheet("")
            self._bar.setValue(0)
            self._ring.set_level(None)


class PlaceholderCard(CardWidget):
    """设备未检测到时的占位卡。"""

    def __init__(self, source_name: str, parent: QWidget = None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 12, 18, 12)
        lay.setSpacing(2)

        title = SubtitleLabel(source_name, self)
        title.setWordWrap(True)
        title.setMinimumWidth(0)
        lay.addWidget(title)

        detail = CaptionLabel("未检测到该设备", self)
        detail.setWordWrap(True)
        detail.setMinimumWidth(0)
        lay.addWidget(detail)


__all__ = ["DeviceCard", "PlaceholderCard"]

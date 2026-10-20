# -*- coding: utf-8 -*-
"""cards.py —— 设备卡片

展示设备名、来源与型号、VID:PID 或蓝牙地址、电量（大号数字 + 进度条）、
状态、固件、更新时间。
"""

from __future__ import annotations

import time
from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (BodyLabel, CaptionLabel, CardWidget, ProgressBar,
                            StrongBodyLabel, SubtitleLabel)

from device_battery.devices import Reading, charging_text

from ..tray import icon_render


def _params_text(r: Reading) -> str:
    info = r.info
    if info is None:
        return ""
    bits = []
    vid_pid = info.params.get("vid_pid")
    if vid_pid:
        bits.append(vid_pid)
    addr = info.params.get("address")
    if addr:
        bits.append(f"蓝牙地址 {addr}")
    if info.transport:
        bits.append(info.transport)
    fw = info.params.get("firmware")
    if fw:
        bits.append(f"固件 {fw}")
    proto = info.params.get("protocol")
    if proto:
        bits.append(proto)
    return "  ·  ".join(bits)


class DeviceCard(CardWidget):
    """一张设备卡片。"""

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.setFixedHeight(170)

        root = QHBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(16)

        self._icon = BodyLabel(self)
        self._icon.setFixedSize(40, 40)
        self._icon.setAlignment(Qt.AlignCenter)
        root.addWidget(self._icon, 0, Qt.AlignTop)

        right = QVBoxLayout()
        right.setSpacing(2)
        root.addLayout(right, 1)

        self._name = SubtitleLabel("设备", self)
        right.addWidget(self._name)

        self._sub = CaptionLabel("", self)
        right.addWidget(self._sub)

        row = QHBoxLayout()
        row.setSpacing(12)
        self._level = StrongBodyLabel("--", self)
        font = QFont()
        font.setPointSize(26)
        font.setBold(True)
        self._level.setFont(font)
        row.addWidget(self._level)
        self._bar = ProgressBar(self)
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setFixedHeight(8)
        row.addWidget(self._bar, 1)
        right.addLayout(row)

        self._status = CaptionLabel("", self)
        right.addWidget(self._status)

        self._params = CaptionLabel("", self)
        self._params.setWordWrap(True)
        right.addWidget(self._params)

        self._detail = CaptionLabel("", self)
        self._detail.setWordWrap(True)
        right.addWidget(self._detail)

    def update_reading(self, r: Reading) -> None:
        info = r.info
        name = info.name if info else r.key
        kind = info.kind if info else ""
        self._name.setText(name)

        sub = []
        if info is not None:
            sub.append(info.transport or "")
            if info.source:
                sub.append(f"来源 {info.source}")
        self._sub.setText("  ·  ".join(x for x in sub if x))

        self._icon.setPixmap(
            icon_render.render("icon", None, kind).pixmap(36, 36))

        if r.online and r.level is not None:
            color = icon_render.level_color(r.level)
            self._level.setText(f"{r.level}%")
            self._level.setStyleSheet(f"color: {color};")
            self._bar.setValue(r.level)
        else:
            self._level.setText("--")
            self._level.setStyleSheet("")
            self._bar.setValue(0)

        if not r.online:
            status = f"未连接 / {r.error or '读取失败'}"
        elif r.level is None:
            status = r.error or "读不到电量"
        else:
            status = charging_text(r.charging)
        self._status.setText(status)

        self._params.setText(_params_text(r))

        bits = []
        if r.detail:
            bits.append(r.detail)
        if r.online:
            bits.append("更新于 " + time.strftime("%H:%M:%S",
                                             time.localtime(r.updated_at)))
        self._detail.setText("  ·  ".join(bits))


class PlaceholderCard(CardWidget):
    """设备未检测到时的占位卡。"""

    def __init__(self, source_name: str, parent: QWidget = None):
        super().__init__(parent)
        self.setFixedHeight(80)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 12, 18, 12)
        lay.addWidget(SubtitleLabel(source_name, self))
        lay.addWidget(CaptionLabel("未检测到该设备", self))


__all__ = ["DeviceCard", "PlaceholderCard"]

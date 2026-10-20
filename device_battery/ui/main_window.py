# -*- coding: utf-8 -*-
"""main_window.py —— FluentWindow 主窗口（设备页 / 设置页 / 调试页）"""

from __future__ import annotations

from typing import Callable, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QVBoxLayout, QWidget
from qfluentwidgets import (CaptionLabel, FluentIcon, FluentWindow, ScrollArea,
                            SubtitleLabel)

from device_battery.devices import Reading, providers

from .cards import DeviceCard, PlaceholderCard
from .debug_page import DebugPage
from .settings_page import SettingsPage
from .theme import apply_theme

# 设备来源的显示名（未检测到时用占位卡列出来）
SOURCE_LABEL = {
    "inphic": "英菲克 IN9 鼠标",
    "atk": "ATK / VXE 无线鼠标",
    "darkrim": "DARKRIM 耳机",
    "bluetooth": "蓝牙设备",
}


class DevicePage(QWidget):
    """设备卡片列表（随扫描结果动态增删）。"""

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.setObjectName("devicePage")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = ScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent}")
        outer.addWidget(scroll)

        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(24, 20, 24, 20)
        self._layout.setSpacing(12)
        scroll.setWidget(self._container)

        self._cards: dict[str, DeviceCard] = {}
        self._placeholders: dict[str, PlaceholderCard] = {}
        self._empty = SubtitleLabel("正在读取设备…", self._container)
        self._layout.addWidget(self._empty)
        self._footer = CaptionLabel("", self._container)
        self._layout.addWidget(self._footer)
        self._layout.addStretch(1)

    def update_readings(self, readings: list[Reading],
                        show_absent: bool) -> None:
        present = {r.key: r for r in readings}
        present_sources = {r.info.source for r in readings if r.info}

        # 删除已消失的设备卡
        for key in list(self._cards):
            if key not in present:
                card = self._cards.pop(key)
                self._layout.removeWidget(card)
                card.deleteLater()

        # 新增 / 更新设备卡（插到 stretch 之前）
        insert_at = max(0, self._layout.count() - 2)
        for idx, (key, r) in enumerate(present.items()):
            card = self._cards.get(key)
            if card is None:
                card = DeviceCard(self._container)
                self._cards[key] = card
                self._layout.insertWidget(min(insert_at + idx,
                                              self._layout.count() - 2), card)
            card.update_reading(r)

        # 占位卡（可选）
        for key in list(self._placeholders):
            if not show_absent or key in present_sources:
                card = self._placeholders.pop(key)
                self._layout.removeWidget(card)
                card.deleteLater()
        if show_absent:
            for provider in providers():
                src = provider.source
                if src in present_sources or src in self._placeholders:
                    continue
                card = PlaceholderCard(SOURCE_LABEL.get(src, src),
                                       self._container)
                self._placeholders[src] = card
                self._layout.insertWidget(self._layout.count() - 2, card)

        self._empty.setVisible(not self._cards and not self._placeholders)
        ok = sum(1 for r in readings if r.online and r.level is not None)
        self._footer.setText(
            f"共 {len(readings)} 个设备，{ok} 个读到电量"
            if readings else "未检测到任何设备")


class MainWindow(FluentWindow):
    """主窗口：设备页 + 设置页 + 调试页。"""

    def __init__(self, cfg: dict,
                 hooks: dict,
                 test_alert: Optional[Callable[[str, str], None]] = None,
                 preview_sound: Optional[Callable[[str, int], None]] = None,
                 log: Optional[Callable[[str], None]] = None,
                 parent: QWidget = None):
        """hooks: {"config_changed": f(cfg), "refresh": f()}"""
        super().__init__(parent)
        self._cfg = cfg
        self._log = log
        self._last_readings: list[Reading] = []

        self.device_page = DevicePage(self)
        self.settings_page = SettingsPage(
            cfg, hooks,
            test_alert=test_alert, preview_sound=preview_sound, log=log,
            parent=self)
        self.debug_page = DebugPage(self)

        self.addSubInterface(self.device_page, FluentIcon.HOME, "设备")
        self.addSubInterface(self.settings_page, FluentIcon.SETTING, "设置")
        self.addSubInterface(self.debug_page, FluentIcon.DEVELOPER_TOOLS, "调试")

        self.setWindowTitle("设备电量")
        self.resize(980, 660)

    # ---- 数据刷新 -----------------------------------------------------
    def update_readings(self, readings: list[Reading]) -> None:
        self._last_readings = readings
        self.device_page.update_readings(
            readings, bool(self._cfg.get("show_absent_devices", False)))
        self.settings_page.update_devices(readings)

    # ---- 配置 ---------------------------------------------------------
    def apply_config(self, cfg: dict) -> None:
        self._cfg = cfg
        apply_theme(cfg.get("theme", "auto"))
        self.update_readings(self._last_readings)

    def show_settings(self) -> None:
        self.switchTo(self.settings_page)

    # ---- 窗口行为 -----------------------------------------------------
    def closeEvent(self, event) -> None:
        """默认关闭 = 隐藏到托盘；勾了"关闭窗口时退出"才真正退出。"""
        if self._cfg.get("quit_on_close", False):
            event.accept()
            QApplication.instance().quit()
        else:
            event.ignore()
            self.hide()
            if self._log:
                self._log("窗口已隐藏到托盘（可在托盘菜单里退出）")

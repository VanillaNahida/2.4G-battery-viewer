# -*- coding: utf-8 -*-
"""main_window.py —— FluentWindow 主窗口（设备页 / 设置页 / 调试页）"""

from __future__ import annotations

from typing import Callable, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QApplication, QHBoxLayout, QVBoxLayout, QWidget)
from qfluentwidgets import (CaptionLabel, FluentIcon, FluentWindow, PushButton,
                            ScrollArea, SubtitleLabel, Theme,
                            TransparentToolButton, isDarkTheme, qconfig, setTheme)

from device_battery.core import config as cfgmod
from device_battery.core import fonts as fontmod
from device_battery.core.dpi import initial_window_size
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


def is_present(r: Reading) -> bool:
    """设备「真的连着」：在线且读到了电量。"""
    return bool(r.online and r.level is not None)


class DevicePage(QWidget):
    """设备卡片列表（随扫描结果动态增删）+ 顶部「立即刷新」。"""

    def __init__(self, parent: QWidget = None, style: str = "ring",
                 font_family: str = "",
                 on_refresh: Optional[Callable[[], None]] = None):
        super().__init__(parent)
        self.setObjectName("devicePage")
        self._style = style
        self._font_family = font_family
        self._on_refresh = on_refresh

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QWidget(self)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(24, 16, 24, 6)
        header_layout.setSpacing(12)
        self._summary = SubtitleLabel("设备", header)
        self._summary.setMinimumWidth(0)
        header_layout.addWidget(self._summary, 1)
        self._refresh_btn = PushButton("立即刷新", header, FluentIcon.SYNC)
        self._refresh_btn.setToolTip("马上重新读取一次所有设备")
        self._refresh_btn.clicked.connect(self._refresh_clicked)
        header_layout.addWidget(self._refresh_btn, 0, Qt.AlignRight)
        outer.addWidget(header)

        scroll = ScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent}")
        # 视口也要透明，否则深色主题下会透出浅色底
        scroll.viewport().setStyleSheet("background: transparent;")
        outer.addWidget(scroll, 1)

        self._container = QWidget()
        self._container.setMinimumWidth(0)
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(24, 6, 24, 20)
        self._layout.setSpacing(10)
        scroll.setWidget(self._container)

        self._cards: dict[str, DeviceCard] = {}
        self._placeholders: dict[str, PlaceholderCard] = {}
        self._empty = CaptionLabel("正在读取设备…", self._container)
        self._empty.setWordWrap(True)
        self._layout.addWidget(self._empty)
        self._footer = CaptionLabel("", self._container)
        self._footer.setWordWrap(True)
        self._footer.setMinimumWidth(0)
        self._layout.addWidget(self._footer)
        self._layout.addStretch(1)

    # ---- 配置变化 -----------------------------------------------------
    def set_battery_style(self, style: str) -> None:
        self._style = "bar" if style == "bar" else "ring"
        for card in self._cards.values():
            card.set_style(self._style)

    def set_font_family(self, family: str) -> None:
        self._font_family = family or ""
        for card in self._cards.values():
            card.set_font_family(self._font_family)

    # ---- 刷新 ---------------------------------------------------------
    def _refresh_clicked(self) -> None:
        self._refresh_btn.setEnabled(False)
        self._refresh_btn.setText("刷新中…")
        if self._on_refresh:
            self._on_refresh()

    def _reset_refresh_button(self) -> None:
        self._refresh_btn.setEnabled(True)
        self._refresh_btn.setText("立即刷新")

    # ---- 数据刷新 -----------------------------------------------------
    def update_readings(self, readings: list[Reading], show_absent: bool,
                        hidden_count: int = 0) -> None:
        self._reset_refresh_button()
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
                card = DeviceCard(self._container, style=self._style)
                card.set_font_family(self._font_family)
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
        total = len(readings) + hidden_count
        if total:
            text = f"共 {total} 个设备，{ok} 个读到电量"
            if hidden_count:
                text += f"；{hidden_count} 个未连接（已隐藏）"
        else:
            text = "未检测到任何设备"
        self._footer.setText(text)


class MainWindow(FluentWindow):
    """主窗口：设备页 + 设置页 + 调试页。"""

    def __init__(self, cfg: dict,
                 hooks: dict,
                 test_alert: Optional[Callable[[str, str], None]] = None,
                 preview_sound: Optional[Callable[[str, int], None]] = None,
                 test_notify: Optional[Callable[[str, str], None]] = None,
                 log: Optional[Callable[[str], None]] = None,
                 parent: QWidget = None):
        """hooks: {"config_changed": f(cfg), "refresh": f()}"""
        super().__init__(parent)
        self._cfg = cfg
        self._hooks = hooks
        self._log = log
        self._last_readings: list[Reading] = []

        style = cfgmod.battery_style(cfg)
        ring_font = fontmod.icon_font_family(cfgmod.tray_font(cfg))
        self.device_page = DevicePage(
            self, style=style, font_family=ring_font,
            on_refresh=lambda: hooks.get("refresh") and hooks["refresh"]())
        self.settings_page = SettingsPage(
            cfg, hooks,
            test_alert=test_alert, preview_sound=preview_sound,
            test_notify=test_notify, log=log, parent=self)
        self.debug_page = DebugPage(self)

        self.addSubInterface(self.device_page, FluentIcon.HOME, "设备")
        self.addSubInterface(self.settings_page, FluentIcon.SETTING, "设置")
        self.addSubInterface(self.debug_page, FluentIcon.DEVELOPER_TOOLS, "调试")

        self.setWindowTitle("设备电量")
        self._add_theme_button()

        width, height = initial_window_size()
        self.resize(width, height)
        self.setMinimumSize(760, 520)
        self._sync_theme_button()
        try:
            qconfig.themeChanged.connect(self._sync_theme_button)
        except Exception:
            pass

    # ---- 标题栏：深色 / 浅色切换 --------------------------------------
    def _add_theme_button(self) -> None:
        self._theme_btn = TransparentToolButton(FluentIcon.CONSTRACT,
                                                self.titleBar)
        self._theme_btn.setFixedSize(30, 30)
        self._theme_btn.setToolTip("切换深色 / 浅色")
        self._theme_btn.clicked.connect(self.toggle_theme)
        layout = getattr(self.titleBar, "buttonLayout", None)
        if layout is not None:
            layout.insertWidget(0, self._theme_btn, 0, Qt.AlignVCenter)

    def _sync_theme_button(self) -> None:
        dark = isDarkTheme()
        self._theme_btn.setToolTip("切换到浅色" if dark else "切换到深色")

    def toggle_theme(self) -> None:
        """在深色 / 浅色之间切换（会写进配置，下次启动仍然生效）。"""
        dark = isDarkTheme()
        value = "light" if dark else "dark"
        setTheme(Theme.LIGHT if dark else Theme.DARK)
        self._cfg["theme"] = value
        cfgmod.save(self._cfg)
        self.settings_page.sync_theme(value)
        hook = self._hooks.get("config_changed")
        if hook:
            hook(self._cfg)
        self._sync_theme_button()

    # ---- 数据刷新 -----------------------------------------------------
    def update_readings(self, readings: list[Reading]) -> None:
        self._last_readings = readings
        show_absent = bool(self._cfg.get("show_absent_devices", False))
        present = [r for r in readings if is_present(r)]
        visible = readings if show_absent else present
        hidden = len(readings) - len(visible)
        self.device_page.update_readings(visible, show_absent, hidden)
        self.settings_page.update_devices(present)

    # ---- 配置 ---------------------------------------------------------
    def apply_config(self, cfg: dict) -> None:
        self._cfg = cfg
        apply_theme(cfg.get("theme", "auto"))
        self.apply_appearance()
        self.settings_page.sync_theme(cfg.get("theme", "auto"))
        self.settings_page.sync_tray_mode(
            str((cfg.get("tray") or {}).get("mode", "number")))
        self.update_readings(self._last_readings)

    def apply_appearance(self) -> None:
        """电量显示方式 + 环形里的字体。"""
        self.device_page.set_battery_style(cfgmod.battery_style(self._cfg))
        self.device_page.set_font_family(
            fontmod.icon_font_family(cfgmod.tray_font(self._cfg)))

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

# -*- coding: utf-8 -*-
"""system_tray.py —— 系统托盘图标管理

规则（与设置项一致）：
  * 上托盘的设备集合 = 已检测到的非蓝牙设备 + （tray.include_bluetooth 打开时的蓝牙设备）
  * tray.multi_icon=true 且集合里多于一个设备 -> 每个设备一个图标
  * 否则只用一个图标，显示集合里电量最低的那个设备，悬停里列出全部

交互：左键单击 = 立即刷新；双击 = 打开主界面；右键 = 菜单。
"""

from __future__ import annotations

import time
from typing import Callable, Optional

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QAction, QMenu, QSystemTrayIcon

from device_battery.devices import Reading, charging_text

from . import icon_render

APP_NAME = "设备电量"

PLACEHOLDER = "__placeholder__"
SINGLE = "__single__"


class SystemTray(QObject):
    """托盘图标集合。"""

    open_ui = pyqtSignal()
    refresh_now = pyqtSignal()
    open_settings = pyqtSignal()
    quit_app = pyqtSignal()

    def __init__(self, cfg: dict, log: Optional[Callable[[str], None]] = None,
                 parent: QObject = None):
        super().__init__(parent)
        self._cfg = cfg
        self._log = log
        self._icons: dict[str, QSystemTrayIcon] = {}
        self._readings: list[Reading] = []

    # ---- 对外 ---------------------------------------------------------
    def apply_config(self, cfg: dict) -> None:
        self._cfg = cfg
        self._render()

    def update(self, readings: list[Reading]) -> None:
        self._readings = readings
        self._render()

    def cleanup(self) -> None:
        for icon in self._icons.values():
            icon.setVisible(False)
            icon.deleteLater()
        self._icons.clear()

    # ---- 内部 ---------------------------------------------------------
    def _tray_devices(self) -> list[Reading]:
        tray_cfg = self._cfg.get("tray", {})
        include_bt = bool(tray_cfg.get("include_bluetooth", False))
        out = []
        for r in self._readings:
            if not r.online:
                continue
            info = r.info
            is_bt = bool(info and info.source == "bluetooth")
            if is_bt and not include_bt:
                continue
            out.append(r)
        out.sort(key=lambda r: (r.level if r.level is not None else 999))
        return out

    def _tooltip(self, r: Reading) -> str:
        info = r.info
        name = info.name if info else r.key
        when = time.strftime("%H:%M", time.localtime(r.updated_at))
        if not self._cfg.get("tray", {}).get("hover_tooltip", True):
            return APP_NAME
        if r.level is None:
            return f"{name}：读取失败（{when}）"
        text = f"{name}：{r.level}%（{when}）"
        if r.charging is not None:
            text += f"  {charging_text(r.charging)}"
        return text

    def _make_menu(self, title: Optional[str]) -> QMenu:
        menu = QMenu()
        if title:
            act = QAction(title, menu)
            act.setEnabled(False)
            menu.addAction(act)
            menu.addSeparator()
        menu.addAction("打开主界面", self.open_ui.emit)
        menu.addAction("立即刷新", self.refresh_now.emit)
        menu.addAction("设置…", self.open_settings.emit)
        menu.addSeparator()
        menu.addAction("退出", self.quit_app.emit)
        return menu

    def _ensure_icon(self, slot: str, menu: QMenu) -> QSystemTrayIcon:
        icon = self._icons.get(slot)
        if icon is None:
            icon = QSystemTrayIcon(self)
            icon.setContextMenu(menu)
            icon.activated.connect(self._on_activated)
            icon.setVisible(True)
            self._icons[slot] = icon
        return icon

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.DoubleClick:
            self.open_ui.emit()
        elif reason == QSystemTrayIcon.Trigger:
            self.refresh_now.emit()

    def _render(self) -> None:
        mode = self._cfg.get("tray", {}).get("mode", "number")
        multi = bool(self._cfg.get("tray", {}).get("multi_icon", True))
        devices = self._tray_devices()

        wanted: list[tuple[str, Reading]] = []
        if not devices:
            wanted.append((PLACEHOLDER, None))
        elif multi and len(devices) > 1:
            for r in devices:
                wanted.append((r.key, r))
        else:
            wanted.append((SINGLE, devices[0]))

        wanted_slots = {slot for slot, _ in wanted}
        for slot in list(self._icons):
            if slot not in wanted_slots:
                old = self._icons.pop(slot)
                old.setVisible(False)
                old.deleteLater()

        for slot, reading in wanted:
            if reading is None:
                menu = self._make_menu(APP_NAME)
                icon = self._ensure_icon(slot, menu)
                icon.setIcon(icon_render.render(mode, None, ""))
                icon.setToolTip("未检测到设备")
                continue
            info = reading.info
            name = info.name if info else reading.key
            kind = info.kind if info else ""
            menu = self._make_menu(name)
            icon = self._ensure_icon(slot, menu)
            icon.setIcon(icon_render.render(mode, reading.level, kind))
            icon.setToolTip(self._full_tooltip(slot, reading, devices))
            if self._log:
                self._log(f"托盘图标 [{slot}] 形态={mode} 电量={reading.level} "
                          f"提示={name}")

    def _full_tooltip(self, slot: str, reading: Reading,
                      devices: list[Reading]) -> str:
        if slot == SINGLE and len(devices) > 1:
            if not self._cfg.get("tray", {}).get("hover_tooltip", True):
                return APP_NAME
            lines = [f"{APP_NAME}（{len(devices)} 个设备）"]
            for r in devices:
                info = r.info
                nm = info.name if info else r.key
                lv = "--" if r.level is None else f"{r.level}%"
                lines.append(f"{nm}：{lv}")
            return "\n".join(lines)
        return self._tooltip(reading)

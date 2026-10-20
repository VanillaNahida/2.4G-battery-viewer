# -*- coding: utf-8 -*-
"""settings_page.py —— 设置页

包含：通用 / 托盘 / 通知 三组设置，以及「设备预警」表
（每个设备可单独设启用开关、阈值、提示音 —— 需求 5）。
所有改动即时保存并通知主程序生效。
"""

from __future__ import annotations

from typing import Callable, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QFileDialog, QHBoxLayout, QVBoxLayout, QWidget)
from qfluentwidgets import (BodyLabel, CaptionLabel, CardWidget, ComboBox,
                            InfoBar, InfoBarPosition, PrimaryPushButton,
                            PushButton, ScrollArea, SpinBox, SubtitleLabel,
                            SwitchButton)

from device_battery.core import autostart, config as cfgmod
from device_battery.core.paths import ASSETS_DIR
from device_battery.devices import Reading

from .theme import THEME_CHOICES, apply_theme

TRAY_MODES = [("number", "数字图标"), ("ring", "环形电量"), ("icon", "纯图标")]


def _row(container: QWidget, label: str, hint: str = ""):
    """在 container 里加一行：左边文字，右边控件（返回行布局）。"""
    line = QHBoxLayout()
    line.setContentsMargins(0, 6, 0, 6)
    line.setSpacing(10)
    text = QVBoxLayout()
    text.setSpacing(0)
    text.addWidget(BodyLabel(label, container))
    if hint:
        cap = CaptionLabel(hint, container)
        cap.setWordWrap(True)
        text.addWidget(cap)
    line.addLayout(text, 1)
    container.layout().addLayout(line)
    return line


class _Group(CardWidget):
    """一组设置（卡片 + 竖向布局）。"""

    def __init__(self, title: str, parent: QWidget = None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 14, 20, 16)
        lay.setSpacing(2)
        lay.addWidget(SubtitleLabel(title, self))


class SettingsPage(QWidget):
    """设置页。"""

    def __init__(self, cfg: dict,
                 hooks: dict,
                 test_alert: Optional[Callable[[str, str], None]] = None,
                 preview_sound: Optional[Callable[[str, int], None]] = None,
                 log: Optional[Callable[[str], None]] = None,
                 parent: QWidget = None):
        """hooks: {"config_changed": f(cfg), "refresh": f()}"""
        super().__init__(parent)
        self.setObjectName("settingsPage")
        self._cfg = cfg
        self._hooks = hooks
        self._test_alert = test_alert
        self._preview_sound = preview_sound
        self._log = log
        self._device_rows: dict[str, QWidget] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent}")
        outer.addWidget(scroll)

        self._body = QWidget()
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(24, 20, 24, 24)
        self._body_layout.setSpacing(14)
        scroll.setWidget(self._body)

        self._build_general()
        self._build_tray()
        self._build_notify()
        self._build_device_group()
        self._body_layout.addStretch(1)

    # ------------------------------------------------------------------
    # 通用
    # ------------------------------------------------------------------
    def _build_general(self) -> None:
        g = _Group("通用", self._body)
        self._body_layout.addWidget(g)

        line = _row(g, "主题", "跟随系统 / 浅色 / 深色")
        combo = ComboBox(g)
        for value, label in THEME_CHOICES:
            combo.addItem(label, userData=value)
        combo.setCurrentIndex(self._index_of(THEME_CHOICES, self._cfg.get("theme", "auto")))
        combo.currentIndexChanged.connect(
            lambda: self._on_theme(combo.currentData()))
        line.addWidget(combo, 0, Qt.AlignRight)

        line = _row(g, "刷新间隔")
        combo = ComboBox(g)
        for seconds, label in cfgmod.INTERVAL_CHOICES:
            combo.addItem(label, userData=seconds)
        combo.setCurrentIndex(
            self._index_of(cfgmod.INTERVAL_CHOICES, int(self._cfg.get("interval", 60))))
        combo.currentIndexChanged.connect(
            lambda: self._on_interval(combo.currentData()))
        line.addWidget(combo, 0, Qt.AlignRight)

        line = _row(g, "开机自启", "在「启动」文件夹放快捷方式，任务管理器可见")
        sw = SwitchButton(g)
        sw.setChecked(autostart.is_autostart_enabled())
        sw.setOnText("开")
        sw.setOffText("关")
        sw.checkedChanged.connect(self._on_autostart)
        line.addWidget(sw, 0, Qt.AlignRight)

        line = _row(g, "关闭窗口时退出", "关闭则挂到托盘后台常驻")
        sw = SwitchButton(g)
        sw.setChecked(bool(self._cfg.get("quit_on_close", False)))
        sw.setOnText("退出")
        sw.setOffText("托盘")
        sw.checkedChanged.connect(
            lambda v: self._set("quit_on_close", bool(v)))
        line.addWidget(sw, 0, Qt.AlignRight)

        line = _row(g, "显示未检测到的设备")
        sw = SwitchButton(g)
        sw.setChecked(bool(self._cfg.get("show_absent_devices", False)))
        sw.checkedChanged.connect(
            lambda v: self._set("show_absent_devices", bool(v)))
        line.addWidget(sw, 0, Qt.AlignRight)

    # ------------------------------------------------------------------
    # 托盘
    # ------------------------------------------------------------------
    def _build_tray(self) -> None:
        g = _Group("托盘图标", self._body)
        self._body_layout.addWidget(g)
        tray = self._cfg.setdefault("tray", {})

        line = _row(g, "图标形态", "数字图标 / 环形电量 / 纯图标")
        combo = ComboBox(g)
        for value, label in TRAY_MODES:
            combo.addItem(label, userData=value)
        combo.setCurrentIndex(self._index_of(TRAY_MODES, tray.get("mode", "number")))
        combo.currentIndexChanged.connect(
            lambda: self._set_tray("mode", combo.currentData()))
        line.addWidget(combo, 0, Qt.AlignRight)

        line = _row(g, "多设备多图标", "多于一个设备时每个设备一个托盘图标")
        sw = SwitchButton(g)
        sw.setChecked(bool(tray.get("multi_icon", True)))
        sw.checkedChanged.connect(
            lambda v: self._set_tray("multi_icon", bool(v)))
        line.addWidget(sw, 0, Qt.AlignRight)

        line = _row(g, "悬停显示电量", "鼠标悬停时显示设备名与电量")
        sw = SwitchButton(g)
        sw.setChecked(bool(tray.get("hover_tooltip", True)))
        sw.checkedChanged.connect(
            lambda v: self._set_tray("hover_tooltip", bool(v)))
        line.addWidget(sw, 0, Qt.AlignRight)

        line = _row(g, "蓝牙设备也上托盘", "默认只把 2.4G/USB 设备放托盘")
        sw = SwitchButton(g)
        sw.setChecked(bool(tray.get("include_bluetooth", False)))
        sw.checkedChanged.connect(
            lambda v: self._set_tray("include_bluetooth", bool(v)))
        line.addWidget(sw, 0, Qt.AlignRight)

    # ------------------------------------------------------------------
    # 通知（全局默认；每设备可在下面单独覆盖）
    # ------------------------------------------------------------------
    def _build_notify(self) -> None:
        g = _Group("电量预警（全局默认）", self._body)
        self._body_layout.addWidget(g)
        notify = self._cfg.setdefault("notify", {})

        line = _row(g, "启用低电量提醒")
        sw = SwitchButton(g)
        sw.setChecked(bool(notify.get("enabled", True)))
        sw.checkedChanged.connect(
            lambda v: self._set_notify("enabled", bool(v)))
        line.addWidget(sw, 0, Qt.AlignRight)

        line = _row(g, "全局阈值", "低于该电量时提醒（%）")
        spin = SpinBox(g)
        spin.setRange(1, 100)
        spin.setValue(int(notify.get("threshold", 20)))
        spin.valueChanged.connect(
            lambda v: self._set_notify("threshold", int(v)))
        line.addWidget(spin, 0, Qt.AlignRight)

        line = _row(g, "冷却时间", "同一设备在这段时间内不重复提醒（分钟）")
        spin = SpinBox(g)
        spin.setRange(1, 24 * 60)
        spin.setValue(int(notify.get("cooldown_minutes", 30)))
        spin.valueChanged.connect(
            lambda v: self._set_notify("cooldown_minutes", int(v)))
        line.addWidget(spin, 0, Qt.AlignRight)

        line = _row(g, "提示音")
        self._sound_label = BodyLabel(
            self._cfg.get("notify", {}).get("sound", ""), g)
        line.addWidget(self._sound_label, 0, Qt.AlignRight)

        line = QHBoxLayout()
        line.addStretch(1)
        btn_pick = PushButton("选择提示音…", g)
        btn_pick.clicked.connect(self._pick_sound)
        line.addWidget(btn_pick)
        btn_preview = PrimaryPushButton("试听", g)
        btn_preview.clicked.connect(self._preview)
        line.addWidget(btn_preview)
        g.layout().addLayout(line)

        line = _row(g, "音量（%）")
        spin = SpinBox(g)
        spin.setRange(0, 100)
        spin.setValue(int(notify.get("volume", 70)))
        spin.valueChanged.connect(lambda v: self._set_notify("volume", int(v)))
        line.addWidget(spin, 0, Qt.AlignRight)

    # ------------------------------------------------------------------
    # 设备预警（每设备单独调整）
    # ------------------------------------------------------------------
    def _build_device_group(self) -> None:
        self._dev_group = _Group("设备预警（逐设备单独设置）", self._body)
        self._body_layout.addWidget(self._dev_group)
        self._dev_hint = CaptionLabel(
            "下面每个设备可单独设 启用开关 / 阈值 / 提示音；"
            "改动即时保存，设备离线时设置会保留。", self._dev_group)
        self._dev_group.layout().addWidget(self._dev_hint)

    def update_devices(self, readings: list[Reading]) -> None:
        """按当前设备重建预警表。"""
        seen = set()
        lay = self._dev_group.layout()
        for r in readings:
            info = r.info
            if info is None:
                continue
            key = r.key
            seen.add(key)
            if key in self._device_rows:
                continue
            row = self._make_device_row(info.name, key)
            self._device_rows[key] = row
            lay.addWidget(row)
        for key in list(self._device_rows):
            if key not in seen:
                row = self._device_rows.pop(key)
                lay.removeWidget(row)
                row.deleteLater()

    def _make_device_row(self, name: str, key: str) -> QWidget:
        box = CardWidget(self._dev_group)
        line = QHBoxLayout(box)
        line.setContentsMargins(14, 8, 14, 8)
        line.setSpacing(10)

        title = BodyLabel(name, box)
        line.addWidget(title, 1)

        eff = cfgmod.device_notify(self._cfg, key)

        sw = SwitchButton(box)
        sw.setChecked(bool(eff["enabled"]))
        sw.setOnText("开")
        sw.setOffText("关")
        sw.checkedChanged.connect(
            lambda v, k=key: self._set_device(k, enabled=bool(v)))
        line.addWidget(sw)

        line.addWidget(CaptionLabel("阈值", box))
        spin = SpinBox(box)
        spin.setRange(1, 100)
        spin.setValue(int(eff["threshold"]))
        spin.valueChanged.connect(
            lambda v, k=key: self._set_device(k, threshold=int(v)))
        line.addWidget(spin)

        sound_label = CaptionLabel(eff["sound"] or "", box)
        sound_label.setFixedWidth(180)
        line.addWidget(sound_label)

        btn = PushButton("提示音…", box)
        btn.clicked.connect(lambda _, k=key, lb=sound_label:
                            self._pick_device_sound(k, lb))
        line.addWidget(btn)

        btn_test = PushButton("测试", box)
        btn_test.clicked.connect(lambda _, k=key, n=name: self._test(k, n))
        line.addWidget(btn_test)

        btn_reset = PushButton("恢复默认", box)
        btn_reset.clicked.connect(lambda _, k=key: self._reset_device(k))
        line.addWidget(btn_reset)
        return box

    # ------------------------------------------------------------------
    # 事件
    # ------------------------------------------------------------------
    @staticmethod
    def _index_of(choices, value) -> int:
        for i, (v, _label) in enumerate(choices):
            if v == value:
                return i
        return 0

    def _persist(self) -> None:
        cfgmod.save(self._cfg)
        self._hooks["config_changed"](self._cfg)

    def _set(self, field: str, value) -> None:
        self._cfg[field] = value
        self._persist()

    def _set_tray(self, field: str, value) -> None:
        self._cfg.setdefault("tray", {})[field] = value
        self._persist()

    def _set_notify(self, field: str, value) -> None:
        self._cfg.setdefault("notify", {})[field] = value
        self._persist()

    def _set_device(self, key: str, **fields) -> None:
        cfgmod.set_device_notify(self._cfg, key, **fields)
        self._persist()

    def _reset_device(self, key: str) -> None:
        cfgmod.clear_device_notify(self._cfg, key)
        self._persist()
        for row_key, row in list(self._device_rows.items()):
            if row_key == key:
                row.deleteLater()
                self._device_rows.pop(row_key, None)
        self._hooks["refresh"]()
        InfoBar.success("已恢复全局默认", key, duration=2000,
                        position=InfoBarPosition.TOP_RIGHT, parent=self)

    def _on_theme(self, value) -> None:
        self._cfg["theme"] = value
        apply_theme(value)
        self._persist()

    def _on_interval(self, seconds) -> None:
        self._cfg["interval"] = int(seconds)
        self._persist()
        self._hooks["refresh"]()

    def _on_autostart(self, enabled: bool) -> None:
        ok = autostart.set_autostart(bool(enabled))
        self._cfg["autostart"] = bool(enabled)
        self._persist()
        if enabled and not ok:
            InfoBar.error("开机自启设置失败", "无法创建启动文件夹快捷方式",
                          duration=4000, position=InfoBarPosition.TOP_RIGHT,
                          parent=self)
        else:
            InfoBar.success("开机自启已更新",
                            "任务管理器 ->「启动」标签可查看",
                            duration=2500, position=InfoBarPosition.TOP_RIGHT,
                            parent=self)

    def _pick_sound(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择提示音", str(ASSETS_DIR),
            "音频文件 (*.mp3 *.wav *.m4a *.flac);;所有文件 (*)")
        if not path:
            return
        self._cfg.setdefault("notify", {})["sound"] = path
        self._sound_label.setText(path)
        self._persist()

    def _pick_device_sound(self, key: str, label) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择该设备的提示音", str(ASSETS_DIR),
            "音频文件 (*.mp3 *.wav *.m4a *.flac);;所有文件 (*)")
        if not path:
            return
        self._set_device(key, sound=path)
        label.setText(path)

    def _preview(self) -> None:
        if self._preview_sound:
            self._preview_sound(self._cfg.get("notify", {}).get("sound", ""),
                                int(self._cfg.get("notify", {}).get("volume", 70)))

    def _test(self, key: str, name: str) -> None:
        if self._test_alert:
            self._test_alert(key, name)

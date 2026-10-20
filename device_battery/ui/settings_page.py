# -*- coding: utf-8 -*-
"""settings_page.py —— 设置页

分组：通用（主题 / 间隔 / 自启）、外观（界面字体 / 电量显示方式）、
托盘（形态 / 字体 / 多图标 / 悬停 / 蓝牙）、电量预警（全局 + 逐设备覆盖）、
通知文案（标题 / 正文模板 + 魔法变量 + 发送测试通知）。

布局要点：所有文字标签都能自动换行或省略，控件宽度有上下限，
窗口拉窄到很小也不会把内容顶出边界（滚动区不出横向滚动条）。
"""

from __future__ import annotations

from typing import Callable, Optional

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (QFileDialog, QHBoxLayout, QSizePolicy,
                             QVBoxLayout, QWidget)
from qfluentwidgets import (BodyLabel, CaptionLabel, CardWidget, ComboBox,
                            InfoBar, InfoBarPosition, LineEdit,
                            PrimaryPushButton, PushButton, ScrollArea, SpinBox,
                            SubtitleLabel, SwitchButton, TextEdit)

from device_battery.core import autostart, config as cfgmod
from device_battery.core import fonts as fontmod
from device_battery.core.paths import ASSETS_DIR
from device_battery.devices import Reading
from device_battery.notify import template

from .theme import apply_theme
from .widgets import ElidedLabel


def _text_block(container: QWidget, label: str, hint: str = "") -> QVBoxLayout:
    """左侧文字块：标题 + 说明，都能换行、都能被压缩。"""
    block = QVBoxLayout()
    block.setContentsMargins(0, 0, 0, 0)
    block.setSpacing(1)
    title = BodyLabel(label, container)
    title.setWordWrap(True)
    title.setMinimumWidth(0)
    block.addWidget(title)
    if hint:
        caption = CaptionLabel(hint, container)
        caption.setWordWrap(True)
        caption.setMinimumWidth(0)
        block.addWidget(caption)
    return block


def _row(container: QWidget, label: str, hint: str = "") -> QHBoxLayout:
    """一行设置：左边文字，右边控件（返回行布局）。"""
    line = QHBoxLayout()
    line.setContentsMargins(0, 6, 0, 6)
    line.setSpacing(12)
    line.addLayout(_text_block(container, label, hint), 1)
    container.layout().addLayout(line)
    return line


def _combo(container: QWidget, choices, current,
           on_change) -> ComboBox:
    combo = ComboBox(container)
    for value, label in choices:
        combo.addItem(label, userData=value)
    combo.setCurrentIndex(_index_of(choices, current))
    combo.setMinimumWidth(170)
    combo.setMaximumWidth(280)
    combo.currentIndexChanged.connect(
        lambda: on_change(combo.currentData()))
    return combo


def _switch(container: QWidget, checked: bool, on_change) -> SwitchButton:
    """设置页统一用「不带文字」的开关（只有滑块本身）。"""
    sw = SwitchButton(container)
    sw.setOnText("")
    sw.setOffText("")
    sw.setChecked(bool(checked))
    sw.checkedChanged.connect(lambda v: on_change(bool(v)))
    return sw


def _lookup_index(choices, value) -> int:
    """找不到返回 -1（和「系统默认」的下标 0 区分开）。"""
    for index, (candidate, _label) in enumerate(choices):
        if candidate == value:
            return index
    return -1


def _index_of(choices, value) -> int:
    for index, (candidate, _label) in enumerate(choices):
        if candidate == value:
            return index
    return 0


class _Group(CardWidget):
    """一组设置（卡片 + 竖向布局）。"""

    def __init__(self, title: str, parent: QWidget = None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 14, 20, 16)
        lay.setSpacing(2)
        heading = SubtitleLabel(title, self)
        heading.setWordWrap(True)
        lay.addWidget(heading)


class SettingsPage(QWidget):
    """设置页。"""

    def __init__(self, cfg: dict,
                 hooks: dict,
                 test_alert: Optional[Callable[[str, str], None]] = None,
                 preview_sound: Optional[Callable[[str, int], None]] = None,
                 test_notify: Optional[Callable[[str, str], None]] = None,
                 log: Optional[Callable[[str], None]] = None,
                 parent: QWidget = None):
        """hooks: {"config_changed": f(cfg), "refresh": f()}"""
        super().__init__(parent)
        self.setObjectName("settingsPage")
        self._cfg = cfg
        self._hooks = hooks
        self._test_alert = test_alert
        self._preview_sound = preview_sound
        self._test_notify = test_notify
        self._log = log
        self._device_rows: dict[str, QWidget] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent}")
        # 视口也要透明，否则深色主题下会透出浅色底
        scroll.viewport().setStyleSheet("background: transparent;")
        outer.addWidget(scroll)

        self._body = QWidget()
        self._body.setMinimumWidth(0)
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(24, 20, 24, 24)
        self._body_layout.setSpacing(14)
        scroll.setWidget(self._body)

        self._build_general()
        self._build_appearance()
        self._build_tray()
        self._build_notify()
        self._build_notify_template()
        self._build_device_group()
        self._body_layout.addStretch(1)

    # ------------------------------------------------------------------
    # 通用
    # ------------------------------------------------------------------
    def _build_general(self) -> None:
        g = _Group("通用", self._body)
        self._body_layout.addWidget(g)

        line = _row(g, "主题", "跟随系统 / 浅色 / 深色；也可以点标题栏那个切换按钮")
        self._theme_combo = _combo(g, cfgmod.THEME_CHOICES,
                                   self._cfg.get("theme", "auto"),
                                   self._on_theme)
        line.addWidget(self._theme_combo, 0, Qt.AlignRight | Qt.AlignVCenter)

        line = _row(g, "刷新间隔")
        line.addWidget(_combo(g, cfgmod.INTERVAL_CHOICES,
                              int(self._cfg.get("interval", 60)),
                              self._on_interval), 0,
                       Qt.AlignRight | Qt.AlignVCenter)

        line = _row(g, "开机自启", "在「启动」文件夹放快捷方式，任务管理器可见")
        line.addWidget(_switch(g, autostart.is_autostart_enabled(),
                               self._on_autostart), 0,
                       Qt.AlignRight | Qt.AlignVCenter)

        line = _row(g, "关闭窗口时退出", "关闭则挂到托盘后台常驻")
        line.addWidget(_switch(g, bool(self._cfg.get("quit_on_close", False)),
                               lambda v: self._set("quit_on_close", v)), 0,
                       Qt.AlignRight | Qt.AlignVCenter)

        line = _row(g, "显示未检测到的设备",
                    "打开后，没连上的设备会以占位卡显示；关闭时只显示正在用的设备")
        line.addWidget(_switch(g, bool(self._cfg.get("show_absent_devices", False)),
                               lambda v: self._set("show_absent_devices", v)), 0,
                       Qt.AlignRight | Qt.AlignVCenter)

    # ------------------------------------------------------------------
    # 外观（字体 / 电量显示方式）
    # ------------------------------------------------------------------
    def _build_appearance(self) -> None:
        g = _Group("外观", self._body)
        self._body_layout.addWidget(g)

        line = _row(g, "界面字体", "默认 MiSans；可换成系统里的任意字体")
        self._ui_font_combo = ComboBox(g)
        self._ui_font_combo.setMinimumWidth(160)
        self._ui_font_combo.setMaximumWidth(260)
        self._fill_font_combo(self._ui_font_combo, cfgmod.ui_font(self._cfg))
        self._ui_font_combo.currentIndexChanged.connect(
            lambda: self._on_ui_font(self._ui_font_combo.currentData()))
        line.addWidget(self._ui_font_combo, 0,
                       Qt.AlignRight | Qt.AlignVCenter)
        btn_font = PushButton("加载字体文件…", g)
        btn_font.clicked.connect(self._pick_font_file)
        line.addWidget(btn_font, 0, Qt.AlignRight | Qt.AlignVCenter)

        line = _row(g, "主界面电量显示",
                    "环形：电量环形进度 + 环内百分比；进度条：大号百分比 + 进度条")
        line.addWidget(_combo(g, cfgmod.BATTERY_STYLE_CHOICES,
                              cfgmod.battery_style(self._cfg),
                              self._set_battery_style), 0,
                       Qt.AlignRight | Qt.AlignVCenter)

        orange, red = cfgmod.level_thresholds(self._cfg)

        line = _row(g, "橙黄色阈值",
                    "电量小于等于该值时，环和数字变成橙黄色（%）")
        self._orange_spin = SpinBox(g)
        self._orange_spin.setRange(2, 100)
        self._orange_spin.setValue(orange)
        self._orange_spin.setSuffix(" %")
        self._orange_spin.setFixedWidth(120)
        self._orange_spin.valueChanged.connect(self._on_orange_threshold)
        line.addWidget(self._orange_spin, 0, Qt.AlignRight | Qt.AlignVCenter)

        line = _row(g, "红色阈值",
                    "电量小于等于该值时变红（%），必须小于橙黄色阈值")
        self._red_spin = SpinBox(g)
        self._red_spin.setRange(1, 99)
        self._red_spin.setValue(red)
        self._red_spin.setSuffix(" %")
        self._red_spin.setFixedWidth(120)
        self._red_spin.valueChanged.connect(self._on_red_threshold)
        line.addWidget(self._red_spin, 0, Qt.AlignRight | Qt.AlignVCenter)

    # ------------------------------------------------------------------
    # 托盘
    # ------------------------------------------------------------------
    def _build_tray(self) -> None:
        g = _Group("托盘图标", self._body)
        self._body_layout.addWidget(g)
        tray = self._cfg.setdefault("tray", {})

        line = _row(g, "图标形态", "数字图标 / 环形电量 / 仅圆环 / 纯图标")
        self._tray_mode_combo = _combo(g, cfgmod.TRAY_MODE_CHOICES,
                                       tray.get("mode", "number"),
                                       lambda v: self._set_tray("mode", v))
        line.addWidget(self._tray_mode_combo, 0,
                       Qt.AlignRight | Qt.AlignVCenter)

        line = _row(g, "托盘字体", "图标里数字用的字体（可与界面字体不同）")
        self._tray_font_combo = ComboBox(g)
        self._tray_font_combo.setMinimumWidth(170)
        self._tray_font_combo.setMaximumWidth(280)
        self._fill_font_combo(self._tray_font_combo,
                              cfgmod.tray_font(self._cfg))
        self._tray_font_combo.currentIndexChanged.connect(
            lambda: self._on_tray_font(self._tray_font_combo.currentData()))
        line.addWidget(self._tray_font_combo, 0,
                       Qt.AlignRight | Qt.AlignVCenter)

        line = _row(g, "多设备多图标", "多于一个设备时每个设备一个托盘图标")
        line.addWidget(_switch(g, bool(tray.get("multi_icon", True)),
                               lambda v: self._set_tray("multi_icon", v)), 0,
                       Qt.AlignRight | Qt.AlignVCenter)

        line = _row(g, "悬停显示电量", "鼠标悬停时显示设备名与电量")
        line.addWidget(_switch(g, bool(tray.get("hover_tooltip", True)),
                               lambda v: self._set_tray("hover_tooltip", v)), 0,
                       Qt.AlignRight | Qt.AlignVCenter)

        line = _row(g, "蓝牙设备也上托盘", "默认只把 2.4G/USB 设备放托盘")
        line.addWidget(_switch(g, bool(tray.get("include_bluetooth", False)),
                               lambda v: self._set_tray("include_bluetooth", v)), 0,
                       Qt.AlignRight | Qt.AlignVCenter)

    # ------------------------------------------------------------------
    # 电量预警（全局默认；每设备可在下面单独覆盖）
    # ------------------------------------------------------------------
    def _build_notify(self) -> None:
        g = _Group("电量预警（全局默认）", self._body)
        self._body_layout.addWidget(g)
        notify = self._cfg.setdefault("notify", {})

        line = _row(g, "启用低电量提醒")
        line.addWidget(_switch(g, bool(notify.get("enabled", True)),
                               lambda v: self._set_notify("enabled", v)), 0,
                       Qt.AlignRight | Qt.AlignVCenter)

        line = _row(g, "全局阈值", "低于该电量时提醒（%）")
        spin = SpinBox(g)
        spin.setRange(1, 100)
        spin.setValue(int(notify.get("threshold", 20)))
        spin.setFixedWidth(120)
        spin.valueChanged.connect(lambda v: self._set_notify("threshold", int(v)))
        line.addWidget(spin, 0, Qt.AlignRight | Qt.AlignVCenter)

        line = _row(g, "冷却时间", "同一设备在这段时间内不重复提醒（分钟）")
        spin = SpinBox(g)
        spin.setRange(1, 24 * 60)
        spin.setValue(int(notify.get("cooldown_minutes", 30)))
        spin.setFixedWidth(120)
        spin.valueChanged.connect(
            lambda v: self._set_notify("cooldown_minutes", int(v)))
        line.addWidget(spin, 0, Qt.AlignRight | Qt.AlignVCenter)

        line = _row(g, "提示音", "低电量提醒时播放，可选任意 mp3 / wav")
        btn_pick = PushButton("选择提示音…", g)
        btn_pick.clicked.connect(self._pick_sound)
        line.addWidget(btn_pick, 0, Qt.AlignRight | Qt.AlignVCenter)
        btn_preview = PrimaryPushButton("试听", g)
        btn_preview.clicked.connect(self._preview)
        line.addWidget(btn_preview, 0, Qt.AlignRight | Qt.AlignVCenter)

        # 当前提示音路径单独一行：左对齐、超长省略，不和按钮挤在一起
        self._sound_label = ElidedLabel(
            self._cfg.get("notify", {}).get("sound", "") or "使用默认提示音", g)
        self._sound_label.setMinimumWidth(0)
        g.layout().addWidget(self._sound_label)

        line = _row(g, "音量（%）")
        spin = SpinBox(g)
        spin.setRange(0, 100)
        spin.setValue(int(notify.get("volume", 70)))
        spin.setFixedWidth(120)
        spin.valueChanged.connect(lambda v: self._set_notify("volume", int(v)))
        line.addWidget(spin, 0, Qt.AlignRight | Qt.AlignVCenter)


    # ------------------------------------------------------------------
    # 通知文案（自定义 + 魔法变量 + 测试）
    # ------------------------------------------------------------------
    def _build_notify_template(self) -> None:
        g = _Group("通知文案与测试", self._body)
        self._body_layout.addWidget(g)
        # 文案边打边存太吵，停手 0.4 秒再落盘
        self._tpl_timer = QTimer(self)
        self._tpl_timer.setSingleShot(True)
        self._tpl_timer.setInterval(400)
        self._tpl_timer.timeout.connect(self._persist)
        title_tpl, body_tpl = cfgmod.render_templates(self._cfg)

        g.layout().addLayout(_text_block(
            g, "通知标题",
            "支持魔法变量，例如 {min_name} 电量偏低"))

        self._title_edit = LineEdit(g)
        self._title_edit.setPlaceholderText(
            cfgmod.DEFAULTS["notify"]["title_template"])
        self._title_edit.setText(title_tpl)
        self._title_edit.setClearButtonEnabled(True)
        self._title_edit.textChanged.connect(
            lambda t: self._on_template_changed("title_template", t))
        g.layout().addWidget(self._title_edit)

        g.layout().addLayout(_text_block(
            g, "通知正文",
            "示例：{name} 只剩 {level_pct}，{status}（{time} 检测）"))

        self._body_edit = TextEdit(g)
        self._body_edit.setPlaceholderText(
            cfgmod.DEFAULTS["notify"]["body_template"])
        self._body_edit.setPlainText(body_tpl)
        self._body_edit.setFixedHeight(72)
        self._body_edit.textChanged.connect(
            lambda: self._on_template_changed(
                "body_template", self._body_edit.toPlainText()))
        g.layout().addWidget(self._body_edit)

        self._var_hint = CaptionLabel("", g)
        self._var_hint.setWordWrap(True)
        self._var_hint.setMinimumWidth(0)
        g.layout().addWidget(self._var_hint)

        self._refresh_variable_hint()

        line = QHBoxLayout()
        line.setContentsMargins(0, 6, 0, 0)
        btn_reset = PushButton("恢复默认文案", g)
        btn_reset.clicked.connect(self._reset_templates)
        line.addWidget(btn_reset)
        line.addStretch(1)
        btn_test = PrimaryPushButton("发送测试通知", g)
        btn_test.clicked.connect(self._send_test_notification)
        line.addWidget(btn_test)
        g.layout().addLayout(line)

    def _variable_text(self) -> str:
        items = [f"{{{name}}} {desc}" for name, desc in template.VARIABLES]
        return "可用变量：" + " · ".join(items)

    def _refresh_variable_hint(self) -> None:
        unknown: list[str] = []
        for text in (self._title_edit.text(), self._body_edit.toPlainText()):
            for name in template.unknown_variables(text):
                if name not in unknown:
                    unknown.append(name)
        hint = self._variable_text()
        if unknown:
            hint += ("\n认不出的变量会原样显示：" +
                     "、".join("{" + name + "}" for name in unknown))
        self._var_hint.setText(hint)

    def _on_template_changed(self, field: str, value: str) -> None:
        self._cfg.setdefault("notify", {})[field] = value
        self._refresh_variable_hint()
        self._tpl_timer.start()

    def _reset_templates(self) -> None:
        defaults = cfgmod.DEFAULTS["notify"]
        self._title_edit.setText(defaults["title_template"])
        self._body_edit.setPlainText(defaults["body_template"])
        self._refresh_variable_hint()

    def _send_test_notification(self) -> None:
        if not self._test_notify:
            InfoBar.warning("测试不可用", "通知模块未就绪",
                            duration=3000,
                            position=InfoBarPosition.TOP_RIGHT, parent=self)
            return
        title_tpl = self._title_edit.text()
        body_tpl = self._body_edit.toPlainText()
        result = self._test_notify(title_tpl, body_tpl)
        if isinstance(result, tuple) and len(result) == 2:
            title, body = result
            InfoBar.success("测试通知已发送",
                            f"标题：{title}\n正文：{body}\n"
                            "已通过 Windows 系统通知发出（可在通知中心查看）",
                            duration=6000,
                            position=InfoBarPosition.TOP_RIGHT, parent=self)
        else:
            InfoBar.success("测试通知已发送", "请查看 Windows 通知中心",
                            duration=3000,
                            position=InfoBarPosition.TOP_RIGHT, parent=self)

    # ------------------------------------------------------------------
    # 设备预警（每设备单独调整）
    # ------------------------------------------------------------------
    def _build_device_group(self) -> None:
        self._dev_group = _Group("设备预警（逐设备单独设置）", self._body)
        self._body_layout.addWidget(self._dev_group)
        hint = CaptionLabel(
            "下面每个设备可单独设 启用开关 / 阈值 / 提示音；"
            "改动即时保存，设备离线时设置会保留。", self._dev_group)
        hint.setWordWrap(True)
        hint.setMinimumWidth(0)
        self._dev_group.layout().addWidget(hint)

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
        box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        line = QHBoxLayout(box)
        line.setContentsMargins(14, 10, 14, 10)
        line.setSpacing(10)

        eff = cfgmod.device_notify(self._cfg, key)

        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(1)
        title = BodyLabel(name, box)
        title.setWordWrap(True)
        title.setMinimumWidth(0)
        text.addWidget(title)

        sound_label = ElidedLabel(eff["sound"] or "使用全局提示音", box)
        sound_label.setMinimumWidth(60)
        text.addWidget(sound_label)
        line.addLayout(text, 1)

        line.addWidget(_switch(box, bool(eff["enabled"]),
                               lambda v, k=key: self._set_device(k, enabled=v)),
                       0, Qt.AlignVCenter)

        spin = SpinBox(box)
        spin.setRange(1, 100)
        spin.setValue(int(eff["threshold"]))
        spin.setFixedWidth(120)
        spin.setSuffix(" %")
        spin.valueChanged.connect(
            lambda v, k=key: self._set_device(k, threshold=int(v)))
        line.addWidget(spin, 0, Qt.AlignVCenter)

        btn_sound = PushButton("提示音…", box)
        btn_sound.clicked.connect(
            lambda _, k=key, lb=sound_label: self._pick_device_sound(k, lb))
        line.addWidget(btn_sound, 0, Qt.AlignVCenter)

        btn_test = PushButton("测试", box)
        btn_test.clicked.connect(lambda _, k=key, n=name: self._test(k, n))
        line.addWidget(btn_test, 0, Qt.AlignVCenter)

        btn_reset = PushButton("跟随全局", box)
        btn_reset.clicked.connect(lambda _, k=key: self._reset_device(k))
        line.addWidget(btn_reset, 0, Qt.AlignVCenter)
        return box

    # ------------------------------------------------------------------
    # 字体
    # ------------------------------------------------------------------
    def _font_choices(self) -> list[tuple[str, str]]:
        families = fontmod.available_families()
        preferred = [cfgmod.DEFAULTS["ui"]["font"], "MiSans"]
        ordered: list[str] = []
        for family in preferred:
            if family in families and family not in ordered:
                ordered.append(family)
        for family in families:
            if family not in ordered:
                ordered.append(family)
        return [("", "系统默认")] + [(f, f) for f in ordered]

    def _fill_font_combo(self, combo: ComboBox, current: str) -> None:
        combo.blockSignals(True)
        combo.clear()
        choices = self._font_choices()
        for value, label in choices:
            combo.addItem(label, userData=value)
        index = _lookup_index(choices, current or "")
        if index < 0:
            index = _lookup_index(choices, fontmod.resolve_family(current or ""))
        combo.setCurrentIndex(max(0, index))
        combo.blockSignals(False)

    def _on_ui_font(self, family) -> None:
        self._cfg.setdefault("ui", {})["font"] = family or ""
        self._persist()
        InfoBar.success("界面字体已更新", family or "系统默认",
                        duration=2000, position=InfoBarPosition.TOP_RIGHT,
                        parent=self)

    def _on_tray_font(self, family) -> None:
        self._cfg.setdefault("tray", {})["font"] = family or ""
        self._persist()

    def _pick_font_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "加载字体文件", str(ASSETS_DIR),
            "字体文件 (*.ttf *.otf *.ttc *.otc);;所有文件 (*)")
        if not path:
            return
        family = fontmod.register_font_file(path)
        if not family:
            InfoBar.error("字体加载失败", "这个文件不是 Qt 能识别的字体",
                          duration=4000,
                          position=InfoBarPosition.TOP_RIGHT, parent=self)
            return
        files = self._cfg.setdefault("fonts", {}).setdefault("extra_files", [])
        if path not in files:
            files.append(path)
        self._cfg.setdefault("ui", {})["font"] = family
        self._fill_font_combo(self._ui_font_combo, family)
        self._fill_font_combo(self._tray_font_combo,
                              cfgmod.tray_font(self._cfg))
        self._persist()
        InfoBar.success("字体已加载", f"{family}（已设为界面字体）",
                        duration=3000, position=InfoBarPosition.TOP_RIGHT,
                        parent=self)

    # ------------------------------------------------------------------
    # 事件
    # ------------------------------------------------------------------
    def _persist(self) -> None:
        cfgmod.save(self._cfg)
        hook = self._hooks.get("config_changed")
        if hook:
            hook(self._cfg)

    def _set(self, field: str, value) -> None:
        self._cfg[field] = value
        self._persist()

    def _set_tray(self, field: str, value) -> None:
        self._cfg.setdefault("tray", {})[field] = value
        self._persist()

    def _set_notify(self, field: str, value) -> None:
        self._cfg.setdefault("notify", {})[field] = value
        self._persist()

    def _set_battery_style(self, value) -> None:
        self._cfg.setdefault("ui", {})["battery_style"] = value
        self._persist()

    def _set_device(self, key: str, **fields) -> None:
        cfgmod.set_device_notify(self._cfg, key, **fields)
        self._persist()

    def _reset_device(self, key: str) -> None:
        cfgmod.clear_device_notify(self._cfg, key)
        self._persist()
        row = self._device_rows.pop(key, None)
        if row is not None:
            self._dev_group.layout().removeWidget(row)
            row.deleteLater()
        self._hooks["refresh"]()
        InfoBar.success("已恢复全局默认", key, duration=2000,
                        position=InfoBarPosition.TOP_RIGHT, parent=self)

    def _on_orange_threshold(self, value: int) -> None:
        orange = int(value)
        red = min(int(cfgmod.level_thresholds(self._cfg)[1]), orange - 1)
        self._apply_thresholds(orange, max(1, red))

    def _on_red_threshold(self, value: int) -> None:
        red = int(value)
        orange = max(int(cfgmod.level_thresholds(self._cfg)[0]), red + 1)
        self._apply_thresholds(min(100, orange), red)

    def _apply_thresholds(self, orange: int, red: int) -> None:
        self._cfg["colors"] = {"orange_at": orange, "red_at": red}
        for spin, value in ((getattr(self, "_orange_spin", None), orange),
                            (getattr(self, "_red_spin", None), red)):
            if spin is None:
                continue
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)
        self._persist()

    def sync_tray_mode(self, value: str) -> None:
        """托盘右键菜单里切换图标形态后，让下拉框跟着显示。"""
        combo = getattr(self, "_tray_mode_combo", None)
        if combo is None:
            return
        combo.blockSignals(True)
        combo.setCurrentIndex(_index_of(cfgmod.TRAY_MODE_CHOICES, value))
        combo.blockSignals(False)

    def sync_theme(self, value: str) -> None:
        """标题栏那个按钮切换主题后，让下拉框跟着显示正确的值。"""
        combo = getattr(self, "_theme_combo", None)
        if combo is None:
            return
        combo.blockSignals(True)
        combo.setCurrentIndex(_index_of(cfgmod.THEME_CHOICES, value))
        combo.blockSignals(False)

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

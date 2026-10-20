# -*- coding: utf-8 -*-
"""debug_page.py —— 调试页（精简版）

包含：
  * HID 接口枚举表（VID:PID / Usage / 报告长度 / 是否系统独占 / 是否厂商页）
  * 选中接口的 Feature Report 转储
  * 选中接口的「监听原始报文」（把收到的 Input Report 原样打出来）

原 app.py 的「手动标定协议并保存 JSON」不在本次范围内。
"""

from __future__ import annotations

from typing import Callable, Optional

from PyQt5.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QPlainTextEdit, QVBoxLayout, QWidget
from qfluentwidgets import (BodyLabel, CardWidget, PrimaryPushButton,
                            PushButton, TableWidget, TitleLabel)

from device_battery.hid import hid_win as hw
from device_battery.hid.hid_win import HidDevice

COLUMNS = ["设备", "VID:PID", "Usage", "In", "Out", "Feature", "备注"]


class _MonSignals(QObject):
    done = pyqtSignal(list, str)


class _MonitorTask(QRunnable):
    """在后台读一段时间 Input Report。"""

    def __init__(self, path: str, seconds: float, signals: _MonSignals):
        super().__init__()
        self._path = path
        self._seconds = seconds
        self._signals = signals

    def run(self) -> None:
        reports: list[bytes] = []
        err = ""
        try:
            import time
            dev = HidDevice(self._path, write=False)
            try:
                if dev.caps.InputReportByteLength:
                    dev.drain()
                end = time.monotonic() + self._seconds
                while time.monotonic() < end:
                    r = dev.read_input(timeout_ms=200)
                    if r:
                        reports.append(r)
            finally:
                dev.close()
        except Exception as e:
            err = str(e)
        self._signals.done.emit(reports, err)


class DebugPage(QWidget):
    """调试页。"""

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.setObjectName("debugPage")
        self._interfaces: list[hw.HidInterface] = []
        self._pool = QThreadPool.globalInstance()
        self._signals = _MonSignals(self)
        self._signals.done.connect(self._on_monitor_done)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(10)

        head = QHBoxLayout()
        head.addWidget(TitleLabel("HID 接口", self))
        head.addStretch(1)
        btn_refresh = PrimaryPushButton("刷新列表", self)
        btn_refresh.clicked.connect(self.refresh_interfaces)
        head.addWidget(btn_refresh)
        lay.addLayout(head)

        self._table = TableWidget(self)
        self._table.setColumnCount(len(COLUMNS))
        self._table.setHorizontalHeaderLabels(COLUMNS)
        self._table.setBorderVisible(True)
        self._table.setBorderRadius(8)
        self._table.setWordWrap(False)
        self._table.verticalHeader().setVisible(False)
        self._table.itemSelectionChanged.connect(self._on_select)
        lay.addWidget(self._table, 1)

        ops = QHBoxLayout()
        self._hint = BodyLabel("选中一个接口后可转储 Feature Report 或监听原始报文"
                               "（监听默认 3 秒）", self)
        ops.addWidget(self._hint, 1)
        btn_feature = PushButton("转储 Feature Report", self)
        btn_feature.clicked.connect(self._dump_features)
        ops.addWidget(btn_feature)
        btn_mon = PushButton("监听原始报文", self)
        btn_mon.clicked.connect(self._monitor)
        ops.addWidget(btn_mon)
        lay.addLayout(ops)

        box = CardWidget(self)
        box_lay = QVBoxLayout(box)
        box_lay.setContentsMargins(14, 12, 14, 12)
        box_lay.addWidget(BodyLabel("输出", box))
        self._output = QPlainTextEdit(box)
        self._output.setReadOnly(True)
        self._output.setMinimumHeight(180)
        box_lay.addWidget(self._output)
        lay.addWidget(box, 1)

        self.refresh_interfaces()

    # ---- 接口列表 -----------------------------------------------------
    def refresh_interfaces(self) -> None:
        try:
            self._interfaces = hw.enumerate_hid()
        except Exception as e:
            self._interfaces = []
            self._log(f"枚举 HID 失败：{e}")
            return
        self._table.setRowCount(len(self._interfaces))
        for row, it in enumerate(self._interfaces):
            flags = []
            if it.is_vendor_page:
                flags.append("厂商页")
            if it.reserved:
                flags.append("系统独占")
            if it.error:
                flags.append(it.error)
            values = [
                it.product or it.display_name,
                it.vid_pid,
                it.describe_usage(),
                str(it.input_len),
                str(it.output_len),
                str(it.feature_len),
                " ".join(flags),
            ]
            for col, text in enumerate(values):
                self._table.setItem(row, col, _cell(text))
        self._log(f"共 {len(self._interfaces)} 个 HID 接口")

    def _selected(self) -> Optional[hw.HidInterface]:
        row = self._table.currentRow()
        if 0 <= row < len(self._interfaces):
            return self._interfaces[row]
        return None

    def _on_select(self) -> None:
        it = self._selected()
        if it is None:
            return
        self._hint.setText(f"{it.product or it.display_name}  ·  {it.vid_pid}  ·  "
                           f"{it.describe_usage()}")
        self._log(f"路径：{it.path}")
        for key, value in it.__dict__.items():
            if key in ("path", "group"):
                continue
            self._log(f"  {key} = {value}")

    # ---- 操作 ---------------------------------------------------------
    def _dump_features(self) -> None:
        it = self._selected()
        if it is None:
            self._log("请先选中一个接口")
            return
        if not it.feature_len:
            self._log("该接口没有 Feature Report")
            return
        try:
            with HidDevice(it.path, write=False) as dev:
                for rid in range(0x00, 0x10):
                    try:
                        data = dev.get_feature_report(rid, it.feature_len)
                    except Exception as e:
                        self._log(f"  Feature 0x{rid:02X} 读取失败：{e}")
                        continue
                    self._log(f"  Feature 0x{rid:02X}: {data.hex(' ')}")
        except Exception as e:
            self._log(f"打开接口失败：{e}")

    def _monitor(self) -> None:
        it = self._selected()
        if it is None:
            self._log("请先选中一个接口")
            return
        if not it.input_len:
            self._log("该接口没有 Input Report")
            return
        self._log(f"开始监听 3 秒：{it.path}")
        self._pool.start(_MonitorTask(it.path, 3.0, self._signals))

    def _on_monitor_done(self, reports: list, err: str) -> None:
        if err:
            self._log(f"监听失败：{err}")
            return
        self._log(f"收到 {len(reports)} 条报文：")
        for r in reports:
            self._log("   " + r.hex(" "))

    def _log(self, text: str) -> None:
        self._output.appendPlainText(text)


def _cell(text: str):
    from PyQt5.QtWidgets import QTableWidgetItem
    return QTableWidgetItem(text)

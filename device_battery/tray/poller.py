# -*- coding: utf-8 -*-
"""poller.py —— 读取调度

用 QTimer 定时触发，实际读取放到线程池里跑（不阻塞界面），
结果通过信号回到主线程。界面与托盘共用同一个 Poller。
"""

from __future__ import annotations

from typing import Callable, Optional

from PyQt5.QtCore import QObject, QRunnable, QThreadPool, QTimer, pyqtSignal

from device_battery.devices import scan_all


class _TaskSignals(QObject):
    done = pyqtSignal(list)


class _ScanTask(QRunnable):
    """在线程池里跑一次 scan_all()。"""

    def __init__(self, signals: _TaskSignals):
        super().__init__()
        self._signals = signals

    def run(self) -> None:
        try:
            results = scan_all()
        except Exception:
            results = []
        self._signals.done.emit(results)


class Poller(QObject):
    """定时扫描所有设备；结果通过 resultsReady 发回主线程。"""

    resultsReady = pyqtSignal(list)

    def __init__(self, interval_s: int = 60, parent: QObject = None,
                 log: Optional[Callable[[str], None]] = None):
        super().__init__(parent)
        self._interval_s = max(5, int(interval_s))
        self._busy = False
        self._log = log
        self._pool = QThreadPool.globalInstance()
        self._signals = _TaskSignals(self)
        self._signals.done.connect(self._on_done)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)

    # ---- 生命周期 -----------------------------------------------------
    def start(self) -> None:
        self._timer.start(self._interval_s * 1000)
        self.refresh()

    def stop(self) -> None:
        self._timer.stop()

    def set_interval(self, seconds: int) -> None:
        self._interval_s = max(5, int(seconds))
        if self._timer.isActive():
            self._timer.start(self._interval_s * 1000)

    @property
    def interval_s(self) -> int:
        return self._interval_s

    # ---- 刷新 ---------------------------------------------------------
    def refresh(self) -> None:
        if self._busy:
            return
        self._busy = True
        if self._log:
            self._log("开始读取设备…")
        self._pool.start(_ScanTask(self._signals))

    def _on_done(self, results: list) -> None:
        self._busy = False
        self.resultsReady.emit(results)

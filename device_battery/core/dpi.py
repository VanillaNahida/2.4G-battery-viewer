# -*- coding: utf-8 -*-
"""dpi.py —— 高 DPI 适配

Windows 上如果进程不声明 DPI 感知，系统会把窗口按位图拉伸（发糊）；
只声明 DPI 感知而不打开 Qt 的高 DPI 缩放，界面又会按 96 DPI 的物理像素画，
在 2K / 4K 屏幕上显得异常小。两者都要做：

    enable_dpi_awareness()      # 声明进程 DPI 感知（每屏感知）
    enable_high_dpi_scaling()   # 打开 Qt 的高 DPI 缩放（必须在 QApplication 之前）

必须在创建 QApplication **之前**调用，之后调用无效。
"""

from __future__ import annotations

import sys

# Windows 的 DPI 感知级别（shcore!SetProcessDpiAwareness）
_PER_MONITOR_DPI_AWARE = 2


def enable_dpi_awareness() -> bool:
    """让进程按「每屏 DPI 感知」运行；成功返回 True。"""
    if sys.platform != "win32":
        return False
    import ctypes

    # Windows 8.1+：shcore.SetProcessDpiAwareness
    try:
        shcore = ctypes.windll.shcore
        if shcore.SetProcessDpiAwareness(_PER_MONITOR_DPI_AWARE) == 0:
            return True
    except Exception:
        pass
    # Windows 7/8 与已经设置过的情况：退回系统级感知
    try:
        ctypes.windll.user32.SetProcessDPIAware()
        return True
    except Exception:
        return False


def enable_high_dpi_scaling() -> None:
    """打开 Qt 的高 DPI 缩放（小数倍率按原值处理，不取整）。"""
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QApplication

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    try:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    except Exception:
        pass


def initial_window_size(base: tuple[int, int] = (1040, 720),
                        max_ratio: float = 0.92,
                        minimum: tuple[int, int] = (880, 580)) -> tuple[int, int]:
    """按当前屏幕可用区域算一个合适的初始窗口大小（逻辑像素）。

    高 DPI 缩放打开后，坐标已经是逻辑像素，所以这里只需保证
    「不要超出屏幕、也不要小到内容挤成一团」。
    """
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance()
    screen = app.primaryScreen() if app is not None else None
    if screen is None:
        return base
    avail = screen.availableGeometry()
    width = min(base[0], max(minimum[0], int(avail.width() * max_ratio)))
    height = min(base[1], max(minimum[1], int(avail.height() * max_ratio)))
    return width, height

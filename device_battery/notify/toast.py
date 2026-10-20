# -*- coding: utf-8 -*-
"""toast.py —— Windows 系统通知

只走系统通知渠道，不用程序自绘的弹窗：

  1. 首选 `Shell_NotifyIcon(NIF_INFO)`（也就是 `QSystemTrayIcon.showMessage`），
     通知图标用 **Information**，标题 = 标题、正文 = 内容，会进 Windows 通知中心；
  2. 万一没有可用的托盘图标（极端情况），退回 WinRT toast（同样带标题 / 正文，
     AUMID 保证它归属于「设备电量」）。

发送失败只记录，不影响主流程。
"""

from __future__ import annotations

import ctypes
import os
import sys
from typing import Callable, Optional

APP_ID = "设备电量"
AUMID = "DeviceBattery.Viewer"
SHORTCUT_NAME = "设备电量.lnk"

# 由主程序注入：返回一个当前可见的托盘图标（QSystemTrayIcon），没有则返回 None
_tray_provider: Optional[Callable[[], object]] = None
_registered: Optional[bool] = None


def set_tray_provider(provider: Optional[Callable[[], object]]) -> None:
    global _tray_provider
    _tray_provider = provider


# --------------------------------------------------------------------------
# 通知身份（WinRT toast 需要）
# --------------------------------------------------------------------------
def _set_process_app_id() -> bool:
    if sys.platform != "win32":
        return False
    try:
        hr = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            ctypes.c_wchar_p(AUMID))
        return hr == 0
    except Exception:
        return False


def apply_process_app_id() -> bool:
    """只设置进程级 AUMID（任务栏 / 通知身份），不建快捷方式。"""
    try:
        return _set_process_app_id()
    except Exception:
        return False


def ensure_app_id(log: Optional[Callable[[str], None]] = None) -> bool:
    """注册通知身份（进程 AUMID + 开始菜单快捷方式），只做一次。"""
    global _registered
    if _registered is not None:
        return _registered
    if sys.platform != "win32":
        _registered = False
        return False

    ok = _set_process_app_id()
    try:
        from device_battery.core import autostart, win_shell

        lnk = os.path.join(win_shell.programs_dir(), SHORTCUT_NAME)
        if not win_shell.shortcut_exists(lnk):
            target = autostart.launcher_target()
            ok = win_shell.create_shortcut(
                lnk, target,
                arguments=autostart.launcher_arguments(),
                workdir=str(autostart.BASE_DIR),
                description="设备电量监视器",
                icon=target,
                app_id=AUMID,
            ) and ok
    except Exception as e:
        if log:
            log(f"注册通知身份失败：{e}")
    _registered = ok
    return ok


# --------------------------------------------------------------------------
# 发送
# --------------------------------------------------------------------------
def _send_tray_bubble(title: str, message: str) -> bool:
    """托盘气泡（NIF_INFO / NIIF_INFO）：Windows 原生通知，带 info 图标。"""
    provider = _tray_provider
    if provider is None:
        return False
    try:
        icon = provider()
    except Exception:
        return False
    if icon is None:
        return False
    try:
        from PyQt5.QtWidgets import QSystemTrayIcon
        if not icon.isVisible():
            return False
        icon.showMessage(title, message, QSystemTrayIcon.Information, 8000)
        return True
    except Exception:
        return False


def _send_winrt(title: str, message: str,
                log: Optional[Callable[[str], None]] = None) -> bool:
    ensure_app_id(log)
    try:
        from winotify import Notification, audio
        toast = Notification(app_id=AUMID, title=title, msg=message)
        toast.set_audio(audio.Silent, loop=False)
        toast.show()
        return True
    except Exception as e:
        if log:
            log(f"发送通知失败：{e}")
        return False


def show(title: str, message: str,
         log: Optional[Callable[[str], None]] = None) -> bool:
    """发一条 Windows 系统通知：标题 = title，内容 = message，图标 = info。"""
    if _send_tray_bubble(title, message):
        return True
    return _send_winrt(title, message, log)

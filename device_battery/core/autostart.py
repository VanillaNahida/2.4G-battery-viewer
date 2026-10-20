# -*- coding: utf-8 -*-
"""autostart.py —— 开机自启（启动文件夹里的快捷方式）

实现方式：在「启动」文件夹放一个 .lnk 指向 venv 的 pythonw.exe + `-m device_battery
--minimized`。这样任务管理器 ->「启动」标签里能直接看到「电量托盘」，可以启用/禁用。

同时写 `StartupApproved` 注册表值，让任务管理器里的开关状态和这里保持一致。

重要约定（沿用旧版教训）：**只读不改**——常驻程序绝不替用户"纠正"系统设置，
只在用户主动开关时才写。
"""

from __future__ import annotations

import os
import sys
from typing import Optional

from .paths import BASE_DIR
from . import win_shell

STARTUP_LNK_NAME = "电量托盘.lnk"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
STARTUP_APPROVED_FOLDER = (r"Software\Microsoft\Windows\CurrentVersion"
                           r"\Explorer\StartupApproved\StartupFolder")

# 早期版本写在注册表 Run 里的值名，启动时顺手清掉（迁移用）
LEGACY_RUN_VALUE = "DeviceBatteryTray"

MODULE_ARGS = "-m device_battery --minimized"
FROZEN_ARGS = "--minimized"


def is_frozen() -> bool:
    """是否是 PyInstaller 打出来的 exe。"""
    return bool(getattr(sys, "frozen", False))


def pythonw_path() -> str:
    """当前解释器对应的 pythonw.exe（避免弹黑窗）。"""
    exe = sys.executable or ""
    cand = os.path.join(os.path.dirname(exe), "pythonw.exe")
    return cand if os.path.exists(cand) else exe


def launcher_target() -> str:
    """快捷方式要指向的可执行文件：打包后就是 exe 自己。"""
    if is_frozen():
        return str(os.path.abspath(sys.executable))
    return pythonw_path()


def launcher_arguments() -> str:
    """快捷方式参数：打包后不需要 -m device_battery。"""
    return FROZEN_ARGS if is_frozen() else MODULE_ARGS


def autostart_command() -> str:
    return f'"{launcher_target()}" {launcher_arguments()}'


def startup_lnk() -> str:
    return os.path.join(win_shell.startup_dir(), STARTUP_LNK_NAME)


def _startup_approved() -> Optional[bool]:
    """任务管理器里的启用状态：True 启用 / False 禁用 / None 没记录。"""
    import winreg
    base = os.path.basename(startup_lnk())
    names = (base, os.path.splitext(base)[0])
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_APPROVED_FOLDER,
                            0, winreg.KEY_READ) as k:
            for name in names:
                try:
                    data, _ = winreg.QueryValueEx(k, name)
                except OSError:
                    continue
                if isinstance(data, (bytes, bytearray)) and data:
                    return data[0] != 0x03        # 0x03 = 已禁用
    except OSError:
        pass
    return None


def _set_startup_approved(enabled: bool) -> None:
    import winreg
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, STARTUP_APPROVED_FOLDER,
                                0, winreg.KEY_SET_VALUE) as k:
            data = bytes([0x02 if enabled else 0x03]) + bytes(11)
            winreg.SetValueEx(k, os.path.basename(startup_lnk()), 0,
                              winreg.REG_BINARY, data)
    except OSError:
        pass


def _clear_startup_approved() -> None:
    import winreg
    base = os.path.basename(startup_lnk())
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, STARTUP_APPROVED_FOLDER,
                                0, winreg.KEY_SET_VALUE) as k:
            for name in (base, os.path.splitext(base)[0]):
                try:
                    winreg.DeleteValue(k, name)
                except OSError:
                    pass
    except OSError:
        pass


def legacy_autostart_enabled() -> bool:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_READ) as k:
            val, _ = winreg.QueryValueEx(k, LEGACY_RUN_VALUE)
            return bool(val)
    except OSError:
        return False


def _clear_legacy_autostart() -> None:
    import winreg
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                                winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, LEGACY_RUN_VALUE)
    except OSError:
        pass


def is_autostart_enabled() -> bool:
    """开机自启是否生效：快捷方式在、且没被任务管理器禁用。"""
    if win_shell.shortcut_exists(startup_lnk()):
        return _startup_approved() is not False
    return legacy_autostart_enabled()


def set_autostart(enabled: bool) -> bool:
    """开关开机自启。"""
    if enabled:
        ok = win_shell.create_shortcut(
            startup_lnk(), launcher_target(),
            arguments=launcher_arguments(),
            workdir=str(BASE_DIR),
            description="设备电量托盘：常驻显示设备电量",
            icon=launcher_target())
        _set_startup_approved(True)
    else:
        _clear_startup_approved()
        ok = (win_shell.remove_shortcut(startup_lnk())
              or not win_shell.shortcut_exists(startup_lnk()))
    _clear_legacy_autostart()          # 迁移：清掉旧的注册表项
    return ok


def autostart_status() -> dict:
    """给界面/命令行看的自启状态摘要。"""
    lnk = startup_lnk()
    approved = _startup_approved()
    return {
        "enabled": is_autostart_enabled(),
        "method": "启动文件夹快捷方式（任务管理器可见）",
        "shortcut": lnk,
        "shortcut_exists": win_shell.shortcut_exists(lnk),
        "taskmanager_state": ("已启用" if approved is not False
                              else "已被任务管理器禁用")
                              if approved is not None else "未记录（默认启用）",
        "target": autostart_command(),
        "legacy_registry": legacy_autostart_enabled(),
    }

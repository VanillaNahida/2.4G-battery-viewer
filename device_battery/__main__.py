# -*- coding: utf-8 -*-
"""__main__.py —— 程序入口

命令行用法：
    python -m device_battery                启动（主窗口 + 托盘）
    python -m device_battery --minimized    只留托盘（开机自启用）
    python -m device_battery --once         命令行读一次，打印所有设备
    python -m device_battery --bluetooth    只列出蓝牙设备与电量
    python -m device_battery --status       打印配置 / 开机自启 / 是否已有实例在跑
    python -m device_battery --quit         通知正在运行的实例退出
    python -m device_battery --debug        输出调试日志到控制台
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from .core import autostart, config as cfgmod, single_instance
from .devices import scan_all


# --------------------------------------------------------------------------
# 命令行模式（不需要图形界面）
# --------------------------------------------------------------------------
def _cmd_once() -> int:
    readings = scan_all()
    if not readings:
        print("未检测到任何设备")
        return 1
    for r in readings:
        name = r.info.name if r.info else r.key
        if r.online and r.level is not None:
            extra = f"   {r.detail}" if r.detail else ""
            print(f"{name}: {r.level}%{extra}")
        else:
            print(f"{name}: 读取失败 —— {r.error or '未知原因'}")
    return 0


def _cmd_bluetooth() -> int:
    from .devices.bluetooth import BluetoothProvider
    provider = BluetoothProvider()
    infos = provider.enumerate()
    if not infos:
        print("没有检测到带电量属性的蓝牙设备")
        return 1
    for info in infos:
        r = provider.read(info)
        addr = info.params.get("address") or "-"
        if r.online and r.level is not None:
            print(f"{info.name}  ({info.kind})  电量={r.level}%  地址={addr}")
        else:
            print(f"{info.name}  ({info.kind})  {r.error}  地址={addr}")
    return 0


def _cmd_status() -> int:
    from PyQt5.QtCore import QCoreApplication
    app = QCoreApplication(sys.argv[:1])       # QLocalSocket 需要事件循环基础
    assert app is not None
    cfg = cfgmod.load()
    print("配置：", json.dumps(cfg, ensure_ascii=False, indent=2))
    st = autostart.autostart_status()
    print("开机自启：", "已启用" if st["enabled"] else "未启用")
    print("  方式：", st["method"])
    print("  快捷方式：", st["shortcut"], "(存在)" if st["shortcut_exists"] else "(不存在)")
    print("  任务管理器状态：", st["taskmanager_state"])
    print("  目标：", st["target"])
    print("已在运行实例：", single_instance.is_running())
    return 0


def _cmd_quit() -> int:
    from PyQt5.QtCore import QCoreApplication
    app = QCoreApplication(sys.argv[:1])
    assert app is not None
    ok = single_instance.send_to_running("quit")
    print("已通知退出" if ok else "没有正在运行的实例")
    return 0 if ok else 1


# --------------------------------------------------------------------------
# 图形界面模式
# --------------------------------------------------------------------------
def _run_gui(minimized: bool, debug: bool) -> int:
    from PyQt5.QtWidgets import QApplication

    from .notify.manager import NotifyManager
    from .tray.poller import Poller
    from .tray.system_tray import SystemTray
    from .ui.main_window import MainWindow
    from .ui.theme import apply_theme

    app = QApplication([sys.argv[0]])
    app.setApplicationName("设备电量")
    app.setQuitOnLastWindowClosed(False)       # 关窗口不退出（默认挂到托盘）

    def log(msg: str) -> None:
        if debug:
            import time
            print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

    # 单实例
    instance = single_instance.SingleInstance()
    if not instance.try_lock():
        log("已有实例在运行，已通知它显示窗口，本实例退出")
        return 0

    cfg = cfgmod.load()
    apply_theme(cfg.get("theme", "auto"))

    notify_mgr = NotifyManager(cfg, log)
    tray = SystemTray(cfg, log=log)

    # 回调用字典持有，主程序稍后填好，界面/设置页在运行时取
    hooks = {"config_changed": lambda c: None, "refresh": lambda: None}
    window = MainWindow(
        cfg, hooks,
        test_alert=notify_mgr.test_alert,
        preview_sound=notify_mgr.preview_sound,
        log=log,
    )
    poller = Poller(int(cfg.get("interval", 60)), log=log)

    def show_window() -> None:
        window.show()
        window.raise_()
        window.activateWindow()

    def quit_app() -> None:
        log("退出")
        poller.stop()
        tray.cleanup()
        app.quit()

    def on_config_changed(new_cfg: dict) -> None:
        apply_theme(new_cfg.get("theme", "auto"))
        poller.set_interval(int(new_cfg.get("interval", 60)))
        tray.apply_config(new_cfg)
        notify_mgr.apply_config(new_cfg)
        window.apply_config(new_cfg)

    hooks["config_changed"] = on_config_changed
    hooks["refresh"] = poller.refresh

    def on_results(readings: list) -> None:
        tray.update(readings)
        window.update_readings(readings)
        notify_mgr.handle(readings)

    poller.resultsReady.connect(on_results)
    tray.open_ui.connect(show_window)
    tray.refresh_now.connect(poller.refresh)
    tray.open_settings.connect(lambda: (show_window(), window.show_settings()))
    tray.quit_app.connect(quit_app)
    instance.message_received.connect(
        lambda msg: show_window() if msg == "show"
        else quit_app() if msg == "quit" else None)

    if not minimized:
        show_window()
    poller.start()
    log("启动完成")
    return app.exec_()


# --------------------------------------------------------------------------
def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="设备电量：2.4G 外设 + 蓝牙设备")
    parser.add_argument("--once", action="store_true", help="命令行读一次并退出")
    parser.add_argument("--bluetooth", action="store_true", help="只列出蓝牙设备")
    parser.add_argument("--status", action="store_true", help="打印状态")
    parser.add_argument("--quit", action="store_true", help="通知已运行实例退出")
    parser.add_argument("--minimized", action="store_true", help="只留托盘不显示窗口")
    parser.add_argument("--debug", action="store_true", help="输出调试日志")
    args = parser.parse_args(argv)

    if args.once:
        return _cmd_once()
    if args.bluetooth:
        return _cmd_bluetooth()
    if args.status:
        return _cmd_status()
    if args.quit:
        return _cmd_quit()
    return _run_gui(minimized=args.minimized, debug=args.debug)


if __name__ == "__main__":
    sys.exit(main())

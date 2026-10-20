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
# --------------------------------------------------------------------------
# 主窗口的显示 / 隐藏（托盘单击用）
# --------------------------------------------------------------------------
def bring_to_front(window) -> None:
    """显示主窗口并置前（从隐藏 / 最小化状态都能拉回来）。"""
    if window.isMinimized():
        window.showNormal()
    else:
        window.show()
    window.raise_()
    window.activateWindow()


def toggle_window_visibility(window) -> None:
    """单击托盘图标：显示 / 隐藏主窗口。

    三种情况分开处理，避免"想置前却被收起来"：
      * 没显示 / 已最小化  -> 显示并置前
      * 已经在最前（有焦点）-> 隐藏到托盘
      * 显示着但在后面      -> 置前，不隐藏
    """
    if not window.isVisible() or window.isMinimized():
        bring_to_front(window)
    elif window.isActiveWindow():
        window.hide()
    else:
        bring_to_front(window)


def _run_gui(minimized: bool, debug: bool) -> int:
    from .core import dpi

    # 必须在创建 QApplication 之前：声明 DPI 感知 + 打开 Qt 的高 DPI 缩放
    dpi.enable_dpi_awareness()
    dpi.enable_high_dpi_scaling()

    from PyQt5.QtWidgets import QApplication

    from .core import fonts as fontmod
    from .notify import toast
    from .notify.manager import NotifyManager
    from .tray import icon_render
    from .tray.poller import Poller
    from .tray.system_tray import SystemTray
    from .ui.main_window import MainWindow
    from .ui.theme import apply_theme

    app = QApplication([sys.argv[0]])
    app.setApplicationName("设备电量")
    app.setQuitOnLastWindowClosed(False)       # 关窗口不退出（默认挂到托盘）

    # 程序 / 窗口 / 任务栏图标用 assets/logo.ico（托盘图标另算，见 tray/icon_render）
    from PyQt5.QtGui import QIcon

    from .core.paths import ASSETS_DIR

    logo = ASSETS_DIR / "logo.ico"
    if not logo.exists():
        logo = ASSETS_DIR / "logo.png"
    if logo.exists():
        app.setWindowIcon(QIcon(str(logo)))
    # 任务栏 / 通知身份（和开始菜单快捷方式用同一个 AUMID）。
    # Windows 拿这个快捷方式的图标当任务栏按钮和通知的图标，所以启动时
    # 顺手核对一遍：快捷方式过期（比如曾经从源码跑过）会导致显示 Python 图标。
    try:
        from .notify import toast
        toast.ensure_app_id(log=None)
    except Exception:
        pass

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

    # 字体：先注册（MiSans 默认 + 用户加载的字体文件），再应用界面字体
    fontmod.load_default_fonts()
    fontmod.load_extra_fonts(cfgmod.extra_font_files(cfg))
    applied_font = cfgmod.ui_font(cfg)
    fontmod.apply_ui_font(applied_font)
    icon_render.set_font_family(
        fontmod.icon_font_family(cfgmod.tray_font(cfg)))
    icon_render.set_level_thresholds(*cfgmod.level_thresholds(cfg))

    apply_theme(cfg.get("theme", "auto"))

    notify_mgr = NotifyManager(cfg, log)
    tray = SystemTray(cfg, log=log)
    # 系统通知走托盘气泡（带 info 图标），需要拿一个可见的托盘图标
    toast.set_tray_provider(tray.notify_icon)

    # 回调用字典持有，主程序稍后填好，界面/设置页在运行时取
    hooks = {"config_changed": lambda c: None, "refresh": lambda: None}
    window = MainWindow(
        cfg, hooks,
        test_alert=notify_mgr.test_alert,
        preview_sound=notify_mgr.preview_sound,
        test_notify=notify_mgr.test_notification,
        log=log,
    )
    poller = Poller(int(cfg.get("interval", 60)), log=log)

    def show_window() -> None:
        bring_to_front(window)

    def toggle_window() -> None:
        toggle_window_visibility(window)


    def quit_app() -> None:
        log("退出")
        poller.stop()
        tray.cleanup()
        app.quit()

    def on_config_changed(new_cfg: dict) -> None:
        nonlocal applied_font
        apply_theme(new_cfg.get("theme", "auto"))
        icon_render.set_level_thresholds(*cfgmod.level_thresholds(new_cfg))
        poller.set_interval(int(new_cfg.get("interval", 60)))
        tray.apply_config(new_cfg)
        notify_mgr.apply_config(new_cfg)
        window.apply_config(new_cfg)

        wanted = cfgmod.ui_font(new_cfg)
        if wanted != applied_font:
            fontmod.load_extra_fonts(cfgmod.extra_font_files(new_cfg))
            fontmod.apply_ui_font(wanted)
            applied_font = wanted

    hooks["config_changed"] = on_config_changed
    hooks["refresh"] = poller.refresh

    def on_results(readings: list) -> None:
        tray.update(readings)
        window.update_readings(readings)
        notify_mgr.handle(readings)

    poller.resultsReady.connect(on_results)
    def set_tray_mode(mode: str) -> None:
        cfg.setdefault("tray", {})["mode"] = mode
        cfgmod.save(cfg)
        on_config_changed(cfg)
        log(f"托盘图标形态切换为 {mode}")

    tray.tray_mode_changed.connect(set_tray_mode)
    tray.open_ui.connect(show_window)
    tray.toggle_ui.connect(toggle_window)
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
class _NullStream:
    """打包成 --noconsole 的 exe 时 sys.stdout 是 None，挡住 print 的异常。"""

    def write(self, *_args) -> int:
        return 0

    def flush(self) -> None:
        return None


def _guard_stdio() -> None:
    if sys.stdout is None:
        sys.stdout = _NullStream()
    if sys.stderr is None:
        sys.stderr = _NullStream()


def main(argv: Optional[list] = None) -> int:
    _guard_stdio()
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

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""build_exe.py —— 一键用 PyInstaller 把本程序打包成 exe

用法（在项目根目录执行）::

    uv run python build_exe.py              # 单文件：dist/设备电量.exe
    uv run python build_exe.py --onedir     # 目录版：dist/设备电量/设备电量.exe（启动更快）
    uv run python build_exe.py --console    # 带控制台，方便看报错
    uv run python build_exe.py --clean      # 先清掉 build/ 和 dist/
    uv run python build_exe.py --no-install # 不自动安装 PyInstaller

要点：
  * 程序图标用 `assets/logo.ico`（同时是 exe 的内嵌图标和窗口/任务栏图标；
    托盘图标仍由程序自己画电量，不受影响）；
  * **只打包运行时真正用到的资源**（白名单，见 ASSET_GLOBS）：
      - `assets/fonts/*.ttf`   界面 / 托盘字体（MiSans）
      - `assets/*.mp3`         提示音
      - `assets/logo.ico`      程序与窗口图标
    其余素材（logo.png、logo.svg、键鼠.png、设计稿 PNG…）一律不进 exe；
  * `config.json` 不打进去——运行时会生成在 **exe 同目录**，方便改；
  * 版本资源（Exe 属性 -> 详细信息里的文件说明 / 版权 / 版本号）来自
    `pyinstaller_version.txt`，通过 `--version-file` 交给 PyInstaller；
    版本号和 `pyproject.toml`、`device_battery.__version__` 不一致时会提醒。
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_ICON = ROOT / "assets" / "logo.ico"
DEFAULT_NAME = "设备电量"
DEFAULT_VERSION_FILE = ROOT / "pyinstaller_version.txt"
ENTRY = ROOT / "build" / "entry.py"

ENTRY_SOURCE = '''# -*- coding: utf-8 -*-
"""PyInstaller 入口（由 build_exe.py 生成）。"""
import sys

from device_battery.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
'''

# 用不到的大模块，排除掉能显著减小体积
EXCLUDES = [
    "tkinter", "matplotlib", "numpy", "scipy", "pandas", "PIL",
    "PyQt5.QtWebEngineWidgets", "PyQt5.QtWebEngineCore", "PyQt5.QtWebEngine",
    "PyQt5.QtQml", "PyQt5.QtQuick", "PyQt5.QtQuickWidgets", "PyQt5.Qt3DCore",
    "PyQt5.QtBluetooth", "PyQt5.QtNfc", "PyQt5.QtPositioning",
    "PyQt5.QtSerialPort", "PyQt5.QtSql", "PyQt5.QtTest", "PyQt5.QtDesigner",
]

HIDDEN_IMPORTS = ["winotify", "qfluentwidgets", "PyQt5.QtMultimedia"]

# 运行时真正需要的资源（相对 assets/ 的 glob）。加文件时改这里就行。
ASSET_GLOBS = ("fonts/*.ttf", "fonts/*.otf", "*.mp3", "logo.ico")


def log(message: str) -> None:
    print(f"[build] {message}", flush=True)


def _has_module(name: str) -> bool:
    import importlib.util
    return importlib.util.find_spec(name) is not None


def _install_pyinstaller() -> bool:
    """装 PyInstaller：优先 pip，其次 uv（本项目用 uv 建的 venv 里可能没有 pip）。"""
    installers: list[list[str]] = []
    if _has_module("pip"):
        installers.append([sys.executable, "-m", "pip", "install", "pyinstaller"])
    uv = shutil.which("uv")
    if uv:
        installers.append([uv, "pip", "install", "--python", sys.executable,
                           "pyinstaller"])
    if not installers:
        installers.append([sys.executable, "-m", "ensurepip", "--upgrade"])
        installers.append([sys.executable, "-m", "pip", "install", "pyinstaller"])
    for cmd in installers:
        log("安装：" + " ".join(cmd))
        if subprocess.run(cmd).returncode == 0:
            return True
    return False


def check_pyinstaller(auto_install: bool) -> bool:
    try:
        import PyInstaller  # noqa: F401
        return True
    except ImportError:
        pass
    if not auto_install:
        log("未安装 PyInstaller，请先执行：pip install pyinstaller")
        return False
    log("未检测到 PyInstaller，正在自动安装…")
    if not _install_pyinstaller():
        log("自动安装失败，请手动安装：uv pip install pyinstaller")
        return False
    return check_pyinstaller(auto_install=False)


def collect_assets() -> tuple[list[Path], list[Path]]:
    """按白名单挑出要打包的资源，返回 (要打包的, 被跳过的)。"""
    root = ROOT / "assets"
    keep: list[Path] = []
    for pattern in ASSET_GLOBS:
        for path in sorted(root.glob(pattern)):
            if path.is_file() and path not in keep:
                keep.append(path)
    skip = [p for p in sorted(root.rglob("*")) if p.is_file() and p not in keep]
    return keep, skip


def check_version_consistency(version_file: Path) -> None:
    """版本文件里的 filevers 与代码里的 __version__ 不一致时提醒（不阻断）。"""
    import re

    try:
        text = version_file.read_text(encoding="utf-8")
        code = (ROOT / "device_battery" / "__init__.py").read_text(encoding="utf-8")
    except OSError:
        return
    in_file = re.search(r"filevers\s*=\s*\((\d+)\s*,\s*(\d+)\s*,\s*(\d+)", text)
    in_code = re.search(r'__version__\s*=\s*"([\d.]+)"', code)
    if in_file and in_code:
        file_ver = ".".join(in_file.groups())
        if file_ver != in_code.group(1):
            log(f"提醒：{version_file.name} 里的版本是 {file_ver}，"
                f"而 __version__ 是 {in_code.group(1)}，两处不一致")


def write_entry() -> Path:
    ENTRY.parent.mkdir(parents=True, exist_ok=True)
    ENTRY.write_text(ENTRY_SOURCE, encoding="utf-8")
    return ENTRY


def build(args: argparse.Namespace) -> int:
    icon = Path(args.icon).resolve()
    if not icon.is_file():
        log(f"找不到图标文件：{icon}")
        return 2

    if not (ROOT / "assets").is_dir():
        log(f"找不到资源目录：{ROOT / 'assets'}")
        return 2

    version_file: Path | None = None
    if args.version_file:
        version_file = Path(args.version_file).resolve()
        if version_file.is_file():
            check_version_consistency(version_file)
            log(f"版本资源：{version_file}")
        else:
            log(f"找不到版本信息文件：{version_file}（本次不带版本资源打包）")
            version_file = None
    else:
        log("未指定版本资源文件，本次不带版本资源打包")

    keep, skip = collect_assets()
    if not keep:
        log("没有匹配到任何资源文件，请检查 assets/ 目录")
        return 2
    total_mb = sum(p.stat().st_size for p in keep) / (1024 * 1024)
    log(f"打包资源 {len(keep)} 个（{total_mb:.2f} MB）：")
    for path in keep:
        log(f"  + {path.relative_to(ROOT).as_posix()}")
    if skip:
        skipped_mb = sum(p.stat().st_size for p in skip) / (1024 * 1024)
        names = ", ".join(p.name for p in skip[:6])
        more = "" if len(skip) <= 6 else f" 等 {len(skip)} 个"
        log(f"跳过 {len(skip)} 个未使用文件（{skipped_mb:.2f} MB）：{names}{more}")

    if args.clean:
        for folder in ("build", "dist"):
            target = ROOT / folder
            if target.exists():
                log(f"清理 {target}")
                shutil.rmtree(target, ignore_errors=True)

    entry = write_entry()

    cmd: list[str] = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--name", args.name,
        "--icon", str(icon),
        "--paths", str(ROOT),
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build"),
        "--specpath", str(ROOT / "build"),
    ]
    if version_file is not None and sys.platform == "win32":
        cmd += ["--version-file", str(version_file)]
    cmd += ["--onefile"] if args.onefile else ["--onedir"]
    cmd += ["--console"] if args.console else ["--windowed"]
    if args.clean:
        cmd.append("--clean")
    for module in EXCLUDES:
        cmd += ["--exclude-module", module]
    for module in HIDDEN_IMPORTS:
        cmd += ["--hidden-import", module]
    # 逐个文件塞进 assets/ 下对应的子目录（只有白名单里的）
    for path in keep:
        relative = path.relative_to(ROOT / "assets")
        dest = "assets" if relative.parent == Path(".") else f"assets/{relative.parent.as_posix()}"
        cmd += ["--add-data", f"{path}{os.pathsep}{dest}"]
    cmd.append(str(entry))

    log("执行：" + " ".join(cmd))
    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode != 0:
        log("打包失败，请看上面的 PyInstaller 输出")
        return result.returncode

    if args.onefile:
        exe = ROOT / "dist" / f"{args.name}.exe"
    else:
        exe = ROOT / "dist" / args.name / f"{args.name}.exe"

    log("打包完成")
    if exe.exists():
        size = exe.stat().st_size / (1024 * 1024)
        log(f"输出：{exe}  （{size:.1f} MB）")
        log("提示：config.json 会在首次运行时生成在 exe 同目录")
    else:
        log(f"没有找到预期输出：{exe}")
        return 3
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="一键打包 设备电量 为 exe")
    parser.add_argument("--onedir", dest="onefile", action="store_false",
                        help="打成目录版（启动更快，推荐长期使用）")
    parser.add_argument("--onefile", dest="onefile", action="store_true",
                        help="打成单文件（默认）")
    parser.set_defaults(onefile=True)
    parser.add_argument("--console", action="store_true",
                        help="保留控制台窗口（调试用，--once/--status 才看得到输出）")
    parser.add_argument("--clean", action="store_true",
                        help="打包前清掉 build/ 与 dist/")
    parser.add_argument("--name", default=DEFAULT_NAME, help="exe 名字")
    parser.add_argument("--icon", default=str(DEFAULT_ICON),
                        help="exe / 窗口图标（.ico）")
    parser.add_argument("--version-file", default=str(DEFAULT_VERSION_FILE),
                        help="exe 版本资源（文件说明 / 版权 / 版本号），"
                             "传空字符串则不使用")
    parser.add_argument("--no-install", action="store_true",
                        help="缺少 PyInstaller 时不自动安装")
    args = parser.parse_args(argv)

    if not check_pyinstaller(auto_install=not args.no_install):
        return 1
    return build(args)


if __name__ == "__main__":
    raise SystemExit(main())

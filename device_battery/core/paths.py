# -*- coding: utf-8 -*-
"""paths.py —— 项目内所有固定路径

两种运行方式都要能对：

* **源码运行**（uv 可编辑安装）：项目根 = 本文件往上两级，资源在 <root>/assets；
* **PyInstaller 打包后**：只读资源被塞进 exe（onefile 会解压到临时目录，
  路径在 `sys._MEIPASS`），而 `config.json` 这类用户文件**放在 exe 旁边**。

所以这里拆成两个根：
    BASE_DIR   可写根（exe 所在目录 / 项目根）—— config.json、tray_config.json
    BUNDLE_DIR 只读资源根（_MEIPASS / 项目根）—— assets（字体、提示音、logo）
"""

from __future__ import annotations

import sys
from pathlib import Path


def _app_dir() -> Path:
    """可写根：冻结后是 exe 所在目录，源码运行时是项目根。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _bundle_dir() -> Path:
    """只读资源根：onefile 解压目录，否则与可写根相同。"""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return _app_dir()


BASE_DIR = _app_dir()
BUNDLE_DIR = _bundle_dir()
ASSETS_DIR = BUNDLE_DIR / "assets"
CONFIG_PATH = BASE_DIR / "config.json"
LEGACY_CONFIG_PATH = BASE_DIR / "tray_config.json"

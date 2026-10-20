# -*- coding: utf-8 -*-
"""paths.py —— 项目内所有固定路径

BASE_DIR 取源码树根目录（本文件位于 <root>/device_battery/core/paths.py，
再往上两级就是项目根），因此用 uv 的「可编辑安装」运行时，
无论从哪个工作目录启动都能拿到正确的项目根。
"""

from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
ASSETS_DIR = BASE_DIR / "assets"
CONFIG_PATH = BASE_DIR / "config.json"
LEGACY_CONFIG_PATH = BASE_DIR / "tray_config.json"

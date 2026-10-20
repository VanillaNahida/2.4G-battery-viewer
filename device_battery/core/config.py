# -*- coding: utf-8 -*-
"""config.py —— 配置读写

配置项见 DEFAULTS。要点：
  * 缺键自动补默认值（新旧版本配置互相兼容）；
  * `notify.overrides` 以**设备 key** 为键，实现「每个设备单独设预警」；
  * 旧版 `tray_config.json` 会自动迁移到 `config.json`（旧文件改名 .bak）。
"""

from __future__ import annotations

import copy
import json
import os
from typing import Optional

from .paths import ASSETS_DIR, BASE_DIR, CONFIG_PATH, LEGACY_CONFIG_PATH

DEFAULTS: dict = {
    "interval": 60,             # 刷新间隔（秒）
    "autostart": False,         # 开机自启
    "theme": "auto",            # auto / light / dark
    "quit_on_close": False,     # 关闭窗口时退出（否则隐藏到托盘）
    "show_absent_devices": False,
    "tray": {
        "mode": "number",       # number / ring / icon
        "multi_icon": True,     # 多设备时每个设备一个托盘图标
        "hover_tooltip": True,  # 悬停是否显示电量提示
        "include_bluetooth": False,   # 蓝牙设备是否也上托盘
    },
    "notify": {
        "enabled": True,
        "threshold": 20,        # 全局低电量阈值
        "sound_enabled": True,
        "sound": "assets/notification-2.mp3",
        "volume": 70,           # 0-100
        "cooldown_minutes": 30,
        "overrides": {},        # {"<设备key>": {"enabled":..,"threshold":..,"sound":..}}
    },
}

INTERVAL_CHOICES = [(30, "30 秒"), (60, "1 分钟"), (120, "2 分钟"),
                    (300, "5 分钟"), (600, "10 分钟"), (1800, "30 分钟")]

OVERRIDE_FIELDS = ("enabled", "threshold", "sound")


def _merge(base: dict, data: dict) -> dict:
    """把 data 合进 base（只认 base 里已有的键，嵌套字典递归）。"""
    out = copy.deepcopy(base)
    for k, v in (data or {}).items():
        if k not in out:
            continue
        if isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def _migrate_legacy() -> Optional[dict]:
    """旧版 tray_config.json -> 新配置。"""
    if not os.path.exists(LEGACY_CONFIG_PATH):
        return None
    try:
        with open(LEGACY_CONFIG_PATH, "r", encoding="utf-8") as f:
            old = json.load(f)
    except Exception:
        return None
    migrated: dict = {}
    if isinstance(old, dict):
        for k in ("interval", "autostart"):
            if k in old:
                migrated[k] = old[k]
    try:
        os.replace(LEGACY_CONFIG_PATH, str(LEGACY_CONFIG_PATH) + ".bak")
    except OSError:
        pass
    return migrated


def load(path: Optional[str] = None) -> dict:
    target = path or str(CONFIG_PATH)
    data = None
    if os.path.exists(target):
        try:
            with open(target, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = None
    if data is None:
        data = _migrate_legacy()
    cfg = _merge(DEFAULTS, data or {})
    if data is None or not os.path.exists(target):
        save(cfg, path)
    return cfg


def save(cfg: dict, path: Optional[str] = None) -> None:
    target = path or str(CONFIG_PATH)
    cfg = _merge(DEFAULTS, cfg)
    tmp = target + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(tmp, target)
    except OSError:
        pass


# --------------------------------------------------------------------------
# 每设备预警：全局默认 + override
# --------------------------------------------------------------------------
def device_notify(cfg: dict, key: str) -> dict:
    """取某设备生效的预警设置（override 优先，其余回落全局）。"""
    global_notify = cfg.get("notify", DEFAULTS["notify"])
    result = {
        "enabled": bool(global_notify.get("enabled", True)),
        "threshold": int(global_notify.get("threshold", 20)),
        "sound": global_notify.get("sound", DEFAULTS["notify"]["sound"]),
        "sound_enabled": bool(global_notify.get("sound_enabled", True)),
        "volume": int(global_notify.get("volume", 70)),
        "cooldown_minutes": int(global_notify.get("cooldown_minutes", 30)),
    }
    for field, value in (global_notify.get("overrides", {}).get(key) or {}).items():
        if field in OVERRIDE_FIELDS or field in result:
            result[field] = value
    return result


def set_device_notify(cfg: dict, key: str, **fields) -> dict:
    """写入某设备的预警覆盖（只接受 OVERRIDE_FIELDS）。"""
    overrides = cfg.setdefault("notify", {}).setdefault("overrides", {})
    item = dict(overrides.get(key) or {})
    for field, value in fields.items():
        if field in OVERRIDE_FIELDS:
            item[field] = value
    if item:
        overrides[key] = item
    else:
        overrides.pop(key, None)
    return cfg


def clear_device_notify(cfg: dict, key: str) -> dict:
    """清掉某设备的覆盖，回到全局默认。"""
    (cfg.setdefault("notify", {}).setdefault("overrides", {})).pop(key, None)
    return cfg


def has_override(cfg: dict, key: str) -> bool:
    return bool((cfg.get("notify", {}).get("overrides", {}) or {}).get(key))


# --------------------------------------------------------------------------
# 提示音路径
# --------------------------------------------------------------------------
def resolve_sound(cfg: dict, path: str) -> str:
    """提示音路径：相对路径按项目根解析，绝对路径原样返回。"""
    if not path:
        return ""
    p = str(path)
    if os.path.isabs(p) and os.path.exists(p):
        return p
    cand = os.path.join(str(BASE_DIR), p)
    if os.path.exists(cand):
        return cand
    cand2 = os.path.join(str(ASSETS_DIR), p)
    if os.path.exists(cand2):
        return cand2
    return ""

# -*- coding: utf-8 -*-
"""config.py —— 配置读写

配置项见 DEFAULTS。要点：
  * 缺键自动补默认值（新旧版本配置互相兼容）；
  * 非法值（例如旧版本留下的 `"theme": 30`）在读取时纠正回默认值；
  * `notify.overrides` 以**设备 key** 为键，实现「每个设备单独设预警」；
  * 旧版 `tray_config.json` 会自动迁移到 `config.json`（旧文件改名 .bak）。
"""

from __future__ import annotations

import copy
import json
import os
from typing import Optional

from .paths import (ASSETS_DIR, BASE_DIR, BUNDLE_DIR, CONFIG_PATH,
                    LEGACY_CONFIG_PATH)

DEFAULTS: dict = {
    "interval": 60,             # 刷新间隔（秒）
    "autostart": False,         # 开机自启
    "theme": "auto",            # auto / light / dark
    "quit_on_close": False,     # 关闭窗口时退出（否则隐藏到托盘）
    "show_absent_devices": False,
    "ui": {
        "font": "MiSans",       # 界面字体（family 名；空 = 系统默认链）
        "battery_style": "ring",  # 主界面电量显示：ring（环内百分比）/ bar（进度条）
    },
    "tray": {
        "mode": "number",       # number / ring / icon
        "multi_icon": True,     # 多设备时每个设备一个托盘图标
        "hover_tooltip": True,  # 悬停是否显示电量提示
        "include_bluetooth": False,   # 蓝牙设备是否也上托盘
        "font": "MiSans",       # 托盘图标里的数字字体
    },
    "fonts": {
        # 用户通过「加载字体文件…」加入的字体（启动时自动注册）
        "extra_files": [],
    },
    "colors": {
        "orange_at": 30,        # 电量 <= 该值：橙色（环 / 数字）
        "red_at": 20,           # 电量 <= 该值：红色（优先级高于橙色）
    },
    "notify": {
        "enabled": True,
        "threshold": 20,        # 全局低电量阈值
        "sound_enabled": True,
        "sound": "assets/notification-2.mp3",
        "volume": 70,           # 0-100
        "cooldown_minutes": 30,
        "overrides": {},        # {"<设备key>": {"enabled":..,"threshold":..,"sound":..}}
        # 通知文案模板，支持魔法变量（见 notify/template.py）
        "title_template": "设备电量不足",
        "body_template": "{name}：{level_pct}（{status}）",

    },
}

INTERVAL_CHOICES = [(30, "30 秒"), (60, "1 分钟"), (120, "2 分钟"),
                    (300, "5 分钟"), (600, "10 分钟"), (1800, "30 分钟")]

THEME_CHOICES = [("auto", "跟随系统"), ("light", "浅色"), ("dark", "深色")]

TRAY_MODE_CHOICES = [("number", "数字图标"), ("ring", "环形电量"),
                     ("ring_only", "仅圆环"), ("icon", "纯图标")]

BATTERY_STYLE_CHOICES = [("ring", "环形电量（环内百分比）"),
                         ("bar", "进度条 + 百分比")]

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


def _one_of(value, choices, default):
    for candidate, _label in choices:
        if value == candidate:
            return candidate
    return default


def _sanitize(cfg: dict) -> dict:
    """把明显非法的值纠正回默认值（不猜用户意图，只回退）。"""
    try:
        cfg["interval"] = int(cfg.get("interval", DEFAULTS["interval"]))
    except (TypeError, ValueError):
        cfg["interval"] = DEFAULTS["interval"]

    cfg["theme"] = _one_of(cfg.get("theme"), THEME_CHOICES, DEFAULTS["theme"])

    ui = cfg.setdefault("ui", {})
    ui["battery_style"] = _one_of(ui.get("battery_style"),
                                  BATTERY_STYLE_CHOICES,
                                  DEFAULTS["ui"]["battery_style"])
    if not isinstance(ui.get("font"), str):
        ui["font"] = DEFAULTS["ui"]["font"]

    tray = cfg.setdefault("tray", {})
    tray["mode"] = _one_of(tray.get("mode"), TRAY_MODE_CHOICES,
                           DEFAULTS["tray"]["mode"])
    if not isinstance(tray.get("font"), str):
        tray["font"] = DEFAULTS["tray"]["font"]

    fonts = cfg.setdefault("fonts", {})
    files = fonts.get("extra_files")
    if not isinstance(files, list):
        files = []
    fonts["extra_files"] = [str(f) for f in files if isinstance(f, str)]

    colors = cfg.setdefault("colors", {})
    orange, red = level_thresholds(cfg)
    colors["orange_at"] = orange
    colors["red_at"] = red

    notify = cfg.setdefault("notify", {})
    for key in ("title_template", "body_template"):
        if not isinstance(notify.get(key), str):
            notify[key] = DEFAULTS["notify"][key]
    return cfg


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
    merged = _merge(DEFAULTS, data or {})
    # _sanitize 是原地修改，所以先留一份原始值用来判断「有没有被纠正过」
    cfg = _sanitize(copy.deepcopy(merged))
    if data is None or not os.path.exists(target) or cfg != merged:
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
# 取值小工具（读取嵌套配置，缺键回落默认）
# --------------------------------------------------------------------------
def ui_font(cfg: dict) -> str:
    return str((cfg.get("ui") or {}).get("font") or "")


def tray_font(cfg: dict) -> str:
    return str((cfg.get("tray") or {}).get("font") or "")


def level_thresholds(cfg: dict) -> tuple[int, int]:
    """颜色阈值 (橙色阈值, 红色阈值)，保证 红色 < 橙色、都在 1..100。"""
    colors = cfg.get("colors") or {}
    try:
        red = int(colors.get("red_at", DEFAULTS["colors"]["red_at"]))
        orange = int(colors.get("orange_at", DEFAULTS["colors"]["orange_at"]))
    except (TypeError, ValueError):
        red, orange = (DEFAULTS["colors"]["red_at"],
                       DEFAULTS["colors"]["orange_at"])
    red = min(max(1, red), 99)
    orange = min(max(red + 1, orange), 100)
    return orange, red


def battery_style(cfg: dict) -> str:
    return _one_of((cfg.get("ui") or {}).get("battery_style"),
                   BATTERY_STYLE_CHOICES, DEFAULTS["ui"]["battery_style"])


def extra_font_files(cfg: dict) -> list[str]:
    files = (cfg.get("fonts") or {}).get("extra_files") or []
    return [str(f) for f in files if isinstance(f, str)]


def render_templates(cfg: dict) -> tuple[str, str]:
    """通知模板 (标题, 正文)；缺键回落默认。"""
    notify = cfg.get("notify") or {}
    title = notify.get("title_template")
    body = notify.get("body_template")
    if not isinstance(title, str):
        title = DEFAULTS["notify"]["title_template"]
    if not isinstance(body, str):
        body = DEFAULTS["notify"]["body_template"]
    return title, body


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
# 资源路径（提示音 / 字体文件）
# --------------------------------------------------------------------------
def resolve_asset_path(path: str) -> str:
    """相对路径按项目根 / assets 解析，绝对路径原样返回；不存在返回空串。"""
    if not path:
        return ""
    p = str(path)
    if os.path.isabs(p) and os.path.exists(p):
        return p
    # 1) exe 旁边的相对路径（用户自己换的提示音放这里）
    cand = os.path.join(str(BASE_DIR), p)
    if os.path.exists(cand):
        return cand
    # 2) 打包进 exe 的资源（onefile 时是解包目录）
    cand2 = os.path.join(str(BUNDLE_DIR), p)
    if os.path.exists(cand2):
        return cand2
    # 3) 直接给 assets 里的文件名，如 "notification-1.mp3"
    cand3 = os.path.join(str(ASSETS_DIR), p)
    if os.path.exists(cand3):
        return cand3
    return ""


def resolve_sound(cfg: dict, path: str) -> str:
    """提示音路径：相对路径按项目根解析，绝对路径原样返回。"""
    return resolve_asset_path(path)

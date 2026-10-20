# -*- coding: utf-8 -*-
"""template.py —— 通知文案模板（魔法变量）

模板里用 `{变量名}` 占位，发送前换成真实值。写错的变量**原样保留**，
方便用户在通知里一眼看出自己拼错了，而不是被静默吞掉。

可用变量见 VARIABLES（设置页会把这份清单显示给用户）。
"""

from __future__ import annotations

import re
import time
from typing import Iterable, Optional

from device_battery.devices import (KIND_GAMEPAD, KIND_HEADSET,
                                    KIND_KEYBOARD, KIND_MOUSE, KIND_OTHER,
                                    Reading, charging_text)

KIND_NAMES = {
    KIND_MOUSE: "鼠标",
    KIND_KEYBOARD: "键盘",
    KIND_HEADSET: "耳机",
    KIND_GAMEPAD: "手柄",
    KIND_OTHER: "设备",
}

# (变量名, 说明) —— 顺序即设置页里的展示顺序
VARIABLES: list[tuple[str, str]] = [
    ("name", "设备名"),
    ("level", "电量数字，不含 %"),
    ("level_pct", "电量带百分号，如 35%"),
    ("status", "充电状态：充电中 / 放电中 / 充电状态未知"),
    ("charging", "充电状态简写：充电 / 未充电 / 未知"),
    ("kind", "设备类型：鼠标 / 键盘 / 耳机 / 手柄"),
    ("source", "数据来源：inphic / atk / darkrim / bluetooth"),
    ("transport", "连接方式：2.4G / USB / Bluetooth"),
    ("vid_pid", "VID:PID 或蓝牙地址"),
    ("threshold", "该设备的低电量阈值（%）"),
    ("time", "当前时间，如 21:30"),
    ("date", "当前日期，如 2024-05-20"),
    ("count", "当前设备数量"),
    ("min_name", "电量最低的设备名"),
    ("min_level", "电量最低设备的电量数字"),
    ("app", "程序名"),
]

_DEFAULT_SAMPLE_LEVEL = 15

_PATTERN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def render(template: str, context: dict) -> str:
    """把模板里的 `{变量}` 换成 context 里的值（不认识的变量原样保留）。"""
    if not template:
        return ""

    def replace(match: "re.Match[str]") -> str:
        key = match.group(1)
        if key in context:
            return str(context[key])
        return match.group(0)

    return _PATTERN.sub(replace, template)


def unknown_variables(template: str,
                      known: Optional[Iterable[str]] = None) -> list[str]:
    """找出模板里拼错的变量名（用于设置页提示）。"""
    names = set(known if known is not None else (v for v, _ in VARIABLES))
    out: list[str] = []
    for match in _PATTERN.finditer(template or ""):
        key = match.group(1)
        if key not in names and key not in out:
            out.append(key)
    return out


def _charging_word(charging: Optional[bool]) -> str:
    if charging is True:
        return "充电"
    if charging is False:
        return "未充电"
    return "未知"


def build_context(reading: Optional[Reading], *,
                  threshold: int = 20,
                  count: int = 0,
                  min_reading: Optional[Reading] = None,
                  app_name: str = "设备电量",
                  now: Optional[float] = None) -> dict:
    """把一次读数变成模板变量表。reading 为 None 时给一份示例数据。"""
    stamp = time.localtime(now if now is not None else time.time())

    if reading is None:
        level: Optional[int] = _DEFAULT_SAMPLE_LEVEL
        name = "示例设备"
        kind = KIND_OTHER
        source = "sample"
        transport = "2.4G"
        vid_pid = "0000:0000"
        charging: Optional[bool] = None
        status = charging_text(charging)
        key = "sample:device"
    else:
        info = reading.info
        level = reading.level
        name = info.name if info else reading.key
        kind = info.kind if info else KIND_OTHER
        source = info.source if info else ""
        transport = info.transport if info else ""
        vid_pid = ""
        if info is not None:
            vid_pid = (info.params.get("vid_pid")
                       or info.params.get("address") or "")
        charging = reading.charging
        status = charging_text(charging)
        if not reading.online:
            status = reading.error or "未连接"
        key = reading.key

    lowest = min_reading if min_reading is not None else reading
    lowest_level = lowest.level if lowest is not None else None
    lowest_name = ""
    if lowest is not None:
        lowest_name = lowest.info.name if lowest.info else lowest.key

    return {
        "name": name,
        "level": "--" if level is None else level,
        "level_pct": "--" if level is None else f"{level}%",
        "status": status,
        "charging": _charging_word(charging),
        "kind": KIND_NAMES.get(kind, "设备"),
        "source": source or "-",
        "transport": transport or "-",
        "vid_pid": vid_pid or "-",
        "threshold": threshold,
        "time": time.strftime("%H:%M", stamp),
        "date": time.strftime("%Y-%m-%d", stamp),
        "count": count,
        "min_name": lowest_name or name,
        "min_level": "--" if lowest_level is None else lowest_level,
        "app": app_name,
        "key": key,
    }

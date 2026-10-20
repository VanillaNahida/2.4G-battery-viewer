# -*- coding: utf-8 -*-
"""devices —— 设备抽象层与各来源实现

对外只暴露两个入口：
    providers()  -> 所有设备来源
    scan_all()   -> 扫一遍，返回所有设备的一次读数（Reading.info 里带展示信息）
"""

from __future__ import annotations

from typing import Optional

from .atk_vxe import AtkVxeProvider
from .base import (DeviceInfo, DeviceProvider, Reading, charging_text,
                    KIND_GAMEPAD, KIND_HEADSET, KIND_KEYBOARD, KIND_MOUSE,
                    KIND_OTHER)
from .bluetooth import BluetoothProvider
from .darkrim import DarkrimProvider
from .inphic_in9 import InphicProvider


def providers() -> list[DeviceProvider]:
    """所有设备来源。新增设备来源时在这里登记。"""
    return [
        InphicProvider(),      # 英菲克 IN9（2.4G）
        AtkVxeProvider(),      # ATK / VXE 无线鼠标（2.4G）
        DarkrimProvider(),     # DARKRIM 耳机（2.4G dongle）
        BluetoothProvider(),   # 蓝牙：耳机 / 键鼠 / 手柄（0..N 个）
    ]


def scan_all(debug=None) -> list[Reading]:
    """扫一遍所有来源，返回设备读数列表。

    单个来源出错不会影响其它来源；debug 传入可调用对象时会收到错误说明。
    """
    out: list[Reading] = []
    for provider in providers():
        try:
            infos = provider.enumerate()
        except Exception as e:
            if debug:
                debug(f"来源 {provider.source} 枚举失败：{e}")
            continue
        for info in infos:
            try:
                reading = provider.read(info)
            except Exception as e:
                reading = Reading(key=info.key, online=False,
                                  error=f"读取异常：{e}")
            reading.info = info
            out.append(reading)
    return out


def find_reading(readings: list[Reading], key: str) -> Optional[Reading]:
    for r in readings:
        if r.key == key:
            return r
    return None


__all__ = [
    "DeviceInfo", "DeviceProvider", "Reading", "charging_text",
    "KIND_GAMEPAD", "KIND_HEADSET", "KIND_KEYBOARD", "KIND_MOUSE", "KIND_OTHER",
    "providers", "scan_all", "find_reading",
]

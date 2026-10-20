# -*- coding: utf-8 -*-
"""base.py —— 设备抽象层

设计要点：蓝牙是「动态多设备」（插拔、增删），所以抽象不是「一个类 = 一个设备」，
而是「一个来源（Provider）可以枚举出 0..N 个设备」：

    DeviceProvider.enumerate() -> list[DeviceInfo]    # 未检测到就返回空列表
    DeviceProvider.read(info)  -> Reading             # 读一次电量

主程序只调用 devices.scan_all()，不关心具体来源怎么通信。
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

# 设备类别（决定托盘/卡片用哪个图标）
KIND_MOUSE = "mouse"
KIND_KEYBOARD = "keyboard"
KIND_HEADSET = "headset"
KIND_GAMEPAD = "gamepad"
KIND_OTHER = "other"


@dataclass
class DeviceInfo:
    """一个设备的身份信息（稳定标识 + 展示参数）。"""
    key: str                             # 全局唯一稳定 id，如 "inphic:in9"
    source: str                          # 来源标签："inphic"/"atk"/"darkrim"/"bluetooth"
    name: str                            # 显示名
    kind: str = KIND_OTHER               # 设备类别
    transport: str = ""                  # "2.4G" / "USB" / "Bluetooth"
    params: dict = field(default_factory=dict)
    # params 约定键：vid_pid / manufacturer / firmware / address / instance_id / protocol


@dataclass
class Reading:
    """一次读取结果。key 用于回指 DeviceInfo。"""
    key: str
    level: Optional[int] = None          # 0-100；None = 读不到
    charging: Optional[bool] = None      # True/False/None(未知)
    online: bool = False                 # 是否检测到设备
    error: str = ""                      # 失败原因（给卡片/提示用）
    detail: str = ""                     # 数据来源说明
    updated_at: float = field(default_factory=time.time)
    info: "Optional[DeviceInfo]" = None  # scan_all() 会填上，界面用它取展示信息


class DeviceProvider(ABC):
    """设备来源：一个模块实现一个来源，自己负责找接口。"""

    source: str = ""

    @abstractmethod
    def enumerate(self) -> list[DeviceInfo]:
        """列出当前存在的设备；没有就返回空列表，不抛异常。"""

    @abstractmethod
    def read(self, info: DeviceInfo) -> Reading:
        """读一次电量。"""


def charging_text(charging: Optional[bool]) -> str:
    """统一的状态文案（未知不臆测）。"""
    if charging is True:
        return "充电中"
    if charging is False:
        return "放电中"
    return "充电状态未知"

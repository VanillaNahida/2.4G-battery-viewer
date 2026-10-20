# -*- coding: utf-8 -*-
"""atk_vxe.py —— ATK / VXE / VGN 无线鼠标（Nordic 方案，含 4K 接收器）

协议要点（已在真机验证，实现见 hid/strategies.py 的厂商协议表）：
  * 协议 2：64 字节 Output Report，Report ID 0x08，命令 0x72；
    请求 `08 7D 72 02 00 01 07 01 00 …`；回复校验 `resp[1]==0x72 and resp[5]==0x07`，
    电量 = resp[7]。接口 UsagePage 0xFF05。
  * 协议 1：17 字节 Output Report，Report ID 0x08；
    请求 `04 00 … 00 49`；电量 = 回复第 6 字节，第 7 字节非 0 表示有线连接。
    接口 UsagePage 0xFF02（ATK 0x373B / VXE 0x3554）。
  * 收不到回复通常是鼠标休眠，提示用户动一下鼠标。

本模块只负责「找到这个来源的设备 + 取一次电量」，协议细节复用
hid/strategies.py 里已验证的厂商协议框架。
"""

from __future__ import annotations

from typing import Optional

from device_battery.hid import strategies as st
from device_battery.hid.hid_win import HidInterface

from .base import KIND_MOUSE, DeviceInfo, DeviceProvider, Reading

VIDS = (0x373B, 0x3554)      # 0x373B = ATK / 0x3554 = VXE
KEY = "atk:mouse"


def find_interface() -> Optional[HidInterface]:
    """找 ATK/VXE 无线鼠标的命令接口。"""
    for want_len in (64, 17):
        for page in (0xFF05, 0xFF02):
            for d in st.hw.enumerate_hid():
                if (d.vid in VIDS and d.usage_page == page
                        and d.output_len == want_len):
                    return d
    for page in (0xFF05, 0xFF02):
        for d in st.hw.enumerate_hid():
            if d.vid in VIDS and d.usage_page == page:
                return d
    return None


class AtkVxeProvider(DeviceProvider):
    """ATK / VXE 无线鼠标的设备来源。"""

    source = "atk"

    def enumerate(self) -> list[DeviceInfo]:
        iface = find_interface()
        if iface is None:
            return []
        return [DeviceInfo(
            key=KEY, source=self.source, name="ATK / VXE 无线鼠标",
            kind=KIND_MOUSE, transport="2.4G",
            params={"vid_pid": iface.vid_pid,
                    "protocol": "Nordic 厂商协议（Report ID 0x08）"},
        )]

    def read(self, info: DeviceInfo) -> Reading:
        iface = find_interface()
        if iface is None:
            return Reading(key=info.key, online=False,
                           error="没找到接收器（请把 2.4G 接收器插上）")
        try:
            res = (st.strategy_vendor_protocol(iface)
                   or st.strategy_standard_battery_usage(iface))
        except Exception as e:
            return Reading(key=info.key, online=True, error=f"读取出错：{e}")
        if res is None:
            return Reading(key=info.key, online=True,
                           error="这台设备没有可用的读取方式")
        if not res.ok:
            return Reading(key=info.key, online=True,
                           error=res.detail or "读取失败")
        charging: Optional[bool] = None
        if res.status == "charging":
            charging = True
        elif res.status == "discharging":
            charging = False
        return Reading(key=info.key, level=res.level, charging=charging,
                       online=True, detail=res.source)

# -*- coding: utf-8 -*-
r"""bbw_lingyun.py —— 墨将（BIGBIG WON）凌云 手柄电量（2.4G / 有线）

协议来源：逆向官方客户端 C:\Program Files (x86)\BIGBIG WON
（DevMgr.dll 的 CDeviceBBwon::GetDevicePowerInfo /
CDeviceBBwon::OnReceiveDataFromDevice），并对真机发命令验证过。

设备：VID 0x413D，手柄在系统里会同时暴露
  - XInput 兼容集合（显示成 "XBOX 360 For Windows"，15 字节输入报文，只有按键/摇杆）
  - 厂商集合 MI_02：UsagePage 0xFF7A Usage 0x0001，
    输入/输出各 65 字节（首字节是 Report ID 0x00）——电量走这里。

命令（65 字节，后面补 0）::

    00 A5 04 04 AD 00 ... 00
       |  |  |  |  +-- 校验 = (A5+04+04) & 0xFF
       |  |  |  +----- 命令字：读电量
       |  |  +-------- 长度
       |  +----------- 帧头
       +-------------- Report ID

应答（65 字节，实测）::

    00 A5 06 04 4E 00 FD 00 ... 00
       |  |  |  |  |  +-- 校验 = (A5+06+04+4E+00) & 0xFF
       |  |  |  |  +----- 标志位（含义未确认，观测恒为 0）
       |  |  |  +-------- 电量百分比（0x4E = 78%）
       |  |  +----------- 命令字：0x04 = 电量应答
       |  +-------------- 长度
       +----------------- 帧头

要点：
- 报文长度必须是 65 字节（少一个字节就 ERROR_INVALID_PARAMETER 87）。
- 电量是手柄自己在应答里给出的百分比，不是客户端估算的。
- 应答第 6 字节（标志位）观测恒为 0x00，含义未确认，所以充电状态不臆测，
  统一返回 None（界面显示"充电状态未知"）。
- 电量跟 XInput 无关：官方客户端对 XInput 只调了 XInputGetState，
  从来没调过 XInputGetBatteryInformation。
- 2.4G 接收器和 USB 线连接时，厂商集合的 VID/PID、usage page 完全一样，
  程序无法区分当前是有线还是无线，所以界面统一显示"2.4G/有线连接"（不猜）。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from device_battery.hid import hid_win as hw
from device_battery.hid.hid_win import HidDevice

from .base import KIND_GAMEPAD, DeviceInfo, DeviceProvider, Reading

VID = 0x413D
USAGE_PAGE = 0xFF7A
USAGE = 0x0001
REPORT_LEN = 65

HEADER = 0xA5
CMD_POWER = 0x04
REPLY_LEN = 0x06

OFF_PCT = 3          # 相对帧头 0xA5 的偏移：电量百分比
OFF_FLAG = 4         # 标志位（含义未确认，观测为 0）
OFF_CHECKSUM = 5

KEY = "bbw:lingyun"
NAME = "墨将凌云游戏手柄"


def checksum(head: bytes) -> int:
    """校验 = 参与校验的字节逐字节求和取低 8 位。"""
    return sum(head) & 0xFF


def build_request() -> bytes:
    """构造电量查询请求（65 字节）。"""
    f = bytearray(REPORT_LEN)
    f[0] = 0x00              # Report ID
    f[1] = HEADER
    f[2] = 0x04              # 长度
    f[3] = CMD_POWER         # 命令字：读电量
    f[4] = checksum(bytes(f[1:4]))
    return bytes(f)


@dataclass
class PowerReply:
    """一条电量应答的解析结果。"""
    level: int               # 0-100，-1 表示字段越界
    raw_level: int           # 应答里的原始电量字节
    flag: int                # 标志位（含义未知）
    checksum_ok: bool
    raw: bytes

    @property
    def detail(self) -> str:
        expect = checksum(bytes([HEADER, REPLY_LEN, CMD_POWER,
                                 self.level & 0xFF, self.flag]))
        return (f"厂商 HID 协议 0xFF7A（A5 04 04 AD -> A5 06 04 "
                f"{self.level & 0xFF:02X} {self.flag:02X} {expect:02X}）")


def parse_power(report: bytes) -> Optional[PowerReply]:
    """从一条 Input Report 里取出电量；不是电量应答就返回 None。"""
    # 首字节通常是 Report ID 0x00，但也容忍没有 Report ID 的形态
    for start in (1, 0):
        if len(report) < start + OFF_CHECKSUM + 1:
            continue
        if report[start] != HEADER:
            continue
        if report[start + 1] != REPLY_LEN or report[start + 2] != CMD_POWER:
            continue
        raw_level = report[start + OFF_PCT]
        flag = report[start + OFF_FLAG]
        expect = checksum(report[start:start + OFF_CHECKSUM])
        return PowerReply(level=raw_level if raw_level <= 100 else -1,
                          raw_level=raw_level,
                          flag=flag,
                          checksum_ok=(report[start + OFF_CHECKSUM] == expect),
                          raw=bytes(report))
    return None


def find_interfaces() -> list[hw.HidInterface]:
    """找出所有墨将手柄的厂商命令接口（0xFF7A，65 字节报文）。"""
    exact = [d for d in hw.enumerate_hid()
             if d.vid == VID and d.usage_page == USAGE_PAGE
             and d.output_len == REPORT_LEN]
    if exact:
        return exact
    # 兼容固件改了 usage 的情况：仍限定 VID + 厂商页 + 可写
    return [d for d in hw.enumerate_hid()
            if d.vid == VID and d.usage_page >= 0xFF00
            and d.output_len == REPORT_LEN]


def _key_for(iface: hw.HidInterface, index: int) -> str:
    """稳定、可复现的设备 key（同一个手柄每次跑都一致）。"""
    if index == 0:
        return KEY
    tail = "".join(ch for ch in iface.path.split("#")[-2:] if ch)[-8:]
    return f"{KEY}:{tail}" if tail else f"{KEY}:{index}"


def query_power(iface: hw.HidInterface, timeout: float = 0.6) -> Optional[PowerReply]:
    """对单个接口发一次电量查询，超时返回 None。"""
    with HidDevice(iface.path, write=True) as dev:
        if dev.caps.InputReportByteLength:
            dev.drain()
        # 必须走 WriteFile（中断 OUT 端点）：HidD_SetOutputReport 在这台设备上
        # 会返回成功但报文根本没发出去（和英菲克 IN9 同样的坑）。
        dev.write_output(build_request(), use_hidd=False)
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            r = dev.read_input(timeout_ms=120)
            if not r:
                continue
            got = parse_power(r)
            if got is not None:
                return got
    return None


class BbwLingyunProvider(DeviceProvider):
    """墨将（BIGBIG WON）凌云手柄的设备来源。"""

    source = "bbw"

    def enumerate(self) -> list[DeviceInfo]:
        infos: list[DeviceInfo] = []
        for index, iface in enumerate(find_interfaces()):
            infos.append(DeviceInfo(
                key=_key_for(iface, index),
                source=self.source,
                name=NAME,
                kind=KIND_GAMEPAD,
                # 2.4G 接收器和 USB 线走的是同一套厂商集合，程序分不出来，
                # 所以如实标成两种可能（不猜当前是哪一种）。
                transport="2.4G/有线连接",
                params={
                    "vid_pid": iface.vid_pid,
                    "protocol": "墨将厂商 HID 协议（A5 04 04 AD 读电量）",
                },
            ))
        return infos

    def read(self, info: DeviceInfo) -> Reading:
        peers = find_interfaces()
        if not peers:
            return Reading(key=info.key, online=False,
                           error="没找到墨将手柄的厂商接口（请确认手柄已开机并连上）")
        index = 0
        if info.key != KEY:
            tail = info.key.split(":", 1)[-1]
            for i, iface in enumerate(peers):
                if _key_for(iface, i).endswith(tail):
                    index = i
                    break
        if index >= len(peers):
            return Reading(key=info.key, online=False,
                           error="手柄厂商接口已不在（可能已断开）")
        iface = peers[index]
        reply = None
        try:
            # 手柄偶尔会漏掉一次查询（正在休眠/刚刚唤醒），重试一次就够
            for _ in range(2):
                reply = query_power(iface)
                if reply is not None:
                    break
        except Exception as e:
            return Reading(key=info.key, online=False, error=f"读取失败：{e}")
        if reply is None:
            return Reading(key=info.key, online=False,
                           error="手柄没有应答（请按一下手柄按键唤醒）")
        if reply.level < 0:
            return Reading(key=info.key, online=True,
                           error=f"电量字段异常（原始值 {reply.raw_level:02X}）")
        if not reply.checksum_ok:
            return Reading(key=info.key, online=True,
                           error="应答校验不通过（报文被改坏或协议已变）")
        return Reading(
            key=info.key, level=reply.level,
            charging=None,      # 标志位含义未确认，不臆测
            online=True,
            detail=f"{reply.detail}，标志位 0x{reply.flag:02X}",
        )


if __name__ == "__main__":
    ifaces = find_interfaces()
    print(f"找到 {len(ifaces)} 个厂商接口：")
    for i, d in enumerate(ifaces):
        print(f"  [{i}] {d.describe_usage()}  {d.vid_pid}  "
              f"in={d.input_len} out={d.output_len}  {d.product}")
    for i, d in enumerate(ifaces):
        print(f"\n查询 [{i}] {d.path}")
        print("  请求:", build_request()[:8].hex(" "))
        rep = query_power(d)
        if rep is None:
            print("  没有应答")
            continue
        print("  应答:", rep.raw[:8].hex(" "))
        print(f"  电量: {rep.level}%  标志: 0x{rep.flag:02X}  校验: "
              f"{'通过' if rep.checksum_ok else '不通过'}")

# -*- coding: utf-8 -*-
"""inphic_in9.py —— 英菲克 IN9（三模游戏鼠标）2.4G 接收器电量

协议来源：逆向官方驱动 `C:\\Program Files (x86)\\Inphic Mouse\\Inphic Mouse.exe`
（静态分析 IDA + 真机报文验证），已在英菲克 IN9 上验证通过。

设备：2.4G 接收器 VID 0x249A PID 0x5C2F（USB 有线为 0x248A:0x5C2E）。
通信接口：官方 config.xml 里写的是 `VID_249A&PID_5C2F&MI_02`，对应
HID UsagePage=0x0001 Usage=0x0000 的那个 33 字节接口（无 Report ID）。

帧格式（33 字节）：
    偏移  说明
    0     0x00 固定
    1     0x10 固定（请求/应答类型）
    2     0x00（请求）
    3     命令字；请求 0x00 表示「读状态」，应答回 0x01 表示这是一条应答
    4     载荷长度（字节数）
    5..   载荷
    32    校验和 = 求和(帧[5:32]) & 0xFF

电量：读状态命令（命令字 0x00、长度 0）的应答里，应答[14] = 电量百分比。
充电：**应答报文里没有充电位**。驱动是从设备主动上报的事件
    `00 c0 <充电标志> <电量> …` 取充电状态的（见 sub_44A2C0）。
    该事件不是每次都能收到，所以只在读取窗口内真的抓到事件时才给结论，
    否则返回 None（未知），避免误报。

发送方式：**必须用 WriteFile（中断 OUT 端点）**，用 HidD_SetOutputReport 无效。

调试：直接运行本文件可持续监听设备上报内容（内容一变就打印）。
"""

from __future__ import annotations

import time
from typing import Optional

from device_battery.hid import hid_win as hw
from device_battery.hid.hid_win import HidDevice

from .base import KIND_MOUSE, DeviceInfo, DeviceProvider, Reading

VIDS = (0x249A, 0x248A)          # 2.4G(249A) / 2.4G(248A)；USB 有线为 248A:5C2E
USAGE_PAGE = 0x0001
USAGE = 0x0000
FRAME_LEN = 33

OFF_CMD = 3
OFF_LEN = 4
PAYLOAD_OFF = 5
OFF_CHECKSUM = 32

CMD_STATUS = 0x00
REPLY_MARKER = 0x01

REPLY_BATTERY = 14

# 设备主动上报事件：00 c0 <充电标志> <电量> …
EVENT_TAG = 0xC0
EVENT_CHARGING = 2
EVENT_BATTERY = 3

KEY = "inphic:in9"


def checksum(frame: bytes) -> int:
    """校验和 = 帧[5:32] 逐字节相加取低 8 位。"""
    return sum(frame[PAYLOAD_OFF:OFF_CHECKSUM]) & 0xFF


def build_frame(cmd: int, payload: bytes = b"") -> bytes:
    """构造一条请求帧。"""
    f = bytearray(FRAME_LEN)
    f[0] = 0x00
    f[1] = 0x10
    f[2] = 0x00
    f[3] = cmd & 0xFF
    f[4] = len(payload) & 0xFF
    f[PAYLOAD_OFF:PAYLOAD_OFF + len(payload)] = payload
    f[OFF_CHECKSUM] = checksum(f)
    return bytes(f)


def is_reply(report: bytes) -> bool:
    """是不是一条「应答」而不是请求回显。"""
    return (len(report) > OFF_CMD
            and report[1] == 0x10
            and report[OFF_CMD] == REPLY_MARKER)


def is_event(report: bytes) -> bool:
    """是不是设备主动上报的事件（00 c0 <充电标志> <电量> …）。"""
    return (len(report) > EVENT_BATTERY
            and report[0] == 0x00 and report[1] == EVENT_TAG)


def find_interface() -> Optional[hw.HidInterface]:
    """找到 IN9 接收器的命令接口（0x0001:0x0000，33 字节）。"""
    for d in hw.enumerate_hid():
        if (d.vid in VIDS and d.usage_page == USAGE_PAGE and d.usage == USAGE
                and d.output_len == FRAME_LEN):
            return d
    for d in hw.enumerate_hid():
        if d.vid in VIDS and d.usage_page == USAGE_PAGE and d.usage == USAGE:
            return d
    return None


def _read_status(dev: HidDevice,
                 timeout: float = 0.4) -> tuple[Optional[bytes], Optional[bytes]]:
    """发「读状态」命令，返回 (应答帧, 期间收到的设备事件或 None)。"""
    dev.drain()
    dev.write_output(build_frame(CMD_STATUS), use_hidd=False)
    reply = None
    event = None
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        r = dev.read_input(timeout_ms=80)
        if not r:
            continue
        if event is None and is_event(r):
            event = r
        elif reply is None and is_reply(r):
            reply = r
        if reply is not None and event is not None:
            break
    return reply, event


def _charging_from(event: Optional[bytes]) -> Optional[bool]:
    """从设备事件里取充电标志；没抓到事件就返回 None（未知）。"""
    if event is None:
        return None
    return bool(event[EVENT_CHARGING])


def describe(report: bytes) -> str:
    """把一条报文翻译成人能看懂的一行（调试用）。"""
    if is_event(report):
        return (f"设备事件   充电标志={report[EVENT_CHARGING]} "
                f"电量字段={report[EVENT_BATTERY]}")
    if is_reply(report):
        return f"状态应答   电量={report[REPLY_BATTERY]}%"
    return "其他/回显  " + report.hex(" ")


def monitor(query_every: float = 0.0, duration: float = 0.0,
            out=print) -> None:
    """持续监听设备上报，**内容一变就打印**（相同内容不重复打印）。

    query_every > 0 时，另外每隔该秒数补发一次「读状态」查询。
    duration > 0 时只监听这么多秒就返回（0 = 一直监听，Ctrl+C 停止）。
    """
    iface = find_interface()
    if iface is None:
        out("没找到 IN9 接收器（请插上 2.4G 接收器）")
        return
    out(f"开始监听 {iface.path}")
    out("（插拔充电线或操作鼠标，看有没有新报文；Ctrl+C 结束）")
    t0 = time.monotonic()
    last = None
    last_query = t0
    try:
        with HidDevice(iface.path, write=True) as dev:
            while True:
                now = time.monotonic()
                if duration > 0 and now - t0 >= duration:
                    out("监听结束")
                    return
                r = dev.read_input(timeout_ms=200)
                if r is None:
                    if query_every > 0 and now - last_query >= query_every:
                        try:
                            dev.write_output(build_frame(CMD_STATUS),
                                             use_hidd=False)
                        except Exception as e:
                            out(f"[{now - t0:6.1f}s] 查询失败：{e}")
                        last_query = now
                    continue
                if r == last:
                    continue
                last = r
                out(f"[{now - t0:6.1f}s] {describe(r)}   原始={r.hex(' ')}")
    except KeyboardInterrupt:
        out("已停止")


class InphicProvider(DeviceProvider):
    """英菲克 IN9 的设备来源。"""

    source = "inphic"

    def enumerate(self) -> list[DeviceInfo]:
        iface = find_interface()
        if iface is None:
            return []
        return [DeviceInfo(
            key=KEY, source=self.source, name="英菲克 IN9 鼠标",
            kind=KIND_MOUSE, transport="2.4G",
            params={"vid_pid": iface.vid_pid,
                    "protocol": "厂商 HID 33 字节帧（命令 0x00 = 读状态）"},
        )]

    def read(self, info: DeviceInfo) -> Reading:
        iface = find_interface()
        if iface is None:
            return Reading(key=info.key, online=False,
                           error="没找到 IN9 接收器（请插上 2.4G 接收器）")
        try:
            with HidDevice(iface.path, write=True) as dev:
                reply, event = _read_status(dev, timeout=0.4)
        except Exception as e:
            return Reading(key=info.key, online=False, error=f"读取失败：{e}")
        if reply is None:
            return Reading(key=info.key, online=False,
                           error="接收器没有应答（请动一下鼠标唤醒）")
        level = reply[REPLY_BATTERY]
        if level == 0 or level > 100:
            return Reading(key=info.key, online=True,
                           error=f"电量字段异常（原始值 {level}）")
        return Reading(
            key=info.key, level=level, charging=_charging_from(event),
            online=True, detail="厂商 HID 协议（33 字节帧，命令 0x00 = 读状态）",
        )


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="英菲克 IN9（2.4G 接收器）读取")
    ap.add_argument("--query", type=float, default=0.0, metavar="SEC",
                    help="监听时另外每隔 SEC 秒补发一次读状态查询")
    ap.add_argument("--duration", type=float, default=0.0, metavar="SEC",
                    help="只监听 SEC 秒后退出（0 = 一直监听）")
    args = ap.parse_args()
    monitor(query_every=args.query, duration=args.duration)

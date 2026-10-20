# -*- coding: utf-8 -*-
"""bluetooth.py —— 蓝牙设备电量（耳机/音箱、键鼠、手柄等）

原理
----
Windows 蓝牙栈收到设备上报的电量后，会把它写进设备节点上的一个**未公开 PnP 属性**：

    PROPERTYKEY {104EA319-6EE2-4701-BD47-8DDBF425BBE5}, 2   (DEVPROP_TYPE_BYTE)
    值 = 电量百分比（0-100）

要点：
  1. 蓝牙耳机的该属性挂在 **Hands-Free AG（免提）节点** 上，不在设备主节点上。
     蓝牙键鼠/手柄则可能挂在 BTHENUM / BTHLE 的 HID 节点上。
     所以这里把 BTHENUM、BTHLE、蓝牙类、系统类、全部类都枚举一遍再合并。
  2. 属性由驱动在收到设备上报时写入；**设备断开或不上报时属性可能是 0 或不存在**。
     本模块把「值为 0」如实标成"未连接或未上报电量"，绝不当作 0%。
  3. 同一物理设备会挂在多个节点（免提 / A2DP / HID …），按**蓝牙地址**去重，
     只保留有电量值的那个节点。

全部走 ctypes 调 setupapi，零第三方依赖（与 hid 层一致）。
"""

from __future__ import annotations

import ctypes
import re
import sys
from ctypes import wintypes
from typing import Optional

from device_battery.hid.hid_win import GUID, setupapi

from .base import (KIND_GAMEPAD, KIND_HEADSET, KIND_KEYBOARD, KIND_MOUSE,
                   KIND_OTHER, DeviceInfo, DeviceProvider, Reading)

# 蓝牙电量属性：{104EA319-6EE2-4701-BD47-8DDBF425BBE5}, 2
BT_FMTID = GUID(0x104EA319, 0x6EE2, 0x4701,
                (ctypes.c_ubyte * 8)(0xBD, 0x47, 0x8D, 0xDB, 0xF4, 0x25,
                                     0xBB, 0xE5))
BT_BATTERY_PID = 2

DIGCF_PRESENT = 0x02
DIGCF_ALLCLASSES = 0x04
SPDRP_DEVICEDESC = 0x00
SPDRP_FRIENDLYNAME = 0x0C

# 类 GUID：蓝牙 {e0cbf06c-cd8b-4647-bb8a-263b43f0f974}、系统 {4d36e97d-e325-11ce-bfc1-08002be10318}
CLASS_BLUETOOTH = GUID(0xE0CBF06C, 0xCD8B, 0x4647,
                       (ctypes.c_ubyte * 8)(0xBB, 0x8A, 0x26, 0x3B, 0x43,
                                            0xF0, 0xF9, 0x74))
CLASS_SYSTEM = GUID(0x4D36E97D, 0xE325, 0x11CE,
                    (ctypes.c_ubyte * 8)(0xBF, 0xC1, 0x08, 0x00, 0x2B,
                                         0xE1, 0x03, 0x18))

BT_PREFIXES = ("BTHENUM", "BTHLE", "BTHLEDEVICE", "BTHHFENUM")


class PROPERTYKEY(ctypes.Structure):
    _fields_ = [("fmtid", GUID), ("pid", wintypes.DWORD)]


class SP_DEVINFO_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("ClassGuid", GUID),
        ("DevInst", wintypes.DWORD),
        ("Reserved", ctypes.c_void_p),
    ]


setupapi.SetupDiEnumDeviceInfo.restype = wintypes.BOOL
setupapi.SetupDiEnumDeviceInfo.argtypes = [
    ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(SP_DEVINFO_DATA),
]
setupapi.SetupDiGetDeviceRegistryPropertyW.restype = wintypes.BOOL
setupapi.SetupDiGetDeviceRegistryPropertyW.argtypes = [
    ctypes.c_void_p, ctypes.POINTER(SP_DEVINFO_DATA), wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p, wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
]
setupapi.SetupDiGetDevicePropertyW.restype = wintypes.BOOL
setupapi.SetupDiGetDevicePropertyW.argtypes = [
    ctypes.c_void_p, ctypes.POINTER(SP_DEVINFO_DATA),
    ctypes.POINTER(PROPERTYKEY), ctypes.POINTER(wintypes.ULONG),
    ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
    wintypes.DWORD,
]
setupapi.SetupDiGetDeviceInstanceIdW.restype = wintypes.BOOL
setupapi.SetupDiGetDeviceInstanceIdW.argtypes = [
    ctypes.c_void_p, ctypes.POINTER(SP_DEVINFO_DATA), wintypes.LPWSTR,
    wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
]

# 名称 -> 类别 的关键字（小写匹配，中英都认）
KIND_KEYWORDS = (
    (KIND_HEADSET, ("handsfree", "hands-free", "免提", "headset", "耳机",
                    "音箱", "speaker", "ag audio", "audio sink", "a2dp",
                    "headphone", "headset")),
    (KIND_MOUSE, ("mouse", "鼠标")),
    (KIND_KEYBOARD, ("keyboard", "键盘")),
    (KIND_GAMEPAD, ("gamepad", "手柄", "xbox", "controller", "joystick")),
)

_MAC_RE = re.compile(r"[0-9A-Fa-f]{12}")
_GUID_RE = re.compile(r"\{[0-9A-Fa-f-]{20,}\}")


def _instance_id(hdev, info: SP_DEVINFO_DATA) -> str:
    buf = ctypes.create_unicode_buffer(512)
    need = wintypes.DWORD(0)
    if not setupapi.SetupDiGetDeviceInstanceIdW(
            hdev, ctypes.byref(info), buf, 512, ctypes.byref(need)):
        return ""
    return buf.value


def _device_string(hdev, info: SP_DEVINFO_DATA, prop: int) -> str:
    buf = ctypes.create_string_buffer(1024)
    need = wintypes.DWORD(0)
    if not setupapi.SetupDiGetDeviceRegistryPropertyW(
            hdev, ctypes.byref(info), prop, None, buf, 1024, ctypes.byref(need)):
        return ""
    return buf.raw.decode("utf-16-le", errors="ignore").split("\x00")[0]


def _read_battery(hdev, info: SP_DEVINFO_DATA) -> tuple[Optional[int], bool]:
    """返回 (电量, 属性是否存在)。值为 0 表示未上报。"""
    key = PROPERTYKEY(BT_FMTID, BT_BATTERY_PID)
    ptype = wintypes.ULONG(0)
    value = ctypes.c_ubyte(0)
    need = wintypes.DWORD(0)
    ok = setupapi.SetupDiGetDevicePropertyW(
        hdev, ctypes.byref(info), ctypes.byref(key), ctypes.byref(ptype),
        ctypes.byref(value), 1, ctypes.byref(need), 0,
    )
    if not ok:
        return None, False
    return int(value.value), True


def bluetooth_address(instance_id: str) -> str:
    """从设备实例 ID 里解析蓝牙地址（6 字节 MAC）；解析不到返回空串。"""
    text = _GUID_RE.sub("", instance_id)
    m = _MAC_RE.search(text)
    return m.group(0).lower() if m else ""


def classify(name: str) -> str:
    low = (name or "").lower()
    for kind, keys in KIND_KEYWORDS:
        if any(k in low for k in keys):
            return kind
    return KIND_OTHER


# --------------------------------------------------------------------------
# 连接状态：Windows 会把「已配对」设备的电量属性一直留着，
# 只有 bthprops 的 fConnected 才反映「现在到底连没连」。
# --------------------------------------------------------------------------
BLUETOOTH_MAX_NAME_SIZE = 248
_bth = None


class _SYSTEMTIME(ctypes.Structure):
    _fields_ = [("wYear", wintypes.WORD), ("wMonth", wintypes.WORD),
                ("wDayOfWeek", wintypes.WORD), ("wDay", wintypes.WORD),
                ("wHour", wintypes.WORD), ("wMinute", wintypes.WORD),
                ("wSecond", wintypes.WORD), ("wMilliseconds", wintypes.WORD)]


class _BLUETOOTH_ADDRESS(ctypes.Structure):
    _fields_ = [("ullLong", ctypes.c_ulonglong)]


class _BLUETOOTH_DEVICE_INFO(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("Address", _BLUETOOTH_ADDRESS),
        ("ulClassofDevice", wintypes.ULONG),
        ("fConnected", wintypes.BOOL),
        ("fRemembered", wintypes.BOOL),
        ("fAuthenticated", wintypes.BOOL),
        ("stLastSeen", _SYSTEMTIME),
        ("stLastUsed", _SYSTEMTIME),
        ("szName", wintypes.WCHAR * BLUETOOTH_MAX_NAME_SIZE),
    ]


class _BLUETOOTH_DEVICE_SEARCH_PARAMS(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("fReturnAuthenticated", wintypes.BOOL),
        ("fReturnRemembered", wintypes.BOOL),
        ("fReturnUnknown", wintypes.BOOL),
        ("fReturnConnected", wintypes.BOOL),
        ("fIssueInquiry", wintypes.BOOL),
        ("cTimeoutMultiplier", ctypes.c_ubyte),
        ("hRadio", wintypes.HANDLE),
    ]


def connection_states() -> Optional[dict[str, bool]]:
    """已配对蓝牙设备的连接状态 {MAC(12 位小写): 是否已连接}。

    查询不可用（不是 Windows / 蓝牙服务没起）时返回 None，
    调用方据此**不做**任何过滤，避免把设备全藏了。
    """
    global _bth
    if sys.platform != "win32":
        return None
    try:
        if _bth is None:
            _bth = ctypes.WinDLL("bthprops.cpl", use_last_error=True)
            _bth.BluetoothFindFirstDevice.restype = wintypes.HANDLE
            _bth.BluetoothFindFirstDevice.argtypes = [
                ctypes.POINTER(_BLUETOOTH_DEVICE_SEARCH_PARAMS),
                ctypes.POINTER(_BLUETOOTH_DEVICE_INFO)]
            _bth.BluetoothFindNextDevice.restype = wintypes.BOOL
            _bth.BluetoothFindNextDevice.argtypes = [
                wintypes.HANDLE, ctypes.POINTER(_BLUETOOTH_DEVICE_INFO)]
            _bth.BluetoothFindDeviceClose.restype = wintypes.BOOL
            _bth.BluetoothFindDeviceClose.argtypes = [wintypes.HANDLE]

        params = _BLUETOOTH_DEVICE_SEARCH_PARAMS()
        params.dwSize = ctypes.sizeof(_BLUETOOTH_DEVICE_SEARCH_PARAMS)
        params.fReturnAuthenticated = True
        params.fReturnRemembered = True
        params.fReturnUnknown = False
        params.fReturnConnected = True
        params.fIssueInquiry = False          # 不做查询，马上返回
        params.cTimeoutMultiplier = 2
        params.hRadio = None

        info = _BLUETOOTH_DEVICE_INFO()
        info.dwSize = ctypes.sizeof(_BLUETOOTH_DEVICE_INFO)

        handle = _bth.BluetoothFindFirstDevice(ctypes.byref(params),
                                               ctypes.byref(info))
        if not handle:
            return None
        states: dict[str, bool] = {}
        try:
            while True:
                mac = "%012x" % info.Address.ullLong
                states[mac] = bool(info.fConnected)
                if not _bth.BluetoothFindNextDevice(handle, ctypes.byref(info)):
                    break
        finally:
            _bth.BluetoothFindDeviceClose(handle)
        return states
    except Exception:
        return None


def _scan_nodes() -> list[tuple[str, str, Optional[int], bool]]:
    """扫描所有蓝牙相关节点，返回 [(实例ID, 名称, 电量, 属性存在)]。

    只保留**当前真的连着**的设备：Windows 对已配对但断开的设备仍然保留
    电量属性（缓存的旧值），只靠属性会把没开机的耳机当在线。
    """
    attempts = (
        (None, None, DIGCF_ALLCLASSES),
        ("BTHENUM", None, 0),
        ("BTHLE", None, 0),
        (None, CLASS_BLUETOOTH, 0),
        (None, CLASS_SYSTEM, 0),
    )
    states = connection_states()
    seen: dict[str, tuple[str, str, Optional[int], bool]] = {}
    for enumerator, class_guid, flags in attempts:
        hdev = setupapi.SetupDiGetClassDevsW(
            ctypes.byref(class_guid) if class_guid is not None else None,
            enumerator, None, flags | DIGCF_PRESENT,
        )
        if not hdev or hdev == ctypes.c_void_p(-1).value:
            continue
        try:
            index = 0
            while True:
                info = SP_DEVINFO_DATA()
                info.cbSize = ctypes.sizeof(SP_DEVINFO_DATA)
                if not setupapi.SetupDiEnumDeviceInfo(
                        hdev, index, ctypes.byref(info)):
                    break
                index += 1
                iid = _instance_id(hdev, info)
                if not iid or iid in seen:
                    continue
                if not iid.upper().startswith(BT_PREFIXES):
                    continue
                addr = bluetooth_address(iid)
                if states is not None and addr and states.get(addr) is False:
                    continue        # 已配对但没连上：跳过
                name = (_device_string(hdev, info, SPDRP_FRIENDLYNAME)
                        or _device_string(hdev, info, SPDRP_DEVICEDESC))
                level, has = _read_battery(hdev, info)
                if not has:
                    continue
                seen[iid] = (iid, name, level, has)
        finally:
            setupapi.SetupDiDestroyDeviceInfoList(hdev)
    return list(seen.values())


def _dedup(nodes: list[tuple[str, str, Optional[int], bool]]
           ) -> list[tuple[str, str, Optional[int]]]:
    """按蓝牙地址合并同一物理设备的多个节点；优先保留有电量值的那个。"""
    merged: dict[str, tuple[str, str, Optional[int]]] = {}
    for iid, name, level, _has in nodes:
        addr = bluetooth_address(iid) or iid
        cur = merged.get(addr)
        if cur is None:
            merged[addr] = (iid, name, level)
            continue
        # 已有值、或用新节点替换"无值"的旧节点
        if cur[2] in (None, 0) and level not in (None, 0):
            merged[addr] = (iid, cur[1] if len(name) < len(cur[1]) else name,
                            level)
        elif len(name) > len(cur[1]):
            merged[addr] = (iid, name, cur[2])
    return list(merged.values())


class BluetoothProvider(DeviceProvider):
    """蓝牙设备来源：一次枚举可产出 0..N 个设备。"""

    source = "bluetooth"

    def enumerate(self) -> list[DeviceInfo]:
        try:
            nodes = _dedup(_scan_nodes())
        except Exception:
            return []
        out: list[DeviceInfo] = []
        for iid, name, _level in nodes:
            addr = bluetooth_address(iid)
            pretty = name.strip() or "蓝牙设备"
            out.append(DeviceInfo(
                key=f"bt:{iid}",
                source=self.source,
                name=pretty,
                kind=classify(pretty),
                transport="Bluetooth",
                params={
                    "address": (":".join(addr[i:i + 2] for i in range(0, 12, 2))
                                if addr else ""),
                    "instance_id": iid,
                    "protocol": "Windows 蓝牙电量 PnP 属性",
                },
            ))
        return out

    def read(self, info: DeviceInfo) -> Reading:
        try:
            nodes = _dedup(_scan_nodes())
        except Exception as e:
            return Reading(key=info.key, online=False, error=f"读取失败：{e}")
        for iid, name, level in nodes:
            if not info.key.endswith(iid):
                continue
            if level is None or level == 0:
                return Reading(key=info.key, online=False,
                               error="设备未连接或未上报电量")
            if level > 100:
                return Reading(key=info.key, online=True,
                               error=f"电量字段异常（原始值 {level}）")
            return Reading(key=info.key, level=level, online=True,
                           detail="Windows 蓝牙电量 PnP 属性（由设备上报后由驱动写入）")
        return Reading(key=info.key, online=False,
                       error="设备已断开（枚举不到该节点）")


if __name__ == "__main__":
    nodes = _scan_nodes()
    print(f"扫描到 {len(nodes)} 个带电量属性的蓝牙节点：")
    for iid, name, level, _has in nodes:
        addr = bluetooth_address(iid) or "?"
        print(f"  {name or '(无名称)'}  电量={level}  地址={addr}  类别={classify(name)}")
        print(f"      {iid}")
    print("\n去重后：")
    for iid, name, level in _dedup(nodes):
        print(f"  {name}  电量={level}")

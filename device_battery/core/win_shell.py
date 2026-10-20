# -*- coding: utf-8 -*-
"""win_shell.py —— Windows 外壳相关：已知文件夹路径 + 快捷方式(.lnk)

* 已知文件夹用 `SHGetKnownFolderPath`，这样用户把桌面/启动文件夹改到
  OneDrive 也能找到正确位置。
* 快捷方式用 `IShellLinkW` + `IPersistFile` 纯 ctypes 创建（不依赖 pywin32 /
  PowerShell），并提供 `read_shortcut()` 把内容读回来做校验。
"""

from __future__ import annotations

import ctypes
import os
from ctypes import POINTER, byref, wintypes

ole32 = ctypes.WinDLL("ole32")
shell32 = ctypes.WinDLL("shell32")


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8)]

    def __init__(self, text: str = ""):
        super().__init__()
        if text:
            t = text.strip("{}")
            d1, d2, d3, rest = t.split("-", 3)
            self.Data1 = int(d1, 16)
            self.Data2 = int(d2, 16)
            self.Data3 = int(d3, 16)
            self.Data4 = (ctypes.c_ubyte * 8)(*bytes.fromhex(rest.replace("-", "")))


CLSID_SHELLLINK = GUID("{00021401-0000-0000-C000-000000000046}")
IID_ISHELLLINKW = GUID("{000214F9-0000-0000-C000-000000000046}")
IID_IPERSISTFILE = GUID("{0000010b-0000-0000-C000-000000000046}")

FOLDERID_Desktop = GUID("{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}")
FOLDERID_Startup = GUID("{B97D20BB-F46A-4C97-BA10-5E3608430854}")

CLSCTX_INPROC_SERVER = 1
STGM_READ = 0x00000000

shell32.SHGetKnownFolderPath.restype = ctypes.c_long
shell32.SHGetKnownFolderPath.argtypes = [POINTER(GUID), wintypes.DWORD,
                                         ctypes.c_void_p,
                                         POINTER(ctypes.c_wchar_p)]
ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
ole32.CoInitialize.argtypes = [ctypes.c_void_p]
ole32.CoCreateInstance.restype = ctypes.c_long
ole32.CoCreateInstance.argtypes = [POINTER(GUID), ctypes.c_void_p,
                                   wintypes.DWORD, POINTER(GUID),
                                   POINTER(ctypes.c_void_p)]


# --------------------------------------------------------------------------
# 已知文件夹
# --------------------------------------------------------------------------
def _known_folder(folder: GUID, fallback: str) -> str:
    try:
        p = ctypes.c_wchar_p()
        if shell32.SHGetKnownFolderPath(byref(folder), 0, None, byref(p)) == 0:
            if p.value:
                path = p.value
                ole32.CoTaskMemFree(ctypes.cast(p, ctypes.c_void_p))
                return path
    except Exception:
        pass
    return fallback


def desktop_dir() -> str:
    return _known_folder(FOLDERID_Desktop,
                         os.path.join(os.path.expanduser("~"), "Desktop"))


def startup_dir() -> str:
    return _known_folder(
        FOLDERID_Startup,
        os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows",
                     "Start Menu", "Programs", "Startup"))


# --------------------------------------------------------------------------
# COM 小工具
# --------------------------------------------------------------------------
def _vtbl(this: ctypes.c_void_p):
    return ctypes.cast(this, POINTER(POINTER(ctypes.c_void_p))).contents


def _call(vtbl, index: int, argtypes, *args):
    """按 vtable 下标调用 COM 方法（args 里第一个是接口指针 this）。"""
    proto = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)
    return proto(vtbl[index])(*args)


def _release(this: ctypes.c_void_p) -> None:
    try:
        proto = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)
        proto(_vtbl(this)[2])(this)
    except Exception:
        pass


# --------------------------------------------------------------------------
# 快捷方式
# --------------------------------------------------------------------------
def create_shortcut(lnk_path: str, target: str, arguments: str = "",
                    workdir: str = "", description: str = "",
                    icon: str = "") -> bool:
    """创建 .lnk 快捷方式。返回是否成功（成功后会自动读回校验）。"""
    lnk_path = os.path.abspath(lnk_path)
    os.makedirs(os.path.dirname(lnk_path), exist_ok=True)

    ole32.CoInitialize(None)
    punk = ctypes.c_void_p()
    hr = ole32.CoCreateInstance(byref(CLSID_SHELLLINK), None,
                                CLSCTX_INPROC_SERVER, byref(IID_ISHELLLINKW),
                                byref(punk))
    if hr < 0 or not punk:
        return False
    R = ctypes.c_long
    try:
        v = _vtbl(punk)
        _call(v, 20, [wintypes.LPCWSTR], punk, target)              # SetPath
        if arguments:
            _call(v, 11, [wintypes.LPCWSTR], punk, arguments)       # SetArguments
        if workdir:
            _call(v, 9, [wintypes.LPCWSTR], punk, workdir)          # SetWorkingDirectory
        if description:
            _call(v, 7, [wintypes.LPCWSTR], punk, description)      # SetDescription
        if icon:
            _call(v, 17, [wintypes.LPCWSTR, ctypes.c_int], punk,
                  icon, 0)                                          # SetIconLocation

        pf = ctypes.c_void_p()
        hr = _call(v, 0, [POINTER(GUID), POINTER(ctypes.c_void_p)], punk,
                   byref(IID_IPERSISTFILE), byref(pf))              # QueryInterface
        if hr < 0 or not pf:
            return False
        try:
            vf = _vtbl(pf)
            hr = _call(vf, 6, [wintypes.LPCWSTR, wintypes.BOOL], pf,
                       lnk_path, True)                              # Save
            if hr < 0:
                return False
        finally:
            _release(pf)
    finally:
        _release(punk)

    got = read_shortcut(lnk_path)
    return bool(got and os.path.normcase(os.path.abspath(got.get("target", "")))
                == os.path.normcase(os.path.abspath(target)))


def read_shortcut(lnk_path: str) -> dict:
    """读回 .lnk 的内容（用于校验），失败返回 {}。"""
    lnk_path = os.path.abspath(lnk_path)
    if not os.path.exists(lnk_path):
        return {}
    ole32.CoInitialize(None)
    punk = ctypes.c_void_p()
    hr = ole32.CoCreateInstance(byref(CLSID_SHELLLINK), None,
                                CLSCTX_INPROC_SERVER, byref(IID_ISHELLLINKW),
                                byref(punk))
    if hr < 0 or not punk:
        return {}
    R = ctypes.c_long
    out: dict = {}
    try:
        v = _vtbl(punk)
        pf = ctypes.c_void_p()
        hr = _call(v, 0, [POINTER(GUID), POINTER(ctypes.c_void_p)], punk,
                   byref(IID_IPERSISTFILE), byref(pf))
        if hr < 0 or not pf:
            return {}
        try:
            vf = _vtbl(pf)
            if _call(vf, 5, [wintypes.LPCWSTR, wintypes.DWORD], pf,
                     lnk_path, STGM_READ) < 0:                       # Load
                return {}

            def text(index: int, nargs: int, size: int = 1024) -> str:
                buf = ctypes.create_unicode_buffer(size)
                if nargs == 4:                                       # GetPath
                    _call(v, index,
                          [wintypes.LPWSTR, ctypes.c_int, ctypes.c_void_p,
                           wintypes.DWORD], punk, buf, size, None, 0)
                else:                                                # 两个参数
                    _call(v, index, [wintypes.LPWSTR, ctypes.c_int],
                          punk, buf, size)
                return buf.value

            out["target"] = text(3, 4)                               # GetPath
            out["arguments"] = text(10, 2)                           # GetArguments
            out["workdir"] = text(8, 2)                              # GetWorkingDirectory
        finally:
            _release(pf)
    finally:
        _release(punk)
    return out


def remove_shortcut(lnk_path: str) -> bool:
    try:
        os.remove(lnk_path)
        return True
    except OSError:
        return False


def shortcut_exists(lnk_path: str) -> bool:
    return os.path.isfile(lnk_path)

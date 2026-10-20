# -*- coding: utf-8 -*-
"""toast.py —— Windows 通知

用 winotify（纯 Python，经 PowerShell 调 WinRT）发系统通知。
通知本身设为静音，提示音由 notify/sound.py 自己播放，这样用户可以换成任意音频文件。

发送失败只记录，不影响主流程。
"""

from __future__ import annotations

from typing import Callable, Optional

APP_ID = "设备电量"
ICON = ""


def show(title: str, message: str,
         log: Optional[Callable[[str], None]] = None) -> bool:
    """弹一条 Windows 通知；成功返回 True。"""
    try:
        from winotify import Notification, audio
        toast = Notification(app_id=APP_ID, title=title, msg=message)
        # 静音：提示音我们自己播（用户可自定义）
        toast.set_audio(audio.Silent, loop=False)
        toast.show()
        return True
    except Exception as e:
        if log:
            log(f"发送通知失败：{e}")
        return False

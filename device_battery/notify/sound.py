# -*- coding: utf-8 -*-
"""sound.py —— 播放提示音（QtMultimedia，支持 mp3）

PyQt5 自带 QtMultimedia，Windows 上走 Media Foundation，可直接播 mp3，
不需要额外安装音频库。播放器常驻一个实例，避免重复创建。
"""

from __future__ import annotations

import os
from typing import Callable, Optional

from PyQt5.QtCore import QUrl
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer

_player: Optional[QMediaPlayer] = None


def _ensure_player() -> QMediaPlayer:
    global _player
    if _player is None:
        _player = QMediaPlayer()
    return _player


def play(path: str, volume: int = 70,
         log: Optional[Callable[[str], None]] = None) -> bool:
    """播放指定音频；路径为空或文件不存在则不播。"""
    if not path or not os.path.exists(path):
        if log and path:
            log(f"提示音文件不存在，跳过：{path}")
        return False
    try:
        player = _ensure_player()
        player.setVolume(max(0, min(100, int(volume))))
        player.setMedia(QMediaContent(QUrl.fromLocalFile(path)))
        player.play()
        return True
    except Exception as e:
        if log:
            log(f"播放提示音失败：{e}")
        return False


def stop() -> None:
    if _player is not None:
        _player.stop()

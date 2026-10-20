# -*- coding: utf-8 -*-
"""manager.py —— 低电量预警（按设备单独生效）

每个设备一套独立状态机：
   启用（override 优先） -> 跌破阈值 -> 弹 Windows 通知 + 播提示音
   再次告警需满足：先回升到阈值以上，或距上次告警超过 cooldown_minutes

阈值 / 提示音 / 开关都可以按设备单独设置（见 core/config.py 的 notify.overrides）。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Optional

from device_battery.core import config as cfgmod
from device_battery.devices import Reading

from . import sound, toast


@dataclass
class _State:
    alerted: bool = False
    last_ts: float = 0.0


class NotifyManager:
    """按设备维护预警状态。"""

    def __init__(self, cfg: dict, log: Optional[Callable[[str], None]] = None):
        self._cfg = cfg
        self._log = log
        self._states: dict[str, _State] = {}

    def apply_config(self, cfg: dict) -> None:
        self._cfg = cfg

    def handle(self, readings: list[Reading]) -> None:
        for r in readings:
            try:
                self._handle_one(r)
            except Exception as e:
                if self._log:
                    self._log(f"预警处理异常（{r.key}）：{e}")

    # ---- 内部 ---------------------------------------------------------
    def _handle_one(self, r: Reading) -> None:
        settings = cfgmod.device_notify(self._cfg, r.key)
        state = self._states.setdefault(r.key, _State())

        if not settings["enabled"] or not r.online or r.level is None:
            state.alerted = False
            return

        threshold = int(settings["threshold"])
        if r.level > threshold:
            state.alerted = False          # 回升到阈值以上，允许下次再告警
            return

        cooldown = max(1, int(settings["cooldown_minutes"])) * 60
        now = time.time()
        if state.alerted and (now - state.last_ts) < cooldown:
            return

        name = r.info.name if r.info else r.key
        if toast.show("设备电量不足", f"{name}：{r.level}%", self._log):
            if self._log:
                self._log(f"已发送低电量通知：{name} {r.level}%")
        if settings["sound_enabled"]:
            path = cfgmod.resolve_sound(self._cfg, settings["sound"])
            sound.play(path, int(settings["volume"]), self._log)

        state.alerted = True
        state.last_ts = now

    def test_alert(self, key: str, name: str, level: int = 15) -> None:
        """设置页的「试听/测试」用：立刻按该设备的设置弹一次。"""
        settings = cfgmod.device_notify(self._cfg, key)
        toast.show("设备电量不足（测试）", f"{name}：{level}%", self._log)
        if settings["sound_enabled"]:
            path = cfgmod.resolve_sound(self._cfg, settings["sound"])
            sound.play(path, int(settings["volume"]), self._log)

    def preview_sound(self, path: str, volume: int = 70) -> None:
        """设置页的「试听」用。"""
        sound.play(cfgmod.resolve_sound(self._cfg, path), int(volume), self._log)

# -*- coding: utf-8 -*-
"""manager.py —— 低电量预警（按设备单独生效）

每个设备一套独立状态机：
   启用（override 优先） -> 跌破阈值 -> 弹通知 + 播提示音
   再次告警需满足：先回升到阈值以上，或距上次告警超过 cooldown_minutes

通知只走 Windows 系统通知（托盘气泡，带 info 图标），会进通知中心。

通知文案走 `notify.title_template` / `notify.body_template` 模板，
支持魔法变量（见 notify/template.py）；设置页可以自定义并当场发一条测试通知。

阈值 / 提示音 / 开关都可以按设备单独设置（见 core/config.py 的 notify.overrides）。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Optional

from device_battery.core import config as cfgmod
from device_battery.devices import Reading

from . import sound, template, toast

APP_NAME = "设备电量"


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
        self._readings: list[Reading] = []

    def apply_config(self, cfg: dict) -> None:
        self._cfg = cfg

    def handle(self, readings: list[Reading]) -> None:
        self._readings = readings
        for r in readings:
            try:
                self._handle_one(r)
            except Exception as e:
                if self._log:
                    self._log(f"预警处理异常（{r.key}）：{e}")

    # ---- 内部 ---------------------------------------------------------
    @staticmethod
    def _lowest(readings: list[Reading]) -> Optional[Reading]:
        candidates = [r for r in readings if r.online and r.level is not None]
        if not candidates:
            return None
        return min(candidates, key=lambda r: r.level)

    def _context(self, r: Optional[Reading], threshold: int) -> dict:
        return template.build_context(
            r,
            threshold=threshold,
            count=len(self._readings),
            min_reading=self._lowest(self._readings),
            app_name=APP_NAME,
        )

    def _templates(self) -> tuple[str, str]:
        return cfgmod.render_templates(self._cfg)


    def _send(self, reading: Optional[Reading], threshold: int,
              title_tpl: str, body_tpl: str) -> tuple[str, str]:
        """渲染模板并同时走系统通知 + 应用内弹窗，返回 (标题, 正文)。"""
        ctx = self._context(reading, threshold)
        title = template.render(title_tpl, ctx).strip() or APP_NAME
        body = template.render(body_tpl, ctx).strip()
        if not body:
            body = f"{ctx['name']}：{ctx['level_pct']}"

        toast.show(title, body, self._log)
        if self._log:
            self._log(f"已发送通知：{title} / {body}")
        return title, body

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

        title_tpl, body_tpl = self._templates()
        self._send(r, threshold, title_tpl, body_tpl)

        if settings["sound_enabled"]:
            path = cfgmod.resolve_sound(self._cfg, settings["sound"])
            sound.play(path, int(settings["volume"]), self._log)

        state.alerted = True
        state.last_ts = now

    # ---- 设置页用 -----------------------------------------------------
    def test_alert(self, key: str, name: str, level: int = 15) -> tuple[str, str]:
        """设备预警表里的「测试」：按该设备的设置，用模板发一条通知。"""
        settings = cfgmod.device_notify(self._cfg, key)
        reading = next((r for r in self._readings if r.key == key), None)
        title_tpl, body_tpl = self._templates()
        title, body = self._send(reading, int(settings["threshold"]),
                                 title_tpl, body_tpl)
        if settings["sound_enabled"]:
            path = cfgmod.resolve_sound(self._cfg, settings["sound"])
            sound.play(path, int(settings["volume"]), self._log)
        return title, body

    def test_notification(self, title_tpl: str = "", body_tpl: str = ""
                          ) -> tuple[str, str]:
        """通知测试：用给定模板 + 当前（或示例）设备数据发一条通知。"""
        if not title_tpl and not body_tpl:
            title_tpl, body_tpl = self._templates()
        reading = self._lowest(self._readings)
        settings = cfgmod.device_notify(self._cfg,
                                        reading.key if reading else "")
        return self._send(reading, int(settings["threshold"]),
                          title_tpl, body_tpl)

    def preview_sound(self, path: str, volume: int = 70) -> None:
        """设置页的「试听」用。"""
        sound.play(cfgmod.resolve_sound(self._cfg, path), int(volume), self._log)

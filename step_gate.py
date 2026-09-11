# -*- coding: utf-8 -*-
"""可开关的"每步延迟 / 断点单步"闸门——调试时用来观察机器狗的实时运行。

闸门挂在 tracing 客户端上，**不需要改动 robot.py 的策略代码**：每次
/measure、/clear（以及 /enter）之前与之后各过一道闸门，按 config.json 的
debug 配置决定是"睡一会儿"还是"停下来等网页点下一步"。

两道安全阀（避免忘记点"下一步"把正式测试机会烧掉）
------------------------------------------------
1. 单个断点最长等待 ``breakpoint.timeout_s`` 秒，超时自动放行；
2. /enter 时记住本局剩余现实时间，留出 ``breakpoint.reserve_s`` 秒余量，
   到点**强制放行**，之后不再停。
"""

from __future__ import annotations

import copy
import json
import threading
import time
from collections import deque
from pathlib import Path

ACTIONS = ("enter", "measure", "clear")

DEFAULT_DEBUG = {
    "enabled": True,
    "delay": {
        "enabled": False,
        "before_s": 0.2,
        "after_s": 0.0,
        "actions": ["enter", "measure", "clear"],
    },
    "breakpoint": {
        "enabled": False,
        "actions": ["measure", "clear"],
        "channels": [],            # 空列表 = 所有频道；否则只在这些频道上停
        "every_n": 1,              # 每 n 次命中的动作停一次
        "timeout_s": 600.0,        # 单步最长等待
        "reserve_s": 90.0,         # 为现实时间预算留的余量
    },
}


class AbortRequested(RuntimeError):
    """用户在网页上点了"中止"。"""


def merge_debug(base: dict, patch: dict) -> dict:
    """把 patch 深合并进 base（只覆盖出现的键）。"""
    out = copy.deepcopy(base)
    for k, v in (patch or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge_debug(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_debug_config(path: str | Path = "config.json") -> dict:
    """从 config.json 里读 debug 段并补齐默认值；文件不存在就用默认值。"""
    cfg = copy.deepcopy(DEFAULT_DEBUG)
    p = Path(path)
    if not p.exists():
        return cfg
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return cfg
    return merge_debug(cfg, raw.get("debug", {}))


class StepGate:
    """每步延迟 / 断点的闸门。线程安全：机器人线程在这里等，HTTP 线程来放行。"""

    def __init__(self, config: dict | None = None) -> None:
        self._lock = threading.RLock()
        self._cfg = merge_debug(DEFAULT_DEBUG, config or {})
        self._release = threading.Event()
        self._abort = threading.Event()
        self._count = 0          # 走过的动作总数
        self._hit = 0            # 命中断点条件的动作数
        self._wall_deadline: float | None = None   # 现实时间放行时刻（epoch s）
        self._budget_note: str | None = None
        self.pending: dict | None = None
        self.last: dict | None = None
        self.log: deque = deque(maxlen=200)
        self._outbox: list = []          # 待写进 trace 的闸门事件

    def take_notes(self) -> list:
        """取走尚未写入 trace 的闸门事件。"""
        with self._lock:
            out = list(self._outbox)
            self._outbox.clear()
            return out

    def reset_run(self) -> None:
        """开始新一局前清空每局状态与中止标志（日志保留）。"""
        with self._lock:
            self._count = 0
            self._hit = 0
            self.pending = None
            self.last = None
            self._wall_deadline = None
            self._budget_note = None
            self._outbox.clear()
        self._abort.clear()
        self._release.clear()

    # ------------------------------------------------------------ 配置
    def snapshot(self) -> dict:
        with self._lock:
            return copy.deepcopy(self._cfg)

    def update(self, patch: dict) -> dict:
        with self._lock:
            self._cfg = merge_debug(self._cfg, patch or {})
            return copy.deepcopy(self._cfg)

    def set_budget(self, remaining_real_s: float | None) -> None:
        """由 /enter 的剩余现实时间推算强制放行时刻。"""
        if not remaining_real_s or remaining_real_s <= 0:
            return
        with self._lock:
            reserve = float(self._cfg["breakpoint"].get("reserve_s", 90.0))
        self._wall_deadline = time.time() + max(remaining_real_s - reserve, 0.0)

    # ------------------------------------------------------------ 控制
    def release(self, reason: str = "manual") -> bool:
        """放行当前等待的动作（网页"下一步"）。"""
        if self.pending is None:
            return False
        self._release.set()
        return True

    def request_abort(self) -> None:
        self._abort.set()
        self._release.set()

    def aborting(self) -> bool:
        return self._abort.is_set()

    def state(self) -> dict:
        """给网页看的完整状态。"""
        with self._lock:
            cfg = copy.deepcopy(self._cfg)
            pending = copy.deepcopy(self.pending)
            last = copy.deepcopy(self.last)
            log = list(self.log)[-30:]
            n = self._count
            hit = self._hit
        now = time.time()
        return {
            "config": cfg,
            "pending": pending,
            "last": last,
            "log": log,
            "count": n,
            "hit": hit,
            "aborting": self._abort.is_set(),
            "budget_deadline": self._wall_deadline,
            "budget_left_s": (None if self._wall_deadline is None
                              else max(self._wall_deadline - now, 0.0)),
            "budget_note": self._budget_note,
        }

    # ------------------------------------------------------------ 闸门
    def before(self, kind: str, info: dict | None = None) -> None:
        if self._abort.is_set():
            raise AbortRequested("用户请求中止")
        with self._lock:
            cfg = copy.deepcopy(self._cfg)
        self._count += 1
        if not cfg.get("enabled", True):
            return

        delay = cfg.get("delay", {})
        if delay.get("enabled") and kind in delay.get("actions", []):
            self._sleep(float(delay.get("before_s", 0.0)))

        bp = cfg.get("breakpoint", {})
        if bp.get("enabled") and kind in bp.get("actions", []):
            channels = bp.get("channels") or []
            ch = (info or {}).get("channel")
            if not channels or ch in channels:
                self._hit += 1
                every = max(int(bp.get("every_n", 1) or 1), 1)
                if self._hit % every == 0:
                    self._halt(kind, info or {}, bp)

    def after(self, kind: str, info: dict | None = None) -> None:
        with self._lock:
            cfg = copy.deepcopy(self._cfg)
        if not cfg.get("enabled", True):
            return
        delay = cfg.get("delay", {})
        if delay.get("enabled") and kind in delay.get("actions", []):
            self._sleep(float(delay.get("after_s", 0.0)))

    # ------------------------------------------------------------ 内部
    def _sleep(self, seconds: float) -> None:
        if seconds <= 0:
            return
        if self._abort.wait(seconds):
            raise AbortRequested("用户请求中止")

    def _halt(self, kind: str, info: dict, bp: dict) -> None:
        """停下来等人的地方。返回时说明放行原因。"""
        now = time.time()
        step_deadline = now + float(bp.get("timeout_s", 600.0) or 600.0)
        deadline = step_deadline
        reason_fixed = None
        if self._wall_deadline is not None:
            if now >= self._wall_deadline:
                reason_fixed = "budget"
            else:
                deadline = min(deadline, self._wall_deadline)
                if deadline == self._wall_deadline:
                    reason_fixed = "budget"      # 到点是先撞现实预算
        self._release.clear()
        with self._lock:
            self.pending = {
                "kind": kind,
                "info": copy.deepcopy(info),
                "since": now,
                "deadline": deadline,
                "auto_release_at": deadline,
                "auto_release_in": max(deadline - now, 0.0),
                "seq": self._count,
                "hint": ("现实时间余量不足，将自动放行" if reason_fixed == "budget" else None),
            }
        got = self._release.wait(timeout=max(deadline - now, 0.0))
        waited = time.time() - now
        if self._abort.is_set():
            reason = "abort"
        elif got:
            reason = "manual"
        elif reason_fixed == "budget":
            reason = "budget"
        else:
            reason = "timeout"
        note = {"kind": "gate", "action": kind, "reason": reason,
                "waited_s": round(waited, 2), "at": time.strftime("%H:%M:%S"),
                "info": copy.deepcopy(info)}
        with self._lock:
            self.pending = None
            self.last = note
            self.log.append(note)
            self._outbox.append(note)
            if reason == "budget":
                self._budget_note = "现实时间余量不足，断点已被强制放行"
                self._wall_deadline = 0.0     # 之后不再停
        if reason == "abort":
            raise AbortRequested("用户请求中止")

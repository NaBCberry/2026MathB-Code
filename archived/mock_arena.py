# -*- coding: utf-8 -*-
"""无线电干扰源环境模拟器 —— 本地离线版本（用于算法自测，不联网）。

严格按题目附录与附件1/附件2 的规则实现，接口与 sim_client.SimulatorClient 一致：
``enter() / measure(x, y, ch) / clear(x, y, ch) / exit()``。

与真实模拟器的差别只有一点：这里能直接读到真值（干扰源个数、位置、接收半径、
定向方向），因此可以在没有模拟器、没有网络的时候检验策略的
"被清除干扰源个数的比例"和"平均定位清除时间"。

已实现的规则
------------
- 10~16 个干扰源，频道从 1..20 中互不相同；位置在半径 1800 m 圆域内均匀分布。
- 有效接收半径 1000~1500 m，各源不同，且不对外暴露。
- 示向度误差：**同一地点固定**（同坐标重复检测读数不变），取值在 [-1°, 1°]。
- 示向度按 [0,360) 归一化；距离 ≤5 m 且在覆盖角度内返回 near 且不给示向度。
- 定向源：有效覆盖角度为定向方向两侧各 90°（含），覆盖外返回 no_signal。
- 清除：20 m 内必成功；同一源只清除一次；/clear 不切换测向机频道。
- 虚拟时间：移动距离/5 + 换频道 1 s（仅 /measure）+ 检测 5 s / 清除 3 s 或 5 s。
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass

ARENA_R = 1800.0
R_MIN, R_MAX = 1000.0, 1500.0
SPEED = 5.0
MEASURE_S = 5.0
SWITCH_S = 1.0
CLEAR_HIT_S = 5.0
CLEAR_MISS_S = 3.0
NEAR_M = 5.0
CLEAR_M = 20.0
MAX_VIRTUAL_S = 360000.0
MAX_REAL_S = 1200


@dataclass
class Source:
    channel: int
    x: float
    y: float
    radius: float                # 有效接收半径
    direction: float | None      # 定向方向（度）；None 表示全向
    cleared: bool = False


class MockArena:
    """本地模拟器。用法与 SimulatorClient 相同。"""

    def __init__(self, seed: int | None = None, *, n_sources: int | None = None,
                 directional_fraction: float = 0.0, verbose: bool = False):
        self.verbose = verbose
        rng = random.Random(seed)
        self.seed = seed
        n = n_sources if n_sources is not None else rng.randint(10, 16)
        channels = rng.sample(range(1, 21), n)
        self.sources: list[Source] = []
        for ch in channels:
            r = ARENA_R * math.sqrt(rng.random())
            th = rng.uniform(0.0, 2 * math.pi)
            radius = rng.uniform(R_MIN, R_MAX)
            directional = rng.random() < directional_fraction
            direction = rng.uniform(0.0, 360.0) if directional else None
            self.sources.append(Source(ch, r * math.cos(th), r * math.sin(th),
                                       radius, direction))
        self.n_sources = n
        self.n_directional = sum(1 for s in self.sources if s.direction is not None)

        self.pos = (0.0, 0.0)
        self.cur_channel = 1
        self.virtual_time = 0.0
        self.entered = False
        self.history: list[tuple] = []
        self._bias_cache: dict[tuple, float] = {}
        self._seq = 0

    # ------------------------------------------------------------ 工具
    def _bias(self, x: float, y: float) -> float:
        """该地点的固定示向度误差（度），∈ [-1, 1]。"""
        key = (round(x, 6), round(y, 6))
        v = self._bias_cache.get(key)
        if v is None:
            h = hashlib.sha256(f"{self.seed}|{key[0]}|{key[1]}".encode()).digest()
            v = (int.from_bytes(h[:4], "big") / 2 ** 32) * 2.0 - 1.0
            self._bias_cache[key] = v
        return v

    @staticmethod
    def _in_coverage(src: Source, x: float, y: float) -> bool:
        if src.direction is None:
            return True
        bearing = math.degrees(math.atan2(src.y - y, src.x - x)) % 360.0
        diff = abs((bearing - src.direction + 180.0) % 360.0 - 180.0)
        return diff <= 90.0 + 1e-9

    def _move_cost(self, x: float, y: float) -> float:
        return math.hypot(x - self.pos[0], y - self.pos[1]) / SPEED

    def _source_of(self, ch: int) -> Source | None:
        for s in self.sources:
            if s.channel == ch and not s.cleared:
                return s
        return None

    # ------------------------------------------------------------ 4 条指令
    def enter(self) -> dict:
        self.entered = True
        self.pos = (0.0, 0.0)
        self.cur_channel = 1
        self.virtual_time = 0.0
        return {"accepted": True, "real_timestamp_ms": 0, "virtual_time_s": 0.0,
                "max_virtual_duration_s": MAX_VIRTUAL_S,
                "max_real_duration_s": MAX_REAL_S,
                "remaining_real_duration_s": MAX_REAL_S}

    def measure(self, x: float, y: float, ch: int) -> dict:
        dt = self._move_cost(x, y)
        switch = SWITCH_S if ch != self.cur_channel else 0.0
        self.virtual_time += dt + switch + MEASURE_S
        self.pos = (x, y)
        self.cur_channel = ch
        self._seq += 1

        src = self._source_of(ch)
        result: dict = {"accepted": True, "virtual_time_s": self.virtual_time}
        if src is None:
            result["measure_result"] = "no_signal"
        else:
            d = math.hypot(src.x - x, src.y - y)
            if d <= NEAR_M and self._in_coverage(src, x, y):
                result["measure_result"] = "near"
            elif d <= src.radius and self._in_coverage(src, x, y):
                bearing = math.degrees(math.atan2(src.y - y, src.x - x))
                result["measure_result"] = "direction"
                result["svd_deg"] = round((bearing + self._bias(x, y)) % 360.0, 2)
            else:
                result["measure_result"] = "no_signal"
        self.history.append(("measure", x, y, ch, result.get("measure_result"),
                             result.get("svd_deg"), self.virtual_time))
        if self.verbose:
            print(self.history[-1])
        return result

    def clear(self, x: float, y: float, ch: int) -> dict:
        dt = self._move_cost(x, y)
        self.pos = (x, y)
        self._seq += 1
        src = self._source_of(ch)
        hit = src is not None and math.hypot(src.x - x, src.y - y) <= CLEAR_M
        self.virtual_time += dt + (CLEAR_HIT_S if hit else CLEAR_MISS_S)
        if hit:
            src.cleared = True
        res = "success" if hit else "no_target_in_range"
        self.history.append(("clear", x, y, ch, res, None, self.virtual_time))
        if self.verbose:
            print(self.history[-1])
        return {"accepted": True, "virtual_time_s": self.virtual_time,
                "clear_result": res}

    def exit(self) -> dict:
        self.entered = False
        return {"accepted": True, "virtual_time_s": self.virtual_time,
                "exit_reason": "user_exit"}

    # ------------------------------------------------------------ 统计
    @property
    def n_cleared(self) -> int:
        return sum(1 for s in self.sources if s.cleared)

    @property
    def miss_distance(self) -> float:
        """未清除的干扰源到清除点的最小距离之类的诊断量（此处返回 0 占位）。"""
        return 0.0

    def __enter__(self) -> "MockArena":
        return self

    def __exit__(self, *_exc) -> None:
        pass

# -*- coding: utf-8 -*-
"""问题 4 · v5：外环 1930 m —— 既严格可证完备、角裕度又比 v2 更大。

与 v2 的**唯一**差别是外环半径：v1/v2/v3 取 ``ρ = 1900`` m，本版取 ``ρ = 1930`` m。
站数、完备性判据、铺清方式、候选点排序、滚动计价全部沿用 v2，不引入新逻辑。

【为什么是 1930，而不是 1950】
三角覆盖判据（可零抽样地证明完备性）对环状布站给出两条必须同时满足的条件：

    C1 外切（凸包须包含圆域）  ρ ≥ R_T/cos(π/n)
    C2 弦长（环站间距 ≤ R_min）ρ ≤ R_min/(2 sin(π/n))

两者相容 ⟺ tan(π/n) ≤ R_min/(2R_T) = 0.2778 ⟺ **n ≥ 12**。
取 n = 12 时可行窗口为 ρ ∈ [1863.5, 1931.9] m。于是：

    ρ = 1900 m（v2）：弦长  983.5 m ✓，角间隔 171.80°，裕度  8.20°
    ρ = 1930 m（本版）：弦长  999.0 m ✓，角间隔 165.34°，裕度 14.66°
    ρ = 1931.8 m      ：弦长 1000.0 m ✓（临界），裕度 15.03°
    ρ = 1950 m（v4）：弦长 1009.4 m ✗ 超限，三角覆盖判据不成立

即 1930 m 是"贴着 C2 上限、仍在严格可证区间内"的最佳取值：
相比 v2 把角裕度提高 6.5°，同时完整保留可证明性；再往外（1950）虽然数值裕度更大，
但外环弦长超过 1000 m，失去严格证明。

【代价】外环周长比 v2 多 2π×30 ≈ 188 m，离线实测约慢 1% 量级（v2 608.3 s/源）。
"""

from __future__ import annotations

from .base import AlgorithmSpec
from .p4_directional import _inner_lattice, _outer_ring
from .p4_v2_receding import P4V2Hunter


class P4V5Hunter(P4V2Hunter):
    """只改布站：外环半径 1900 m → 1930 m，其余与 v2 完全一致。"""

    DEFAULTS = {
        **P4V2Hunter.DEFAULTS,
        "outer_r": 1930.0,      # 外环半径（v1/v2/v3 用 1900 m；v4 用 1950 m）
    }

    def survey_stations(self) -> list[tuple[float, float]]:
        """内层六边形格 13 站（不变）+ 半径 ρ 外环 k 站（默认 ρ=1930、k=12）。"""
        k = int(self.p.get("outer_k", 12))
        rho = float(self.p.get("outer_r", 1930.0))
        pts: list[tuple[float, float]] = [(0.0, 0.0)]
        pts += [q for q in _inner_lattice() if q != (0.0, 0.0)]
        if k > 0:
            pts += _outer_ring(rho, k)
        return pts


# ================================================================== 算法登记
SPEC = AlgorithmSpec(
    id="p4-v5-ring1930",
    name="第四题 v5 外环 1930 m（可证 + 高裕度）",
    problem="问题4",
    summary="v2 策略不变，外环 1900 → 1930 m：角裕度 8.20° → 14.66°，且完备性仍严格可证",
    description=(
        "【与 v2 相同的部分】25 站包围式排查（内层六边形格 13 站 + 外环 12 站）、"
        "凸包/角间隔式排除判据、楔形交会定位、牛耕式铺清、滚动时域巡访，全部沿用。\n"
        "【唯一改动·外环半径】把外环从 ρ=1900 m 外推到 ρ=1930 m。\n"
        "【为什么是 1930】三角覆盖判据（零抽样证明完备性）要求同时满足两条：\n"
        "  C1 外切：ρ ≥ R_T/cos(π/n)；C2 弦长：2ρ sin(π/n) ≤ R_min。\n"
        "  两者相容 ⟺ n ≥ 12；n=12 时可行窗口 ρ ∈ [1863.5, 1931.9] m。\n"
        "  ρ=1900 弦长 983.5（裕度 8.20°）；ρ=1930 弦长 999.0（裕度 14.66°）；\n"
        "  ρ=1950 弦长 1009.4 超限（角裕度虽 18.80° 但失去严格证明）。\n"
        "  故 1930 是“贴着弦长上限、仍在严格可证区间内”的最佳取值。\n"
        "【与 v2 的实测差异】站数相同（25），外环周长多约 188 m，时间约慢 1% 量级。"
    ),
    params=dict(P4V5Hunter.DEFAULTS),
    entry="algorithms/p4_v5_ring1930.py: P4V5Hunter",
)


def build(sim, params: dict | None = None, *, verbose: bool = False):
    """构造 v5 策略对象。"""
    return P4V5Hunter(sim, params, verbose=verbose)

# -*- coding: utf-8 -*-
"""问题 4 · v7：**测站补测闸门** + 落空频道加强扫描。

────────────────────────────────────────────────────────────────
一、要修的现象（seed 27880 · 频道 19，实测诊断）
────────────────────────────────────────────────────────────────

该局频道 19 是一个**贴边界的定向源**：位置 (-1432.2, 323.0)、接收半径 1241 m、
定向方向 119.49°。全程走完 25 个测站、320 次测量，最后 14/15 清除，
频道 19 未清除，**保证误差界一直停在 237.4 m**，24 次 /clear 全部落空。

把每次测站巡访时的真实几何与代码分支逐条打出来（tools/diag_ch19_probe.py）：

     t/s      测站        到源/m  与定向夹角  当时方位线数  测了19?  跳过的分支
   ------------------------------------------------------------------------
   2263   (-500, 866)    1078.8     89.3°        0→1       是   首条方位线在此产生
   3282   (-1900, 0)      568.5     95.1°         10       否   已有10条方位线 -> 跳过
   3448   (-1500, 866)    547.2     22.4°         10       否   同上
   3699   (-1645, 950)    662.2     10.7°         10       否   同上

三条事实：

1. `clean_sweep()` 对已发现频道只有一条补测路径——**恰好 1 条方位线、且该站离
   这条射线 ≤ 900 m**。一旦 ≥2 条，测站再也不会测它。也就是说测站在算法里
   只承担"发现 / 攒 no_signal 排除证据"，**从不承担多站交会**。
2. 首测之后主循环立刻用 `work()` 抢走了该频道（逼近点 562 m ≈ 112 s，而下一个
   测站 (-1900,0) 在 1646 m ≈ 329 s），于是在 2515–3278 s 沿首条射线连测 10 条，
   读数全落在 207.7°–212.7°，**两两交会角中位仅 1.94°**（136 对里最大 15.6°）。
3. 等狗走到几何上最理想的外环站时已经 10 条，直接跳过。反事实（同一套裁剪 +
   最小外接圆）：

        首条 + 外环 (-1500,866)（交会角 65.3°）   → 保证误差界 27.4 m
        首条 + 两个外环站（65.3° / 77.9°）        → 保证误差界 21.7 m
        实际 10 条近共线线                        → 保证误差界 237.4 m

   即：**采到手的线和最该采的线正好反了**。外环 12 站本来是为"边界完备性"
   才不得不设的（`boundary_miss` 的半平面判据），它们恰好是唯一能从侧后方
   看这个边界定向源的一批站，却被完全浪费。

────────────────────────────────────────────────────────────────
二、v7 的两条判断（本模块实际生效的改动）
────────────────────────────────────────────────────────────────

**判断 A · 测站补测闸门**（"定位区域落在该测站作用范围内就顺便测一下"）

在每个测站扫描完（`super().clean_sweep()`）之后，对每个"已测到但未清除"的频道：

    ① 廉价拒绝：定位区域（凸多边形）到该站的最小距离 > R_MAX=1500 m → 该站
       根本不可能测到它，跳过。
    ② **保证性收益检验**：把该站看区域的角张成 [θ0, θ1] 均匀采样 `gate_samples`
       个可能的示向度 φ（真源必在区域内，故真实读数必落在张角内），对每个 φ 算
       新区域 = 旧区域 ∩ 楔形(s,φ) ∩ 圆盘(s,R_MAX) 的最小外接圆半径，取**最大值**
       （最坏读数的后果）。只有当"最坏情况下的新误差界"比现状至少降
       `gate_gain`（默认 35%）时，才真的在该站测一次。

   这一步的物理含义：区域是凸的、且真源必在区域内，所以"真实读数"一定落在该站
   看区域的角张成之内——闸门算的是**这个张成内最坏的那个读数**，因此它给出的是
   收益的下界，而不是期望值。

   代价说明：闸门放行的那次测量如果撞上定向盲区会返回 no_signal，这种结果**不进
   区域裁剪**（`_refresh_region` 只用示向度），只能算浪费 6 s。seed 27880 在
   (-1900,0) 就浪费了一次（该站在源背后 95.1°，必然盲区）。6 s 相对于一次
   几百米的绕路（100 s 量级）可以忽略，所以闸门只做"值不值得"的粗筛，不复用
   no_signal 证据。

**判断 B · 落空频道加强扫描**（"扫描扇形多次清不掉就加强"）

给每个频道记 `/clear` 落空次数 `miss`，按它分三档放宽：

    miss <  k        → 收益门槛 gate_gain        = 35%
    k ≤ miss < 2k    → 收益门槛 gate_gain_eager  = 10%
    miss ≥ 2k        → 只要严格变小就测（门槛 0）

并且 `miss ≥ k` 的频道，其牛耕式铺清的光栅间距乘 `eager_pitch_scale`（默认 0.5）：
22 m → 11 m，覆盖半径 15.6 m → 7.8 m，落空清除明显减少。

────────────────────────────────────────────────────────────────
三、开关与回归
────────────────────────────────────────────────────────────────

`station_gate=False` 时与 v6 逐位等价（可作回归对照）。
默认参数见 DEFAULTS；去掉闸门只需把 `station_gate` 置 False。
"""

from __future__ import annotations

import math

from .base import AlgorithmSpec
from .p3_baseline import (CHANNELS, CLEAR_RADIUS, R_MAX, arena_polygon,
                          clip_disc, clip_wedge, min_enclosing_circle)
from .p4_v2_receding import _axis_raster
from .p4_v6_policy import P4V6Hunter


class P4V7Hunter(P4V6Hunter):
    """v6 之上：测站补测闸门（判断 A）+ 落空频道加强扫描（判断 B）。"""

    DEFAULTS = {
        **P4V6Hunter.DEFAULTS,
        # ---- 判断 A：测站补测闸门 ----
        "station_gate": True,
        "gate_gain": 0.35,          # 常规频道：最坏情况误差界至少要降这么多
        "gate_gain_eager": 0.10,    # 落空 ≥ gate_miss_k 次后的放宽门槛
        "gate_miss_k": 2,           # "多次无法清除"的阈值（每频道 /clear 落空次数）
        "gate_samples": 6,          # 该站看区域的角向采样数
        "gate_max_per_station": 4,  # 每个测站最多额外补几条（防单站爆炸）
        "gate_disc_n": 36,          # 闸门里"距离 ≤1500"圆盘的近似边数（只用于估值）
        # ---- 判断 B：落空频道加强扫描 ----
        "eager_pitch_scale": 0.5,   # 落空 ≥ gate_miss_k 的频道，光栅间距 ×0.5
    }

    def __init__(self, sim, params: dict | None = None, *, verbose: bool = False):
        super().__init__(sim, params, verbose=verbose)
        self._miss_ch: dict[int, int] = {}      # 频道 → /clear 落空次数

    # ------------------------------------------------------------ 落空计数
    def clear(self, x, y, ch):
        r = super().clear(x, y, ch)
        if r.get("clear_result") != "success":
            self._miss_ch[ch] = self._miss_ch.get(ch, 0) + 1
        return r

    # ------------------------------------------------------------ 判断 A
    def clean_sweep(self, x: float | None = None, y: float | None = None) -> None:
        """先把 v6 的扫描做完（发现 + 攒 no_signal 证据），再过测站补测闸门。"""
        super().clean_sweep(x, y)
        if not bool(self.p.get("station_gate", True)):
            return
        x = self.pos[0] if x is None else x
        y = self.pos[1] if y is None else y
        s = (x, y)
        quota = int(self.p["gate_max_per_station"])
        for ch in CHANNELS:
            if quota <= 0:
                break
            if self._out_of_time():
                return
            st = self.state[ch]
            if st.cleared or not st.known or st.near_at is not None:
                continue
            if not st.polygon or st.center is None or not math.isfinite(st.radius):
                continue
            if st.radius <= CLEAR_RADIUS:
                continue
            if self._gate_want(ch, s):
                self.measure(x, y, ch)
                quota -= 1

    def _gate_want(self, ch: int, s: tuple[float, float]) -> bool:
        """在测站 s 补测一次频道 ch 是否**保证**有足够收益。"""
        st = self.state[ch]
        gain = self._gate_gain(ch)
        # ① 廉价拒绝：区域离该站太远，这个站根本测不到
        if self._poly_min_dist(st.polygon, s) > R_MAX:
            return False
        # ② 保证性收益检验
        worst = self._worst_after(ch, s)
        if worst is None:
            return False
        return worst <= st.radius * (1.0 - gain)

    def _worst_after(self, ch: int, s: tuple[float, float]) -> float | None:
        """在站 s 补测一条方位线后，**最坏读数**下的误差界。

        真源必在区域 poly 内，所以真实读数一定落在"该站看 poly 的角张成"里；
        对该张成均匀采样，取新区域最小外接圆半径的最大值，就是收益的下界。
        返回 None 表示该站读到任何有效方位线都不可行（楔形与区域无交）。
        """
        poly = self.state[ch].polygon
        if not poly:
            return None
        a0, span = self._angular_span(poly, s)
        k = max(int(self.p["gate_samples"]), 2)
        worst = 0.0
        seen = False
        for i in range(k):
            phi = a0 + span * (i / (k - 1) if k > 1 else 0.5)
            q = clip_wedge(poly, s, phi)
            if len(q) < 3:
                continue                    # 这个读数不可能发生（楔形与区域无交）
            q = clip_disc(q, s, R_MAX, n=int(self.p["gate_disc_n"]))
            if len(q) < 3:
                continue
            _c, r = min_enclosing_circle(q)
            seen = True
            worst = max(worst, r)
        return worst if seen else None

    def _gate_gain(self, ch: int) -> float:
        """落空越多，门槛越低（判断 B 的第一半）。"""
        miss = self._miss_ch.get(ch, 0)
        k = max(int(self.p["gate_miss_k"]), 1)
        base = float(self.p["gate_gain"])
        if miss >= 2 * k:
            return 0.0                      # 只要严格变小就补测
        if miss >= k:
            return min(base, float(self.p["gate_gain_eager"]))
        return base

    # ------------------------------------------------------------ 判断 B
    def _sweep_plan(self, ch: int):
        """落空 ≥ gate_miss_k 次的频道：光栅间距减半，铺得更密。"""
        scale = float(self.p.get("eager_pitch_scale", 1.0))
        if scale >= 1.0 or self._miss_ch.get(ch, 0) < int(self.p["gate_miss_k"]):
            return super()._sweep_plan(ch)
        if str(self.p.get("sweep_mode", "raster")) != "raster":
            return super()._sweep_plan(ch)
        st = self.state[ch]
        if not st.polygon:
            return None
        pitch = float(self.p["raster_pitch"]) * scale
        cap = int(self.p["max_probes"])
        plan = _axis_raster(st.polygon, pitch)
        if not plan:
            return super()._sweep_plan(ch)
        done = set(self._probes.get(ch, []))
        todo = [q for q in plan if q not in done]
        if not todo:
            return None
        cx, cy = self.pos
        todo.sort(key=lambda q: math.hypot(q[0] - cx, q[1] - cy))
        return todo[:cap]

    # ------------------------------------------------------------ 几何工具
    @staticmethod
    def _poly_min_dist(poly: list, s: tuple[float, float]) -> float:
        """点 s 到凸区域 poly 的最小距离（顶点 + 点到边段）。"""
        best = float("inf")
        n = len(poly)
        for i in range(n):
            a, b = poly[i], poly[(i + 1) % n]
            best = min(best, math.hypot(s[0] - a[0], s[1] - a[1]))
            vx, vy = b[0] - a[0], b[1] - a[1]
            L2 = vx * vx + vy * vy
            if L2 <= 1e-12:
                continue
            t = ((s[0] - a[0]) * vx + (s[1] - a[1]) * vy) / L2
            t = min(max(t, 0.0), 1.0)
            px, py = a[0] + t * vx, a[1] + t * vy
            best = min(best, math.hypot(s[0] - px, s[1] - py))
        return best

    @staticmethod
    def _angular_span(poly: list, s: tuple[float, float]) -> tuple[float, float]:
        """区域被 s 看到的角张成：返回 (起始角, 张角)。s 在内部时张角为 360°。"""
        angs = sorted(math.degrees(math.atan2(p[1] - s[1], p[0] - s[0])) % 360.0
                      for p in poly)
        if len(angs) < 2:
            return (angs[0] if angs else 0.0), 0.0
        best_gap, best_i = -1.0, 0
        for i in range(len(angs)):
            nxt = angs[(i + 1) % len(angs)] + (360.0 if i + 1 == len(angs) else 0.0)
            gap = nxt - angs[i]
            if gap > best_gap:
                best_gap, best_i = gap, i
        a0 = angs[(best_i + 1) % len(angs)]
        return a0, max(360.0 - best_gap, 0.0)


# ================================================================== 算法登记
SPEC = AlgorithmSpec(
    id="p4-v7-stationgate",
    name="第四题 v7 测站补测闸门版",
    problem="问题4",
    summary="v6 之上：定位区域落在测站作用范围内且补测能保证降误差界就读一条；落空多次的频道放宽门槛并加密铺清",
    description=(
        "【修的现象】seed 27880 频道19（贴边界定向源，位置 -1432,323、半径1241m、"
        "方向119.5°）最终未清除、误差界停在 237 m。诊断：clean_sweep() 只在"
        "『恰好 1 条方位线且该站距首条射线 ≤900 m』时补测，一旦 ≥2 条就不再测；"
        "而首测后 work() 立刻把它抢走，沿首条射线连测 10 条近共线线（两两交会角"
        "中位 1.94°），等狗走到外环站 (-1500,866)（交会角 65.3°）时已 10 条被跳过。"
        "反事实：首条+该站 → 误差界 27.4 m；两站 → 21.7 m；实际 → 237.4 m。\n"
        "【判断 A·测站补测闸门】每个测站扫描后，对『已测到未清除』的频道："
        "区域到该站最小距离 ≤1500 m，且把该站看区域的角张成采样 6 个可能示向度算"
        "『最坏情况下的新误差界』，只有当它比现状至少降 35%（gate_gain）时才补测。"
        "每站最多补 4 条。\n"
        "【判断 B·落空加强】按每频道 /clear 落空次数分档放宽门槛：<2 次 35%、"
        "2–3 次 10%、≥4 次只要严格变小就测；落空 ≥2 次的频道牛耕式光栅间距 ×0.5"
        "（22 m → 11 m，覆盖半径 15.6 m → 7.8 m）。\n"
        "【开关】station_gate=False 与 v6 逐位等价，可作回归对照。"
    ),
    params=dict(P4V7Hunter.DEFAULTS),
    entry="algorithms/p4_v7_gate.py: P4V7Hunter",
)


def build(sim, params: dict | None = None, *, verbose: bool = False):
    """构造 v7 策略对象。"""
    return P4V7Hunter(sim, params, verbose=verbose)

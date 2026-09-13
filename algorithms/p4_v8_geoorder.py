# -*- coding: utf-8 -*-
"""问题 4 · v8：**几何测站优先**——把"最值钱的那条方位线"提到调度层。

────────────────────────────────────────────────────────────────
一、v7 修到哪一步，还剩什么
────────────────────────────────────────────────────────────────

v7（测站补测闸门）解决了"走到测站却不测已发现频道"的问题，但它是**被动**的：
只有当狗**恰好**还会经过那个几何上合适的站时才有用。seed 27880 里纯属运气——
外环站 (-1500,866) 本来就在剩余巡访清单里。

而在 v7 的时序里，那个站是**在 10 条近共线方位线之后**才被走到的：首测发生在
(-500,866)（t=2263），之后主循环按滚动 TSP 计价，最近的选择是"顺着射线朝估计
中心走 562 m"（≈112 s），而去下一个测站 (-1900,0) 要 1646 m（≈329 s）——
于是狗先去逼近、连测 10 条共线线，等走到外环站时区域已经被"锁死"在一条细缝里。

**根因不在 `clean_sweep`，而在主循环的计价函数 `_task_cost`：它只认"路程"，
不认"这一趟能买到多好的交会几何"。**

────────────────────────────────────────────────────────────────
二、v8 的改动：给"值钱的测站"减任务代价（只在逼近卡住时启动）
────────────────────────────────────────────────────────────────

先试过"一发现就绕"的版本，直接实测就是负收益：

    geo_bonus_s = 0（= v7）  569.9 s      ← 200 例基准
    geo_bonus_s = 40         569.8 s      ← 与 v7 持平，且救不回 27880
    geo_bonus_s = 80         592.0 s
    geo_bonus_s = 150        604.4 s      ← +6%，无条件打折会把 25 站巡访路线打乱

原因很清楚：**减项是给"站"的，而站是 25 个普查任务之一**；只要打折就会让狗
偏离滚动 TSP 的巡访主线，绕路成本摊到每一个正常频道上。而 27880 那种"几何
被锁死"的频道是**稀有事件**（实测触发率约 1/300），不该让 99.7% 的案例陪跑。

于是 v8 的默认形态是**条件触发**：只有该频道"逼近卡住"（连续 `geo_trigger_stuck`
轮既没新增铺清点、误差界也没降 2%，即 v2 已有的 `self._stuck[ch]`）时，才允许
为它绕站。触发后：

  ① 取当前定位区域 poly（必须存在），只对**方位线 ≤ geo_max_bearings 条、
     误差界 ≥ geo_min_radius** 的频道做（区域已经很小就没必要绕）。
  ② 对 25 个测站逐个算 `_worst_after(ch, s)`——即"在该站补测一条方位线后，
     最坏读数下的误差界"（复用 v7 的保证性估值：区域凸、真源必在区域内，
     故真实读数必落在该站看区域的角张成内）。
  ③ 若 `new_r ≤ radius × (1 − geo_gain)`，说明这一趟能把误差界砍掉一大块，
     就给这个站一个减项：

         bonus = min(geo_bonus_s, geo_weight × (radius − new_r) / SPEED)

     多个频道对同一个站取值取最大。结果按 (频道, 方位线条数, 误差界, 顶点数)
     指纹缓存，只在区域真的变了之后才重算；先用"区域到该站的最小距离 ≤ R_MAX"
     把不可能测到的站滤掉，所以每个指纹只算几个站。

减项只加在 **survey 任务**上（`_task_cost(kind="survey")`），即"去那个测站"，
而不是"去逼近点"。到站之后 v7 的闸门 + v1 的单线补测规则会自动测到该频道，
顺带还完成了那个站的普查——**一趟同时买到几何与覆盖**。

直觉：`(radius − new_r)/SPEED` 把"误差界少走的路"折成秒，`geo_bonus_s` 封顶，
保证减项不会让狗为了一个站横跨半张地图（2000 m = 400 s 的路程减不掉）。

`geo_order=False` 时与 v7 逐位等价（回归对照）。

────────────────────────────────────────────────────────────────
三、实测
────────────────────────────────────────────────────────────────

单例（离线 mock，`python tools/diag_ch19_probe.py 27880 19 <算法>`）：

    seed 27880：v6 14/15（579.0 s）→ v7 15/15（533.7 s）→ v8 15/15（**514.3 s**）
    seed 1031 ：v6 14/15（603.6 s）→ v7 15/15（543.6 s）→ v8 15/15（543.2 s）

批量（`robot.py --dry-run --problem 4 --quiet`，指标 = 平均定位清除时间）：

    seeds 1–200      v6 577.5 s / 100.00%  v7 569.9 s / 100.00%  v8 569.9 s / 100.00%
    seeds 1001–1300  v6 577.8 s /  99.98%  v7 570.3 s / 100.00%  v8 570.3 s / 100.00%
    seeds 5000–5299  —                      v7 561.3 s / 100.00%  v8 561.3 s / 100.00%

触发统计（`tools/diag_v8_activation.py`）：seeds 1–200 触发 **0** 次；
seeds 1001–1300 只有 seed 1031 触发（12 次）；seeds 5000–5299 只有 seed 5085
触发（23 次，但那几次没有改变任何选择，逐例结果与 v7 完全一致）。

即：**v8 在 800 个案例上零代价（逐位等于 v7），只在 27880 这种"逼近被锁死"的
案例上真正生效**（提前 19.4 s 并在 v7 之前就把该频道收掉）。CPU 成本与 v7 无
差别（20 例：v7 3.61 s / v8 3.59 s）。

已知边界：减项只作用于**还没巡访的测站**（`pending` 里的站）。若某个频道被发现时
几何上最合适的站**已经走过**了，v8 不会回头——那需要"允许重访测站"的更激进版本。
"""

from __future__ import annotations

import math

from .base import AlgorithmSpec
from .p3_baseline import CHANNELS, R_MAX, SPEED
from .p4_v7_gate import P4V7Hunter


def _skey(p) -> tuple[float, float]:
    """测站坐标的字典键（裁剪过的浮点，避免对象身份依赖）。"""
    return (round(float(p[0]), 3), round(float(p[1]), 3))


class P4V8Hunter(P4V7Hunter):
    """v7 之上：按"这条方位线有多值钱"给测站减任务代价（几何测站优先）。"""

    DEFAULTS = {
        **P4V7Hunter.DEFAULTS,
        "geo_order": True,
        # 触发条件：该频道"逼近卡住"（连续没改进）才启动几何绕站。
        # 直接实测过"一发现就绕"的版本：200 例 604.4 s（比 v7 慢 6%），
        # 减项 40/80/150 s 分别 569.8 / 592.0 / 604.4 s——无条件打折会把
        # 25 站巡访路线打乱，得不偿失。所以改成只在"逼近不动了"时才绕。
        "geo_trigger_stuck": 2,     # 复用 v2 的 _stuck 计数；0 = 关闭该条件
        "geo_max_bearings": 12,     # 方位线过多的频道不再绕（区域已被锁死）
        "geo_min_radius": 200.0,    # 误差界小于它就不值得专门绕
        "geo_gain": 0.5,            # 误差界至少砍掉一半才算"值钱的站"
        "geo_weight": 1.0,          # (radius−new_r)/SPEED × 权重
        "geo_bonus_s": 150.0,       # 单个站最多减多少秒（防横跨全图）
    }

    def __init__(self, sim, params: dict | None = None, *, verbose: bool = False):
        super().__init__(sim, params, verbose=verbose)
        self._geo_cache: dict[int, tuple] = {}      # 频道 → (指纹, {站键: 预测误差界})
        self._stations_cache: list | None = None

    # ------------------------------------------------------------ 调度层
    def _task_cost(self, pt, kind: str, ch: int | None) -> float:
        c = super()._task_cost(pt, kind, ch)
        if kind == "survey" and bool(self.p.get("geo_order", True)):
            c -= self._geo_bonus(pt)
        return c

    def _geo_bonus(self, pt) -> float:
        """去测站 pt 这一趟能买到的几何收益（秒），多个频道取最大。"""
        key = _skey(pt)
        best = 0.0
        for ch in CHANNELS:
            st = self.state[ch]
            if st.cleared or not st.known or st.near_at is not None:
                continue
            if not st.polygon or st.center is None or not math.isfinite(st.radius):
                continue
            nb = len(st.bearings)
            if nb < 1 or nb > int(self.p["geo_max_bearings"]):
                continue
            if st.radius < float(self.p["geo_min_radius"]):
                continue
            stuck_k = int(self.p.get("geo_trigger_stuck", 0))
            if stuck_k > 0 and self._stuck.get(ch, 0) < stuck_k:
                continue                # 逼近还在正常收拢，不必专门绕路
            new_r = self._geo_table(ch).get(key)
            if new_r is None:
                continue
            if new_r > st.radius * (1.0 - float(self.p["geo_gain"])):
                continue
            val = float(self.p["geo_weight"]) * (st.radius - new_r) / SPEED
            best = max(best, min(val, float(self.p["geo_bonus_s"])))
        return best

    def _geo_table(self, ch: int) -> dict:
        """该频道在 25 个测站上补测后的预测误差界表（带指纹缓存）。"""
        st = self.state[ch]
        sig = (len(st.bearings), round(st.radius, 1), len(st.polygon))
        hit = self._geo_cache.get(ch)
        if hit is not None and hit[0] == sig:
            return hit[1]
        if self._stations_cache is None:
            self._stations_cache = [s for s in self.survey_stations() if s != (0.0, 0.0)]
        table: dict = {}
        for s in self._stations_cache:
            if self._poly_min_dist(st.polygon, s) > R_MAX:
                continue                        # 这个站根本测不到这个频道
            r = self._worst_after(ch, s)
            if r is not None:
                table[_skey(s)] = r
        self._geo_cache[ch] = (sig, table)
        return table


# ================================================================== 算法登记
SPEC = AlgorithmSpec(
    id="p4-v8-geoorder",
    name="第四题 v8 几何测站优先版",
    problem="问题4",
    summary="v7 之上：逼近卡住时，按『这一趟能把误差界砍掉多少』给测站减任务代价，主动绕去把最值钱的方位线买回来",
    description=(
        "【动机】v7 的闸门是被动的——只有狗恰好还会经过那个几何合适的站才有用。"
        "seed 27880 里首测在 (-500,866)（t=2263），主循环按滚动 TSP 计价选了"
        "『顺射线逼近 562 m ≈112 s』，而不是『去 1646 m 外的测站 ≈329 s』，于是"
        "先连测 10 条近共线方位线，等走到外环站 (-1500,866) 时区域已被锁成细缝。"
        "根因在主循环的 _task_cost 只认路程、不认交会几何。\n"
        "【改动】对『逼近卡住（v2 的 _stuck ≥ 2）、方位线 ≤12 条、误差界 ≥200 m』"
        "的频道，逐站算"
        "_worst_after(ch,s)（该站补一条线后、最坏读数下的误差界，v7 同一套保证性估值），"
        "若能把误差界砍掉 ≥50%，给该站的 survey 任务减 "
        "min(geo_bonus_s=150, (radius−new_r)/SPEED) 秒，多频道取最大。"
        "带指纹缓存 + 『区域到站距离 >1500 m』预筛，所以每换一次区域只算几个站。"
        "减项只加在『去那个测站』上，到站后 v7 闸门/单线补测规则自动把该频道测掉，"
        "一趟同时买到几何与覆盖。\n"
        "【为什么必须条件触发】无条件打折实测是负收益：geo_bonus_s = 40/80/150 时"
        "200 例分别为 569.8 / 592.0 / 604.4 s（v7 基准 569.9 s）——减项是给 25 个"
        "普查任务之一打的，会把人从滚动 TSP 主线上拽走；而『几何被锁死』是约 1/300 的"
        "稀有事件，不该让其余案例陪跑。\n"
        "【实测】seed 27880：v6 14/15（579.0 s）→ v7 15/15（533.7 s）→ v8 15/15（514.3 s）；"
        "seed 1031：v6 14/15 → v7/v8 15/15（543.6 → 543.2 s）。批量：seeds 1–200 "
        "v8 = v7 = 569.9 s/100.00%（本批 0 次触发）；seeds 1001–1300 两者均 570.3 s/100.00%；"
        "seeds 5000–5299 两者均 561.3 s/100.00%。触发统计见 tools/diag_v8_activation.py。\n"
        "【已知边界】减项只作用于还没巡访的测站；若发现该频道时最合适的站已经走过，"
        "本版不会回头（需要允许重访测站的激进版本）。geo_order=False 与 v7 逐位等价。"
    ),
    params=dict(P4V8Hunter.DEFAULTS),
    entry="algorithms/p4_v8_geoorder.py: P4V8Hunter",
)


def build(sim, params: dict | None = None, *, verbose: bool = False):
    """构造 v8 策略对象。"""
    return P4V8Hunter(sim, params, verbose=verbose)

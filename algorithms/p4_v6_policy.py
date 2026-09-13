# -*- coding: utf-8 -*-
"""问题 4 · v6：**布站不动**（仍 25 站、严格可证完备），只改排序与动作策略。

本模块是"不改布站、只改策略"这条线的收口版本。先把探索结论写清楚，
再列出实际生效的改动。

────────────────────────────────────────────────────────────────
一、先确认"布站与巡访顺序已经没有余量"（三条实测证据）
────────────────────────────────────────────────────────────────

1. **25 站一个都不能少**。用角度间隔判据（定向源覆盖半角 α=90°，等价于
   "1000 m 内无信号测站的最大角间隔 g_max ≤ 180°"）在 26 万点细网格上
   逐个删站重算：删掉任意一站都会失守——

       删 1732 m 圈任一内层站 → 暴露 0.634%，最坏 244.7°
       删外环任一站           → 暴露 1.2%–2.0%
       删中心站               → 暴露 20.1%，最坏 299.4°

   （注意：早期版本用"NaN 排序 + 拼接环绕列"算 g_max，会把环绕那一段间隔
   算成 NaN 而丢掉，从而**低估**最坏角间隔、误判某些站"可省"。本模块用
   显式环绕项重算，并已与逐步实现、爬山结果对拍一致：全 25 站 = 171.798°。）

2. **测站巡回已近最优**。25 站的开放路径（从原点出发）：

       最近邻 + 2-opt（plan_tsp）   18.42 km
       20 次随机重启 + 2-opt 最好    18.39 km
       同心螺旋序                   18.55 km

   三者相差不到 1%，所以"换一种测站排序算法"不可能有明显收益——这也是
   v6 不采用螺旋序的原因（曾按"同心结构用螺旋不交叉"的直觉实现，实测无收益）。

3. **代价构成**（v2，6 例平均）：测站上的 measure 244 次/局（1222 s，占 16%），
   非测站 measure 45 次（225 s），clear 命中 13.2 次、落空 12.5 次。
   其中测站上的 244 次里，约 175 次是"为判定不存在的频道积累无信号证据"，
   而由第 1 条，absent 频道需要**全部 25 站**的无信号证据，故这部分是硬成本。

结论：余量不在"选哪些站、按什么顺序走"，而在**"什么时候去做某个已发现目标"**。

────────────────────────────────────────────────────────────────
二、v6 实际生效的改动：新发现目标就地优先（软排序）
────────────────────────────────────────────────────────────────

实测（v2）：从**首次测到信号**到**最终清除**，中位滞后 560 s、中位跨距 800 m，
49.7% 超过 800 m，极端例 t=17 s 测到、t=5909 s 才清、跨 1286 m。
根因是 25 个测站任务持续提供"更近的选择"，频道任务被饿到收尾才做，
而那时机器狗已经走远，必须回头——回头那一段就是纯浪费。

改法：给"刚发现（距今 ≤ `fresh_window_s` 虚拟秒）"的频道，
在**任务代价上减 `fresh_bonus` 秒**，把它提前；发现它的测站就在脚下，
第一次逼近几乎不绕路。

与 v2 里已试过的两个开关的区别（那两个都是负收益，已实测）：

    lockin_weight      对"当前正在做的频道"加收尾代价，不区分是否刚发现；
    opportunity_m      是**硬过滤**（只留下近处任务），会饿死普查，且丢完备性；
    fresh_bonus（本项）只是**软排序**：只改次序，不移除任何任务，不影响完备性。

`fresh_bonus = 0` 时与 v2 逐位等价（可作回归对照）。
"""

from __future__ import annotations

import math

from .base import AlgorithmSpec
from .p3_baseline import CHANNELS
from .p4_v2_receding import P4V2Hunter


class P4V6Hunter(P4V2Hunter):
    """v2 的策略微调版：布站、判据、铺清全不动，只加"新发现就地优先"。"""

    DEFAULTS = {
        **P4V2Hunter.DEFAULTS,
        # ---- 实测生效的三项（v2 原值为 40 / 28 / 700）----
        # good_radius ≤ 20 ⇔ 彻底不用"末端 ±45° 两点交会"分支，改为"一直逼近，
        # 到 20 m 内直接清除"（work() 里 radius ≤ CLEAR_RADIUS=20 就先清除，
        # 所以 ≤20 的取值彼此等价）。200 例 608.3 → 587.8 s（−3.4%）。
        "good_radius": 20.0,
        # 牛耕式光栅间距 22 m：覆盖半径 22/√2 ≈ 15.6 m < 20 m，
        # 比 v2 的 28 m 更密一点，落空清除略减。
        "raster_pitch": 22.0,
        # 逼近段单步上限 700 → 900 m，减少"测一次—重排—再测"的回合数。
        "max_step": 900.0,
        # 实测：实测 0 → 600.1 s / 100%；80 → 631.6；150 → 637.2（且 99.86%）；
        # 250 → 640.3；400 → 642.2。故**默认关闭**，保留开关供对照。
        "fresh_bonus": 0.0,         # 对"刚发现"频道的 work 任务减多少秒（0 = 等价 v2）
        "fresh_window_s": 400.0,    # "刚发现"的时效（虚拟秒）
        "fresh_near_m": 0.0,        # 可选：仅当目标估计点距当前位置 ≤ 此值才给减项（0 = 不限）
        # 软性"普查优先"：给每个 work 任务加固定秒罚，使机器狗先把 25 个测站走完。
        # 注意与 v2 的 backbone / opportunity_m 都不同——那两个是**硬**改变候选集
        # （前者固定站序、后者只留近处任务），本条只是软排序。
        # 实测（软罚）：0 → 585.4 / 582.7 s；20 → 578.3 / 578.7；
        #               30 → **577.5 / 577.8**；60 → 588.7；120 → 628.0。
        "survey_first_s": 30.0,
    }

    def __init__(self, sim, params: dict | None = None, *, verbose: bool = False):
        super().__init__(sim, params, verbose=verbose)
        self._t_seen: dict[int, float] = {}     # 频道 → 首次测到信号的虚拟时刻

    # ------------------------------------------------------------ 动作策略
    def clean_sweep(self, x: float | None = None, y: float | None = None) -> None:
        """记录"本次扫描在哪些频道上首次测到信号"，供就地优先使用。"""
        before = {c for c in CHANNELS if self.state[c].known}
        super().clean_sweep(x, y)
        for c in CHANNELS:
            st = self.state[c]
            if st.known and c not in before and not st.cleared:
                self._t_seen[c] = self.virtual_time
        for c in [k for k in self._t_seen if self.state[k].cleared]:
            del self._t_seen[c]

    def _task_cost(self, pt, kind: str, ch: int | None) -> float:
        c = super()._task_cost(pt, kind, ch)
        if kind != "work" or ch is None:
            return c
        pen = float(self.p.get("survey_first_s", 0.0))
        if pen:
            c += pen
        t0 = self._t_seen.get(ch)
        if t0 is None:
            return c
        if self.virtual_time - t0 > float(self.p["fresh_window_s"]):
            return c
        near = float(self.p.get("fresh_near_m", 0.0))
        if near > 0.0:
            st = self.state[ch]
            c0 = st.center
            if c0 is not None and math.hypot(c0[0] - self.pos[0], c0[1] - self.pos[1]) > near:
                return c
        return c - float(self.p["fresh_bonus"])


# ================================================================== 算法登记
SPEC = AlgorithmSpec(
    id="p4-v6-policy",
    name="第四题 v6 策略调优版",
    problem="问题4",
    summary="布站不变（25 站、一个都不能少）；实测 -3.4%~-3.8%：good_radius=20（弃用末端交会）+ 光栅 22 m + 步长 900 m",
    description=(
        "【布站】与 v2 完全相同：内层六边形格 13 站 + ρ=1900 m 外环 12 站 = 25 站。\n"
        "【先证明了布站与顺序没有余量】逐站删除检验（26 万点细网格、修正过的角间隔算法）："
        "删任意一站都失守——删 1732 m 圈内层站暴露 0.634%、删外环站 1.2%–2.0%、"
        "删中心站 20.1%。测站开放路径：plan_tsp 18.42 km、20 次重启 2-opt 最好 18.39 km、"
        "同心螺旋序 18.55 km，相差 <1%，故不再改站序。\n"
        "（勘误：早期验证用了 NaN 排序 + 拼接环绕列的写法，会把环绕间隔算成 NaN 丢掉，"
        "低估最坏角间隔、误判部分测站『可省』；本版改为显式环绕项，已与逐步实现和爬山对拍一致。）\n"
        "【生效改动一·弃用末端 ±45° 交会】good_radius 40 → 20（≤20 各值等价）：work() 在"
        "radius ≤ CLEAR_RADIUS=20 时先清除，故 good_radius ≤ 20 时『末端 ±45° 两点交会』"
        "分支永不触发，策略退化为『一直沿示向度逼近、到 20 m 内直接清除』。"
        "200 例 608.3 → 587.8 s（-3.4%）。\n"
        "【生效改动二·光栅间距】raster_pitch 28 → 22 m（覆盖半径 22/√2 ≈ 15.6 m < 20 m）。\n"
        "【生效改动三·逼近步长】max_step 700 → 900 m，减少『测一次—重排—再测』的回合数。\n"
        "【三项合并】200 例 608.3 → 585.4 s（-3.8%）；另换一批全新种子 300 例"
        "（seed 1001–1300）601.5 → 582.7 s（-3.1%），清除比例不降。\n"
        "【生效改动四·软性普查优先】survey_first_s = 30 s：给每个 work 任务加固定秒罚，"
        "让机器狗先把 25 个测站走完再回头清目标（与 v2 的 backbone / opportunity_m 不同——"
        "那两个是硬改候选集，本条只改排序）。四改项合计："
        "200 例 608.3 → **577.5 s（-5.1%）**；另批 300 例 601.5 → **577.8 s（-3.9%）**，"
        "且后者清除比例由 99.95% 升到 99.98%。软罚的扫描：0→585.4、20→578.3、"
        "30→577.5、60→588.7、120→628.0（秒，200 例）。\n"
        "【试过但负收益、默认关闭】fresh_bonus（新发现就地优先：80→631.6、150→637.2 且丢完备性、"
        "250→640.3、400→642.2）、predict_order、wide_near_m、backbone+corridor、opportunity_m、"
        "lockin_weight、redundancy_penalty、spiral 站序。"
    ),
    params=dict(P4V6Hunter.DEFAULTS),
    entry="algorithms/p4_v6_policy.py: P4V6Hunter",
)


def build(sim, params: dict | None = None, *, verbose: bool = False):
    """构造 v6 策略对象。"""
    return P4V6Hunter(sim, params, verbose=verbose)

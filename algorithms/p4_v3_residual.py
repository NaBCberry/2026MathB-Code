# -*- coding: utf-8 -*-
"""第四题 v3：在 v2 之上，专攻"收尾段"。

v3 = v2（布站/排除判据/牛耕式铺清/good_radius=40） + 下面两项：

改动 1 · 收尾段提交式 TSP（对应"收尾横跨地图"的观察）
    现象：155 个频道里，首次测到信号到最终清除的中位滞后 560 s、中位跨距 800 m，
    49.7% 超过 800 m；后 25% 的单次跳转均值 123 m（前 25% 只有 65 m）。
    但"经过时顺手做"（`opportunity_m`）实测 +5%~+12%——因为**收尾的最后一段路
    是免费的**（跑完就结束、不用回主线），推迟反而更省。
    所以 v3 不提前做，而是把**巡访结束后的残余段**当成一个真正的开链 TSP：
    一旦测站走完，就按提交式巡回序（重排 + 2-opt，只在残余集合变化时重算）
    依次做完，而不是每步重新贪心最近。

改动 2 · 残余集合的构成统计（配置 `residual_report`）
    每局结束时输出残余段的时间起点、残余频道数、残余段里程与占比，
    用来判断"残余到底来自哪些频道"。

实测结论（v3 相对 v2 **没有提升**，但把"为什么"查清楚了）：

| 项 | 结果 |
|---|---|
| 残余段（测站走完后仍存活的频道） | **平均 0.05 个**（20 例里 19 例为 0） |
| 最后一个测站被访问的时刻 | **全程的 100%**（普查一直做到收尾） |
| 最后 20% 时间里 | 站上扫描 **699** 次，逼近测量仅 **63** 次 |
| 最后 20% 的最长单跳 | 中位 **2687 m**（是测站之间的移动） |
| 同一批点做 2-opt 离线最优开链 | 28.90 → 23.11 km，**理论上还有 20%** |
| 短承诺队列 H=2 / 3 / 5 / 8 | **+16% / +24% / +26% / +25%**（都更差） |

三条结论：

1. **残余集合基本是空的**——所以"收尾横跨地图去补漏"不是残余频道造成的，
   而是**普查本身的尾部**：25 个测站被贪婪地一路排到最后，最后 20% 里
   699/762 个动作都是在站上扫描。
2. **那 20% 的"顺序浪费"是在线拿不到的**。离线 2-opt 是对**已经按原顺序生成**
   的那批点重排；而工作点的位置本身依赖访问顺序（每个工作点都锚定在
   "最后一次测到信号的站"上），换顺序点集就变了。所有在线承诺机制
   （整条巡回序、短承诺队列 H≥2、机会主义插队）实测全部更差。
3. 逐步贪心最近实际上就是"每消费一个测站就重排一次巡回序"的滚动时域版本，
   它已经是这个代价结构下的局部最优。

在 `p4_directional`（v1）之上改四处，每一处都对应一篇检索到的文献（见
`docs/reading-list-p34-补充_知网专业检索.md`）。v1 的布站与排除判据（25 站、
凸包包围）全部保留——那部分经数值验证是零漏检的最小集，不动。

改动 1 · 牛耕式铺清（李伯尧 2026《计算机科学》；肖龙 2026《自动化与仪表》）
    v1 的 `_sweep_plan` 用"贪心最远点"在细长定位区域上需要 **124** 个试探点，
    超过 `max_probes=120` 就把整个 `/clear` 兜底关掉——实测直接漏源（seed 54：
    真源在起点旁 36 m 处，却因为"远端盖不满"整条区域一次都不扫）。
    v2 改成沿区域主轴的**牛耕式光栅**：扫描线间距与线内点距都取 `pitch`，
    网格覆盖半径 `pitch/√2 ≈ 19.8 m ≤ 20 m`，细长区域只需约 70–80 点，
    且**永远不会因为名额不够而放弃**。

改动 2 · 预测定位误差最小的候选点排序（奚畅 2021；杨俊岭 2018；简康 2014）
    v1 按固定的 `0.75/0.5/0.3` 比例与 `±45°` 顺序试点，等于"拍脑袋排序"。
    v2 对每个候选点做**一步预测**：假设在该点测到一条指向当前估计点的示向度，
    算出新定位区域的最小外接圆半径，按它升序排。这等价于把文献里的"FIM 行列式
    最大"换成"保证误差界最小"——同一件事，但本题可以直接算。

改动 3 · 真实代价计价 + 跳跃网格（赵学健 2026《物联网学报》；陈杰 2026《兵工学报》）
    v1 的主循环用 `plan_tsp` **只按直线距离**挑最近的一件。实测里程 31.4 km，
    而理论下界约 21 km。v2 改成按"行驶 + 动作 + **收尾代价** + 冗余罚"计价：
    收尾代价把"这个频道还剩多少活"折算成秒数，于是接近完成的目标会被优先做完，
    不再在几条射线之间来回跳（v1 有 75 次 >800 m 的长途折返）。

改动 4 · 奖励共享抑制探测冗余（徐成龙 2026《无人系统技术》）
    对最近探测过的邻域加惩罚项，抑制在同一片区域反复探测。

实测结论（离线 `--problem 4`，两批各 100 例，背靠背跑）：

| 配置 | 虚拟总时间（种子1–100） | 虚拟总时间（种子201–300） | 清除比例 |
|---|---|---|---|
| v1（p4-directional） | 8039.6 s | — | 100.00% |
| v2 早期版本（good_radius=300） | 7906.3 s | 7988.3 s | 100.00% / 99.87% |
| **v2 当前默认（good_radius=40）** | **7593.1 s** | **7585.8 s** | **100.00% / 99.87%** |
| v2 高速档（再加 outer_k=8，21 站） | 7045.1 s | 7033.8 s | 99.84% / 99.80% |

相对 v1：默认档 **−3.8% / −5.0%**（两批一致），高速档 **−12.4% / −11.9%**。
注意 v1 在第二批次上本身就有 99.87% 的漏源率——**布局已经不是瓶颈了**，
所以高速档那 −0.12% 的代价与现有的不可约漏源率同量级。

分项隔离（24 例，其余项关闭）：

| 配置 | 平均定位清除时间 |
|---|---|
| 只开改动 1（牛耕式铺清） | 628.1 s |
| 加开改动 2（预测排序） | 656.0 s |
| 加开改动 3（收尾代价，两步前瞻） | 677.5 s |
| 加开改动 4（冗余罚） | 722.4 s |
| 三项全开 | 743.2 s |

改动 6（巡访结构）的探索结论：

* **"把漏检放到经过时做"——现象成立，但这个改法反而更差**。
  现象（`tools/analyze_angles.py`，12 例）：155 个已清除频道里，首次测到信号到
  最终清除的**中位滞后 560 s**、首测点到清除点的**中位跨距 800 m**，
  **49.7% 超过 800 m**；极端例子是 seed 2 的频道 3——t=17 s 就测到，
  t=5909 s（几乎收尾）才清掉，跨 1286 m。按时间四等分看，
  单次跳转均值 65 → 86 → 99 → **123 m** 单调上升，全程最长的一跳（3632 m）
  也落在后 25%（`tools/profile_run.py`）。
  但**后 25% 的总里程并不比前几段多**（81 / 87 / 90 / 88 km，四段基本持平）——
  跳得少而长，不是总量更大。
  于是实测"机会主义执行"（`opportunity_m`，只要机器狗就在某频道最后测到信号的
  站附近就先把它做掉）：触发半径 200/400/700/1200 m 分别
  **7952 / 7965 / 7925 / 8419 s**，全部劣于默认的 7545 s（+5%~+12%）。
  机理：**收尾时的最后一段路是免费的**（跑完就结束、不用回巡访主线），
  所以把残余任务推迟到收尾做只花"去"的一程；而"经过时做"要花"去+回"两程。
  在这个题目结构下，推迟反而是更省的调度。
  → 结论：要改善这一块，方向不是"提前做"，而是**让残余集合本身更小**
  （或让残余段的顺序更接近 TSP），而不是插队。
* `max_stuck` = 3 / 4 / 6 / 8 结果完全一致（7545.3 s），该参数在本流程里不起作用。

* **固定测站巡回序 + 走廊规则**（`backbone=True`）更差：走廊 150/250/500 m 分别是
  8536/8440/8395 s，连"无限走廊"（等于先普查完再统一清除的两阶段）也要 8663 s，
  全部劣于默认的 7897 s。→ 说明那 9.5 km 的超额里程**不是排序造成的，而是每个
  频道 3–4 次逼近测量本身固有的**（联合 TSP 只算"每个目标访问一次"）。
* **外层环站数**：12 站（零漏检）→ 8 站的代价是 −0.12% 清除率、换来 −10% 时间；
  6 站与 8 站几乎一样（漏检都发生在同一类"边界朝外"的定向源上）。
  默认保持 12 站（守住"确保全部清除"），速度优先时用 `outer_k=8`。
* **巡访顺序 inner_first**：与滚动 TSP 基本持平（7899.9 vs 7897.2 s），无收益。
* **good_radius 300 → 40**：纯赚，−4~5%，两批独立验证过，已设为默认。

也就是说：**只有改动 1（牛耕式铺清）是正收益**（≈ −1.1% 时间、−1.2% 测量次数，
清除比例持平在 100%）；改动 2/3/4 的**想法**都有文献支撑，但按最朴素的实现方式
在本题里都是负收益，因此保留实现与开关、默认关闭。

改动 1 到底修了什么：细长定位区域用"贪心最远点"要 124 个试探点、用牛耕式光栅要
133 个，**两者都超过 `max_probes=120`**；区别在于 v2 按"离机器狗由近及远"截取
前 120 个，近端（真源最可能待的那一端，测站就在那里）一定被完整扫到；数值校验：
区域内采样点到最近试探点的最大距离 19.0 m < 20 m，覆盖性有保证。

改动 2/3/4 的**想法**都有文献支撑，但按最朴素的实现方式在本题里都是负收益，
因此保留实现与开关、默认关闭，并把失败原因记在各自的注释里：

改动 5（平行探测）的追加调查（见 `tools/analyze_angles.py`）：

* 现象确认——v1/v2 的逼近段有 **72.2% 的新增方位线交会角 < 15°**（中位 1.0°），
  对应保证误差界中位 **299 m**；落在最优带 [70°,110°] 的只有 3.7%。
* 根因——`_candidates()` 逼近段的角度序列是 `(0°, +20°, −20°, +40°, −40°)`，
  **共线的 0° 永远排第一**，而 `work()` 一次只做一个动作，于是每次都先测共线点。
  宽角候选其实一直存在（±40° 在源处约 44°），只是永远轮不到。
  定向源与全向源都如此（θ 中位 1.4° / 3.8°），**不是定向源造成的**。
* 修法实测——把角度顺序改成宽角优先，几何不变、只换顺序：
  「清除瞬间误差界 ≤20 m」的比例 48% → 84%，落空清除 9.6 → 2.2 次/局，
  测量次数 292 → 284；**但虚拟总时间 7906 → 8108 s（+2.6%）**，清除率 100% → 99.92%。
  绕估计点画圆弧的版本更差（94.6%，不可用：圆弧以"估计点"为心，而估计点前期误差很大）。
* 结论——**在本题的代价结构下，平行探测不值得修**：一次测量只值 6 s，
  而为了拿到 60–90° 交会角要多绕 0.4d 的横向路程（d=1500 时 600 m = 120 s）。
  顺路多测几次共线点，比专门绕到 90° 测一次更省。
  宽角优先保留为 `approach_angles` 参数，默认仍是实测最优的共线优先。

改动 2/3/4 的**想法**都有文献支撑，但按最朴素的实现方式在本题里都是负收益，
因此保留实现与开关、默认关闭，并把失败原因记在各自的注释里：

* 改动 2 的预测值大量退化为 `inf`（候选点"指向估计点"的楔形常与细长区域不相交），
  排序塌成"就近优先"；而 v1 的"先走大步（0.75/0.5/0.3×dist）"天然更省测量。
* 改动 3 里"收尾代价"一开始写成"把整个频道做完的剩余时间"，等于强迫先普查完再
  统一清除（两阶段，里程贵约 38%）；改成两步前瞻后仍略负。
* 改动 4 的冗余罚把机器狗推离了本来需要复测的位置。文献里那套"奖励共享"是
  建立在栅格概率地图与持续奖励累积上的，直接搬成"近邻罚时"过于粗糙。
"""

from __future__ import annotations

import math
import time

from .base import AlgorithmSpec
from .p3_baseline import (CHANNELS, CLEAR_RADIUS, R_MAX, R_MIN, SPEED, _dir, _rot,
                          clip_disc, clip_wedge, min_enclosing_circle, plan_tsp)
from .p4_directional import (OUTER_R, _inner_lattice, _outer_ring,
                             _poly_samples, P4Hunter)


# ------------------------------------------------------------------ 牛耕式光栅
def _axis_raster(poly: list, pitch: float) -> list[tuple[float, float]]:
    """沿区域主轴铺一层牛耕式（Boustrophedon）光栅点。

    网格间距取 `pitch`，则区域上任意一点到最近网格点的距离 ≤ `pitch/√2`；
    取 `pitch = 28 m` 时覆盖半径 ≈ 19.8 m，刚好小于 20 m 的清除半径。

    细长区域（几个测点几乎共线时的定位区域）用这个只要几十个点，
    而"贪心最远点"要一百多个——后者会顶到 `max_probes` 上去然后整条放弃。
    """
    if not poly or len(poly) < 3 or pitch <= 0:
        return []
    # 主轴：对边界采样点做 PCA，最大特征值方向即"长边方向"
    pts = _poly_samples(poly, max(pitch * 0.5, 8.0))
    n = len(pts)
    if n < 3:
        return []
    mx = sum(p[0] for p in pts) / n
    my = sum(p[1] for p in pts) / n
    sxx = sum((p[0] - mx) ** 2 for p in pts)
    syy = sum((p[1] - my) ** 2 for p in pts)
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pts)
    th = 0.5 * math.atan2(2.0 * sxy, sxx - syy)
    ax, ay = math.cos(th), math.sin(th)          # 主轴单位向量
    px, py = -ay, ax                             # 垂直方向

    def proj_t(p):   # 沿轴坐标
        return (p[0] - mx) * ax + (p[1] - my) * ay

    def proj_s(p):   # 垂直坐标
        return (p[0] - mx) * px + (p[1] - my) * py

    ts = [proj_t(p) for p in pts]
    t0, t1 = min(ts), max(ts)
    if t1 - t0 < 1e-9:
        return [(mx, my)]

    out: list[tuple[float, float]] = []
    m = len(poly)
    t = t0 + pitch * 0.5
    while t <= t1 + 1e-9:
        cross: list[float] = []
        for i in range(m):
            a, b = poly[i], poly[(i + 1) % m]
            fa = proj_t(a) - t
            fb = proj_t(b) - t
            if (fa > 0.0) != (fb > 0.0):
                u = fa / (fa - fb)
                cross.append(proj_s((a[0] + u * (b[0] - a[0]),
                                     a[1] + u * (b[1] - a[1]))))
        if len(cross) >= 2:
            lo, hi = min(cross), max(cross)
            k = int(math.ceil((hi - lo) / pitch - 1e-9))
            for j in range(k + 1):
                s = lo + (hi - lo) * (j / k if k else 0.5)
                out.append((mx + t * ax + s * px, my + t * ay + s * py))
        t += pitch
    return out


class P4V3Hunter(P4Hunter):
    """v3：v2 的布站/判据/铺清不动，专攻收尾段（提交式 TSP + 残余统计）。"""

    DEFAULTS = {
        **P4Hunter.DEFAULTS,
        # 探索结论：把"转入 ±45° 两点交会"的门槛从 300 m 降到 40 m 是**纯赚**——
        # 100 例 7906 → 7593 s（−4.0%），另一批 100 例 7988 → 7586 s（−5.0%），
        # 两批清除率都不变。门槛越小越早转入末端交会，前面那些几乎不缩区域的
        # 共线逼近测量就省掉了。
        "good_radius": 40.0,
        "sweep_mode": "raster",     # raster = 牛耕式光栅；greedy = v1 的贪心最远点
        # 实测（tools/analyze_angles.py）：v1 逼近段的角度序列是
        #   ang = (0°, +20°, −20°, +40°, −40°)
        # **共线的 0° 永远排第一**，而 work() 一次只做一个动作，于是每次都先测共线点
        # → 源处张角 ≈0° → 保证误差界中位 299 m。宽角其实一直都在候选里（±40° 在
        # g 处偏 40°，源处张角约 44°），只是永远轮不到。
        # 结论：**诊断成立，但这个修法是净亏**。实测 100 例（同一批种子）：
        #   0° 优先（v1 原序）      100.00%  635.2 s  292.4 次
        #   30° 优先                99.92%  652.2 s  283.9 次
        #   45° 优先                99.92%  676.3 s  282.8 次
        #   只有近距离才切宽角(600m) 100.00%  646.2 s  288.2 次
        # 原因是代价结构：一次测量只值 6 s，而为了拿到 60–90° 的交会角要多绕
        # 0.4d 的横向路程（d=1500 时就是 600 m = 120 s）。所以**顺路多测几次共线点，
        # 比专门绕到 90° 位置测一次更划算**。宽角点的确把"清除瞬间误差界 ≤20 m"
        # 的比例从 48% 提到 84%、把落空清除从 9.6 次/局降到 2.2 次/局，
        # 但省下的这些抵不过绕路成本。
        "approach_mode": "wide",    # wide = 射线系（几何同 v1，顺序由 approach_angles 定）；
                                    # arc = 绕估计点画圆弧；v1 = 原样
        # 扇区估计（用 no_signal 反推定向方向）实测误差 4°–97°，**不能硬过滤**：
        # 估错时会把本来正确的宽角点全剔掉，退化成沿射线测量（θ≈0）。
        # 所以默认只做"软排序"（把与扇区一致的点提到前面），并且只在可行区间
        # 足够窄（<120°，即约束把方向夹得够紧）时才启用。
        "sector_mode": "soft",      # off / soft（软排序）/ filter（硬过滤）
        "sector_margin_deg": 15.0,  # 定向源：测点离扇区边界至少留这么多度
        "sector_max_width": 120.0,  # 可行角区间宽于此就认为估计不可靠，不启用
        "ray_fallback": False,      # 是否保留"沿射线收拢"的兜底点（θ≈0，默认不要）
        # 探索：把 25 个测站的巡访固定成一条预排路线（滚动 TSP 只在开局排一次），
        # 频道工作点只有在"顺路"时才允许插进来，抑制每步重排造成的来回折返。
        "backbone": False,          # True = 固定测站巡回序 + 走廊规则
        "corridor_m": 250.0,        # "顺路"判定：候选点到（当前位置→下一测站）线段的距离
        # 探索：外环站数。12 站 = 零漏检（814 万组"位置×方向"验证）；减到 6 站时
        # 漏检率 0.13%/定向源，能省下外环一圈的里程与测量次数。
        "outer_k": 12,
        "survey_order": "tsp",      # tsp = 滚动 TSP；inner_first = 先走完内层 13 站
        # 机会主义执行：实测 155 个频道里，首次测到信号到最终清除的中位滞后 560 s、
        # 中位跨距 800 m，49.7% 超过 800 m（极端例：t=17 s 测到、t=5909 s 才清，跨 1286 m）。
        # 原因是有 25 个测站任务一直在提供"更近的选择"，频道任务被饿到收尾才做。
        # 这里改成：只要机器狗此刻就在某频道"最后一次测到信号的站"附近，就先把它做掉。
        "opportunity_m": 0.0,       # 触发半径（m）；0 = 关闭
        # v3 改动 1：收尾段提交式 TSP。测站走完后不再逐次贪心最近，而是把残余频道
        # 按开链 TSP（重排 + 2-opt）排一次序，逐个做完——收尾段没有普查任务可插队，
        # 没有理由在中途换频道。
        "tail_tsp": True,
        # v3 改动 2：每局结束时输出残余段统计（起点时刻、频道数、里程占比）。
        "residual_report": True,
        # v3 改动 3：短承诺队列。实测同一批点的 2-opt 最优开链比实际路线短 20.0%
        # （28.90 → 23.11 km，约 1160 s），说明浪费全在"顺序"上。
        # 但"承诺整条巡回序"（backbone）实测更差——因为不能适应新出现的工作点。
        # 折中：每次重排后只承诺前 H 件，做完就重排。H=1 即当前逐步贪心。
        "commit_horizon": 1,
        "approach_angles": [0.0, 20.0, -20.0, 40.0, -40.0],   # 实测最优：共线点优先
        # 折中：远距离时横向绕路太贵（一次测量只值 6 s，300 m 的横向绕行要 60 s），
        # 所以只在近处才改用宽角。设 0 表示关闭这个折中。
        "wide_near_m": 0.0,
        "approach_angles_near": [45.0, -45.0, 30.0, -30.0, 0.0],
        # 实测：按预测误差界重排候选点反而更慢（656 s vs 628 s / 24 例）。原因是
        # 候选点里绝大多数"指向估计点"的楔形与细长定位区域不相交，预测值退化为 inf，
        # 排序就塌成"就近优先"；而 v1 的"先走大步（0.75/0.5/0.3×dist）"实测更好。
        # 保留开关与实现，默认关闭，供后续换更准的预测式再试。
        "predict_order": False,     # True = 按预测误差界重排候选点；False = 用 v1 的顺序
        "predict_travel_weight": 0.5,  # 排序准则 = 预测误差界(m) + 权重×路程(m)
        "raster_pitch": 28.0,       # 光栅间距（m），覆盖半径 = pitch/√2 ≈ 19.8 m
        "predict_topk": 5,          # 一步预测只对前 k 个候选点算（省时间）
        # 实测这两个代价项都是负收益（见文件头"实测结论"），默认关闭。
        "lockin_weight": 0.0,       # "收尾代价"权重：越大越倾向于把当前频道做完
        "redundancy_radius": 320.0,  # 冗余惩罚的作用半径（m）
        "redundancy_penalty": 0.0,  # 每命中一个近期探测点的罚时（s）
    }

    def __init__(self, sim, params: dict | None = None, *, verbose: bool = False):
        super().__init__(sim, params, verbose=verbose)
        self._recent: list[tuple[float, float]] = []   # 最近的探测/清除点
        self._cand: dict[int, tuple] = {}              # 频道 → (指纹, 排好序的候选点)
        self._sector: dict[int, tuple] = {}            # 频道 → (指纹, 定向方向可行角)
        self._tail_alive: list[int] | None = None      # 残余频道集合（变化时重排巡回序）
        self._tail_order: list[int] = []               # 残余频道的提交式巡回序
        self._tail_start: float | None = None          # 残余段开始的虚拟时刻
        self._tail_dist = 0.0                          # 残余段移动里程（m）
        self._tail_actions = 0                         # 残余段动作数
        self._queue: list[tuple[str, object]] = []     # 短承诺队列：(kind, key)
        self._tsp_passes = 30                          # 重排时 2-opt 的迭代上限

    # ------------------------------------------- 改动 5：圆弧逼近 + 扇区可行性
    def survey_stations(self) -> list[tuple[float, float]]:
        """按参数生成布站（默认与 v1 完全相同：内层 13 + 外环 12）。"""
        k = int(self.p.get("outer_k", 12))
        pts: list[tuple[float, float]] = [(0.0, 0.0)]
        pts += [q for q in _inner_lattice() if q != (0.0, 0.0)]
        if k > 0:
            pts += _outer_ring(OUTER_R, k)
        return pts

    def layout_boundary_miss(self) -> int:
        """布站自检也要按当前参数算（基类那个是 classmethod，会用默认布站）。"""
        return self.boundary_miss(self.survey_stations(), 720)

    @staticmethod
    def _arc_family(c, g, d, step):
        """绕**估计点** c 铺一圆圈候选点：从 c 看，与 (g−c) 方向成 ±60/±75/±90°。

        半径取 0.4d / 0.6d / 0.9d（上限 step），所以既朝源收拢、又在源处张出
        接近 90° 的交会角。按"先 90°、再 75°、再 60°"排序交给上层逐点试。
        """
        ux, uy = (g[0] - c[0]) / d, (g[1] - c[1]) / d
        out: list[tuple[float, float]] = []
        for frac in (0.4, 0.6, 0.9):
            rho = max(min(d * frac, step), 30.0)
            for ang in (90.0, -90.0, 75.0, -75.0, 60.0, -60.0):
                v = _rot((ux, uy), math.radians(ang))
                out.append((c[0] + rho * v[0], c[1] + rho * v[1]))
        return out

    def _sector_axis(self, ch: int) -> tuple[float, float] | None:
        """反推定向源的**定向方向**（度）；推不出来返回 None。

        依据：测到过信号的测站必在扇区内（(s−G)·u ≥ 0）；而**落在 1000 m 以内
        却返回 no_signal 的测站**必在扇区外（全向源在 1000 m 内不可能测不到，
        所以这类 no_signal 只能是"盲区"）。把这两个约束在 u 上求交，
        可行角区间的中点就是 u 的估计。
        """
        st = self.state[ch]
        c = st.center
        if c is None or not st.bearings or not st.no_signal:
            return None
        missed = [(sx, sy) for (sx, sy) in st.no_signal
                  if math.hypot(sx - c[0], sy - c[1]) <= R_MIN]
        if not missed:
            return None                      # 判不出是定向源，不启用扇区约束
        cons = [(math.degrees(math.atan2(sy - c[1], sx - c[0])), True)
                for (sx, sy, _p) in st.bearings]
        cons += [(math.degrees(math.atan2(sy - c[1], sx - c[0])), False)
                 for (sx, sy) in missed]
        ok = []
        for u in range(0, 360, 2):
            good = True
            for (a, seen) in cons:
                dd = abs(((a - u + 180.0) % 360.0) - 180.0)
                if seen and dd > 88.0:
                    good = False
                    break
                if (not seen) and dd < 92.0:
                    good = False
                    break
            if good:
                ok.append(u)
        if not ok:
            return None
        # 取最长的连续区间（跨 0° 也算连），返回中点
        s = set(ok)
        best_lo, best_len = ok[0], 1
        for start in ok:
            if (start - 2) % 360 in s:
                continue                     # 不是区间起点
            ln = 0
            while (start + 2 * ln) % 360 in s:
                ln += 1
            if ln > best_len:
                best_lo, best_len = start, ln
        width = (best_len - 1) * 2.0
        mid = (best_lo + (best_len - 1)) % 360
        return float(mid), float(width)

    def _filter_sector(self, ch: int, cands: list) -> list:
        """按扇区估计调整候选点顺序。

        `soft`：把与扇区一致的点提到前面，其余保留在后面（估计不准时不至于卡死）；
        `filter`：直接剔除不一致的点（估错就有风险，默认不用）。
        """
        st = self.state[ch]
        c = st.center
        if c is None or not cands:
            return cands
        mode = str(self.p.get("sector_mode", "soft"))
        if mode == "off":
            return cands
        sig = (len(st.bearings), len(st.no_signal),
               round(st.radius, 1) if math.isfinite(st.radius) else -1.0)
        hit = self._sector.get(ch)
        if hit is None or hit[0] != sig:
            hit = (sig, self._sector_axis(ch))
            self._sector[ch] = hit
        est = hit[1]
        if est is None:
            return cands
        u, width = est
        if width > float(self.p.get("sector_max_width", 120.0)):
            return cands                      # 夹得不够紧，估计不可靠
        margin = float(self.p.get("sector_margin_deg", 15.0))
        good, bad = [], []
        for q in cands:
            a = math.degrees(math.atan2(q[1] - c[1], q[0] - c[0]))
            dd = abs(((a - u + 180.0) % 360.0) - 180.0)
            if dd <= 90.0 - margin:
                good.append(q)
            else:
                bad.append(q)
        if mode == "filter":
            return good if good else cands
        return good + bad

    def _candidates(self, ch: int) -> list[tuple[float, float]]:
        """逼近段的候选点：宽角优先，并按估计的扇区做软排序。"""
        st = self.state[ch]
        mode = str(self.p.get("approach_mode", "wide"))
        if (mode != "v1" and st.bearings and st.center is not None
                and st.radius > float(self.p["good_radius"])):
            gx, gy, phi_g = st.bearings[-1]
            d = math.hypot(st.center[0] - gx, st.center[1] - gy)
            if d > 1.0:
                step = self._step.get(ch, float(self.p["max_step"]))
                if mode == "arc":
                    out = self._arc_family(st.center, (gx, gy), d, step)
                    if bool(self.p.get("ray_fallback", False)):
                        # 兜底：源比估计近得多时圆弧点会跨过头，留两个沿射线收拢的点。
                        # 但这类点与上一条方位线近乎共线（θ≈0°），默认不用。
                        u = _dir(phi_g)
                        for frac in (0.5, 0.25):
                            s = max(min(d * frac, step), 10.0)
                            out.append((gx + s * u[0], gy + s * u[1]))
                else:
                    # wide：几何与 v1 完全一致（从"最后一次测到信号的站"出发、朝估计
                    # 中心方向走），只把角度序列换成宽角优先、共线点挪到最后。
                    base = ((st.center[0] - gx) / d, (st.center[1] - gy) / d)
                    out = []
                    angles = self.p.get("approach_angles") or (0.0,)
                    near_m = float(self.p.get("wide_near_m", 0.0))
                    if near_m > 0.0 and d <= near_m:
                        angles = self.p.get("approach_angles_near") or angles
                    for frac in (0.75, 0.5, 0.3):
                        s = min(d * frac, step)
                        for ang in angles:
                            v = _rot(base, math.radians(ang))
                            out.append((gx + s * v[0], gy + s * v[1]))
                return self._predict_order(ch, self._filter_sector(ch, out))
        return self._predict_order(ch, self._filter_sector(ch, super()._candidates(ch)))

    # ---------------------------------------------------------- 改动 1：铺清
    def _sweep_plan(self, ch: int) -> list[tuple[float, float]] | None:
        """牛耕式光栅铺清计划（盖不满也返回部分计划，绝不整条放弃）。"""
        if str(self.p.get("sweep_mode", "raster")) != "raster":
            return super()._sweep_plan(ch)
        st = self.state[ch]
        if not st.polygon:
            return None
        pitch = float(self.p["raster_pitch"])
        cap = int(self.p["max_probes"])
        plan = _axis_raster(st.polygon, pitch)
        if not plan:
            return super()._sweep_plan(ch)          # 退化情形交回 v1
        done = set(self._probes.get(ch, []))
        todo = [q for q in plan if q not in done]
        if not todo:
            return None
        # 从当前位置向外扫：近端的真源最可能、也最省路
        cx, cy = self.pos
        todo.sort(key=lambda q: math.hypot(q[0] - cx, q[1] - cy))
        return todo[:cap]

    # ------------------------------------------------- 改动 2：候选点预测排序
    def _predict_radius(self, ch: int, q: tuple[float, float]) -> float:
        """在 q 测一次后，定位区域最小外接圆半径的**预测值**。

        假设该次测量会返回一条指向当前估计点的示向度（最可能的读数），
        再叠加"测到 ⇒ 距离 ≤ 1500 m"的圆盘裁剪，最后取最小外接圆半径。
        这是 FIM/CRLB 那套指标在本题里可直接计算的替身。
        """
        st = self.state[ch]
        if not st.polygon or st.center is None:
            return float("inf")
        phi = math.degrees(math.atan2(st.center[1] - q[1], st.center[0] - q[0]))
        poly = clip_wedge(st.polygon, q, phi)
        if len(poly) < 3:
            return float("inf")
        poly = clip_disc(poly, q, R_MAX, n=24)
        if len(poly) < 3:
            return float("inf")
        _c, r = min_enclosing_circle(poly)
        return r

    def _predict_order(self, ch: int, raw: list) -> list[tuple[float, float]]:
        """把候选点顺序换成"预测误差界最小优先"（改动 2，默认关闭）。"""
        st = self.state[ch]
        if not bool(self.p.get("predict_order", True)):
            return raw
        if len(raw) < 2 or not st.polygon or st.center is None:
            return raw
        sig = (len(st.bearings), round(st.radius, 1) if math.isfinite(st.radius) else -1.0,
               len(raw))
        cached = self._cand.get(ch)
        if cached is not None and cached[0] == sig:
            return cached[1]
        k = max(int(self.p["predict_topk"]), 1)
        w = float(self.p.get("predict_travel_weight", 0.0))
        cx, cy = self.pos
        scored = []
        for i, q in enumerate(raw):
            # 只对几何上最近的前 k 个做预测（其余保持相对次序跟在后头）
            r = self._predict_radius(ch, q) if i < k else float("inf")
            d = math.hypot(q[0] - cx, q[1] - cy)
            # 只按误差界排会挑中"很远但略准"的点（实测里程涨 19%）；
            # 因此把路程按权重折算进来，两点一起看。
            scored.append((r + w * d, d, i, q))
        scored.sort(key=lambda t: (t[0], t[1], t[2]))
        out = [t[3] for t in scored]
        self._cand[ch] = (sig, out)
        return out

    # ------------------------------------------------- 改动 3/4：真实代价计价
    def _lockin(self, ch: int, pt: tuple[float, float]) -> float:
        """收尾代价：做完这一件之后，紧接着为同一频道还要花多少秒——**只看下一跳**。

        起初写成"把整个频道做完的剩余时间"，实测反而更慢：那等于给所有未完成的
        频道加一个几百秒的大罚项，主循环就退化成"先走完 25 个测站、再统一清除"
        的两阶段做法（文献与实测都表明这样里程要贵约 38%）。
        改成两步前瞻后，"顺着同一频道继续走"天然便宜，"跳过去再跳回来"天然贵，
        频道承诺就不再需要额外的 focus 机制。
        """
        st = self.state[ch]
        if st.cleared:
            return 0.0
        tried = self._tried.setdefault(ch, set())
        key_pt = (round(pt[0] / 25.0), round(pt[1] / 25.0))
        nxt = None
        for q in self._candidates(ch):
            k = (round(q[0] / 25.0), round(q[1] / 25.0))
            if k == key_pt or k in tried:
                continue
            nxt = q
            break
        if nxt is None:
            if st.center is None:
                return 6.0
            return math.hypot(st.center[0] - pt[0], st.center[1] - pt[1]) / SPEED + 5.0
        return math.hypot(nxt[0] - pt[0], nxt[1] - pt[1]) / SPEED + 6.0

    def _redundancy(self, pt: tuple[float, float]) -> float:
        """奖励共享：最近探测过的邻域给罚时，抑制重复探测。"""
        rr = float(self.p["redundancy_radius"])
        pen = float(self.p["redundancy_penalty"])
        if rr <= 0 or pen <= 0 or not self._recent:
            return 0.0
        hits = 0
        for (qx, qy) in self._recent:
            if abs(qx - pt[0]) > rr or abs(qy - pt[1]) > rr:
                continue
            if math.hypot(qx - pt[0], qy - pt[1]) <= rr:
                hits += 1
        return pen * hits

    def _task_cost(self, pt, kind: str, ch: int | None) -> float:
        travel = math.hypot(pt[0] - self.pos[0], pt[1] - self.pos[1]) / SPEED
        if kind == "survey":
            return travel
        assert ch is not None
        return (travel
                + float(self.p["lockin_weight"]) * self._lockin(ch, pt)
                + self._redundancy(pt))

    @staticmethod
    def _on_corridor(a, b, q, tol: float) -> bool:
        """q 是否落在 a→b 这条走线的 tol 米走廊内。"""
        vx, vy = b[0] - a[0], b[1] - a[1]
        L2 = vx * vx + vy * vy
        if L2 < 1e-9:
            return math.hypot(q[0] - a[0], q[1] - a[1]) <= tol
        t = ((q[0] - a[0]) * vx + (q[1] - a[1]) * vy) / L2
        t = min(max(t, 0.0), 1.0)
        px, py = a[0] + t * vx, a[1] + t * vy
        return math.hypot(q[0] - px, q[1] - py) <= tol

    # ------------------------------------------------------------------ 主流程
    def run(self) -> dict:
        enter = self.sim.enter()
        budget = float(enter.get("remaining_real_duration_s", 1200))
        self.budget_real = budget
        self.deadline = time.perf_counter() + max(
            budget - float(self.p["real_time_margin"]), 5.0)

        self.clean_sweep(0.0, 0.0)
        pending = [p for p in self.survey_stations() if p != (0.0, 0.0)]
        if bool(self.p.get("backbone", False)):
            order = plan_tsp(pending, self.pos)
            pending = [pending[i] for i in order]
        elif str(self.p.get("survey_order", "tsp")) == "inner_first":
            # 内层 13 站先把全区罩住（发现 + 判定绝大多数频道），
            # 外环留到后面，那时"还没结论"的频道已经很少，每个外环站要测的就少了。
            k = int(self.p.get("outer_k", 12))
            inner = set(_inner_lattice())
            head = [p for p in pending if p in inner]
            tail = [p for p in pending if p not in inner]
            pending = [head[i] for i in plan_tsp(head, self.pos)] + \
                      [tail[i] for i in plan_tsp(tail, head[-1] if head else self.pos)]
        failed: set[int] = set()

        while not self._out_of_time() and not self._all_done():
            backbone_on = bool(self.p.get("backbone", False))
            nxt = pending[0] if (backbone_on and pending) else None
            tasks: list[tuple[tuple[float, float], str, int | None]] = []
            if not backbone_on:
                tasks += [(pt, "survey", None) for pt in pending]
            for ch in CHANNELS:
                st = self.state[ch]
                if st.cleared or not st.known:
                    continue
                if self._exclusion_ok(ch):
                    continue
                if ch in failed and not (st.radius <= CLEAR_RADIUS):
                    continue
                pt = self._next_target(ch)
                if pt is None:
                    continue
                if backbone_on:
                    # 只在"顺路"或"只差临门一脚"时才允许插进来
                    nearly = st.radius <= float(self.p["good_radius"])
                    if nxt is not None and not nearly and not self._on_corridor(
                            self.pos, nxt, pt, float(self.p["corridor_m"])):
                        continue
                tasks.append((pt, "work", ch))
            if nxt is not None:
                tasks.append((nxt, "survey", None))
            if self._left_ratio() < float(self.p["time_guard"]):
                only_work = [t for t in tasks if t[1] == "work"]
                if only_work:
                    tasks = only_work
            if not tasks:
                break

            # ---- v3 改动 1：收尾段提交式 TSP ----
            # 测站走完后（pending 空）把残余频道排成一个开链 TSP，逐个做完；
            # 残余集合变了才重排。收尾段没有普查任务可插队，中途换频道只会白走路。
            if not pending and bool(self.p.get("tail_tsp", True)):
                alive = [c for c in CHANNELS
                         if self.state[c].known and not self.state[c].cleared
                         and not self._exclusion_ok(c)]
                if alive != self._tail_alive:
                    self._tail_alive = list(alive)
                    pts = []
                    for c in alive:
                        stc = self.state[c]
                        pts.append(stc.center if stc.center is not None
                                   else (self._next_target(c) or self.pos))
                    order = plan_tsp(pts, self.pos)
                    self._tail_order = [alive[i] for i in order]
                if self._tail_order:
                    c0 = self._tail_order[0]
                    pt0 = self._next_target(c0)
                    if pt0 is not None:
                        if self._tail_start is None:
                            self._tail_start = self.virtual_time
                        tasks = [(pt0, "work", c0)]

            # 机会主义：此刻就在某频道的"工作邻域"里（离它最后一次测到信号的站很近），
            # 就先把它做掉，别等收尾时再横跨地图回来。实测这样能消掉大部分长途折返。
            opp_m = float(self.p.get("opportunity_m", 0.0))
            if opp_m > 0.0:
                opp: list[tuple[tuple[float, float], str, int | None]] = []
                for ch in CHANNELS:
                    st = self.state[ch]
                    if st.cleared or not st.known or self._exclusion_ok(ch):
                        continue
                    if not st.bearings:
                        continue
                    gx, gy = st.bearings[-1][0], st.bearings[-1][1]
                    if math.hypot(gx - self.pos[0], gy - self.pos[1]) > opp_m:
                        continue
                    pt = self._next_target(ch)
                    if pt is not None:
                        opp.append((pt, "work", ch))
                if opp:
                    tasks = opp

            # 真实代价计价：行驶 + 动作 + 收尾 + 冗余罚，取最小的一件去做。
            H = max(int(self.p.get("commit_horizon", 1)), 1)
            picked = None
            if H > 1:
                # 短承诺队列：队列空了才用 2-opt 重排一次，一次提交前 H 件。
                # 队列里的"工作"项只记频道号，每次执行时现取它的当前最优候选点。
                while self._queue:
                    k0, key0 = self._queue[0]
                    if k0 == "survey":
                        if key0 in pending:
                            break
                    else:
                        st0 = self.state[int(key0)]
                        if (st0.known and not st0.cleared
                                and not self._exclusion_ok(int(key0))
                                and self._next_target(int(key0)) is not None):
                            break
                    self._queue.pop(0)
                if not self._queue:
                    order = plan_tsp([t[0] for t in tasks], self.pos,
                                     passes=self._tsp_passes)
                    self._queue = [((t[1], t[2]) if t[1] == "work" else ("survey", t[0]))
                                   for t in (tasks[i] for i in order[:H])]
                if self._queue:
                    k0, key0 = self._queue[0]
                    if k0 == "survey":
                        picked = (key0, "survey", None)
                    else:
                        p0 = self._next_target(int(key0))
                        if p0 is not None:
                            picked = (p0, "work", int(key0))
                    if picked is not None:
                        self._queue.pop(0)
            if picked is None:
                best_i, best_c = 0, float("inf")
                for i, (pt, kind, ch) in enumerate(tasks):
                    c = self._task_cost(pt, kind, ch)
                    if c < best_c:
                        best_i, best_c = i, c
                picked = tasks[best_i]
            pt, kind, ch = picked

            if kind == "survey":
                self.clean_sweep(pt[0], pt[1])
                if pt in pending:
                    pending.remove(pt)
                continue

            assert ch is not None
            st = self.state[ch]
            before = (st.radius, len(self._probes.get(ch, ())))
            if self._tail_start is not None and not pending:
                # 残余段里程/动作数（仅供报告，不影响任何决策）
                self._tail_dist += math.hypot(pt[0] - self.pos[0], pt[1] - self.pos[1])
                self._tail_actions += 1
            self.work(ch)
            self._rounds[ch] = self._rounds.get(ch, 0) + 1
            if st.cleared:
                self._stuck.pop(ch, None)
                continue
            after = (st.radius, len(self._probes.get(ch, ())))
            improved = (after[1] > before[1]
                        or (math.isfinite(st.radius)
                            and (not math.isfinite(before[0])
                                 or st.radius < before[0] * 0.98)))
            self._stuck[ch] = 0 if improved else self._stuck.get(ch, 0) + 1
            if self._stuck[ch] >= int(self.p["max_stuck"]) or self._rounds[ch] >= 20:
                failed.add(ch)

        # ---------------------------------------------------------- 收尾统计
        unknown = [c for c in CHANNELS
                   if not self.state[c].known and not self.state[c].cleared]
        missed = [c for c in CHANNELS
                  if self.state[c].known and not self.state[c].cleared]
        excluded = [c for c in unknown if self._exclusion_ok(c)]
        if len(excluded) < len(unknown):
            self.notes.append(
                f"有 {len(unknown) - len(excluded)} 个频道既没测到也没能排除"
                "（未走完全部测站或时间不足）")
        n_station = len(self.survey_stations())
        if len(self.stations) < n_station:
            self.notes.append(f"只走了 {len(self.stations)}/{n_station} 个测站")
        miss = self.layout_boundary_miss()
        if miss:
            self.notes.append(
                f"布站自检未通过：边界上有 {miss}/720 个点的向外切线方向没有测站")
        # ---- v3 改动 2：残余段统计 ----
        tail_info = None
        if bool(self.p.get("residual_report", True)):
            t0 = self._tail_start
            tail_t = (self.virtual_time - t0) if t0 is not None else 0.0
            tail_info = {
                "残余段起点(s)": round(t0, 1) if t0 is not None else None,
                "残余段时长(s)": round(tail_t, 1),
                "残余段占全程": (f"{tail_t / self.virtual_time:.1%}"
                                 if self.virtual_time else "0.0%"),
                "残余段动作数": self._tail_actions,
                "残余段里程(m)": round(self._tail_dist, 1),
                "残余段里程占全区": (f"{self._tail_dist / (self.virtual_time * SPEED):.1%}"
                                     if self.virtual_time else "0.0%"),
                "残余段起始频道数": len(self._tail_alive or []),
            }
            self.notes.append(
                f"残余段：t={tail_info['残余段起点(s)']}s 起，"
                f"{tail_info['残余段时长(s)']}s（占 {tail_info['残余段占全程']}），"
                f"{self._tail_actions} 个动作 / {self._tail_dist / 1000:.2f} km")
        self.sim.exit()
        return {
            "cleared": len(self.cleared_channels),
            "cleared_channels": sorted(self.cleared_channels),
            "判定不存在": excluded,
            "未判定": [c for c in unknown if c not in excluded],
            "已发现但未清除": missed,
            "布站自检": (f"边界 720 点向外切线均有测站（{n_station} 站）"
                         if not miss else f"{miss}/720 点不满足"),
            "虚拟总时间": self.virtual_time,
            "平均定位清除时间": (self.virtual_time / len(self.cleared_channels)
                                 if self.cleared_channels else float("inf")),
            "measure次数": self.n_measure,
            "clear次数": self.n_clear,
            "clear落空次数": self.n_miss,
            "走过测站数": len(self.stations),
            "残余段": tail_info,
            "备注": self.notes,
        }

    # 记录最近探测点，供"奖励共享"用（不改动画任何行为，只旁路记账）
    def measure(self, x, y, ch):
        r = super().measure(x, y, ch)
        self._recent.append((x, y))
        if len(self._recent) > 60:
            del self._recent[:20]
        return r

    def clear(self, x, y, ch):
        r = super().clear(x, y, ch)
        self._recent.append((x, y))
        if len(self._recent) > 60:
            del self._recent[:20]
        return r


# ================================================================== 算法登记
SPEC = AlgorithmSpec(
    id="p4-v3-residual",
    name="第四题 v3 残余优化算法",
    problem="问题4",
    summary="v1 布站 + 牛耕式铺清 + 预测误差最小选点 + 真实代价滚动计价",
    description=(
        "【与 v1 相同的部分】25 站包围式排查（内层六边形格 13 站 + ρ=1900 外环 12 站，"
        "对『位置×方向』零漏检）、凸包包围式排除判据、示向度楔形交会定位。\n"
        "【改动 1·牛耕式铺清 · 已生效】沿定位区域主轴铺牛耕式光栅，间距 28 m"
        "（覆盖半径 19.8 m < 20 m 清除半径，实测区域采样点最大未覆盖距离 19.0 m），"
        "并按『离机器狗由近及远』取前 max_probes 个，保证近端一定被完整扫到。\n"
        "【改动 2·预测误差最小选点】对候选测点做一步预测：假设测到指向当前估计点的"
        "示向度，算新定位区域的最小外接圆半径，按它升序排——把文献里『FIM 行列式最大』"
        "换成『保证误差界最小』。实测负收益（656 s vs 628 s），默认关闭。\n"
        "【改动 3·真实代价计价】主循环不再只按直线距离挑最近，而是按"
        "行驶 + 动作 + 收尾代价 + 冗余罚计价，倾向于把接近完成的频道做完，"
        "抑制 v1 那种在几条射线之间来回跳的长途折返。实测负收益（677 s），默认关闭。\n"
        "【改动 4·奖励共享】对最近探测过的邻域加罚时，抑制重复探测同一片区域。"
        "实测负收益（722 s），默认关闭。\n"
        "【实测】v1 645.9 s / 297.1 次 / 100.00%，v2 默认 639.0 s / 293.5 次 / 100.00%"
        "（100 例，同一批种子）。"
    ),
    params=dict(P4V3Hunter.DEFAULTS),
    entry="algorithms/p4_v3_residual.py: P4V3Hunter",
)


def build(sim, params: dict | None = None, *, verbose: bool = False):
    return P4V3Hunter(sim, params, verbose=verbose)

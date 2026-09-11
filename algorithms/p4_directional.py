# -*- coding: utf-8 -*-
"""第四题导航算法 —— 25 站包围式排查 + 单条滚动回路 + 沿示向度逼近清除。

思路与全部数值依据见 `docs/问题3-4_导航思路.md`。与第三题（`p3_baseline.py`）
的差别只有三条，但每条都致命：

1) **排除性布站必须"包围"而不是"距离覆盖"**
   定向源只在定向方向两侧各 90° 内辐射，所以 no_signal 不再蕴含"距离 > 1000 m"
   （还可能是"在盲区"）。判"某频道不存在"的正确条件变成：对区域内每一点 p，
   p 必须落在"距 p ≤ 1000 m 的**无信号测站**"的凸包内——只要 p 在凸包里，
   任何发射方向都会至少罩住其中一个测站，与它返回 no_signal 矛盾。
   实测：只布内层 13 站时定向漏检率 5.97%；内层 13 站 + ρ=1900 m 外环 12 站
   （本文件 `survey_stations()`）在 2821 个网格点 × 36 个方向上**零漏检**。
   区域边界上朝外的定向源，在区域内部任何位置都测不到，所以外环不能省。

2) **不能用 no_signal 反推距离**
   第三题的 `_ray_intervals()` 靠"别处 no_signal ⇒ 源距该处 > 1000 m"把源锁在
   射线上的一小段里；第四题这条推理不成立，因此本文件不调用它，只用示向度楔形
   交会（楔形本身与定向无关，只要测到过就成立）。

3) **不能靠 near 收尾**
   从背面靠近定向源返回的是 no_signal，所以第四题必须走完整的
   "逼近 → 交会 → 从中心 /clear"。好在 /clear 只看距离 ≤ 20 m，与朝向无关。

导航主干（与第三题相同的一条回路）：

    待办池 = {未去的测站} ∪ {待逼近/待清除的已知频道}
    每一步对当前待办点集做一次滚动 TSP，走最近的一件——排查、定位、清除共用
    同一条路线，而不是"先普查再清除"（后者里程要贵约 38%，见思路文档 §4.2）。

逼近机动的依据（思路文档 §5，问题2 的定理）：第一次测到某频道时若源距测站
r₁ > 1146 m，那么**无论第二个测站放哪里**都不可能把定位误差压到 20 m
（R_c ≥ r₁·tan1°）。所以必须沿示向度推进、边走边重测，把"最后一次测量的距离"
压到 ~700 m 以内，再按 ψ≈±45°、d≈√2·r 布置两点，此时 R_c ≤ 20 m，一次命中。
"""

from __future__ import annotations

import math
import time

from .base import AlgorithmSpec
from .p3_baseline import (ARENA_R, CHANNELS, CLEAR_RADIUS, R_MAX, R_MIN, SAMPLES,
                          ChannelState, InterferenceHunter, _dir, _rot,
                          point_segment_distance, plan_tsp)

# ------------------------------------------------------------------ 布站参数
LATTICE_D = 1000.0          # 内层六边形格间距（覆盖半径 d/√3 ≈ 577 m < 1000 m）
LATTICE_LIMIT = 1900.0      # 内层格点保留到半径 1900 m ⇒ 13 站
OUTER_R = 1900.0            # 外环半径（在区域外；题目允许向区域外提交坐标）
OUTER_K = 12                # 外环站数（间距 2·1900·sin15° ≈ 984 m）
_HEX_U = (LATTICE_D, 0.0)
_HEX_V = (LATTICE_D * 0.5, LATTICE_D * math.sqrt(3.0) / 2.0)


def _inner_lattice(limit: float = LATTICE_LIMIT) -> list[tuple[float, float]]:
    """内层六边形格点，保留在半径 limit 内的（d=1000、lim=1900 时为 13 站）。"""
    pts: list[tuple[float, float]] = []
    for i in range(-3, 4):
        for j in range(-3, 4):
            x = i * _HEX_U[0] + j * _HEX_V[0]
            y = i * _HEX_U[1] + j * _HEX_V[1]
            if math.hypot(x, y) <= limit + 1e-9:
                pts.append((x, y))
    return sorted(pts, key=lambda p: math.hypot(p[0], p[1]))


def _outer_ring(r: float = OUTER_R, k: int = OUTER_K) -> list[tuple[float, float]]:
    """区域外的包围环：半径 1900 m 均匀 12 站。"""
    return [(r * math.cos(2.0 * math.pi * i / k), r * math.sin(2.0 * math.pi * i / k))
            for i in range(k)]


def _border_samples(r: float = ARENA_R, k: int = 360) -> list[tuple[float, float]]:
    """目标区域边界上的加密采样点（定向源漏检最危险的地方就是边界）。"""
    return [(r * math.cos(2.0 * math.pi * i / k), r * math.sin(2.0 * math.pi * i / k))
            for i in range(k)]


def _poly_samples(poly: list, step: float = 15.0) -> list[tuple[float, float]]:
    """把多边形按 step 米在边上打点（顶点必取），用于"铺清"定位区域。"""
    out: list[tuple[float, float]] = []
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        seg = math.hypot(x1 - x0, y1 - y0)
        k = max(int(seg / step), 1)
        for t in range(k):
            u = t / k
            out.append((x0 + (x1 - x0) * u, y0 + (y1 - y0) * u))
    return out


#: 判定"某频道不存在"时用的采样点：60 m 网格 + 边界 1° 加密
EXCLUDE_SAMPLES = list(SAMPLES) + _border_samples()


class P4Hunter(InterferenceHunter):
    """问题4 的机器狗策略（复用问题3 的观测簿记与交会几何）。"""

    #: 可调参数默认值（键名即 SPEC.params 的键）
    DEFAULTS = {
        "max_step": 700.0,          # 逼近段单次最多走多远（m）
        "good_radius": 300.0,       # 定位区域半径 ≤ 它 → 转入 ±45° 精定位
        "max_stuck": 4,             # 连续几次没进展就放弃该频道（防死循环）
        "max_probes": 120,          # 铺清时最多试探几次 /clear（够盖住区域内任何细长条）
        "probe_gap": 20.0,          # 铺清间距（= 清除半径，保证盖满整个区域）
        "time_guard": 0.25,         # 剩余现实时间低于此比例时，只清目标不再普查
        "real_time_margin": 20.0,   # 现实时间安全余量（s）
    }

    def __init__(self, sim, params: dict | None = None, *, verbose: bool = False):
        super().__init__(sim, verbose=verbose)
        self.p = {**self.DEFAULTS, **(params or {})}
        self._excl: dict[int, tuple[int, bool]] = {}    # 频道 → (证据条数, 是否已排除)
        self._rounds: dict[int, int] = {}               # 频道 → 已经历的工作轮次
        self._stuck: dict[int, int] = {}                # 频道 → 连续无进展次数
        self._tried: dict[int, set] = {}                # 频道 → 已测过的点（同一地点重复测没有新信息）
        self._step: dict[int, float] = {}               # 频道 → 当前逼近步长（自适应）
        self._probes: dict[int, list] = {}              # 频道 → 已经试过的 /clear 点
        self._sweep: dict[int, tuple] = {}              # 频道 → (区域指纹, 铺清计划) 缓存
        self.budget_real = 0.0

    # -------------------------------------------------------------- 布站
    @staticmethod
    def survey_stations() -> list[tuple[float, float]]:
        """25 个排除性测站：内层六边形格 13 站 + ρ=1900 m 外环 12 站。

        该布站对"位置 × 定向方向"零漏检（2821 网格点 × 36 方向全验证过）：
        对区域内每一点 p，距 p ≤ 1000 m 的测站都能把 p 包在凸包里。
        """
        pts = [(0.0, 0.0)]
        pts += [q for q in _inner_lattice() if q != (0.0, 0.0)]
        pts += _outer_ring()
        return pts

    # -------------------------------------------------------------- 排除判据
    @staticmethod
    def _in_hull(p, pts) -> bool:
        """p 是否落在点集 pts 的凸包内（含边界）。

        等价判据：把各点相对 p 的方位角排序后，**最大角隙 ≤ 180°**——只要有一道
        过 p 的直线能把所有点分到同一侧，这个角隙就会 > 180°，p 就在凸包外。
        """
        if not pts:
            return False
        ang: list[float] = []
        for (sx, sy) in pts:
            dx, dy = sx - p[0], sy - p[1]
            if abs(dx) < 1e-9 and abs(dy) < 1e-9:
                return True                     # 测站与 p 重合
            ang.append(math.atan2(dy, dx))
        ang.sort()
        gap = max([ang[i + 1] - ang[i] for i in range(len(ang) - 1)]
                  + [ang[0] + 2.0 * math.pi - ang[-1]])
        return gap <= math.pi + 1e-9

    def _exclusion_ok(self, ch: int) -> bool:
        """该频道能否判定"不存在"：无信号测站在 1000 m 半径下已包围全区。"""
        ns = self.state[ch].no_signal
        hit = self._excl.get(ch)
        if hit is not None and hit[0] == len(ns):
            return hit[1]                       # 证据没变，用缓存（每个测站都要查，必须快）
        # 先过一遍廉价必要条件（圆上各点"向外切线半平面"里得有测站）：过不了就直接否掉，
        # 省下后面几千个采样点的凸包检查。它是完整条件的推论，不会误杀。
        if not self._boundary_necessary(ns):
            self._excl[ch] = (len(ns), False)
            return False
        ok = len(ns) >= 4
        if ok:
            for p in EXCLUDE_SAMPLES:
                near = [(sx, sy) for (sx, sy) in ns
                        if (sx - p[0]) ** 2 + (sy - p[1]) ** 2 <= R_MIN * R_MIN]
                if not self._in_hull(p, near):
                    ok = False
                    break                       # 早退：绝大多数频道在前几个采样点就被否掉
        self._excl[ch] = (len(ns), ok)
        return ok

    @staticmethod
    def _in_polygon(p, poly) -> bool:
        """点是否在多边形内（射线法）——用来判断"狗现在站的这个地方像不像源的位置"。"""
        x, y = p[0], p[1]
        inside = False
        n = len(poly)
        for i in range(n):
            x0, y0 = poly[i]
            x1, y1 = poly[(i + 1) % n]
            if (y0 > y) != (y1 > y):
                t = (y - y0) / (y1 - y0)
                if x < x0 + t * (x1 - x0):
                    inside = not inside
        return inside

    #: 边界自检的采样点数（2° 一个点）
    BOUNDARY_K = 180

    @classmethod
    def boundary_miss(cls, stations, k: int | None = None) -> int:
        """▍停止条件的"必要条件"：圆上每个点的向外切线半平面里都要有测站。

        对圆上一点 p（|p| = 1800），若某定向源就在 p 且朝**外**发射，那么它能被
        探测到的测站 s 必须同时满足 |s−p| ≤ 1000 与 (s−p)·p̂ ≥ 0——即落在"向外
        切线半平面"里。所以只要有一个边界点的这个半平面里没有测站，就一定有
        某些朝向的源永远测不到，**必然漏检**。

        这个条件正是"必须把测站铺到区域外面"的原因：区域内任何点都满足
        (s−p)·p̂ < 0（因为 |s| ≤ 1800 = |p|）。实测（720 个边界点）：
        只布内层 13 站 → 720 个点全不满足；内层 13 + 外环 6 站 → 270 个不满足；
        内层 13 + 外环 10 站 → 0 个不满足；我们用的 12 站外环留了余量。

        返回未满足的边界点数（0 = 通过）。
        """
        k = k or cls.BOUNDARY_K
        bad = 0
        for i in range(k):
            th = 2.0 * math.pi * i / k
            px, py = ARENA_R * math.cos(th), ARENA_R * math.sin(th)
            nx, ny = math.cos(th), math.sin(th)          # 外向法线
            for (sx, sy) in stations:
                if ((sx - px) ** 2 + (sy - py) ** 2 <= R_MIN * R_MIN
                        and (sx - px) * nx + (sy - py) * ny >= 0.0):
                    break
            else:
                bad += 1
        return bad

    def _boundary_necessary(self, ns: list) -> bool:
        """用当前频道的 no_signal 证据快速过一遍边界必要条件。"""
        for i in range(self.BOUNDARY_K):
            th = 2.0 * math.pi * i / self.BOUNDARY_K
            px, py = ARENA_R * math.cos(th), ARENA_R * math.sin(th)
            nx, ny = math.cos(th), math.sin(th)
            for (sx, sy) in ns:
                if ((sx - px) ** 2 + (sy - py) ** 2 <= R_MIN * R_MIN
                        and (sx - px) * nx + (sy - py) * ny >= 0.0):
                    break
            else:
                return False
        return True

    _LAYOUT_MISS: int | None = None

    @classmethod
    def layout_boundary_miss(cls) -> int:
        """本布站的边界自检（结果缓存，一局只算一次）。"""
        if cls._LAYOUT_MISS is None:
            cls._LAYOUT_MISS = cls.boundary_miss(cls.survey_stations(), 720)
        return cls._LAYOUT_MISS

    def _all_done(self) -> bool:
        """终止判据：每个频道要么已清除，要么已被排除。"""
        return all(self.state[c].cleared or self._exclusion_ok(c) for c in CHANNELS)

    # -------------------------------------------------------------- 探测扫描
    def clean_sweep(self, x: float | None = None, y: float | None = None) -> None:
        """在一个测站上扫描"还没有结论"的频道——这些 no_signal 就是排除证据。

        与第三题的关键差别：这里**不能**用"距离覆盖增量 > 0"来决定扫不扫。内层
        13 站已经把全区罩在 1000 m 内，外环站对"距离覆盖"毫无增量，但它们才是
        定向源包围条件的关键，所以每个测站都要照常扫。
        """
        x = self.pos[0] if x is None else x
        y = self.pos[1] if y is None else y
        for ch in CHANNELS:
            if self._out_of_time():
                self.notes.append("现实时间不足，提前结束探测")
                return
            st = self.state[ch]
            if st.cleared or self._exclusion_ok(ch):
                continue
            if not st.known:
                self.measure(x, y, ch)          # 未确认频道：换一个测站就要再扫一次
            elif len(st.bearings) == 1 and st.near_at is None:
                sx, sy, phi = st.bearings[0]
                if point_segment_distance((x, y), (sx, sy), _dir(phi), R_MAX) <= 900.0:
                    self.measure(x, y, ch)      # 顺手补一条方位线（在射线上才值得测）
        self.stations.append((x, y))

    # -------------------------------------------------------------- 逼近与清除
    def _candidates(self, ch: int) -> list[tuple[float, float]]:
        """该频道下一步值得一试的测量点，按优先级排序。

        三条经验都是被离线环境（`--problem 4`）实测逼出来的：

        * **以"最后一次测到信号的站" g 为基准**。g 一定落在源的覆盖扇区里，在它
          附近取点才不会一头撞进盲区；用"估计区域中心"当基准时，点常常落在源的
          背后（定向源的盲区就是源背后那半个平面），实测会来回震荡几十次。
        * **只有一条方位线时沿射线分段前进、先近后远**（250→500→800→1100 m）。
          源的接收半径最大 1500 m，沿示向度走一小段是安全的；但如果源其实比估计
          的近得多，一步跨过去就跑到它背后了，所以先试近的。
        * **区域已经不大时改用 ±45° 两点交会**：点取在 g 周围、朝估计中心的方向
          上，距离取 |g−估计中心|。此时两点到源的距离约 0.77·|g−源|、从源看张角
          约 135°，定位误差 ≈0.011·|g−源|，几百米外也能压进 20 m。
        """
        st = self.state[ch]
        if not st.bearings:
            return []
        gx, gy, phi_g = st.bearings[-1]
        c = st.center
        step = self._step.get(ch, float(self.p["max_step"]))
        out: list[tuple[float, float]] = []
        if c is None:                                   # 还没有区域：沿方位线推进
            u = _dir(phi_g)
            for t in (step, step * 0.5, step * 0.25):   # 先大步试，撞上就减半再来
                t = max(t, 10.0)
                out.append((gx + t * u[0], gy + t * u[1]))
            return out
        dx, dy = c[0] - gx, c[1] - gy
        dist = math.hypot(dx, dy)
        if dist < 1e-6:                                 # g 与估计中心重合：退回方位线
            u = _dir(phi_g)
            base, dist = (u[0], u[1]), max(float(st.radius), 1.0)
        else:
            base = (dx / dist, dy / dist)
        if st.radius > float(self.p["good_radius"]):
            for frac in (0.75, 0.5, 0.3):               # 逼近段：朝估计中心走
                s = min(dist * frac, step)
                for ang in (0.0, 20.0, -20.0, 40.0, -40.0):
                    v = _rot(base, math.radians(ang))
                    out.append((gx + s * v[0], gy + s * v[1]))
        else:
            t = min(max(dist, 50.0), 800.0)             # 末端：±45° 两点交会
            for scale in (1.0, 0.6):
                for ang in (45.0, -45.0, 60.0, -60.0, 90.0, -90.0):
                    v = _rot(base, math.radians(ang))
                    out.append((gx + t * scale * v[0], gy + t * scale * v[1]))
        return out

    def work(self, ch: int) -> bool:
        """对某频道推进一次（一次只做一个动作，交给主循环重排）。返回是否已清除。"""
        st = self.state[ch]
        if st.cleared:
            return True
        if st.near_at is not None:                      # 已经在 5 m 内：直接清
            return self.clear_channel(ch)
        if st.center is not None and st.radius <= CLEAR_RADIUS:
            return self.clear_channel(ch)               # 误差界已进 20 m：一次命中
        tried = self._tried.setdefault(ch, set())
        max_step = float(self.p["max_step"])
        step = self._step.get(ch, max_step)
        for (px, py) in self._candidates(ch):
            key = (round(px / 25.0), round(py / 25.0))  # 25 m 一格去重
            if key in tried:
                continue                                # 同一地点重复测得到同样的读数
            tried.add(key)
            n_before = len(st.bearings)
            r = self.measure(px, py, ch)
            if r["measure_result"] == "near":
                return self.clear_channel(ch)
            if st.cleared:
                return True
            if len(st.bearings) > n_before:             # 又拿到一条方位线：步子可以放大
                self._step[ch] = min(step * 1.5, max_step)
            elif r["measure_result"] == "no_signal":    # 撞到盲区/超距：多半是跨过头了
                self._step[ch] = max(step * 0.5, 20.0)
            if st.center is not None and st.radius <= CLEAR_RADIUS:
                return self.clear_channel(ch)
            # 此刻站的这一点若本身就落在"源可能存在的区域"里，顺手 /clear 探一下：
            # 不用移动、落空只要 3 s（比一次 measure 还便宜），等于沿着逼近路径把
            # 定位区域一路扫过去——这是问题4 在定向盲区下最有效的兜底（文档 §6）。
            if (st.polygon and st.radius > CLEAR_RADIUS
                    and self._in_polygon((px, py), st.polygon)
                    and self.clear(px, py, ch)["clear_result"] == "success"):
                return True
            # 测不到又清不掉：区域不大就按"盖满"的顺序把它铺清
            if (r["measure_result"] == "no_signal" and st.polygon is not None
                    and self._sweep_plan(ch) is not None):
                return self._clear_sweep(ch)
            return False
        # 候选点全试过还没收敛：能铺清就铺清，否则在估计中心做最后一击
        if st.polygon is not None and self._sweep_plan(ch) is not None:
            if self._clear_sweep(ch):
                return True
        if st.center is not None:
            return self.clear_channel(ch)
        return False

    def _next_target(self, ch: int) -> tuple[float, float] | None:
        """主循环排路线用：该频道下一个还没试过的候选点。"""
        tried = self._tried.setdefault(ch, set())
        for (px, py) in self._candidates(ch):
            if (round(px / 25.0), round(py / 25.0)) not in tried:
                return (px, py)
        return self.state[ch].center          # 候选点用完：交给 work() 兜底

    # -------------------------------------------------------------- 铺清兜底
    def _sweep_plan(self, ch: int) -> list[tuple[float, float]] | None:
        """排一个能"盖满"定位区域的 /clear 试探序列；盖不满就返回 None。

        用贪心最远点：每次挑离"已有点集"最远的区域采样点，直到区域上每个点都落在
        某个试探点的 20 m 圆盘内（此时真实源——它**保证**在区域内——必然被盖到）。
        区域很细长时需要的点数取决于长度而不是面积，所以这里直接模拟一遍，够便宜
        才值得用（`max_probes` 次盖不满就老实认输，别把时间烧在铺点上）。
        """
        st = self.state[ch]
        if not st.polygon:
            return None
        gap = float(self.p["probe_gap"])
        cap = int(self.p["max_probes"])
        # 预判：一个半径 20 m 的圆盘最多盖住 2·gap 米边界，周长太长就直接否掉，
        # 免得为了得到一个"盖不满"的结论白跑几百次贪心迭代（长条区域很常见）。
        perim = 0.0
        n = len(st.polygon)
        for i in range(n):
            x0, y0 = st.polygon[i]
            x1, y1 = st.polygon[(i + 1) % n]
            perim += math.hypot(x1 - x0, y1 - y0)
        if perim > 2.0 * gap * cap:
            return None
        samples = _poly_samples(st.polygon, gap)
        if not samples:
            return None
        done: list[tuple[float, float]] = list(self._probes.get(ch, []))
        # 贪心最远点：维护"每个采样点到已有点集的最近距离"，每选一点只做一次 O(n) 更新
        if not samples:
            return None
        dist = [float("inf")] * len(samples)
        for (qx, qy) in done:
            for i, (px, py) in enumerate(samples):
                d = math.hypot(px - qx, py - qy)
                if d < dist[i]:
                    dist[i] = d
        plan: list[tuple[float, float]] = []
        while len(done) + len(plan) < cap:
            i = max(range(len(samples)), key=lambda j: dist[j])
            if dist[i] < gap:
                return plan                  # 区域已被盖满
            bx, by = samples[i]
            plan.append((bx, by))
            for j, (px, py) in enumerate(samples):
                d = math.hypot(px - bx, py - by)
                if d < dist[j]:
                    dist[j] = d
        return None                          # 名额用光还没盖满：放弃铺清

    def _clear_sweep(self, ch: int) -> bool:
        """定位区域测不准时，用 /clear 把它"铺清"。

        这是思路文档 §6 的兜底手段：`/clear` 只看清除点到源的距离 ≤ 20 m、**与定向
        源的朝向无关**，而定位区域是**保证**包含真实源的多边形。于是按最远点顺序在
        区域内试探着清：每点覆盖半径 20 m，直到区域被盖满——盖满就意味着真实源已经
        被某一次 /clear 扫到。细长条形的区域（几个测量点几乎共线时就是这样）通常
        几次就扫掉了，比继续在盲区里绕圈便宜（每次落空只要 3 s）。
        """
        st = self.state[ch]
        # 计划只跟"当前定位区域"有关：同一条区域上连着试探时不必反复重算
        # （贪心最远点是 O(n²)，几十个点重算一遍要几十毫秒，不能每轮都算）。
        sig = (len(st.bearings), round(st.radius, 1) if math.isfinite(st.radius) else -1.0)
        cached = self._sweep.get(ch)
        if cached is None or cached[0] != sig:
            cached = (sig, self._sweep_plan(ch))
            self._sweep[ch] = cached
        plan = cached[1]
        if not plan:
            return False
        done = set(self._probes.get(ch, []))
        todo = [q for q in plan if q not in done]
        if not todo:
            return False
        # 按"离当前位置最近"重排：区域多半是细长条，这样才是沿着条带走而不是来回跳
        px, py = min(todo, key=lambda q: math.hypot(q[0] - self.pos[0], q[1] - self.pos[1]))
        self._probes.setdefault(ch, []).append((px, py))
        return self.clear(px, py, ch)["clear_result"] == "success"

    # -------------------------------------------------------------- 主流程
    def _out_of_time(self) -> bool:
        return self.deadline is not None and time.perf_counter() > self.deadline

    def _left_ratio(self) -> float:
        if not self.budget_real or self.deadline is None:
            return 1.0
        return max(self.deadline - time.perf_counter(), 0.0) / self.budget_real

    def run(self) -> dict:
        enter = self.sim.enter()
        budget = float(enter.get("remaining_real_duration_s", 1200))
        self.budget_real = budget
        self.deadline = time.perf_counter() + max(
            budget - float(self.p["real_time_margin"]), 5.0)

        # 起点 (0,0) 本身就是内层格点之一：先在这里把 20 个频道扫一遍
        self.clean_sweep(0.0, 0.0)
        pending = [p for p in self.survey_stations() if p != (0.0, 0.0)]
        failed: set[int] = set()

        while not self._out_of_time() and not self._all_done():
            tasks: list[tuple[tuple[float, float], str, int | None]] = [
                (pt, "survey", None) for pt in pending]
            for ch in CHANNELS:
                st = self.state[ch]
                if st.cleared or not st.known:
                    continue
                if self._exclusion_ok(ch):
                    continue
                # 放弃过的频道不再花时间找它，但"已经定位到 20 m 内、只差一次
                # /clear"的便宜还是要捡（它可能是在后续普查里顺手测准的）
                if ch in failed and not (st.radius <= CLEAR_RADIUS):
                    continue
                pt = self._next_target(ch)
                if pt is not None:
                    tasks.append((pt, "work", ch))
            # 时间见底时按思路文档 §7.4：先清已发现的目标，普查让位
            if self._left_ratio() < float(self.p["time_guard"]):
                only_work = [t for t in tasks if t[1] == "work"]
                if only_work:
                    tasks = only_work
            if not tasks:
                break
            # 滚动 TSP：对当前待办点集重新排一次序，取最近的一件去做
            order = plan_tsp([t[0] for t in tasks], self.pos)
            pt, kind, ch = tasks[order[0]]
            if kind == "survey":
                self.clean_sweep(pt[0], pt[1])
                if pt in pending:
                    pending.remove(pt)
                continue

            assert ch is not None
            st = self.state[ch]
            before = (st.radius, len(self._probes.get(ch, ())))
            self.work(ch)
            self._rounds[ch] = self._rounds.get(ch, 0) + 1
            if st.cleared:
                self._stuck.pop(ch, None)
                continue
            # 没清掉：只有"定位半径真的变小"或"又铺清试了一点"才算进展，
            # 连续几次没有实质进展就放弃该频道，避免把时间耗在盲区里打转。
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
            "备注": self.notes,
        }


# ================================================================== 算法登记
SPEC = AlgorithmSpec(
    id="p4-directional",
    name="第四题导航算法",
    problem="问题4",
    summary="25 站包围式排查 → 沿示向度逼近 → 90° 交会精定位 → 单条滚动回路清除",
    description=(
        "【布站】内层六边形格 13 站（d=1000 m，覆盖半径 577 m）+ 半径 1900 m 外环 12 站，"
        "共 25 站。定向源只在 ±90° 扇区内辐射，所以判“不存在”的条件不是距离覆盖，"
        "而是包围：区域内每一点 p 都要落在“距 p ≤1000 m 的无信号测站”的凸包内。"
        "数值验证：该布站对“位置 × 方向”零漏检；只用内层 13 站则漏检 5.97%，"
        "边界上朝外的定向源在区域内部根本测不到，外环不能省。\n"
        "【探测】每个测站扫一遍“还没结论”的频道，累积 no_signal 作为排除证据；"
        "与第三题不同，这里绝不用 no_signal 反推距离（它可能只是盲区）。\n"
        "【定位】示向度楔形求交 ∩ 目标圆域 ∩“测到⇒距离≤1500 m”圆盘，最小外接圆半径 "
        "Rc 是保证性误差界。只测到一条方位线时，沿该方位线向前推进 700 m 再测一次"
        "（第一站距离可能 >1146 m，此时无论第二站放哪里 Rc 都压不到 20 m，逼近是必需"
        "而非优化；而且误差是每地点固定的，换点重测既能修正航向也能收窄区域）。\n"
        "【清除】Rc ≤ 300 m 后，在估计点两侧 ±45° 各补一点把交会角做到接近 90°"
        "（R_c = √2·t·tan1° ≤ 20 m ⇔ t ≤ 810 m），收敛到 Rc ≤ 20 m 再从圆心 /clear；"
        "不依赖 near——从背面靠近定向源只会得到 no_signal，但 /clear 只看 20 m 距离、"
        "与朝向无关。\n"
        "【导航】待办池 = {未去的测站} ∪ {待逼近/待清除的已知频道}，每一步对当前待办"
        "点集做一次滚动 TSP 取最近的一件：排查、逼近、清除共用同一条回路，比分两阶段"
        "省约 38% 里程。终止判据：20 个频道全部 ∈ {已清除} ∪ {已排除}。"
    ),
    params=dict(P4Hunter.DEFAULTS),
    entry="algorithms/p4_directional.py: P4Hunter",
)


def build(sim, params: dict | None = None, *, verbose: bool = False):
    """构造第四题策略对象（参数直接传给 P4Hunter，不改任何模块级常量）。"""
    return P4Hunter(sim, params, verbose=verbose)

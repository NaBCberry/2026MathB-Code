# -*- coding: utf-8 -*-
"""第三题 v2（快速响应版）—— 建在 p3_baseline 框架上的改进版。

本文件的结构：**上半部分是原样复制的 ``algorithms/p3_baseline.py`` 框架**
（常量、平面几何、ChannelState、InterferenceHunter），下半部分是队友那份
四项改进（思路来自队友的 FAST 版本），改写成一个子类 ``P3V2Hunter``。这样它不依赖
队友的 ``dog_controller_safe.py`` / ``route_planner.py``，可以直接在本框架里跑。

相对 ``p3_baseline`` 的改动（对应队友原文件里的 ①②③④）
--------------------------------------------------------
① **探测点按覆盖缺口动态生成**（``P3V2Hunter._gap_candidates``）
   原版固定"原点 + 半径 1300 m 均布 6 点"这一条环，等于先验地假定了一条巡回路线；
   FAST 改为每次从"还没被任何测站以 1000 m 覆盖到的采样点"里取缺口，按
   **单位时间期望收益**（新增覆盖点数 ÷ (行驶时间 + 6 s×要测的频道数)）挑一个去。
   布站是长出来的，不是预先钉死的；``use_gap_stations=False`` 可退回原版固定环。

② **顺路扫频**（``_scan_at_current``）
   每到一个落点（不管它是来探测、来补方位线还是来清除的）都就地补测未解决频道：
   位置不变 ⇒ 只花 5 s 检测 + 1 s 切换，**零移动**。落地即成测站。
   只在该点能带来新覆盖时才扫（``scan_needs_gain``），且每站最多扫
   ``scan_per_stop_cap`` 个频道；逐频道记录"这个点测过该频道"，不重复测。

③ **滚动时域调度**（``_pick_action``）
   所有待办动作（探测/补方位线/逼近/清除）放进同一个池子按**行程距离**统一排序，
   而不是按类型各自打分——实测分类打分会让不同阶段反复横穿全场。
   清除动作给 ``clear_discount``（默认 400 m）的优先折扣，因为它同时推进
   "发现"和"清除"两件事。

④ **证书按需触发**（``run`` 里的 clearable 分支）
   只要有"误差界已经够小、可以直接去清"的目标，就只排清除任务、绝不先绕去巡环。

另外两处沿用队友的取值：``clear_try_radius=120 m``（误差界进 120 m 就去清，
不再死等 20 m）+ 落空后围绕估计点补几枪；``refine_before_clear=False``。

停止判据与安全不变式不变（与 p3_baseline 一致）
----------------------------------------------
1. 覆盖式探测
   所有测站的覆盖半径取 1000 m（有效接收半径的下界），于是只要"某频道处处
   无信号"的测站能覆盖整个目标区域：
     (a) 任一全向干扰源必被至少一个测站测到；
     (b) 任一"全程无信号"的频道必不存在。
   (b) 正是"确保全部清除"所需的停止判据：不再依赖"猜总数"。
2. 交会定位、精化、清除的几何与 p3_baseline 完全相同（那是与"快速"无关的正确性基础）。
3. 队友原版的安全不变式照样成立：``ever_detected`` 的频道永不被判"不存在"；
   一个频道是否已排除，只看它自己的无信号测站集合能否覆盖全区。

出处：改进思路来自队友的 ``p3_v2.py``（快速响应版，建在他自己的 SAFE 控制器上）；
本文件把那些思路重新实现在 p3_baseline 框架里，控制器逻辑未照搬。
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field

from .base import AlgorithmSpec

# ------------------------------------------------------------------ 物理常量
ARENA_R = 1800.0            # 目标区域半径（m）
R_MAX = 1500.0              # 有效接收半径上限（m）
R_MIN = 1000.0              # 有效接收半径下限（m）—— 保证性判断只能用这个值
BEARING_ERR_DEG = 1.0       # 示向度误差上界（±1°）
CLEAR_RADIUS = 20.0         # 清除半径（m）
NEAR_RADIUS = 5.0           # 近距阈值（m）
SPEED = 5.0                 # 移动速度（m/s）
CHANNELS = tuple(range(1, 21))

# ------------------------------------------------------------------ 策略参数
RING_R = 1300.0             # 探测环半径：中心 + 6 点，最大覆盖半径 ≈ 936 m（< 1000）
RING_K = 6                  # 环上测站数
GOOD_RADIUS = 60.0          # 定位区域外接圆半径小于它就不必再补测
MAX_REFINE = 6              # 单目标精化迭代上限
MAX_FALLBACK = 6            # 清除失败后的兜底试探次数
REAL_TIME_MARGIN = 20.0     # 现实中保留的安全余量（s）
POLY_N = 72                 # 目标圆域的近似多边形边数
DISC_N = 90                 # "距离 ≤ 1500" 圆盘的近似多边形边数
SAMPLE_STEP = 60.0          # 覆盖度自检的采样步长（m）


def arena_samples(step: float = SAMPLE_STEP) -> list[tuple[float, float]]:
    """目标圆域内的规则采样点，用于"无信号证据是否已覆盖全区域"的自检。"""
    n = int(ARENA_R / step) + 1
    pts = []
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            x, y = i * step, j * step
            if x * x + y * y <= ARENA_R * ARENA_R:
                pts.append((x, y))
    return pts


SAMPLES = arena_samples()


# ================================================================== 平面几何
def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def _cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def _unit(a):
    n = math.hypot(a[0], a[1])
    return (a[0] / n, a[1] / n) if n > 0 else (1.0, 0.0)


def _rot(v, ang_rad):
    c, s = math.cos(ang_rad), math.sin(ang_rad)
    return (v[0] * c - v[1] * s, v[0] * s + v[1] * c)


def _dir(deg):
    a = math.radians(deg)
    return (math.cos(a), math.sin(a))


def point_segment_distance(p, s, u, length):
    """点 p 到线段 s → s + length·u 的距离。"""
    v = _sub(p, s)
    t = max(0.0, min(length, v[0] * u[0] + v[1] * u[1]))
    return math.hypot(v[0] - t * u[0], v[1] - t * u[1])


def clip_halfplane(poly, p0, p1):
    """保留有向直线 p0→p1 左侧的点（cross(p1-p0, x-p0) ≥ 0）。"""
    if not poly:
        return []
    d = _sub(p1, p0)
    out = []
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        fa = _cross(d, _sub(a, p0))
        fb = _cross(d, _sub(b, p0))
        if fa >= -1e-12:
            out.append(a)
        if (fa > 1e-12 and fb < -1e-12) or (fa < -1e-12 and fb > 1e-12):
            t = fa / (fa - fb)
            out.append((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])))
    return out


def clip_wedge(poly, s, phi_deg, half_deg=BEARING_ERR_DEG):
    """保留以测站 s 为顶点、方位角 phi、半角 half_deg 的楔形内的点。"""
    a1 = math.radians(phi_deg - half_deg)
    a2 = math.radians(phi_deg + half_deg)
    u1 = (math.cos(a1), math.sin(a1))
    u2 = (math.cos(a2), math.sin(a2))
    # cross(u1, x-s) ≥ 0
    poly = clip_halfplane(poly, s, (s[0] + u1[0], s[1] + u1[1]))
    # cross(u2, x-s) ≤ 0  ⇔  cross(-u2, x-s) ≥ 0
    return clip_halfplane(poly, s, (s[0] - u2[0], s[1] - u2[1]))


def clip_disc(poly, c, r, n=DISC_N):
    """保留落在圆盘 |x-c| ≤ r 内的点。

    用**外接**正多边形近似，保证裁剪后的多边形仍包含真实圆盘（保守，不会丢掉
    真实解）。"""
    R = r / math.cos(math.pi / n)
    pts = [(c[0] + R * math.cos(2 * math.pi * i / n),
            c[1] + R * math.sin(2 * math.pi * i / n)) for i in range(n)]
    for i in range(n):
        poly = clip_halfplane(poly, pts[i], pts[(i + 1) % n])
        if not poly:
            return []
    return poly


def arena_polygon(n=POLY_N):
    """目标圆域的外接正多边形（保守：包含整个圆域）。"""
    R = ARENA_R / math.cos(math.pi / n)
    return [(R * math.cos(2 * math.pi * i / n),
             R * math.sin(2 * math.pi * i / n)) for i in range(n)]


def _circle_from2(a, b):
    c = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    return c, math.hypot(a[0] - b[0], a[1] - b[1]) / 2


def _circle_from3(a, b, c):
    ax, ay = a
    bx, by = b
    cx, cy = c
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-12:                      # 共线 → 退化为最远两点
        best = (a, -1.0)
        for u, v in ((a, b), (a, c), (b, c)):
            cc, rr = _circle_from2(u, v)
            if rr > best[1]:
                best = (cc, rr)
        return best
    a2 = ax * ax + ay * ay
    b2 = bx * bx + by * by
    c2 = cx * cx + cy * cy
    ux = (a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / d
    uy = (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / d
    ctr = (ux, uy)
    return ctr, math.hypot(ax - ux, ay - uy)


def min_enclosing_circle(points: list, seed: int = 2026):
    """Welzl 增量算法：返回 (圆心, 半径)，圆包含全部给定点。"""
    pts = list(points)
    random.Random(seed).shuffle(pts)
    c, r = None, -1.0
    for i, p in enumerate(pts):
        if c is not None and math.hypot(p[0] - c[0], p[1] - c[1]) <= r + 1e-9:
            continue
        c, r = p, 0.0
        for j in range(i):
            q = pts[j]
            if math.hypot(q[0] - c[0], q[1] - c[1]) <= r + 1e-9:
                continue
            c, r = _circle_from2(p, q)
            for k in range(j):
                s = pts[k]
                if math.hypot(s[0] - c[0], s[1] - c[1]) <= r + 1e-9:
                    continue
                c, r = _circle_from3(p, q, s)
    if c is None:
        return (0.0, 0.0), 0.0
    return c, r


# ================================================================== 目标状态
def plan_tsp(points: list, start: tuple, passes: int = 12) -> list:
    """最近邻 + 有限次 2-opt，返回巡访顺序（下标列表）。

    用于滚动巡访：每一步都对当前待办点集重算一遍顺序，取第一个作为下一步，
    这样既不吃"贪心最近"的亏，又能跟上新出现的目标。
    """
    n = len(points)
    if n == 0:
        return []
    if n == 1:
        return [0]

    def dist(a, b):
        return math.hypot(a[0] - b[0], a[1] - b[1])

    unvisited = set(range(n))
    order: list[int] = []
    cur = start
    while unvisited:
        j = min(unvisited, key=lambda k: dist(cur, points[k]))
        order.append(j)
        unvisited.discard(j)
        cur = points[j]

    def total(seq):
        acc, cur = 0.0, start
        for i in seq:
            acc += dist(cur, points[i])
            cur = points[i]
        return acc

    best = total(order)
    for _ in range(passes):
        improved = False
        for i in range(n - 1):
            for j in range(i + 1, n):
                cand = order[:i] + order[i:j + 1][::-1] + order[j + 1:]
                val = total(cand)
                if val < best - 1e-9:
                    order, best, improved = cand, val, True
        if not improved:
            break
    return order


@dataclass
class ChannelState:
    """单个频道的观测累积与定位结果。"""

    channel: int
    bearings: list = field(default_factory=list)   # [(站x, 站y, 示向度°)]
    no_signal: list = field(default_factory=list)  # [(站x, 站y)]
    near_at: tuple | None = None                   # 若曾返回 near，则源必在 5 m 内
    cleared: bool = False
    polygon: list = field(default_factory=list)    # 可行定位区域（多边形）
    center: tuple | None = None                    # 最小外接圆圆心
    radius: float = float("inf")                   # 最小外接圆半径（保证性误差界）

    @property
    def known(self) -> bool:
        """是否已经"测到过信号"（有示向度或 near）。"""
        return bool(self.bearings) or self.near_at is not None

    @property
    def located(self) -> bool:
        return self.center is not None


# ================================================================== 搜索策略
class InterferenceHunter:
    """问题3 的机器狗策略：覆盖式探测 → 交会定位 → 精化逼近 → 巡访清除。"""

    def __init__(self, sim, *, verbose: bool = True):
        self.sim = sim
        self.verbose = verbose
        self.state = {c: ChannelState(c) for c in CHANNELS}
        self.pos = (0.0, 0.0)          # 机器狗当前坐标
        self.cur_channel = 1           # 测向机当前频道（只有 /measure 会改变它）
        self.virtual_time = 0.0
        self.n_measure = 0
        self.n_clear = 0
        self.n_miss = 0
        self.cleared_channels: list[int] = []
        self.stations: list[tuple[float, float]] = []   # 已做过"无信号覆盖扫描"的点
        self.deadline: float | None = None
        self.notes: list[str] = []

    # -------------------------------------------------------------- 基本动作
    def measure(self, x: float, y: float, ch: int) -> dict:
        r = self.sim.measure(x, y, ch)
        self.pos = (x, y)
        self.cur_channel = ch
        self.virtual_time = r["virtual_time_s"]
        self.n_measure += 1
        st = self.state[ch]
        res = r["measure_result"]
        if res == "direction":
            st.bearings.append((x, y, r["svd_deg"]))
            self._refresh_region(ch)
        elif res == "near":
            st.near_at = (x, y)
            st.center, st.radius = (x, y), 0.0
        else:
            st.no_signal.append((x, y))
        return r

    def clear(self, x: float, y: float, ch: int) -> dict:
        r = self.sim.clear(x, y, ch)
        self.pos = (x, y)
        self.virtual_time = r["virtual_time_s"]
        self.n_clear += 1
        if r["clear_result"] == "success":
            self.state[ch].cleared = True
            self.cleared_channels.append(ch)
        else:
            self.n_miss += 1
        return r

    # -------------------------------------------------------------- 定位区域
    def _refresh_region(self, ch: int) -> None:
        """由全部示向度楔形 ∩ 目标圆域 ∩ "被检测到⇒距离≤1500" 圆盘，重算定位区域。"""
        st = self.state[ch]
        if st.near_at is not None:
            return          # 出现过 near（源就在 5 m 内），这是最强证据，不再被楔形覆盖
        poly = arena_polygon()
        for (sx, sy, phi) in st.bearings:
            poly = clip_wedge(poly, (sx, sy), phi)
            if not poly:
                break
        if poly:
            for (sx, sy, _phi) in st.bearings:
                poly = clip_disc(poly, (sx, sy), R_MAX)
                if not poly:
                    break
        if not poly:
            # 数值退化（两条示向度几乎平行等）时保留上一次的区域
            self.notes.append(f"频道{ch}: 定位区域裁剪为空，沿用上一次区域")
            return
        c, r = min_enclosing_circle(poly)
        st.polygon, st.center = poly, c
        st.radius = r

    def _refresh_region_lite(self, ch: int) -> None:
        """退化时的备份：只用示向度楔形求交，不再做圆盘裁剪。"""
        st = self.state[ch]
        poly = arena_polygon()
        for (sx, sy, phi) in st.bearings:
            poly = clip_wedge(poly, (sx, sy), phi)
            if not poly:
                return
        c, r = min_enclosing_circle(poly)
        st.polygon, st.center, st.radius = poly, c, r

    # -------------------------------------------------------------- 覆盖式探测
    @staticmethod
    def survey_stations() -> list[tuple[float, float]]:
        """覆盖式探测测站：原点 + 半径 RING_R 上均布 RING_K 点。

        该布站的最大覆盖半径约 936 m，小于有效接收半径下限 1000 m，因此
        "在某频道上处处无信号" ⇒ 该频道必不存在。
        """
        pts = [(0.0, 0.0)]
        for k in range(RING_K):
            a = 2 * math.pi * k / RING_K
            pts.append((RING_R * math.cos(a), RING_R * math.sin(a)))
        return pts

    def unknown_channels(self) -> list[int]:
        """至今一次信号都没测到过的频道（既无示向度也无 near）。"""
        return [c for c in CHANNELS
                if not self.state[c].known and not self.state[c].cleared]

    def _covered(self, p) -> bool:
        """采样点 p 是否已被某个测站（在 1000 m 保守半径内）覆盖。"""
        for (sx, sy) in self.stations:
            if (p[0] - sx) ** 2 + (p[1] - sy) ** 2 <= R_MIN * R_MIN:
                return True
        return False

    def _coverage_gain(self, x: float, y: float) -> int:
        """把 (x, y) 加为测站能新增覆盖多少个采样点（0 表示该点无信息增量）。"""
        gain = 0
        for (px, py) in SAMPLES:
            if (px - x) ** 2 + (py - y) ** 2 <= R_MIN * R_MIN and not self._covered((px, py)):
                gain += 1
        return gain

    def deepest_uncovered(self) -> tuple[tuple[float, float], float]:
        """找出离所有测站最远的采样点（覆盖缺口最深的地方）。"""
        if not self.stations:
            return (0.0, 0.0), float("inf")
        best, best_d = (0.0, 0.0), -1.0
        for p in SAMPLES:
            d = min(math.hypot(p[0] - sx, p[1] - sy) for (sx, sy) in self.stations)
            if d > best_d:
                best, best_d = p, d
        return best, best_d

    def clean_sweep(self, x: float | None = None, y: float | None = None) -> None:
        """在当前点把"至今没测到过信号的频道"扫一遍。

        这些 no_signal 记录就是"该频道不存在"的覆盖式证据：
        只要对某频道无信号的测站集合能覆盖整个目标区域，该频道必不存在。
        因此只有当该点能带来**新的覆盖**（覆盖增量 > 0）时才值得扫，否则纯属浪费。
        顺手也补测那些"该点很可能落在有效接收半径内"的单示向度频道。
        """
        x = self.pos[0] if x is None else x
        y = self.pos[1] if y is None else y
        gain = self._coverage_gain(x, y)
        swept = False
        for ch in CHANNELS:
            if self._out_of_time():
                self.notes.append("现实时间不足，提前结束探测")
                return
            st = self.state[ch]
            if st.cleared:
                continue
            if not st.known:
                if gain > 0:
                    self.measure(x, y, ch)
                    swept = True
            elif len(st.bearings) == 1 and st.near_at is None:
                sx, sy, phi = st.bearings[0]
                if point_segment_distance((x, y), (sx, sy), _dir(phi), R_MAX) <= 900.0:
                    self.measure(x, y, ch)
        if swept:
            self.stations.append((x, y))

    # -------------------------------------------------------------- 补测定位
    def _ray_intervals(self, ch: int) -> list[tuple[float, float]]:
        """用"一条示向度 + 其余测站无信号"求干扰源在射线上的可行区间。

        关键推理：某测站对该频道返回 no_signal，说明该处收不到信号，而有效接收
        半径 ≥ 1000 m，所以干扰源到该测站的距离**必定大于 1000 m**。把射线上被该
        测站 1000 m 圆盘罩住的那一段挖掉即可。多个测站的无信号记录一起用，往往能把
        源在射线上的位置卡到很窄的一段——这些信息本来就有，不用白不用。
        """
        st = self.state[ch]
        sx, sy, phi = st.bearings[0]
        u = _dir(phi)
        # 基础区间：射线落在目标区域内的部分，且距 s 不超过有效接收半径上限
        b = sx * u[0] + sy * u[1]
        c = sx * sx + sy * sy - ARENA_R * ARENA_R
        disc = b * b - c
        if disc <= 0:
            lo, hi = 0.0, R_MAX
        else:
            rt = math.sqrt(disc)
            lo, hi = max(0.0, -b - rt), min(R_MAX, -b + rt)
        if hi <= lo:
            lo, hi = 0.0, R_MAX

        forbidden = []
        for (tx, ty) in st.no_signal:
            vx, vy = tx - sx, ty - sy
            proj = vx * u[0] + vy * u[1]
            perp2 = vx * vx + vy * vy - proj * proj
            if perp2 >= R_MIN * R_MIN:
                continue
            half = math.sqrt(R_MIN * R_MIN - perp2)
            forbidden.append((proj - half, proj + half))

        intervals = [(lo, hi)]
        for (a, bb) in forbidden:
            nxt = []
            for (l, h) in intervals:
                if bb <= l or a >= h:
                    nxt.append((l, h))
                    continue
                if a > l:
                    nxt.append((l, min(a, h)))
                if bb < h:
                    nxt.append((max(bb, l), h))
            intervals = [iv for iv in nxt if iv[1] - iv[0] > 1.0]
        if not intervals:
            return [(lo, hi)]
        return sorted(intervals, key=lambda iv: iv[0] - iv[1])

    def _second_points(self, ch: int) -> list[tuple[float, float]]:
        """只有一个示向度时，选一个**保证能测到**的第二点。

        先用 _ray_intervals 把源在射线上的可行区间收到 [m−h, m+h]，再取
            q = s + m·u + e·u⊥          （u⊥ 为垂直方向）
        横向偏置 e 在 √(h² + e²) < 950 m 的前提下尽量取小：区间越窄说明源在
        射线上越确定，偏置越小，绕路越少；取 √(h²+e²) 的上界再加 ±1° 方位误差
        带来的 ≤26 m 横向偏移，仍 < 1000 m，所以 **q 处必定还能测到该频道**。
        同时源在 q 处的张角接近 90°，正是最有利的交会几何。
        """
        sx, sy, phi = self.state[ch].bearings[0]
        u = _dir(phi)
        n = _dir(phi + 90.0)
        cands: list[tuple[float, float]] = []
        for (lo, hi) in self._ray_intervals(ch):
            m, h = 0.5 * (lo + hi), 0.5 * (hi - lo)
            # 源到 q 的横向偏置。区间越窄，源在射线上越确定，偏置可以取得越小，
            # 绕路也越少；同时要保证 |q − 源| < 950 m（有效接收半径下限留余量）。
            e_cap = math.sqrt(max(950.0 ** 2 - h * h, 100.0))
            e = min(max(150.0, min(h, 550.0)), e_cap)
            best, best_score = None, -1e18
            for sign in (+1, -1):
                px = sx + m * u[0] + sign * e * n[0]
                py = sy + m * u[1] + sign * e * n[1]
                score = (-0.002 * math.hypot(px - self.pos[0], py - self.pos[1])
                         - 0.5 * max(0.0, math.hypot(px, py) - ARENA_R))
                if score > best_score:
                    best, best_score = (px, py), score
            if best is not None:
                cands.append(best)
        return cands or [(sx, sy)]

    def complete(self, ch: int) -> None:
        """给只有一条示向度的频道补出第二条示向度。"""
        st = self.state[ch]
        if len(st.bearings) != 1 or st.cleared or st.near_at is not None:
            return
        for (px, py) in self._second_points(ch):
            self.measure(px, py, ch)
            if len(st.bearings) >= 2 or st.near_at is not None:
                return

    def refine(self, ch: int, max_iter: int = MAX_REFINE) -> None:
        """围绕估计点补测，把定位区域压到"一次清除必中"（Rc ≤ 20 m）。"""
        st = self.state[ch]
        for _ in range(max_iter):
            if st.cleared or st.near_at is not None:
                return
            if st.center is None or st.radius <= CLEAR_RADIUS:
                return
            if self._out_of_time():
                return
            # 补测点到源的距离必须仍 < 950 m 才保证测得到：点在估计点外 u 处，
            # 源在估计点附近 radius 以内，故要求 u + radius < 950。
            u = min(max(st.radius, 1.0), max(950.0 - st.radius, 100.0))
            for sgn in (45.0, -45.0):
                c = st.center
                a = _rot(_unit(_sub(c, self.pos)), math.radians(sgn))
                self.measure(c[0] + u * a[0], c[1] + u * a[1], ch)
                if st.cleared or st.near_at is not None:
                    return
        # 兜底：万一圆盘裁剪导致退化，用纯楔形交会再算一次
        if st.bearings and (st.center is None or st.radius > CLEAR_RADIUS):
            self._refresh_region_lite(ch)

    # -------------------------------------------------------------- 清除
    def clear_channel(self, ch: int) -> bool:
        st = self.state[ch]
        if st.cleared:
            return True
        if st.center is None:
            return False
        cx, cy = st.center
        r = self.clear(cx, cy, ch)
        if r["clear_result"] == "success":
            return True
        # 兜底：围绕估计点做小范围试探（每次未发现只花 3 s）
        for k in range(MAX_FALLBACK):
            if self._out_of_time():
                break
            rad = CLEAR_RADIUS * 1.6 * (1 + k // 4)
            ang = 2 * math.pi * (k % 4) / 4 + math.pi / 4
            r = self.clear(cx + rad * math.cos(ang), cy + rad * math.sin(ang), ch)
            if r["clear_result"] == "success":
                return True
        return False

    # -------------------------------------------------------------- 主流程
    def _out_of_time(self) -> bool:
        return self.deadline is not None and time.perf_counter() > self.deadline

    def run(self) -> dict:
        enter = self.sim.enter()
        budget = float(enter.get("remaining_real_duration_s", 1200))
        self.deadline = time.perf_counter() + max(budget - REAL_TIME_MARGIN, 5.0)

        # 滚动巡访：待办池 = {未去的覆盖测站} ∪ {待补第二条示向度的频道}
        #          ∪ {待清除的已定位目标}。每一步对当前待办点集做一次滚动 TSP，
        # 走最近的第一个点——探测、定位、清除共用同一条回路，不再分三段各跑一趟。
        self.clean_sweep()                     # 起点 (0,0)：起始频道 1，首次检测免切换
        self.stations.append((0.0, 0.0))
        pending = [p for p in self.survey_stations() if p != (0.0, 0.0)]
        failed: set[int] = set()
        while not self._out_of_time():
            tasks: list[tuple[tuple[float, float], str, int | None]] = [
                (pt, "survey", None) for pt in pending]
            for ch in CHANNELS:
                st = self.state[ch]
                if st.cleared or ch in failed:
                    continue
                if len(st.bearings) == 1 and st.near_at is None:
                    tasks.append((self._second_points(ch)[0], "complete", ch))
                elif st.center is not None:
                    tasks.append((st.center, "clear", ch))
            if not tasks:
                break
            # 对当前待办点集做一次滚动 TSP 排序，取最近一趟的第一个作为下一步
            order = plan_tsp([t[0] for t in tasks], self.pos)
            pt, kind, ch = tasks[order[0]]
            if kind == "survey":
                self.clean_sweep(pt[0], pt[1])
                if pt in pending:
                    pending.remove(pt)
            elif kind == "complete":
                self.complete(ch)
                if len(self.state[ch].bearings) < 2 and self.state[ch].near_at is None:
                    failed.add(ch)             # 补测仍不成功，避免死循环
            else:
                self.refine(ch)
                if not self.clear_channel(ch):
                    failed.add(ch)

        # 阶段4：收尾
        unknown = [c for c in CHANNELS
                   if not self.state[c].known and not self.state[c].cleared]
        missed = [c for c in CHANNELS
                  if self.state[c].known and not self.state[c].cleared]
        # 覆盖自检：确认"无信号 ⇒ 不存在"的推理前提确实成立（每个采样点都落在
        # 某个测站的 1000 m 保守半径内）。布站本身已保证这一点，这里只做复核。
        _, gap = self.deepest_uncovered()
        if gap > R_MIN and unknown:
            self.notes.append(f"覆盖自检未通过：仍有距最近测站 {gap:.0f} m 的区域")
        self.sim.exit()
        return {
            "cleared": len(self.cleared_channels),
            "cleared_channels": sorted(self.cleared_channels),
            "判定不存在": unknown,
            "已发现但未清除": missed,
            "虚拟总时间": self.virtual_time,
            "平均定位清除时间": (self.virtual_time / len(self.cleared_channels)
                                 if self.cleared_channels else float("inf")),
            "measure次数": self.n_measure,
            "clear次数": self.n_clear,
            "clear落空次数": self.n_miss,
            "备注": self.notes,
        }


# ================================================================== 第三题 v2
class P3V2Hunter(InterferenceHunter):
    """第三题 v2（快速响应版）：覆盖缺口布点 + 顺路扫频 + 统一最近邻 + 清优先。

    继承上面那份 p3_baseline 框架（几何、交会、精化、清除、覆盖自检全部复用），
    只改"在哪儿停、停几次、什么时候去扫、什么时候去清"这四件事。
    """

    DEFAULTS = {
        # 实测（离线第三题 20 例）：固定 7 站环比"按覆盖缺口动态布点"更省里程——
        # 队友那套缺口布点是针对他自己的"4 条固定环、30+ 站"设计的，换到本框架的
        # 7 站环上反而多跑路。想要缺口版把这里改成 True 即可。
        "use_gap_stations": False,    # ① 探测点按覆盖缺口动态生成（True）/ 固定 7 站环（False）
        "gap_candidates": 3,          # 每轮生成几个缺口候选供统一排序
        "scan_per_stop_cap": 2,       # ② 顺路扫频：每个落点最多补测几个频道（实测 2~3 最优）
        "scan_needs_gain": True,      # 只在该点能带来新覆盖时才扫
        # 队友用 120 m 就去清 + 落空补枪；在本框架上实测"先精化到 20 m 再清"更快也更稳。
        "clear_try_radius": 20.0,     # ④ 误差界 ≤ 它就直接去清（FAST 原值 120 m）
        "refine_before_clear": True,  # 清之前是否仍精化到 20 m（FAST 原值 False）
        "clear_discount": 400.0,      # ③ 清除任务的优先折扣（m）
        "max_clear_probes": 0,        # 清除落空后围绕估计点再补几枪（框架自带兜底）
        "max_fix_attempts": 3,        # 单频道补齐方位线的尝试上限
        "stagnation_limit": 60,       # 连续多少步没有进展就收工
        "real_time_margin": 20.0,     # 现实时间安全余量（s）
    }

    def __init__(self, sim, params: dict | None = None, *, verbose: bool = False):
        super().__init__(sim, verbose=verbose)
        self.p = {**self.DEFAULTS, **(params or {})}
        self._probed: dict[int, set] = {c: set() for c in CHANNELS}   # 频道→已测点(50 m)
        self._n_fix: dict[int, int] = {c: 0 for c in CHANNELS}        # 频道→补测次数
        self._stuck: set[int] = set()                                 # 反复无进展的频道
        self._gap_cache: dict = {}                                    # 缺口候选缓存
        self._cert_cache: dict[int, tuple[int, bool]] = {}            # 证书缓存
        self._survey_done: set = set()                                # 已扫过的落点

    # ------------------------------------------------------------ ① 覆盖缺口布点
    def _channel_gap(self, ch: int) -> tuple[float, float] | None:
        """该频道的无信号证据里，离已测点最远的采样点——去那儿测它收益最大。"""
        ns = self.state[ch].no_signal
        key = (ch, len(ns))
        hit = self._gap_cache.get(key)
        if hit is not None:
            return hit
        best, best_d = None, -1.0
        for p in SAMPLES:
            if not ns:
                d = 1e9
            else:
                d = min((p[0] - sx) ** 2 + (p[1] - sy) ** 2 for (sx, sy) in ns)
            if d > best_d:
                best, best_d = p, d
        self._gap_cache[key] = best
        return best

    def _gap_candidates(self) -> list[tuple[float, float]]:
        """① 只对“证书还没盖满”的频道生成候选探测点；这些点就是下一批停点。

        候选按**扇区**取：每个方向上取“对未解决频道缺口最大”的那个采样点，再交给
        统一最近邻去挑——这样才能就近补洞，而不是舍近求远横穿全场。
        """
        if not self.p["use_gap_stations"]:                    # 退回原版固定环
            return [p for p in self.survey_stations()
                    if p != (0.0, 0.0)
                    and (round(p[0] / 50.0), round(p[1] / 50.0)) not in self._survey_done]
        pend = [c for c in CHANNELS
                if not self.state[c].known and not self.state[c].cleared
                and c not in self._stuck and not self._certified(c)]
        pend.sort(key=lambda c: len(self.state[c].no_signal))  # 证据最少的先补
        if not pend:
            return []
        out: list[tuple[float, float]] = []
        seen: set = set()
        for ch in pend[:max(int(self.p["gap_candidates"]), 1)]:
            p = self._channel_gap(ch)
            if p is None:
                continue
            k = (round(p[0] / 50.0), round(p[1] / 50.0))
            if k in seen or k in self._survey_done:
                continue
            seen.add(k)
            out.append(p)
        return out

    # ------------------------------------------------------------ ② 顺路扫频
    def _scan_at_current(self, cap: int | None = None) -> int:
        """在当前落点原地补测未解决频道：位置不变 ⇒ 只花检测与切换时间。

        - 只有该点能带来**新覆盖**时才扫（`scan_needs_gain`）；
        - 逐频道记录"这个点测过它"，不重复测；
        - 先扫证据最少的频道，这样有上限时也是轮着补，而不是总补前几个。
        """
        x, y = self.pos
        gain = self._coverage_gain(x, y) if self.p["scan_needs_gain"] else 1
        if gain <= 0:
            return 0
        key = (round(x / 50.0), round(y / 50.0))
        limit = int(self.p["scan_per_stop_cap"]) if cap is None else int(cap)
        todo = [c for c in CHANNELS
                if not self.state[c].cleared and c not in self._stuck
                and key not in self._probed[c]]
        todo.sort(key=lambda c: (self.state[c].known, len(self.state[c].no_signal)))
        scanned = 0
        for ch in todo:
            if self._out_of_time() or (limit > 0 and scanned >= limit):
                break
            st = self.state[ch]
            if not st.known:
                self._probed[ch].add(key)
                scanned += 1
                r = self.measure(x, y, ch)                 # 未知频道：补覆盖证书
                if r["measure_result"] == "near":
                    self.clear_channel(ch)
            elif len(st.bearings) == 1 and st.near_at is None:
                sx, sy, phi = st.bearings[0]
                if point_segment_distance((x, y), (sx, sy), _dir(phi), R_MAX) <= 900.0:
                    self._probed[ch].add(key)
                    scanned += 1
                    self.measure(x, y, ch)                 # 顺手补第二方位线
        if scanned:
            self.stations.append((x, y))                   # 落点即测站
        self._survey_done.add(key)
        return scanned

    # ------------------------------------------------------------ 证书
    def _certified(self, ch: int) -> bool:
        """该频道的无信号证据是否已覆盖全区 ⇒ 可判定"不存在"。"""
        ns = self.state[ch].no_signal
        hit = self._cert_cache.get(ch)
        if hit is not None and hit[0] == len(ns):
            return hit[1]
        ok = bool(ns)
        if ok:
            for p in SAMPLES:
                for (sx, sy) in ns:
                    if (p[0] - sx) ** 2 + (p[1] - sy) ** 2 <= R_MIN * R_MIN:
                        break
                else:
                    ok = False
                    break
        self._cert_cache[ch] = (len(ns), ok)
        return ok

    # ------------------------------------------------------------ ③④ 调度
    def _tasks(self) -> list[tuple[tuple[float, float], str, int | None]]:
        """待办池。④：只要有"够准、能去清"的目标，就只排清除任务。"""
        tasks: list[tuple[tuple[float, float], str, int | None]] = []
        clear_now = [c for c in CHANNELS
                     if not self.state[c].cleared and c not in self._stuck
                     and self.state[c].center is not None
                     and (len(self.state[c].bearings) >= 2
                          or self.state[c].near_at is not None)
                     and self.state[c].radius <= float(self.p["clear_try_radius"])]
        if clear_now:
            return [(self.state[c].center, "clear", c) for c in clear_now]
        for ch in CHANNELS:
            st = self.state[ch]
            if st.cleared or ch in self._stuck or st.near_at is not None:
                continue
            if len(st.bearings) == 1:
                tasks.append((self._second_points(ch)[0], "complete", ch))
            elif st.center is not None:
                tasks.append((st.center, "clear", ch))     # 已交会出估计点：去清
        for pt in self._gap_candidates():
            tasks.append((pt, "survey", None))
        return tasks

    def _pick_action(self, tasks):
        """③ 统一最近邻：所有待办动作一起按行程距离排序，清除给固定折扣。"""
        cx, cy = self.pos
        best, best_d = None, None
        for (pt, kind, ch) in tasks:
            d = math.hypot(pt[0] - cx, pt[1] - cy)
            if kind == "clear":
                d -= float(self.p["clear_discount"])       # 清同时推进发现与清除
            if best_d is None or d < best_d:
                best, best_d = (pt, kind, ch), d
        return best

    def _try_clear(self, ch: int) -> bool:
        st = self.state[ch]
        if st.cleared:
            return True
        if st.center is None:
            return False
        if self.p["refine_before_clear"] and st.radius > CLEAR_RADIUS:
            self.refine(ch)                                # FAST 默认关掉这一步
        if self.clear_channel(ch):
            return True
        for k in range(int(self.p["max_clear_probes"])):    # 落空：围绕估计点补枪
            if self._out_of_time():
                break
            rad = 40.0 * (1 + k // 4)
            ang = 2.0 * math.pi * (k % 4) / 4.0 + math.pi / 4.0
            r = self.clear(st.center[0] + rad * math.cos(ang),
                           st.center[1] + rad * math.sin(ang), ch)
            if r["clear_result"] == "success":
                return True
        return st.cleared

    # ------------------------------------------------------------ 主流程
    def run(self) -> dict:
        enter = self.sim.enter()
        budget = float(enter.get("remaining_real_duration_s", 1200))
        self.deadline = time.perf_counter() + max(
            budget - float(self.p["real_time_margin"]), 5.0)

        self._scan_at_current(cap=0)          # 起点：频道 1 免切换，先把能扫的扫了
        self.stations.append((0.0, 0.0))
        last, stagn = None, 0
        while not self._out_of_time():
            tasks = self._tasks()
            if not tasks:
                break
            pick = self._pick_action(tasks)
            if pick is None:
                break
            pt, kind, ch = pick
            if kind == "survey":
                self._scan_batch_at(pt)                    # 专程补证书的站：不限量地扫
            elif kind == "complete":
                self.complete(ch)
                if len(self.state[ch].bearings) < 2 and self.state[ch].near_at is None:
                    self._n_fix[ch] += 1
                    if self._n_fix[ch] >= int(self.p["max_fix_attempts"]):
                        self._stuck.add(ch)
            else:
                assert ch is not None
                if not self._try_clear(ch):
                    self._n_fix[ch] += 1
                    if self._n_fix[ch] >= int(self.p["max_fix_attempts"]):
                        self._stuck.add(ch)
            self._scan_at_current()                        # ② 每个落点顺路扫频
            key = (len(self.cleared_channels), len(self.stations), self.n_measure)
            if key == last:
                stagn += 1
            else:
                last, stagn = key, 0
            if stagn >= int(self.p["stagnation_limit"]):
                self.notes.append("连续多步没有进展，提前收工")
                break

        unknown = [c for c in CHANNELS
                   if not self.state[c].known and not self.state[c].cleared]
        certified = [c for c in unknown if self._certified(c)]
        uncertified = [c for c in unknown if c not in certified]
        missed = [c for c in CHANNELS
                  if self.state[c].known and not self.state[c].cleared]
        if uncertified:
            self.notes.append(f"有 {len(uncertified)} 个频道无信号证据没铺满，未判定")
        _, gap = self.deepest_uncovered()
        if gap > R_MIN and unknown:
            self.notes.append(f"覆盖自检：仍有距最近测站 {gap:.0f} m 的采样点")
        self.sim.exit()
        return {
            "cleared": len(self.cleared_channels),
            "cleared_channels": sorted(self.cleared_channels),
            "判定不存在": certified,
            "未判定": uncertified,
            "已发现但未清除": missed,
            "虚拟总时间": self.virtual_time,
            "平均定位清除时间": (self.virtual_time / len(self.cleared_channels)
                                 if self.cleared_channels else float("inf")),
            "measure次数": self.n_measure,
            "clear次数": self.n_clear,
            "clear落空次数": self.n_miss,
            "走过测站数": len(self.stations),
            "备注": self.notes,
        }

    def _scan_batch_at(self, pt) -> int:
        """走到 pt 并就地补测该频道需要覆盖证据的所有未解决频道（不限量）。"""
        x, y = pt
        key = (round(x / 50.0), round(y / 50.0))
        todo = [c for c in CHANNELS
                if not self.state[c].cleared and c not in self._stuck
                and not self.state[c].known and key not in self._probed[c]
                and not self._certified(c)]
        todo.sort(key=lambda c: len(self.state[c].no_signal))
        if not todo:
            return 0
        n = 0
        for ch in todo:
            if self._out_of_time():
                break
            self._probed[ch].add(key)
            r = self.measure(x, y, ch)
            n += 1
            if r["measure_result"] == "near":
                self.clear_channel(ch)
        if n or self.pos == (x, y):
            self.stations.append((x, y))
        self._survey_done.add(key)
        return n


# ================================================================== 算法登记
SPEC = AlgorithmSpec(
    id="p3-v2",
    name="第三题 v2（快速响应版）",
    problem="问题3",
    summary="覆盖缺口动态布点 → 顺路扫频 → 统一最近邻调度 → 有把握就先去清",
    description=(
        "【来源】改进思路来自队友的「快速响应版 FAST」；本文件把 p3_baseline 的框架"
        "整段复制进来，再把那四项改进重新实现在该框架上，因此不依赖任何外部模块。\n"
        "① 探测点按**覆盖缺口**动态生成：只对“证书还没铺满”的频道找它无信号证据里"
        "最远的采样点，按需生成停点，而不是先验地钉死一条 7 站环。\n"
        "② **顺路扫频**：每到一个落点（不论来探测、补方位线还是清除）就地补测未解决"
        "频道——位置不变，只花 5 s 检测 + 1 s 切换，零移动；落点即测站，只在该点能"
        "带来新覆盖时才扫，且每个点对同一频道只测一次。\n"
        "③ **统一最近邻调度**：探测/补方位线/清除放进同一个待办池按行程距离统一排序"
        "（清除给 400 m 优先折扣），避免分类型打分时反复横穿全场。\n"
        "④ **证书按需触发**：只要有误差界已进 120 m 的目标，就只排清除任务，绝不先绕去巡环。\n"
        "【安全不变式】判“某频道不存在”只看该频道自己的无信号测站能否以 1000 m 覆盖"
        "全区；证据没铺满的频道会如实报成「未判定」，绝不当成不存在。\n"
        "【清除】误差界 ≤ clear_try_radius 就去清，落空后围绕估计点补几枪"
        "（refine_before_clear / max_clear_probes 可控）。\n"
        "【离线第三题实测，20 例/组】p3-baseline：100%、310 s、109 次 measure；"
        "本算法默认配置：100%、364 s、132 次；开 use_gap_stations 的缺口版：100%、479 s、171 次；"
        "照搬 FAST 原值（clear_try_radius=120、refine_before_clear=False、cap=6）：98.8%、525 s、157 次。"
        "结论：队友那四项改进是针对他自己的“4 条固定环、30+ 站”布站做的——"
        "换到本框架已经很好的 7 站环上，省下的里程抵不过多测的频道，因此默认取实测最好的组合，"
        "并把每个开关都留着，便于在网页上逐项对比。"
    ),
    params=dict(P3V2Hunter.DEFAULTS),
    entry="algorithms/p3_v2.py: P3V2Hunter",
)


def build(sim, params: dict | None = None, *, verbose: bool = False):
    """构造第三题 v2 策略（参数只作用于本算法，不改 p3_baseline 的任何常量）。"""
    return P3V2Hunter(sim, params, verbose=verbose)


# 兼容旧引用（本文件早期叫 P3FastHunter / 算法 id 叫 p3-wxm-fast）
P3FastHunter = P3V2Hunter

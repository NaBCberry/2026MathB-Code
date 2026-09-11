# -*- coding: utf-8 -*-
"""问题3：机器狗对全向干扰源的自动搜索、定位与清除策略。

用法::

    python robot.py --robot-id <参赛队号>                    # 跑模拟器（演练/正式测试）
    python robot.py --robot-id demo --dry-run --cases 20     # 离线自测，不联网

策略（四步）
------------
1. 覆盖式探测
   在 1 + 6 个测站上轮询频道：原点 + 半径 RING_R 上均布 6 点。该布站的最大
   覆盖半径约 936 m，小于有效接收半径下限 1000 m，于是
     (a) 任一全向干扰源必被至少一个测站测到；
     (b) 任一"全程无信号"的频道必不存在。
   (b) 正是"确保全部清除"所需的停止判据：不再依赖"猜总数"。

2. 交会定位
   对已测到示向度的频道，把 ±1° 示向度楔形求交，得到交会定位区域；再与
   "该频道被检测到 ⇒ 到该测站距离 ≤ 1500 m"的圆盘、以及半径 1800 m 的目标
   圆域求交加以收紧。区域的最小外接圆半径 R 是**保证性**误差界：真实干扰源
   必定落在该圆内（因为示向度误差不会超过 ±1°）。

3. 精化逼近
   R > 20 m（清除半径）时，在估计点附近取两个互成 90° 的补测点，使源处交会角
   接近 90°（本题"同一地点误差固定"的系统误差模型下，最坏情况定位区域最小的
   交会角是 90°，而非随机误差 CEP 准则下的 110°，见问题2 的推导），定位区域
   迅速收缩；收敛到 R ≤ 20 m 后取最小外接圆圆心清除，可保证一次命中。

4. 滚动巡访
   把"尚未走过的探测站 / 待补测的频道 / 待清除的目标"放进同一个待办池，每一步
   挑距离最近的一件去做，执行后立刻按新信息重排——探测、定位、清除共用同一条
   巡访回路，而不是分三段各跑一趟。

对问题4 的扩展点见文件末尾注释。
"""

from __future__ import annotations

import argparse
import math
import random
import time
from dataclasses import dataclass, field

from sim_client import BASE_URL, SimulatorClient

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


# ================================================================== 离线自测
def run_dry_run(args) -> int:
    """用本地模拟环境自测策略，统计"清除比例"与"平均定位清除时间"。"""
    try:
        from mock_arena import MockArena
    except ImportError:
        print("缺少 mock_arena.py，无法离线自测。")
        return 2

    verbose = not args.quiet
    rows = []
    for case in range(args.cases):
        seed = args.seed + case
        arena = MockArena(seed=seed)
        hunter = InterferenceHunter(arena, verbose=verbose)
        stats = hunter.run()
        total = arena.n_sources
        rows.append((seed, total, stats["cleared"], stats["平均定位清除时间"],
                     stats["虚拟总时间"], stats["measure次数"], stats["clear次数"]))
        print(f"[案例 {case + 1:2d}] seed={seed:5d}  干扰源 {total:2d} 个  "
              f"清除 {stats['cleared']:2d} 个 ({stats['cleared'] / total:6.1%})  "
              f"平均定位清除时间 {stats['平均定位清除时间']:7.1f} s  "
              f"虚拟总时间 {stats['虚拟总时间']:7.1f} s  "
              f"measure {stats['measure次数']:3d} / clear {stats['clear次数']:3d}")
        if stats["备注"]:
            print(f"          备注：{'; '.join(stats['备注'][:3])}")

    n = len(rows)
    rate = sum(r[2] / r[1] for r in rows) / n
    ok = [r for r in rows if r[2]]
    avg = sum(r[3] for r in ok) / max(len(ok), 1)
    print("-" * 96)
    print(f"汇总：{n} 个案例，平均清除比例 {rate:6.2%}，平均定位清除时间 {avg:7.1f} s，"
          f"平均虚拟总时间 {sum(r[4] for r in rows) / n:7.1f} s，"
          f"平均 measure {sum(r[5] for r in rows) / n:5.1f} 次")
    return 0


# ================================================================== 入口
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="问题3：干扰源自动搜索定位与清除")
    p.add_argument("--robot-id", required=True, help="参赛队号（须与模拟器登录队号一致）")
    p.add_argument("--url", default=BASE_URL, help="模拟器接口地址")
    p.add_argument("--log-dir", default="logs", help="行为日志目录（空串表示不写日志）")
    p.add_argument("--dry-run", action="store_true", help="离线自测，不连接模拟器")
    p.add_argument("--cases", type=int, default=10, help="离线自测的案例数")
    p.add_argument("--seed", type=int, default=1, help="离线自测的随机种子起点")
    p.add_argument("--quiet", action="store_true", help="不逐条打印请求/响应")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if args.dry_run:
        return run_dry_run(args)
    try:
        with SimulatorClient(args.robot_id, args.url,
                             log_dir=(args.log_dir or None),
                             verbose=not args.quiet) as sim:
            stats = InterferenceHunter(sim, verbose=not args.quiet).run()
    except (OSError, RuntimeError) as exc:
        # 倒计时未结束 / 测试已结束 / 未开始，接口会直接关闭；这类失败不消耗测试次数
        print(f"[失败] 与模拟器通信中断：{exc}")
        print("       请确认：模拟器已登录、已点开始测试、界面提示机器狗接口已就绪，")
        print("       且 robot_id 与模拟器当前登录的参赛队号逐字节一致。")
        return 1
    print("=" * 72)
    for k, v in stats.items():
        print(f"{k:>14}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# ================================================================== 问题4 扩展说明
# 问题4 多了定向干扰源（有效覆盖角度 180°，定向方向未知），需要改三处：
#
# 1) 探测布站：定向源只在其半平面内可测，因此"距离覆盖"不够，还要满足
#    "包围条件"——对区域内任一点 p，p 必须落在"距 p ≤ 1000 m 的测站"的凸包内。
#    数值结果：内层用间距 1000 m 的六边形格点 13 个，另加半径 1900 m、12 等分的
#    外环，共 25 站可做到零漏检（814 万组"位置×方向"全部可覆盖）。外环是必要的：
#    位于区域边界、朝外的定向源，在目标区域内部任何位置都测不到它。
#
# 2) 定位：no_signal 不再等于"距离超限"，还可能是"不在定向覆盖范围内"，
#    因此不能再拿 no_signal 反推距离；示向度楔形交会本身仍然成立（只要测到过）。
#
# 3) 终局判据：near 也要求"位于有效覆盖角度范围内"，从背面靠近会返回
#    no_signal，所以不能等 near；但 /clear 在 20 m 内不受定向朝向限制，
#    因此以"clear 成功"作为终局。

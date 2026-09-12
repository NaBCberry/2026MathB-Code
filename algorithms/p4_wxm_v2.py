# -*- coding: utf-8 -*-
"""第四题算法 —— 机器狗对「全向 + 定向」干扰源的自动搜索、定位与清除。

与第三题（p3_baseline.py）接口一致：命令行入口仍是根目录 ``robot.py``，本文件只
实现 ``InterferenceHunter``（本文件即 ``algorithms/p4_wxm_v2.py``）。网页可视化见
``webui.py``。它是 ``p4_wxm_v1.py``（35 站版）的**精简版**：改用 29 站布站，
把巡回里程压下来。

【问题4 与问题3 的唯一本质区别】
定向干扰源只在「定向方向两侧各 90°」的 180° 扇形内辐射，扇形之外一律 no_signal。
因此第三题赖以成立的停止判据——“某频道处处无信号 ⇒ 该频道不存在”——在问题4 失效：
一个定向干扰源若把背对测站的方向对着测站，测站就收不到它，可能被漏掉。

【本算法的核心：更密的、可证明「定向也必被探测」的覆盖布站】
1. 覆盖布站（29 站）
   原点 + 半径 900 m × 10 点 + 半径 1830 m × 18 点。
   1830 m 环在目标区域(1800 m)之外，专门包围「贴着边界、朝外/切向发射」的定向源。
   该布站满足：**对场内任意位置、任意指向的定向源，必有一个测站同时满足
   「距源 ≤ 1000 m 且落在源的 180° 扇形内」**（已按 20 m 网格 × 3° 指向数值穷举验证，
   失败数 0）。于是：
       (a) 任意干扰源（全向或定向）必被至少一个测站测到；
       (b) 扫完 29 站仍「全程无信号」的频道必不存在——停止判据恢复，不猜总数。

2. 交会定位（与 Q3 相同，因为扇形内场均匀、示向度仍指向源）
   ±1° 示向度楔形求交，再与「被检测到 ⇒ 距该站 ≤1500 m」圆盘、1800 m 目标圆域求交。
   区域最小外接圆半径 R_c = D/2（见问题1/2），是保证性误差界，真实源必在圆内。

3. 定向鲁棒的精化逼近
   (a) 只有一条示向度时，第二点取「沿示向展开」的 6 点 (0,±300)(600,±450)(1200,±350)
        （局部坐标 d 沿示向、e 垂直）：该集合对任意源距(5–1500 m)、任意指向（且首站已在
        扇形内）都保证至少一点「距源 ≤1000 m 且在扇形内」（数值穷举失败 0）。
        只用 ±90° 两侧点不充分——两侧点对源是「镜像」而非「对顶」，180° 扇形可能同时避开。
   (b) 精化补测若返回 no_signal，说明该点落在扇形外（源背对着它），这不是「频道不存在」，
       直接换对侧/换角度继续，不中断。
   (c) 收敛到 R_c ≤ 20 m 后取最小外接圆圆心 /clear：清除只与距离有关、与定向方向无关，
       一次命中可保证。

4. 滚动巡访
   待办池 = {未去的 29 个测站} ∪ {待补第二条示向度的频道} ∪ {待清除目标}，每步对当前
   待办点集做一次滚动 TSP 取最近点——探测、定位、清除共用同一条回路。

【与 Q3 的关键差异小结】
   - 探测环从 1+6 站升级为 1+10+18=29 站（含 1830 m 外环），移动成本 ≈17.1 km；
   - 停止判据不再是「no_signal 覆盖自检」，而是「29 站扫完 + 全程无信号 ⇒ 不存在」；
   - 精化阶段对 no_signal 的解释改为「在扇形外」而非「在 1000 m 外」，并加「换对侧」。
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
# 覆盖布站：保证「任意定向源必被探测」的两环 + 中心（含 1830 m 外环）。
# 经数值穷举（20 m 网格 × 3° 指向）验证失败 0：中心 + 900m×10 + 1830m×18 = 29 站，
# 移动成本 ≈17.1 km（比三环 35 站 ≈26.4 km 省 35%）。
SURVEY_RINGS = [(900.0, 10), (1830.0, 18)]
# 第二点展开（局部坐标：沿示向 d、垂直 ±e）：对任意源距(5–1500)、任意指向(且 S1 在
# 扇形内)都保证至少一个点「距源 ≤1000 m 且在 180° 扇形内」（数值穷举验证失败 0）
SECOND_SPREAD = [(0.0, 300.0), (600.0, 450.0), (1200.0, 350.0)]
GOOD_RADIUS = 60.0          # 定位区域外接圆半径小于它就不必再补测
MAX_REFINE = 8              # 单目标精化迭代上限
MAX_FALLBACK = 6            # 清除失败后的兜底试探次数
REAL_TIME_MARGIN = 20.0     # 现实中保留的安全余量（s）
POLY_N = 72                 # 目标圆域近似多边形边数
DISC_N = 90                 # "距离 ≤ 1500" 圆盘近似多边形边数


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


def clip_halfplane(poly, p0, p1):
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
    a1 = math.radians(phi_deg - half_deg)
    a2 = math.radians(phi_deg + half_deg)
    u1 = (math.cos(a1), math.sin(a1))
    u2 = (math.cos(a2), math.sin(a2))
    poly = clip_halfplane(poly, s, (s[0] + u1[0], s[1] + u1[1]))
    return clip_halfplane(poly, s, (s[0] - u2[0], s[1] - u2[1]))


def clip_disc(poly, c, r, n=DISC_N):
    R = r / math.cos(math.pi / n)
    pts = [(c[0] + R * math.cos(2 * math.pi * i / n),
            c[1] + R * math.sin(2 * math.pi * i / n)) for i in range(n)]
    for i in range(n):
        poly = clip_halfplane(poly, pts[i], pts[(i + 1) % n])
        if not poly:
            return []
    return poly


def arena_polygon(n=POLY_N):
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
    if abs(d) < 1e-12:
        best = (a, -1.0)
        for u, v in ((a, b), (a, c), (b, c)):
            cc, rr = _circle_from2(u, v)
            if rr > best[1]:
                best = (cc, rr)
        return best
    a2, b2, c2 = ax * ax + ay * ay, bx * bx + by * by, cx * cx + cy * cy
    ux = (a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / d
    uy = (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / d
    return (ux, uy), math.hypot(ax - ux, ay - uy)


def min_enclosing_circle(points: list, seed: int = 2026):
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


# ================================================================== 巡访排序
def plan_tsp(points: list, start: tuple, passes: int = 12) -> list:
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
    channel: int
    bearings: list = field(default_factory=list)   # [(x, y, 示向度°)]
    no_signal: list = field(default_factory=list)  # [(x, y)]  定向源时意义为"扇形外/超距"
    near_at: tuple | None = None
    cleared: bool = False
    polygon: list = field(default_factory=list)
    center: tuple | None = None
    radius: float = float("inf")

    @property
    def known(self) -> bool:
        return bool(self.bearings) or self.near_at is not None

    @property
    def located(self) -> bool:
        return self.center is not None


# ================================================================== 搜索策略
class InterferenceHunter:
    """问题4 策略：定向覆盖布站 → 交会定位 → 定向鲁棒精化 → 巡访清除。"""

    def __init__(self, sim, *, verbose: bool = True):
        self.sim = sim
        self.verbose = verbose
        self.state = {c: ChannelState(c) for c in CHANNELS}
        self.pos = (0.0, 0.0)
        self.cur_channel = 1
        self.virtual_time = 0.0
        self.n_measure = 0
        self.n_clear = 0
        self.n_miss = 0
        self.cleared_channels: list[int] = []
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
        st = self.state[ch]
        if st.near_at is not None:
            return
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
            self.notes.append(f"频道{ch}: 定位区域裁剪为空，沿用上一次区域")
            return
        c, r = min_enclosing_circle(poly)
        st.polygon, st.center = poly, c
        st.radius = r

    def _refresh_region_lite(self, ch: int) -> None:
        st = self.state[ch]
        poly = arena_polygon()
        for (sx, sy, phi) in st.bearings:
            poly = clip_wedge(poly, (sx, sy), phi)
            if not poly:
                return
        c, r = min_enclosing_circle(poly)
        st.polygon, st.center, st.radius = poly, c, r

    # -------------------------------------------------------------- 覆盖布站
    @staticmethod
    def survey_stations() -> list[tuple[float, float]]:
        """29 站覆盖布站（含 1830 m 外环），保证任意定向源必被探测。

        顺序：中心 → 内环 → 外环，每环按角序排列，交给滚动 TSP 再优化。
        """
        pts = [(0.0, 0.0)]
        for rad, k in SURVEY_RINGS:
            for i in range(k):
                a = 2 * math.pi * i / k
                pts.append((rad * math.cos(a), rad * math.sin(a)))
        return pts

    def unknown_channels(self) -> list[int]:
        return [c for c in CHANNELS
                if not self.state[c].known and not self.state[c].cleared]

    def clean_sweep(self, x: float | None = None, y: float | None = None) -> None:
        """在当前点把"至今没测到过信号的频道"扫一遍。

        与 Q3 不同：Q4 的停止判据是「29 站扫完 + 全程无信号 ⇒ 不存在」，因此这里
        **不**做 Q3 那种「覆盖增量 > 0 才扫」的裁剪——每个测站都要全扫一遍未检测频道，
        否则会漏掉「背对此站、朝外发射」的定向源。
        """
        x = self.pos[0] if x is None else x
        y = self.pos[1] if y is None else y
        for ch in CHANNELS:
            if self._out_of_time():
                self.notes.append("现实时间不足，提前结束探测")
                return
            st = self.state[ch]
            if st.cleared or st.known:
                continue
            self.measure(x, y, ch)

    # -------------------------------------------------------------- 补测定位
    def _second_points(self, ch: int) -> list[tuple[float, float]]:
        """只有一条示向度时，取「沿示向展开」的 6 个候选第二点。

        展开（局部坐标，沿示向 d、垂直 ±e）：(0,±300)(600,±450)(1200,±350)。
        该集合对任意源距(5–1500 m)、任意指向（且 S1 在扇形内）都保证至少一个点
        「距源 ≤1000 m 且在 180° 扇形内」（已数值穷举验证失败 0）。哪侧/哪点先测到
        示向度就采信哪点，定向源必被补到第二条示向度。
        """
        sx, sy, phi = self.state[ch].bearings[0]
        u = _dir(phi)
        n = _dir(phi + 90.0)
        cands = []
        for (d, e) in SECOND_SPREAD:
            for sign in (+1, -1):
                px = sx + d * u[0] + sign * e * n[0]
                py = sy + d * u[1] + sign * e * n[1]
                cands.append((px, py))
        cands.sort(key=lambda p: math.hypot(p[0] - self.pos[0], p[1] - self.pos[1]))
        return cands

    def complete(self, ch: int) -> None:
        """给只有一条示向度的频道补出第二条示向度（定向：两侧试，取测到的一侧）。"""
        st = self.state[ch]
        if len(st.bearings) != 1 or st.cleared or st.near_at is not None:
            return
        for (px, py) in self._second_points(ch):
            self.measure(px, py, ch)
            if len(st.bearings) >= 2 or st.near_at is not None:
                return

    def refine(self, ch: int, max_iter: int = MAX_REFINE) -> None:
        """围绕估计点补测，把定位区域压到 R_c ≤ 20 m。

        定向鲁棒：每次在估计点周围沿 4 个互成 90° 的方向补测（180° 扇形必含 ≥2 个
        方向），故无论定向源朝哪指，至少一个补测点落在扇形内、能补到示向度；
        no_signal 的补测点（落在扇形外）自然被跳过，不中断。
        """
        st = self.state[ch]
        for _ in range(max_iter):
            if st.cleared or st.near_at is not None:
                return
            if st.center is None or st.radius <= CLEAR_RADIUS:
                return
            if self._out_of_time():
                return
            u = min(max(st.radius * 1.5, 30.0), max(950.0 - st.radius, 60.0))
            c = st.center
            base = _unit(_sub(c, self.pos))
            for k in range(4):
                a = _rot(base, math.radians(90.0 * k))
                self.measure(c[0] + u * a[0], c[1] + u * a[1], ch)
                if st.cleared or st.near_at is not None:
                    return
                if st.radius <= CLEAR_RADIUS:
                    return
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

        self.clean_sweep()                     # 起点 (0,0)
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
            order = plan_tsp([t[0] for t in tasks], self.pos)
            pt, kind, ch = tasks[order[0]]
            if kind == "survey":
                self.clean_sweep(pt[0], pt[1])
                if pt in pending:
                    pending.remove(pt)
            elif kind == "complete":
                self.complete(ch)
                if len(self.state[ch].bearings) < 2 and self.state[ch].near_at is None:
                    failed.add(ch)
            else:
                self.refine(ch)
                if not self.clear_channel(ch):
                    failed.add(ch)

        unknown = [c for c in CHANNELS
                   if not self.state[c].known and not self.state[c].cleared]
        missed = [c for c in CHANNELS
                  if self.state[c].known and not self.state[c].cleared]
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


# ================================================================== 算法登记
SPEC = AlgorithmSpec(
    id="p4-wxm-v2",
    name="第四题定向鲁棒算法 v2（29 站）",
    problem="问题4",
    summary="定向覆盖布站(29站) → 交会定位 → 定向鲁棒精化 → 滚动巡访清除",
    description=(
        "【探测】原点 + 900m×10 + 1830m×18 共 29 站。1830m 外环包围贴着边界"
        "朝外/切向发射的定向源；该布站保证「场内任意位置、任意指向的定向源必被某站以"
        "≤1000m 且在扇形内探测到」，故「扫完 29 站仍全程无信号 ⇒ 频道必不存在」，停止"
        "判据不再依赖猜总数。\n"
        "【定位】扇形内场均匀，示向度仍指向源，故交会定位与 Q3 相同：±1° 楔形求交，"
        "再与「被检测到 ⇒ 距站 ≤1500m」圆盘、1800m 圆域求交，最小外接圆半径 R_c=D/2 "
        "是保证性误差界。\n"
        "【定向鲁棒精化】单示向度时第二点取「沿示向展开」6 点(0,±300)(600,±450)(1200,±350)，"
        "保证至少一点在扇形内；精化补测沿互成 90° 的 4 方向，no_signal 解释为「在扇形外」"
        "自动跳过。R_c ≤ 20m 后取圆心清除，清除与定向方向无关，一次命中可保证。\n"
        "【巡访】探测、定位、清除共用同一条滚动 TSP 回路。"
    ),
    params={
        "good_radius": GOOD_RADIUS,
        "max_refine": MAX_REFINE,
    },
    entry="algorithms/p4_wxm_v2.py: InterferenceHunter",
)

PARAM_CONSTANTS = {
    "good_radius": "GOOD_RADIUS",
    "max_refine": "MAX_REFINE",
    "max_fallback": "MAX_FALLBACK",
    "real_time_margin": "REAL_TIME_MARGIN",
}
_INT_CONSTANTS = ("max_refine", "max_fallback")


def build(sim, params: dict | None = None, *, verbose: bool = False):
    effective = {**SPEC.params, **(params or {})}
    for key, value in effective.items():
        attr = PARAM_CONSTANTS.get(key)
        if not attr or attr not in globals():
            continue
        globals()[attr] = int(value) if key in _INT_CONSTANTS else float(value)

    max_iter = effective.get("max_refine")
    if isinstance(max_iter, (int, float)):
        InterferenceHunter.refine.__defaults__ = (int(max_iter),)

    return InterferenceHunter(sim, verbose=verbose)

# -*- coding: utf-8 -*-
"""问题4 布站优化：在"零漏检"约束下找更省的测站布局。

判据（严格版）：对目标区域内的每一点 p，

    p 必须落在 { s ∈ 测站 : |s−p| ≤ 1000 } 的**凸包**内部

等价的可算形式：把 1000 m 内的测站按"从 p 看过去的方位"排序，
相邻方位差（含首尾环绕）必须**全部 < 180°**。只要有一段空当 ≥ 180°，
朝那个方向的定向源就永远测不到（半平面里没有任何测站）。

用法::

    python tools/optimize_layout.py            # 扫一批结构化布局
    python tools/optimize_layout.py --verify   # 只核对当前算法用的那套
"""

from __future__ import annotations

import argparse
import math
import statistics as stats
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ARENA_R = 1800.0
R_MIN = 1000.0


# ------------------------------------------------------------------ 采样
def arena_samples(rings: int = 26, per_ring: int = 120) -> list[tuple[float, float]]:
    """极坐标采样：圆心 + 若干同心环 + 边界（边界单独加密）。"""
    pts = [(0.0, 0.0)]
    for i in range(1, rings + 1):
        r = ARENA_R * i / rings
        k = max(int(per_ring * i / rings), 8)
        for j in range(k):
            th = 2 * math.pi * j / k
            pts.append((r * math.cos(th), r * math.sin(th)))
    # 边界再加密一圈（定向源朝外的情形最苛刻）
    for j in range(720):
        th = 2 * math.pi * j / 720
        pts.append((ARENA_R * math.cos(th), ARENA_R * math.sin(th)))
    return pts


# ------------------------------------------------------------------ 判据
def miss_ratio(stations, samples) -> float:
    """返回不满足"包围条件"的采样点比例。"""
    bad = 0
    for (px, py) in samples:
        ang = []
        for (sx, sy) in stations:
            dx, dy = sx - px, sy - py
            if dx * dx + dy * dy <= R_MIN * R_MIN:
                ang.append(math.atan2(dy, dx))
        if len(ang) < 3:
            bad += 1
            continue
        ang.sort()
        gaps = [ang[i + 1] - ang[i] for i in range(len(ang) - 1)]
        gaps.append(ang[0] + 2 * math.pi - ang[-1])
        if max(gaps) >= math.pi:
            bad += 1
    return bad / len(samples)


# ------------------------------------------------------------------ 布局族
def hex_lattice(d: float, limit: float) -> list[tuple[float, float]]:
    pts = []
    n = int(limit / d) + 2
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            x = d * i + d * j * 0.5
            y = d * j * math.sqrt(3.0) / 2.0
            if x * x + y * y <= limit * limit:
                pts.append((x, y))
    return pts


def ring(r: float, k: int, phase: float = 0.0):
    return [(r * math.cos(2 * math.pi * i / k + phase),
             r * math.sin(2 * math.pi * i / k + phase)) for i in range(k)]


# ------------------------------------------------------------------ 路线长度
def open_path_len(pts) -> float:
    """从原点出发、走遍所有点的最短开放路径（最近邻 + 2-opt，近似）。"""
    P = [(0.0, 0.0)] + [tuple(q) for q in pts]
    n = len(P)
    D = [[math.dist(P[i], P[j]) for j in range(n)] for i in range(n)]
    unvis = set(range(1, n))
    tour = [0]
    cur = 0
    while unvis:
        nx = min(unvis, key=lambda j: D[cur][j])
        tour.append(nx)
        unvis.discard(nx)
        cur = nx
    for _ in range(80):
        improved = False
        for i in range(1, n - 1):
            for j in range(i + 1, n):
                a, b, c, e = tour[i - 1], tour[i], tour[j], tour[j + 1] if j + 1 < n else None
                if e is None:
                    continue
                if D[a][b] + D[c][e] > D[a][c] + D[b][e] + 1e-9:
                    tour[i:j + 1] = tour[i:j + 1][::-1]
                    improved = True
        if not improved:
            break
    return sum(D[tour[i]][tour[i + 1]] for i in range(len(tour) - 1))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--rings", type=int, default=22)
    args = ap.parse_args()

    S = arena_samples(args.rings)
    print(f"采样点 {len(S)} 个（圆心 + 同心环 + 720 边界点）")

    current = hex_lattice(1000.0, 1900.0) + ring(1900.0, 12)
    print(f"\n当前布站：{len(current)} 站  漏检率 {miss_ratio(current, S):.4%}  "
          f"站点开放路径 {open_path_len(current) / 1000:.2f} km")
    if args.verify:
        return 0

    print("\n族内搜索（内层六边形格 d、保留半径 L；外环半径 rho、站数 k）")
    rows = []
    for d in (900.0, 1000.0, 1100.0):
        for lim in (1500.0, 1700.0, 1900.0):
            inner = hex_lattice(d, lim)
            for rho in (1850.0, 1900.0, 2000.0, 2100.0, 2200.0, 2400.0):
                for k in (6, 8, 10, 12, 14, 16):
                    if abs(math.degrees(2 * math.pi / k)) > 2 * math.degrees(
                            math.acos(min(ARENA_R / rho, 1.0))) + 1.0:
                        continue                      # 边界必要条件就先过不了
                    pts = inner + ring(rho, k)
                    m = miss_ratio(pts, S)
                    rows.append((m, len(pts), open_path_len(pts), d, lim, rho, k))
    ok = [r for r in rows if r[0] <= 0.0]
    ok.sort(key=lambda r: r[2])
    print(f"\n零漏检的布局共 {len(ok)} 个，按站点路径长度排序（前 15）：")
    print("  漏检率   站数  路径(km)  d     L     rho   k")
    for m, n, L, d, lim, rho, k in ok[:15]:
        print(f"  {m:6.2%}  {n:4d}  {L / 1000:7.2f}  {d:4.0f}  {lim:4.0f}  {rho:4.0f}  {k:3d}")

    if not ok:
        print("  （该参数网格内没有零漏检布局）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

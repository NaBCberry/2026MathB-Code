"""问题 1 覆盖性结论的独立数值检验。

检验对象（见 docs/问题2_第二检测点选择_完整推导.md 引理 1-3 与
docs/论文大纲.md 5.3）：

    "两楔求交所得定位区域是中心对称平行四边形，故 R_c = D/2，
      以定位区域直径为直径的圆能覆盖该区域。"

本脚本不引用论文的任何代码，独立实现：
  1. 精确两楔交（4 个半平面求交，不是条带线性化）；
  2. 凸多边形直径 D（顶点对枚举）与最小外接圆半径 R_c（2/3 点枚举）；
  3. 直径圆的覆盖判定（Thales：其余顶点是否都落在以直径对为直径的圆内）；
  4. 随机扫描 theta、r1、r2、示向度误差，统计 R_c - D/2 的分布；
  5. 3 个及以上测点的交会区域；
  6. 加"测到 => 距离 <= 1500 m"与目标圆域后的区域（边界采样）。

运行： python tools/check_p1_cover.py
"""

from __future__ import annotations

import itertools
import math
import random

DEG = math.pi / 180.0
DELTA = 1.0 * DEG          # 示向度误差上界


# ----------------------------------------------------------------- 基础几何
def clip_halfplane(poly, a, b):
    """保留在有向直线 a->b 左侧（叉积 >= 0）的部分。"""
    if not poly:
        return []
    out = []
    n = len(poly)
    for i in range(n):
        p = poly[i]
        q = poly[(i + 1) % n]
        sp = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
        sq = (b[0] - a[0]) * (q[1] - a[1]) - (b[1] - a[1]) * (q[0] - a[0])
        if sp >= 0.0:
            out.append(p)
        if (sp > 0.0) != (sq > 0.0):
            t = sp / (sp - sq)
            out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
    return out


def wedge_region(stations, bearings, half=DELTA, box=1e6):
    """精确楔交区域：每个测站给两个半平面约束，逐条裁剪。

    stations: [(x, y), ...]，bearings: 示向度（度）。
    """
    poly = [(-box, -box), (box, -box), (box, box), (-box, box)]
    for (sx, sy), phi in zip(stations, bearings):
        a1 = (phi - half / DEG) * DEG
        a2 = (phi + half / DEG) * DEG
        u1 = (math.cos(a1), math.sin(a1))
        u2 = (math.cos(a2), math.sin(a2))
        poly = clip_halfplane(poly, (sx, sy), (sx + u1[0], sy + u1[1]))
        poly = clip_halfplane(poly, (sx, sy), (sx - u2[0], sy - u2[1]))
        if not poly:
            return poly
    return poly


def is_bounded(poly, box=1e6):
    """粗判区域是否有界：顶点是否贴住初始大盒子。"""
    lim = box * 0.99
    return all(abs(p[0]) < lim and abs(p[1]) < lim for p in poly)


def diameter(pts):
    """凸多边形直径：由顶点对取得。返回 (D, A, B)。"""
    best = (-1.0, None, None)
    for a, b in itertools.combinations(range(len(pts)), 2):
        d = math.dist(pts[a], pts[b])
        if d > best[0]:
            best = (d, pts[a], pts[b])
    return best


def _circ2(a, b):
    c = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
    return c, math.dist(a, b) / 2.0


def _circ3(a, b, c):
    ax, ay = a
    bx, by = b
    cx, cy = c
    d = 2.0 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-12:
        return None
    sa = ax * ax + ay * ay
    sb = bx * bx + by * by
    sc = cx * cx + cy * cy
    ux = (sa * (by - cy) + sb * (cy - ay) + sc * (ay - by)) / d
    uy = (sa * (cx - bx) + sb * (ax - cx) + sc * (bx - ax)) / d
    return (ux, uy), math.hypot(ux - ax, uy - ay)


def min_enclosing_circle(pts, tol=1e-9):
    """最小外接圆：枚举 2 点 / 3 点定圆，取包含全部点的最小者。"""
    pts = [tuple(map(float, p)) for p in pts]
    if not pts:
        return None, 0.0
    if len(pts) == 1:
        return pts[0], 0.0

    def contains(c, r):
        return all(math.dist(p, c) <= r * (1 + 1e-12) + tol for p in pts)

    best = (None, float("inf"))
    for a, b in itertools.combinations(pts, 2):
        c, r = _circ2(a, b)
        if r < best[1] and contains(c, r):
            best = (c, r)
    for a, b, c3 in itertools.combinations(pts, 3):
        cand = _circ3(a, b, c3)
        if cand is None:
            continue
        c, r = cand
        if r < best[1] and contains(c, r):
            best = (c, r)
    return best


def covers_with_diameter_circle(pts, tol=1e-7):
    """以直径对为直径的圆是否覆盖全部顶点（凸多边形等价于覆盖整个区域）。"""
    D, A, B = diameter(pts)
    c = ((A[0] + B[0]) / 2.0, (A[1] + B[1]) / 2.0)
    r = D / 2.0
    worst = 0.0
    for p in pts:
        worst = max(worst, math.dist(p, c) - r)
    return worst <= tol, worst, (D, A, B)


def is_centrally_symmetric(pts, tol=1e-6):
    """凸多边形是否中心对称：质心（顶点平均）是否为对称中心。"""
    n = len(pts)
    if n < 3:
        return False
    cx = sum(p[0] for p in pts) / n
    cy = sum(p[1] for p in pts) / n
    for p in pts:
        q = (2 * cx - p[0], 2 * cy - p[1])
        if min(math.dist(q, r) for r in pts) > tol * max(1.0, abs(cx) + abs(cy)):
            return False
    return True


def sides_parallel(pts, tol=1e-9):
    """四边形对边是否平行（平行 <=> 中心对称 + 是平行四边形）。"""
    if len(pts) != 4:
        return False
    e = []
    for i in range(4):
        a, b = pts[i], pts[(i + 1) % 4]
        e.append((b[0] - a[0], b[1] - a[1]))
    for i in range(2):
        x, y = e[i], e[i + 2]
        if abs(x[0] * y[1] - x[1] * y[0]) > tol * (
            math.hypot(*x) * math.hypot(*y) + 1e-30
        ):
            return False
    return True


def place_stations(theta_deg, r1, r2, e1_deg=0.0, e2_deg=0.0):
    """G 在原点；GS1 方向 180 度，GS2 方向 180-theta。返回 (站点, 示向度)。"""
    th = theta_deg * DEG
    s1 = (-r1, 0.0)
    s2 = (r2 * math.cos(math.pi - th), r2 * math.sin(math.pi - th))
    b1 = 0.0 + e1_deg                     # S1 -> G 的真实方位为 0 度
    b2 = (math.degrees(math.atan2(-s2[1], -s2[0])) + e2_deg) % 360.0
    return [s1, s2], [b1, b2]


def analyze(stations, bearings, half=DELTA):
    pts = wedge_region(stations, bearings, half)
    if len(pts) < 3 or not is_bounded(pts):
        return None
    # 去除重复顶点
    uniq = []
    for p in pts:
        if not any(math.dist(p, q) < 1e-9 for q in uniq):
            uniq.append(p)
    pts = uniq
    if len(pts) < 3:
        return None
    D, A, B = diameter(pts)
    c, rc = min_enclosing_circle(pts)
    ok, excess, _ = covers_with_diameter_circle(pts)
    return {
        "pts": pts,
        "D": D,
        "Rc": rc,
        "gap": rc - D / 2.0,
        "rel": (rc - D / 2.0) / (D / 2.0),
        "cover": ok,
        "cover_excess": excess,
        "cs": is_centrally_symmetric(pts),
        "para": sides_parallel(pts),
    }


# ----------------------------------------------------------------- 各检验
def part1_table():
    print("=" * 78)
    print("[1] 复算论文表格：r1 = r2 = 1000 m，零误差，精确楔交")
    print("=" * 78)
    print(f"{'theta':>6} {'D_exact':>10} {'D_strip':>10} {'Rc_exact':>10} "
          f"{'D/2':>10} {'覆盖':>5} {'中心对称':>8} {'平行四边形':>10}")
    for th in (60, 75, 90, 105, 120, 150):
        st, br = place_stations(th, 1000.0, 1000.0)
        r = analyze(st, br)
        # 条带线性化公式
        c = math.cos(th * DEG)
        rr = 1000.0 ** 2 + 1000.0 ** 2
        dm = 2 * math.tan(DELTA) * math.sqrt(rr - 2 * 1000.0 ** 2 * c) / math.sin(th * DEG)
        dp = 2 * math.tan(DELTA) * math.sqrt(rr + 2 * 1000.0 ** 2 * c) / math.sin(th * DEG)
        strip = max(dm, dp)
        if r is None:
            print(f"{th:>6} {'unbounded':>10}")
            continue
        print(f"{th:>6} {r['D']:>10.3f} {strip:>10.3f} {r['Rc']:>10.3f} "
              f"{r['D']/2:>10.3f} {str(r['cover']):>5} {str(r['cs']):>8} "
              f"{str(r['para']):>10}")


def part2_random():
    print()
    print("=" * 78)
    print("[2] 随机扫描：精确两楔交区域，Rc 与 D/2 的差")
    print("=" * 78)
    rng = random.Random(2026)
    worst = None
    fails = 0
    total = 0
    pos_gap = 0
    for _ in range(20000):
        th = rng.uniform(5.0, 175.0)
        r1 = rng.uniform(150.0, 1500.0)
        r2 = rng.uniform(150.0, 1500.0)
        e1 = rng.uniform(-1.0, 1.0)
        e2 = rng.uniform(-1.0, 1.0)
        st, br = place_stations(th, r1, r2, e1, e2)
        r = analyze(st, br)
        if r is None:
            continue
        total += 1
        if not r["cover"]:
            fails += 1
        if r["rel"] > 1e-9:
            pos_gap += 1
        if worst is None or r["rel"] > worst["rel"]:
            worst = dict(r, th=th, r1=r1, r2=r2, e1=e1, e2=e2)
    print(f"有效样本        : {total}")
    print(f"直径圆未覆盖    : {fails}  ({100.0*fails/max(total,1):.3f}%)")
    print(f"Rc > D/2 的样本 : {pos_gap}  ({100.0*pos_gap/max(total,1):.3f}%)")
    if worst:
        print(f"最坏相对超出    : {worst['rel']:.3e}  "
              f"(theta={worst['th']:.2f}, r1={worst['r1']:.1f}, "
              f"r2={worst['r2']:.1f}, e=({worst['e1']:+.3f},{worst['e2']:+.3f}))")
        print(f"  D={worst['D']:.4f}  Rc={worst['Rc']:.4f}  "
              f"Rc-D/2={worst['gap']:.3e}  中心对称={worst['cs']}  "
              f"平行四边形={worst['para']}")
        pts = worst["pts"]
        D, A, B = diameter(pts)
        c, rc = min_enclosing_circle(pts)
        on = [i for i, p in enumerate(pts)
              if abs(math.dist(p, c) - rc) < 1e-9 * max(1.0, rc)]
        print(f"  区域顶点({len(pts)}): " + ", ".join(
            f"({p[0]:.2f},{p[1]:.2f})" for p in pts[:8]))
        print(f"  直径对: ({A[0]:.2f},{A[1]:.2f})-({B[0]:.2f},{B[1]:.2f})  "
              f"最小外接圆由 {len(on)} 个顶点确定（下标 {on}）")


def part2b_scaling():
    print()
    print("=" * 78)
    print("[2b] 相对超出随 half-angle delta 的标度（验证 O(delta^2)）")
    print("=" * 78)
    rng = random.Random(11)
    print(f"{'delta':>7} {'max(Rc-D/2)/(D/2)':>20} {'除以 delta^2':>14} "
          f"{'fail率':>9}")
    for half_deg in (0.5, 1.0, 2.0, 4.0, 8.0):
        half = half_deg * DEG
        worst = 0.0
        fails = 0
        total = 0
        for _ in range(8000):
            th = rng.uniform(3.0, 177.0)
            r1 = rng.uniform(150.0, 1500.0)
            r2 = rng.uniform(150.0, 1500.0)
            e1 = rng.uniform(-half_deg, half_deg)
            e2 = rng.uniform(-half_deg, half_deg)
            st, br = place_stations(th, r1, r2, e1, e2)
            r = analyze(st, br, half=half)
            if r is None:
                continue
            total += 1
            worst = max(worst, r["rel"])
            if not r["cover"]:
                fails += 1
        print(f"{half_deg:>7.2f} {worst:>20.4e} {worst/half**2:>14.4f} "
              f"{100.0*fails/max(total,1):>8.2f}%")


def part2c_iff():
    print()
    print("=" * 78)
    print("[2c] '等号 <=> 中心对称' 的必要性检验（钝角三角形反例）")
    print("=" * 78)
    tri = [(0.0, 0.0), (10.0, 0.0), (5.0, 1.0)]
    D, A, B = diameter(tri)
    c, rc = min_enclosing_circle(tri)
    ok, excess, _ = covers_with_diameter_circle(tri)
    print(f"三角形 (0,0),(10,0),(5,1):  D={D:.4f}  Rc={rc:.4f}  "
          f"Rc-D/2={rc-D/2:.2e}  覆盖={ok}  中心对称={is_centrally_symmetric(tri)}")
    print("=> 等号成立并不需要中心对称；'当且仅当'严格来说不成立。")


def part3_theta90():
    print()
    print("=" * 78)
    print("[3] 推荐几何 theta = 90 度附近：非等距 + 最坏误差组合")
    print("=" * 78)
    print(f"{'theta':>6} {'r1':>7} {'r2':>7} {'e1':>6} {'e2':>6} "
          f"{'D':>10} {'Rc':>10} {'(Rc-D/2)/D':>12} {'覆盖':>5}")
    for th, r1, r2, e1, e2 in [
        (90, 1000, 1000, 0, 0),
        (90, 1000, 1000, 1, 1),
        (90, 1000, 1000, 1, -1),
        (90, 600, 1400, 0, 0),
        (90, 600, 1400, 1, -1),
        (90, 300, 1500, 1, -1),
        (75, 1000, 1000, 1, -1),
        (105, 1000, 1000, 1, -1),
        (60, 800, 1200, 1, -1),
        (30, 800, 1200, 1, -1),
        (150, 800, 1200, 1, -1),
    ]:
        st, br = place_stations(th, r1, r2, e1, e2)
        r = analyze(st, br)
        if r is None:
            print(f"{th:>6} {r1:>7} {r2:>7} {e1:>6} {e2:>6} {'unbounded':>10}")
            continue
        print(f"{th:>6} {r1:>7} {r2:>7} {e1:>6} {e2:>6} {r['D']:>10.3f} "
              f"{r['Rc']:>10.3f} {r['rel']:>12.3e} {str(r['cover']):>5}")


def part4_kstations():
    print()
    print("=" * 78)
    print("[4] 3/4 个测点交会（题目说'若干检测点'）")
    print("=" * 78)
    rng = random.Random(7)
    worst = None
    fails = 0
    total = 0
    for _ in range(20000):
        k = rng.choice([3, 4])
        st, br = [], []
        for _ in range(k):
            ang = rng.uniform(0, 2 * math.pi)
            rad = rng.uniform(300.0, 1500.0)
            s = (rad * math.cos(ang), rad * math.sin(ang))
            true_b = math.degrees(math.atan2(-s[1], -s[0])) % 360.0
            st.append(s)
            br.append(true_b + rng.uniform(-1.0, 1.0))
        r = analyze(st, br, half=DELTA)
        if r is None:
            continue
        total += 1
        if not r["cover"]:
            fails += 1
        if worst is None or r["rel"] > worst["rel"]:
            worst = dict(r, k=k)
    print(f"有效样本     : {total}")
    print(f"直径圆未覆盖 : {fails}  ({100.0*fails/max(total,1):.3f}%)")
    if worst:
        print(f"最坏相对超出 : {worst['rel']:.3e}  (k={worst['k']}, "
              f"D={worst['D']:.3f}, Rc={worst['Rc']:.3f})")


def part5_disc_cut():
    print()
    print("=" * 78)
    print("[5] 反例：非楔交形状（扇形 / 等边三角形）——直径圆覆盖性并不普遍")
    print("=" * 78)
    for name, ang in [("sector 60 deg", math.pi / 3),
                      ("sector 90 deg", math.pi / 2),
                      ("half disc 180", math.pi)]:
        R = 1000.0
        # 候选点集很小（顶点 + 弧上的少数采样点），用于定圆；再用密集采样验证包含性
        cand = [(0.0, 0.0)]
        for i in range(65):
            a = -ang / 2 + ang * i / 64
            cand.append((R * math.cos(a), R * math.sin(a)))
        if ang >= math.pi - 1e-9:
            cand = [(R * math.cos(math.pi * i / 64),
                     R * math.sin(math.pi * i / 64)) for i in range(65)]
        D, A, B = diameter(cand)
        c, rc = min_enclosing_circle(cand)
        dense = [(0.0, 0.0)]
        for i in range(4001):
            a = -ang / 2 + ang * i / 4000
            dense.append((R * math.cos(a), R * math.sin(a)))
        dmax = max(math.dist(p, q) for p in dense for q in dense)
        contain = max(math.dist(p, c) for p in dense)
        print(f"{name:<16} D={D:9.3f}  Rc={rc:9.3f}  D/2={D/2:9.3f}  "
              f"Rc/(D/2)={rc/(D/2):7.4f}  密集验证Rc={contain:9.3f}  "
              f"采样D={dmax:9.3f}")
    # 等边三角形：Jung 定理在平面上的取等情形
    side = 1000.0
    tri = [(0.0, 0.0), (side, 0.0), (side / 2, side * math.sqrt(3) / 2)]
    D, A, B = diameter(tri)
    c, rc = min_enclosing_circle(tri)
    print(f"{'equilateral tri':<16} D={D:9.3f}  Rc={rc:9.3f}  D/2={D/2:9.3f}  "
          f"Rc/(D/2)={rc/(D/2):7.4f}  (=2/sqrt(3)={2/math.sqrt(3):.4f})")


def part6_explicit_counterexample():
    print()
    print("=" * 78)
    print("[6] 显式反例：3 个测点等边布置（半径 1000 m），示向度误差 +1°/+0°/+1°")
    print("=" * 78)
    R = 1000.0
    st = [(R, 0.0),
          (R * math.cos(120 * DEG), R * math.sin(120 * DEG)),
          (R * math.cos(240 * DEG), R * math.sin(240 * DEG))]
    br = [181.0, 300.0, 61.0]      # 真值 180 / 300 / 60，误差 +1 / 0 / +1 度
    r = analyze(st, br)
    print("测站: " + "; ".join(f"({p[0]:.3f},{p[1]:.3f})" for p in st))
    print(f"示向度: {br}")
    print(f"区域顶点: " + "; ".join(f"({p[0]:.6f},{p[1]:.6f})" for p in r["pts"]))
    print(f"D = {r['D']:.6f} m   Rc = {r['Rc']:.6f} m   D/2 = {r['D']/2:.6f} m   "
          f"超出 {100.0*r['rel']:.2f}%")
    D, A, B = diameter(r["pts"])
    mid = ((A[0] + B[0]) / 2.0, (A[1] + B[1]) / 2.0)
    worst = max(math.dist(p, mid) - D / 2.0 for p in r["pts"])
    print(f"直径对: ({A[0]:.6f},{A[1]:.6f}) - ({B[0]:.6f},{B[1]:.6f})")
    print(f"顶点离「以直径为直径的圆」最远超出 {worst:.6f} m  => 覆盖={r['cover']}")


def main():
    part1_table()
    part2_random()
    part2b_scaling()
    part2c_iff()
    part3_theta90()
    part4_kstations()
    part5_disc_cut()
    part6_explicit_counterexample()
    print()
    print("说明：part 1-4、6 为精确楔交（半平面裁剪）；part 5 用 4001 点采样扇形边界，")
    print("      展示'非楔交形状'下 Rc > D/2 的反例（等边三角形为 Jung 取等情形）。")


if __name__ == "__main__":
    main()

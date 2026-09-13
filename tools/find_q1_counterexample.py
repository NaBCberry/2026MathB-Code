import math
import random

R_TARGET = 1800.0
ERR_DEG = 1.0
R_MAX = 1500.0


# ------------------------------------------------------------------ 几何
def clip_halfplane(poly, p0, p1):
    if not poly:
        return []
    d = (p1[0] - p0[0], p1[1] - p0[1])
    out = []
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        fa = d[0] * (a[1] - p0[1]) - d[1] * (a[0] - p0[0])
        fb = d[0] * (b[1] - p0[1]) - d[1] * (b[0] - p0[0])
        if fa >= -1e-12:
            out.append(a)
        if (fa > 1e-12 and fb < -1e-12) or (fa < -1e-12 and fb > 1e-12):
            t = fa / (fa - fb)
            out.append((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])))
    return out


def clip_wedge(poly, s, phi_deg, half=ERR_DEG):
    a1 = math.radians(phi_deg - half)
    a2 = math.radians(phi_deg + half)
    u1 = (math.cos(a1), math.sin(a1))
    u2 = (math.cos(a2), math.sin(a2))
    poly = clip_halfplane(poly, s, (s[0] + u1[0], s[1] + u1[1]))
    return clip_halfplane(poly, s, (s[0] - u2[0], s[1] - u2[1]))


def circle_polygon(R, n=720):
    return [(R * math.cos(2 * math.pi * k / n),
             R * math.sin(2 * math.pi * k / n)) for k in range(n)]


CIRCLE = circle_polygon(R_TARGET)


def diameter(poly):
    best = 0.0
    for i in range(len(poly)):
        for j in range(i + 1, len(poly)):
            d = math.hypot(poly[i][0] - poly[j][0], poly[i][1] - poly[j][1])
            best = max(best, d)
    return best


def _c2(a, b):
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), \
        math.hypot(a[0] - b[0], a[1] - b[1]) / 2


def _c3(a, b, c):
    ax, ay = a
    bx, by = b
    cx, cy = c
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-12:
        return None
    a2, b2, c2v = ax * ax + ay * ay, bx * bx + by * by, cx * cx + cy * cy
    ux = (a2 * (by - cy) + b2 * (cy - ay) + c2v * (ay - by)) / d
    uy = (a2 * (cx - bx) + b2 * (ax - cx) + c2v * (bx - ax)) / d
    return (ux, uy), math.hypot(ax - ux, ay - uy)


def mec(points):
    """Welzl 最小外接圆，返回 (圆心, 半径)。"""
    pts = list(points)
    random.shuffle(pts)
    c, r = None, -1.0

    def inside(p):
        return c is not None and math.hypot(p[0] - c[0], p[1] - c[1]) <= r + 1e-9

    for i, p in enumerate(pts):
        if inside(p):
            continue
        c, r = p, 0.0
        for j in range(i):
            q = pts[j]
            if inside(q):
                continue
            c, r = _c2(p, q)
            for k in range(j):
                s = pts[k]
                if inside(s):
                    continue
                cc = _c3(p, q, s)
                if cc is not None:
                    c, r = cc
    return c, r


def region(G, S):
    """给定源 G 与检测点列表 S，返回 (定位区域多边形, D, R_c)。"""
    bearings = [math.degrees(math.atan2(G[1] - sy, G[0] - sx)) % 360 for (sx, sy) in S]
    poly = CIRCLE
    for (sx, sy), b in zip(S, bearings):
        poly = clip_wedge(poly, (sx, sy), b)
        if len(poly) < 3:
            return None, None, None
    return poly, diameter(poly), mec(poly)[1]


def verify(G, S):
    """验证一组 (G, S) 是否满足物理约束并打印 R_c 与 D。"""
    assert math.hypot(*G) <= R_TARGET + 1e-6, "源不在圆内"
    for i, (sx, sy) in enumerate(S):
        assert math.hypot(sx, sy) <= R_TARGET + 1e-6, "测站不在圆内"
        assert math.hypot(G[0] - sx, G[1] - sy) <= R_MAX + 1e-6, "测站距源超过 1500 m"
    poly, D, Rc = region(G, S)
    print("  G=(%.0f,%.0f) |OG|=%.1f m" % (G[0], G[1], math.hypot(*G)))
    for i, (sx, sy) in enumerate(S):
        print("  S%d=(%.0f,%.0f) |S%dG|=%.1f m" % (i + 1, sx, sy, i + 1,
              math.hypot(G[0] - sx, G[1] - sy)))
    print("  区域顶点数=%d  D=%.2f m  R_c=%.2f m  D/2=%.2f m  R_c/(D/2)=%.4f" %
          (len(poly), D, Rc, D / 2, Rc / (D / 2)))


def search(N=80000, seed=2026):
    """随机搜索 R_c > D/2 的算例，返回 (最大比值, (G, S, D, R_c, 顶点数))。"""
    rng = random.Random(seed)
    best = (1.0, None)
    cnt_over = 0
    cnt_total = 0
    for _ in range(N):
        r = R_TARGET - rng.uniform(1, 15)          # 源贴近边界
        a = rng.uniform(0, 2 * math.pi)
        G = (r * math.cos(a), r * math.sin(a))
        # 采样 3 个检测点（圆内、距源 500~1500 m）
        S = None
        for _try in range(200):
            cand = []
            ok = True
            for _k in range(3):
                aa = rng.uniform(0, 2 * math.pi)
                dd = rng.uniform(500, 1500)
                sx = G[0] + dd * math.cos(aa)
                sy = G[1] + dd * math.sin(aa)
                if sx * sx + sy * sy > R_TARGET * R_TARGET:
                    ok = False
                    break
                cand.append((sx, sy))
            if ok:
                S = cand
                break
        if S is None:
            continue
        poly, D, Rc = region(G, S)
        if D is None or D <= 0:
            continue
        cnt_total += 1
        ratio = Rc / (D / 2.0)
        if Rc > D / 2.0 + 1e-6:
            cnt_over += 1
        if ratio > best[0]:
            best = (ratio, (G, S, D, Rc, len(poly)))
    return best, cnt_over, cnt_total


if __name__ == "__main__":
    (ratio, rec), cnt_over, cnt_total = search()
    G, S, D, Rc, nv = rec
    print("=== 随机搜索 ===")
    print("有效算例 %d，其中 R_c>D/2 占 %.2f%%" % (cnt_total, 100.0 * cnt_over / cnt_total))
    print("最大比值 R_c/(D/2) = %.4f" % ratio)
    print("=== 最强反例 ===")
    verify(G, S)

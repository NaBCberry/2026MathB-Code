# -*- coding: utf-8 -*-
"""一次性诊断：seed 27880 的频道 19，在每次测站巡访时为什么没被测量。
不修改任何算法文件，只在外面包一层日志。
"""
import io
import math
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, ".")

import algorithms  # noqa: E402
from algorithms.p3_baseline import R_MAX, point_segment_distance, _dir  # noqa: E402
from archived.mock_arena import MockArena  # noqa: E402

SEED = int(sys.argv[1]) if len(sys.argv) > 1 else 27880
CH = int(sys.argv[2]) if len(sys.argv) > 2 else 19
ALGO = sys.argv[3] if len(sys.argv) > 3 else "p4-v6-policy"

arena = MockArena(seed=SEED, problem=4)
src = next(s for s in arena.sources if s.channel == CH and not s.cleared)
SRC = (src.x, src.y)
RAD = src.radius
DIR = src.direction


def geo(x, y):
    """返回 (距源, 源→测点方位, 与定向方向夹角, 是否在覆盖内, 是否在半径内)。"""
    dx, dy = x - SRC[0], y - SRC[1]
    d = math.hypot(dx, dy)
    to_pt = math.degrees(math.atan2(dy, dx)) % 360.0
    diff = abs((to_pt - DIR + 180.0) % 360.0 - 180.0)
    return d, to_pt, diff, diff <= 90.0, d <= RAD


h = algorithms.build_algorithm(ALGO, arena, {})
Klass = type(h)
orig_clean = Klass.clean_sweep
orig_measure = Klass.measure
orig_clear = Klass.clear

h._in_clean = False
h._log = []
h._clean_hits = []


def clean_sweep(self, x=None, y=None):
    xx = self.pos[0] if x is None else x
    yy = self.pos[1] if y is None else y
    st = self.state[CH]
    snap = dict(
        x=xx, y=yy, t=self.virtual_time,
        known=st.known, nb=len(st.bearings), ns=len(st.no_signal),
        excl=self._exclusion_ok(CH), cleared=st.cleared, n_before=self.n_measure,
    )
    self._in_clean = True
    self._clean_hits = []
    orig_clean(self, x, y)
    self._in_clean = False
    snap.pop("n_before")
    snap["measured"] = CH in self._clean_hits
    snap["geo"] = geo(xx, yy)
    # 复刻 clean_sweep 的分支，标出"为什么没测这个频道"
    if st.cleared:
        snap["why"] = "已清除"
    elif self._exclusion_ok(CH):
        snap["why"] = "已判定不存在"
    elif not st.known:
        snap["why"] = "未测到过 -> 本应测量"
    elif len(st.bearings) == 1 and st.near_at is None:
        sx, sy, phi = st.bearings[0]
        off = point_segment_distance((xx, yy), (sx, sy), _dir(phi), R_MAX)
        snap["why"] = (f"仅1条方位线，离射线{off:.0f}m"
                       + ("(<=900 会补测)" if off <= 900 else "(>900 不补测)"))
    else:
        snap["why"] = f"已有{len(st.bearings)}条方位线 -> 跳过"
    self._log.append(snap)


def measure(self, x, y, ch):
    if ch == CH:
        st = self.state[CH]
        self._clean_hits.append(CH)
        d, to_pt, diff, cov, inr = geo(x, y)
        self._log.append(dict(
            via="clean_sweep" if self._in_clean else "work",
            x=x, y=y, t=self.virtual_time,
            nb=len(st.bearings), radius=st.radius, known=st.known,
            geo=(d, to_pt, diff, cov, inr),
        ))
    r = orig_measure(self, x, y, ch)
    if ch == CH and self._log and "via" in self._log[-1] and "res" not in self._log[-1]:
        self._log[-1]["res"] = r.get("measure_result")
        self._log[-1]["svd"] = r.get("svd_deg")
    return r


Klass.clean_sweep = clean_sweep
Klass.measure = measure


def clear(self, x, y, ch):
    if ch == CH:
        d, to_pt, diff, cov, inr = geo(x, y)
        self._log.append(dict(via="clear", x=x, y=y, t=self.virtual_time,
                              geo=(d, to_pt, diff, cov, inr),
                              radius=self.state[CH].radius))
    return orig_clear(self, x, y, ch)


Klass.clear = clear

result = h.run()

print(f"源：位置={SRC[0]:.1f},{SRC[1]:.1f} 接收半径={RAD:.1f} 定向方向={DIR:.2f}度")
print(f"结果：cleared={result['cleared']} 已发现未清除={result['已发现但未清除']}")
print()
print("① 测站巡访记录（covered=该站在源覆盖内且距离够近）")
print(f"{'t/s':>8} {'站点':>18} {'到源/m':>8} {'源到点方位':>9} {'与定向夹角':>9} "
      f"{'覆盖内':>6} {'半径内':>6} {'当时nb':>6} {'测了19':>7} 跳过原因")
for s in h._log:
    if "measured" not in s:
        continue
    d, to_pt, diff, cov, inr = s["geo"]
    print(f"{s['t']:8.1f} {s['x']:8.1f},{s['y']:8.1f} {d:8.1f} {to_pt:9.1f} "
          f"{diff:9.1f} {str(cov):>6} {str(inr):>6} {s['nb']:6d} {str(s['measured']):>7} "
          f"{s['why']}")
print()
print("② work() 阶段的测量点")
for s in h._log:
    if s.get("via") != "work":
        continue
    d, to_pt, diff, cov, inr = s["geo"]
    print(f"t={s['t']:7.1f} 点=({s['x']:8.1f},{s['y']:8.1f}) 到源={d:7.1f} "
          f"覆盖内={cov} 半径内={inr} 此时nb={s['nb']} 误差界={s['radius']:.1f}")
print()
print("③ 只列出'该站本可测到频道19、但本次巡访没测'的站点")
hits = []
for s in h._log:
    if "measured" not in s:
        continue
    d, to_pt, diff, cov, inr = s["geo"]
    if (not s["measured"]) and cov and inr and not s["cleared"] and not s["excl"]:
        hits.append(s)
        print(f"t={s['t']:7.1f} 站=({s['x']:8.1f},{s['y']:8.1f}) 到源={d:7.1f} "
              f"夹角={diff:5.1f}度 当时nb={s['nb']}")
print(f"合计 {len(hits)} 个")

# ---------------------------------------------------------------- ④ 反事实
print()
print("④ 反事实：如果首条方位线之后就用外环站补测，误差界会是多少")

from algorithms.p3_baseline import (  # noqa: E402
    arena_polygon, clip_disc, clip_wedge, min_enclosing_circle,
)

arena2 = MockArena(seed=SEED, problem=4)


def reading(x, y):
    """在该点测量频道19会得到的示向度（含该点的固定偏差）。"""
    b = math.degrees(math.atan2(SRC[1] - y, SRC[0] - x))
    return (b + arena2._bias(x, y)) % 360.0


def region(pts):
    poly = arena_polygon()
    for (x, y, phi) in pts:
        poly = clip_wedge(poly, (x, y), phi)
        if not poly:
            return None
    for (x, y, _p) in pts:
        poly = clip_disc(poly, (x, y), R_MAX)
        if not poly:
            return None
    c, r = min_enclosing_circle(poly)
    return c, r


def line_angle(a, b):
    """两条方位线在源处的交会角（0..90°）。"""
    d = abs((a - b + 90.0) % 180.0 - 90.0)
    return d


P1 = (-500.0, 866.0254037844386)
P2 = (-1500.0, 866.0254037844386)
P3 = (-1645.44826719043, 950.0)
phi1 = reading(*P1)
phi2 = reading(*P2)
phi3 = reading(*P3)
print(f"  首条站 {P1} 读数={phi1:.2f}°（真值 {math.degrees(math.atan2(SRC[1]-P1[1],SRC[0]-P1[0]))%360:.2f}°）")
print(f"  外环站 {P2} 读数={phi2:.2f}°  交会角={line_angle(phi1, phi2):.1f}°")
print(f"  外环站 {P3} 读数={phi3:.2f}°  交会角={line_angle(phi1, phi3):.1f}°")
for tag, pts in (("首条+外环(-1500,866)", [(P1[0], P1[1], phi1), (P2[0], P2[1], phi2)]),
                 ("首条+外环两站", [(P1[0], P1[1], phi1), (P2[0], P2[1], phi2),
                                (P3[0], P3[1], phi3)])):
    res = region(pts)
    if res is None:
        print(f"  {tag}: 区域为空")
    else:
        c, r = res
        print(f"  {tag}: 保证误差界 = {r:.1f} m（圆心 {c[0]:.1f},{c[1]:.1f}，"
              f"与真源相距 {math.hypot(c[0]-SRC[0], c[1]-SRC[1]):.1f} m）")

ws = [(s["x"], s["y"], reading(s["x"], s["y"])) for s in h._log if s.get("via") == "work"
      and s.get("nb", 0) < 10]
print()
print("  实际 work() 拿到的方位线读数（注意它们几乎相同）：")
for (x, y, phi) in ws:
    print(f"    ({x:8.1f},{y:8.1f})  读数={phi:.2f}°")
angs = []
for i in range(len(ws)):
    for j in range(i + 1, len(ws)):
        angs.append(line_angle(ws[i][2], ws[j][2]))
if angs:
    print(f"    两两交会角：最小 {min(angs):.2f}°  中位 {sorted(angs)[len(angs)//2]:.2f}°  "
          f"最大 {max(angs):.2f}°（共 {len(angs)} 对）")
print()
print("⑤ 对频道19的 /clear 尝试")
for s in h._log:
    if s.get("via") != "clear":
        continue
    d, to_pt, diff, cov, inr = s["geo"]
    print(f"    t={s['t']:7.1f} 点=({s['x']:8.1f},{s['y']:8.1f}) 距源={d:7.1f}")
print()
print("⑥ 最终累积到频道19的方位线")
for (bx, by, phi) in h.state[CH].bearings:
    print(f"    ({bx:8.1f},{by:8.1f})  读数={phi:7.2f}°")
print()
print("⑦ 频道19 的 measure 调用明细（含测站闸门触发的）")
for s in h._log:
    if s.get("via") != "clean_sweep":
        continue
    d, to_pt, diff, cov, inr = s["geo"]
    print(f"    t={s['t']:7.1f} 点=({s['x']:8.1f},{s['y']:8.1f}) 距源={d:7.1f} "
          f"覆盖内={cov} 结果={s.get('res')} 读数={s.get('svd')}")

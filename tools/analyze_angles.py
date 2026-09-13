# -*- coding: utf-8 -*-
"""诊断：同一频道新增一条方位线时，**真实交会角**是多少，以及它和误差界的关系。

用法::

    python tools/analyze_angles.py --cases 10 --problem 4 --algorithm p4-v2-receding

"交会角" θ 定义在**源处**：源 G 与两个测站 S1、S2 连线的夹角 ∠S1GS2。
θ→0°（同向）或 θ→180°（反向）都是退化几何：两条 ±1° 楔形几乎重合，
定位区域会拉成一条细长条，保证误差界 R_c 随之暴涨。
只有 θ≈90° 时 R_c 最小（问题 2 的定理 1）。

本工具用离线模拟器的**真值源位置**算 θ（跑的时候算法并不知道真值，只用于诊断），
并同时记录该次测量之后算法自己算出的 `state[ch].radius`（保证误差界）。
"""

from __future__ import annotations

import argparse
import json
import math
import statistics as stats
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import algorithms  # noqa: E402
from archived.mock_arena import MockArena  # noqa: E402


def angle_at_source(sx: float, sy: float, s1, s2) -> float:
    """源在 (sx,sy)，两个测站 s1/s2 在源处的张角（度，0–180）。"""
    a1 = math.atan2(s1[1] - sy, s1[0] - sx)
    a2 = math.atan2(s2[1] - sy, s2[0] - sx)
    d = abs(math.degrees(a1 - a2)) % 360.0
    return d if d <= 180.0 else 360.0 - d


class Watch:
    """包一层 sim：每次 measure 之后把该频道的真实交会角与误差界记下来。"""

    def __init__(self, inner, by_ch):
        self.inner = inner
        self.by_ch = by_ch
        self.hunter = None
        self.rows: list[tuple[int, int, float, float]] = []   # (ch, n_bearings, θ, Rc)
        self.cleared_theta: dict[int, float] = {}             # 清除前最后一条方位线的 θ
        self.branch: dict[str, int] = {}                      # 新测点相对"上一条方位线"的偏角分布
        self.n_bearings_at_clear: dict[int, int] = {}
        self.sector_margin: list[tuple[float, float]] = []   # 定向源：两站离扇区边界的角距
        self.in_sweep = False                                # 当前是否在 clean_sweep 里
        self.origin: dict[str, int] = {}                     # 新方位线来自"普查"还是"逼近"
        self.pre_clear: list[tuple[int, object, int]] = []    # 清除瞬间的误差界
        self.first_seen: dict[int, tuple[float, float, float]] = {}   # 频道 → (t, x, y)
        self.result_mix: dict[str, int] = {}                          # 来源×结果 计数
        self.cleared_at: dict[int, tuple[float, float, float]] = {}   # 频道 → (t, x, y)

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def measure(self, x, y, ch):
        r = self.inner.measure(x, y, ch)
        if ch not in self.first_seen and r.get("measure_result") in ("direction", "near"):
            self.first_seen[ch] = (float(r.get("virtual_time_s", 0.0)), x, y)
        k2 = ("work/" if not self.in_sweep else "survey/") + str(r.get("measure_result"))
        self.result_mix[k2] = self.result_mix.get(k2, 0) + 1
        src = self.by_ch.get(ch)
        h = self.hunter
        if src is not None and h is not None:
            st = h.state[ch]
            if len(st.bearings) >= 2:
                s1 = (st.bearings[-2][0], st.bearings[-2][1])
                s2 = (st.bearings[-1][0], st.bearings[-1][1])
                th = angle_at_source(src[0], src[1], s1, s2)
                rc = st.radius if math.isfinite(st.radius) else float("inf")
                self.rows.append((ch, len(st.bearings), th, rc))
                self.cleared_theta[ch] = th
                # 新测点相对"上一条方位线方向"的偏角：≈0 说明就沿着原射线走
                phi = st.bearings[-2][2]
                gx, gy = s1
                a_line = math.radians(phi)
                a_new = math.atan2(y - gy, x - gx)
                dd = abs(math.degrees(a_line - a_new)) % 360.0
                dd = dd if dd <= 180.0 else 360.0 - dd
                key = ("沿原射线(≈0°，同向)" if dd < 7.5
                       else "偏 7.5–30°" if dd < 30.0
                       else "偏 30–60°" if dd < 60.0
                       else "偏 60–120°" if dd < 120.0
                       else "偏 120–180°(反向)")
                self.branch[key] = self.branch.get(key, 0) + 1
                ob = "普查顺路测(clean_sweep)" if self.in_sweep else "逼近时测(work)"
                self.origin[ob] = self.origin.get(ob, 0) + 1
                # 定向源：看两个测站离"扇区边界（±90°）"有多近——越近越脆弱
                u = src[2]
                if u is not None:
                    a1 = math.degrees(math.atan2(s1[1] - src[1], s1[0] - src[0]))
                    a2 = math.degrees(math.atan2(s2[1] - src[1], s2[0] - src[0]))
                    e1 = abs(((a1 - u + 180.0) % 360.0) - 180.0)
                    e2 = abs(((a2 - u + 180.0) % 360.0) - 180.0)
                    self.sector_margin.append((e1, e2))
        return r

    def clear(self, x, y, ch):
        st = self.hunter.state[ch] if self.hunter is not None else None
        if st is not None:
            self.pre_clear.append((
                ch,
                "near" if st.near_at is not None else
                (round(st.radius, 1) if math.isfinite(st.radius) else float("inf")),
                len(self.hunter._probes.get(ch, [])),
            ))
        resp = self.inner.clear(x, y, ch)
        if resp.get("clear_result") == "success" and ch not in self.cleared_at:
            self.cleared_at[ch] = (float(resp.get("virtual_time_s", 0.0)), x, y)
        return resp


def run_case(seed: int, problem: int, algorithm: str, params: dict) -> dict:
    arena = MockArena(seed=seed, problem=problem)
    by_ch = {s.channel: (s.x, s.y, s.direction) for s in arena.sources}
    w = Watch(arena, by_ch)
    hunter = algorithms.build_algorithm(algorithm, w, params)
    w.hunter = hunter
    orig_sweep = hunter.clean_sweep

    def sweep(*a, **k):
        w.in_sweep = True
        try:
            return orig_sweep(*a, **k)
        finally:
            w.in_sweep = False

    hunter.clean_sweep = sweep
    hunter.run()
    nb = {ch: len(hunter.state[ch].bearings) for ch in hunter.cleared_channels}
    return {
        "seed": seed,
        "rows": w.rows,
        "cleared": len(hunter.cleared_channels),
        "n_sources": arena.n_sources,
        "n_bearings_at_clear": nb,
        "sector_margin": w.sector_margin,
        "origin": dict(w.origin),
        "result_mix": dict(w.result_mix),
        "pre_clear": w.pre_clear,
        "first_seen": dict(w.first_seen),
        "cleared_at": dict(w.cleared_at),
        "cleared_theta": dict(w.cleared_theta),
        "branch": dict(w.branch),
        "directional": {s.channel for s in arena.sources if s.direction is not None},
    }


def bucket(th: float) -> str:
    if th < 15.0:
        return "  0–15° 同向退化"
    if th < 40.0:
        return " 15–40° 偏窄"
    if th < 70.0:
        return " 40–70° 尚可"
    if th <= 110.0:
        return " 70–110° 接近最优"
    if th <= 145.0:
        return "110–145° 尚可"
    return "145–180° 反向退化"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", type=int, default=10)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--problem", type=int, default=4)
    ap.add_argument("--algorithm", default="p4-v2-receding")
    ap.add_argument("--params", default="")
    args = ap.parse_args()
    params = json.loads(args.params) if args.params else {}

    allrows: list[tuple[int, int, float, float]] = []
    per_case = []
    dir_rows, omni_rows = [], []
    for i in range(args.cases):
        d = run_case(args.seed + i, args.problem, args.algorithm, params)
        per_case.append(d)
        allrows += d["rows"]
        for (ch, n, th, rc) in d["rows"]:
            (dir_rows if ch in d["directional"] else omni_rows).append((th, rc))

    if not allrows:
        print("没有采到 ≥2 条方位线的样本")
        return 1

    print(f"算法 {args.algorithm} · {args.cases} 例 · 共 {len(allrows)} 次"
          f"「新增一条方位线」事件（同频道第 2 条及以后）")
    print()
    print("=== 真实交会角分布 ===")
    buckets: dict[str, list] = {}
    for (_ch, _n, th, rc) in allrows:
        buckets.setdefault(bucket(th), []).append((th, rc))
    for k in sorted(buckets):
        v = buckets[k]
        ths = [t for t, _ in v]
        rcs = [r for _, r in v if math.isfinite(r)]
        rc_txt = f"中位误差界 {stats.median(rcs):7.1f} m" if rcs else "误差界 ∞"
        print(f"  {k:<24} {len(v):5d} 次 ({len(v)/len(allrows):5.1%})  "
              f"θ中位 {stats.median(ths):6.1f}°  {rc_txt}")
    print()
    ths = [t for _, _, t, _ in allrows]
    print(f"  θ 中位数 {stats.median(ths):.1f}°   均值 {stats.mean(ths):.1f}°   "
          f"落在 [70,110] 的比例 {sum(1 for t in ths if 70 <= t <= 110)/len(ths):.1%}")
    print()
    print("=== 按源的类型拆分（θ 中位数 / 样本数）===")
    for name, v in (("全向源", omni_rows), ("定向源", dir_rows)):
        if v:
            print(f"  {name}: θ中位 {stats.median([t for t,_ in v]):6.1f}°   n={len(v)}")
    print()
    print("=== 每个「已发现但最后清除」的频道，清除前最后一次交会角 ===")
    agg_branch: dict[str, int] = {}
    for d in per_case:
        for k, v in d["branch"].items():
            agg_branch[k] = agg_branch.get(k, 0) + v
    tot_b = sum(agg_branch.values()) or 1
    print("  （先看新测点相对上一条方位线的偏角——定位到代码分支）")
    for k in sorted(agg_branch, key=lambda k: -agg_branch[k]):
        print(f"    {k:<26} {agg_branch[k]:5d} 次  {agg_branch[k]/tot_b:5.1%}")
    print()
    # 清除时手上有几条方位线
    hist: dict[int, int] = {}
    for d in per_case:
        for ch, k in d["n_bearings_at_clear"].items():
            hist[k] = hist.get(k, 0) + 1
    tot_c = sum(hist.values()) or 1
    print("=== 清除成功时手上有几条方位线 ===")
    for k in sorted(hist):
        print(f"    {k:>2} 条: {hist[k]:4d} 个频道  {hist[k]/tot_c:5.1%}")
    print(f"    只靠 1 条方位线就清掉的（说明是靠 /clear 铺清兜底）: "
          f"{hist.get(1, 0)/tot_c:.1%}")
    print()
    m = [e for d in per_case for e in d["sector_margin"]]
    agg_o: dict[str, int] = {}
    for d in per_case:
        for k, v in d["origin"].items():
            agg_o[k] = agg_o.get(k, 0) + v
    tot_o = sum(agg_o.values()) or 1
    print("=== 新增的方位线来自哪里 ===")
    for k in sorted(agg_o, key=lambda k: -agg_o[k]):
        print(f"    {k:<24} {agg_o[k]:5d} 次  {agg_o[k]/tot_o:5.1%}")
    print()
    mix: dict[str, int] = {}
    for d in per_case:
        for k, v in d["result_mix"].items():
            mix[k] = mix.get(k, 0) + v
    tot_m = sum(mix.values()) or 1
    print("=== 每一次测量的来源 × 结果（白跑 = work/no_signal）===")
    for k in sorted(mix, key=lambda k: -mix[k]):
        print(f"    {k:<22} {mix[k]:5d} 次  {mix[k]/tot_m:5.1%}")
    wk = sum(v for k, v in mix.items() if k.startswith("work/")) or 1
    wns = mix.get("work/no_signal", 0)
    print(f"    → 逼近测量里 {wns}/{wk} = {wns/wk:.1%} 是 no_signal（打进盲区或超距）")
    print()
    pc = [e for d in per_case for e in d["pre_clear"]]
    # "被推迟的检查"：首次测到信号 → 最终清除，中间隔了多久、跨了多远
    lag_t, lag_d, far = [], [], []
    for d in per_case:
        for ch, (t0, x0, y0) in d["first_seen"].items():
            if ch not in d["cleared_at"]:
                continue
            t1, x1, y1 = d["cleared_at"][ch]
            lag_t.append(t1 - t0)
            dist = math.hypot(x1 - x0, y1 - y0)
            lag_d.append(dist)
            if dist > 800.0:
                far.append((d["seed"], ch, round(t0), round(t1), round(dist)))
    if lag_t:
        print("=== 被推迟的检查：首次测到信号 → 最终清除 ===")
        print(f"    样本 {len(lag_t)} 个频道；滞后时间 中位 {stats.median(lag_t):.0f} s "
              f"（占单局 {stats.median(lag_t) / 7000:.0%} 左右）")
        print(f"    首测点到清除点的距离：中位 {stats.median(lag_d):.0f} m，"
              f">800 m 的占 {sum(1 for v in lag_d if v > 800)/len(lag_d):.1%}")
        if far:
            print(f"    跨图清除的例子（seed, 频道, 首次 t, 清除 t, 距离）：{far[:6]}")
        print()
    if pc:
        near = sum(1 for _c, r, _p in pc if r == "near")
        fin = [r for _c, r, _p in pc if isinstance(r, (int, float)) and math.isfinite(r)]
        n_probe = [p for _c, _r, p in pc if p > 0]
        print("=== 清除瞬间的保证误差界（『大圆有没有造成损失』的直接答案）===")
        print(f"    清除动作 {len(pc)} 次：其中 near（已进 5 m）{near} 次，"
              f"用误差界圆的 {len(fin)} 次")
        if fin:
            fin_sorted = sorted(fin)
            print(f"    误差界中位 {stats.median(fin):.1f} m，"
                  f"≤20 m 占 {sum(1 for r in fin if r <= 20.0)/len(fin):.1%}，"
                  f">100 m 占 {sum(1 for r in fin if r > 100.0)/len(fin):.1%}")
        print(f"    其中 {len(n_probe)} 次是『先铺清试探、再清除』（平均试探 "
              f"{stats.mean(n_probe):.1f} 次）")
        print()
    if m:
        import statistics as _st
        near = sum(1 for e1, e2 in m if max(e1, e2) > 60.0)
        print("=== 定向源：测站离扇区边界（±90°）的角距 ===")
        print(f"    样本 {len(m)} 组；中位角距 {_st.median([max(a,b) for a,b in m]):.1f}°")
        print(f"    至少一个测站落在『边界 30° 以内』（>60°）的比例: {near/len(m):.1%}")
        print("    → 这部分交会一旦估计稍偏，第二次测量就会掉进盲区得到 no_signal")
        print()
    for d in per_case:
        if not d["cleared_theta"]:
            continue
        bad = [(ch, round(t, 1)) for ch, t in sorted(d["cleared_theta"].items())
               if t < 40.0 or t > 140.0]
        print(f"  seed {d['seed']:>3}: 清除 {d['cleared']}/{d['n_sources']}  "
              f"退化交会角(<40°或>140°)的频道: {bad if bad else '无'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

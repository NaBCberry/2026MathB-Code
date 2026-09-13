# -*- coding: utf-8 -*-
"""单局剖析：把一局的虚拟时间拆成"移动 / 换频 / 检测 / 清除"，并统计移动结构。

用法::

    python tools/profile_run.py --cases 5 --problem 4 --algorithm p4-directional
    python tools/profile_run.py --cases 5 --problem 3 --algorithm p3-baseline

输出的是**诊断信息**（不参与评分），用来回答"时间到底花在哪了"：

* 移动 / 换频 / 检测 / 清除四类时间的占比；
* 移动总里程、单步最长移动、超过 800 m 的"长途"次数（路线来回跳的征兆）；
* 走到的测站数、每频道的测量次数；
* 漏掉的源是不是定向源、离最终估计点多远。
"""

from __future__ import annotations

import argparse
import math
import statistics as stats
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import algorithms  # noqa: E402
from archived.mock_arena import MockArena  # noqa: E402

MOVE_SPEED = 5.0
MEASURE_S = 5.0
CLEAR_HIT_S = 5.0
CLEAR_MISS_S = 3.0


class Recorder:
    """包一层 sim，把每个动作的落点、耗时、结果记下来。"""

    def __init__(self, inner) -> None:
        self.inner = inner
        self.events: list[dict] = []

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def _log(self, kind: str, x: float, y: float, ch: int, resp: dict) -> dict:
        self.events.append({
            "kind": kind, "x": x, "y": y, "ch": ch,
            "t": float(resp.get("virtual_time_s", 0.0)),
            "result": resp.get("measure_result") or resp.get("clear_result"),
        })
        return resp

    def measure(self, x, y, ch):
        return self._log("measure", x, y, ch, self.inner.measure(x, y, ch))

    def clear(self, x, y, ch):
        return self._log("clear", x, y, ch, self.inner.clear(x, y, ch))


def profile(seed: int, problem: int, algorithm: str, params: dict) -> dict:
    arena = MockArena(seed=seed, problem=problem)
    rec = Recorder(arena)
    hunter = algorithms.build_algorithm(algorithm, rec, params)
    hunter.run()

    ev = rec.events
    total_t = ev[-1]["t"] if ev else 0.0

    # 位置序列（含起点）→ 里程
    pts = [(0.0, 0.0)] + [(e["x"], e["y"]) for e in ev]
    hops = [math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
            for i in range(len(pts) - 1)]
    distance = sum(hops)
    move_t = distance / MOVE_SPEED

    n_meas = sum(1 for e in ev if e["kind"] == "measure")
    n_hit = sum(1 for e in ev if e["kind"] == "clear" and e["result"] == "success")
    n_miss = sum(1 for e in ev if e["kind"] == "clear" and e["result"] != "success")
    meas_t = MEASURE_S * n_meas
    clear_t = CLEAR_HIT_S * n_hit + CLEAR_MISS_S * n_miss
    switch_t = max(total_t - move_t - meas_t - clear_t, 0.0)

    per_ch: dict[int, int] = {}
    for e in ev:
        if e["kind"] == "measure":
            per_ch[e["ch"]] = per_ch.get(e["ch"], 0) + 1

    stations = getattr(hunter, "stations", [])

    # 把每一步"从哪来、到哪去"分类，看长途跳跃出在谁身上
    st_set = {(round(x, 3), round(y, 3)) for (x, y) in hunter.survey_stations()}
    hops_by_kind: dict[str, list[float]] = {}
    prev_kind, prev_pt = "enter", (0.0, 0.0)
    for e in ev:
        pt = (e["x"], e["y"])
        d = math.hypot(pt[0] - prev_pt[0], pt[1] - prev_pt[1])
        at_station = (round(pt[0], 3), round(pt[1], 3)) in st_set
        kind = "survey" if e["kind"] == "measure" and at_station else e["kind"]
        key = f"{prev_kind}->{kind}"
        hops_by_kind.setdefault(key, []).append(d)
        prev_kind, prev_pt = kind, pt
    hop_stat = {k: (sum(v), len(v), max(v)) for k, v in hops_by_kind.items()}

    # 跳转距离随时间进度（四分位）的分布：看"后段是不是明显更贵"
    total_for_frac = ev[-1]["t"] if ev else 1.0
    quart = [[], [], [], []]
    prev_t, prev_pt2 = 0.0, (0.0, 0.0)
    for e in ev:
        d = math.hypot(e["x"] - prev_pt2[0], e["y"] - prev_pt2[1])
        frac = prev_t / max(total_for_frac, 1.0)
        quart[min(int(frac * 4), 3)].append(d)
        prev_t, prev_pt2 = e["t"], (e["x"], e["y"])
    # 漏掉的源
    missed = []
    if problem == 4:
        for s in arena.sources:
            if not s.cleared:
                missed.append({
                    "channel": s.channel,
                    "directional": s.direction is not None,
                    "dist_to_origin": math.hypot(s.x, s.y),
                })

    return {
        "seed": seed,
        "n_sources": arena.n_sources,
        "n_directional": getattr(arena, "n_directional", 0),
        "cleared": arena.n_cleared,
        "total_t": total_t,
        "move_t": move_t,
        "meas_t": meas_t,
        "switch_t": switch_t,
        "clear_t": clear_t,
        "distance": distance,
        "hops": hops,
        "n_meas": n_meas,
        "n_hit": n_hit,
        "n_miss": n_miss,
        "n_station": len(stations),
        "per_ch": per_ch,
        "missed": missed,
        "hop_stat": hop_stat,
        "quart": quart,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="单局虚拟时间剖析")
    ap.add_argument("--cases", type=int, default=5)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--problem", type=int, default=4, choices=(3, 4))
    ap.add_argument("--algorithm", default="p4-directional")
    ap.add_argument("--params", default="")
    ap.add_argument("--quiet", action="store_true", help="只打汇总")
    args = ap.parse_args()

    import json
    params = json.loads(args.params) if args.params else {}

    rows = [profile(args.seed + i, args.problem, args.algorithm, params)
            for i in range(args.cases)]

    for r in rows:
        if not args.quiet:
            print(f"[seed {r['seed']:>3}] 源 {r['n_sources']}(定向 {r['n_directional']}) "
                  f"清除 {r['cleared']}  虚拟 {r['total_t']:8.1f} s  "
                  f"移动 {r['move_t']:7.1f}({r['move_t'] / max(r['total_t'], 1):5.1%}) "
                  f"检测 {r['meas_t']:7.1f}({r['meas_t'] / max(r['total_t'], 1):5.1%}) "
                  f"换频 {r['switch_t']:6.1f} 清除 {r['clear_t']:6.1f}  "
                  f"里程 {r['distance'] / 1000:6.2f} km  measure {r['n_meas']:>3} "
                  f"clear {r['n_hit']}+{r['n_miss']}  测站 {r['n_station']}")
            if r["missed"]:
                print(f"          漏掉: {r['missed']}")

    n = len(rows)
    tot = sum(r["total_t"] for r in rows)
    print("-" * 100)
    print(f"平均：清除比例 {sum(r['cleared'] for r in rows) / sum(r['n_sources'] for r in rows):6.2%}  "
          f"总虚拟 {tot / n:8.1f} s  "
          f"移动 {sum(r['move_t'] for r in rows) / n:7.1f} s "
          f"({sum(r['move_t'] for r in rows) / tot:5.1%})  "
          f"检测 {sum(r['meas_t'] for r in rows) / n:7.1f} s "
          f"({sum(r['meas_t'] for r in rows) / tot:5.1%})  "
          f"换频 {sum(r['switch_t'] for r in rows) / n:6.1f} s  "
          f"清除 {sum(r['clear_t'] for r in rows) / n:6.1f} s")
    print(f"      里程 {sum(r['distance'] for r in rows) / n / 1000:6.2f} km  "
          f"measure {sum(r['n_meas'] for r in rows) / n:6.1f} 次  "
          f"clear {sum(r['n_hit'] for r in rows) / n:5.1f} 命中 + "
          f"{sum(r['n_miss'] for r in rows) / n:5.1f} 落空  "
          f"测站 {sum(r['n_station'] for r in rows) / n:5.1f}")
    long_hops = [h for r in rows for h in r["hops"] if h > 800]
    print(f"      超过 800 m 的长途移动：{len(long_hops)} 次，"
          f"占里程 {sum(long_hops) / max(sum(r['distance'] for r in rows), 1):5.1%}，"
          f"最长 {max(long_hops) if long_hops else 0:.0f} m")
    med = stats.median([r["total_t"] for r in rows])
    print(f"      单局虚拟时间：中位数 {med:.1f} s，最少 {min(r['total_t'] for r in rows):.1f} s，"
          f"最多 {max(r['total_t'] for r in rows):.1f} s")

    agg: dict[str, list] = {}
    for r in rows:
        for k, (dist, cnt, mx) in r["hop_stat"].items():
            a = agg.setdefault(k, [0.0, 0, 0.0])
            a[0] += dist
            a[1] += cnt
            a[2] = max(a[2], mx)
    grand = sum(v[0] for v in agg.values()) or 1.0
    print("      跳转分类（里程占比 | 次数 | 单次最长）：")
    for k, (dist, cnt, mx) in sorted(agg.items(), key=lambda kv: -kv[1][0]):
        print(f"        {k:<24} {dist / 1000:7.2f} km  {dist / grand:6.1%}  "
              f"{cnt:5d} 次  最长 {mx:6.0f} m")
    print("      按时间进度的四等分，各段移动距离（km / 次数 / 单次均值）：")
    labels = ["前 25%", "25–50%", "50–75%", "后 25%"]
    for lab, seg in zip(labels, zip(*[r["quart"] for r in rows])):
        flat = [d for part in seg for d in part]
        if not flat:
            continue
        print(f"        {lab}: {sum(flat) / 1000:6.2f} km  {len(flat):5d} 次  "
              f"均值 {stats.mean(flat):6.0f} m  最大 {max(flat):6.0f} m")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

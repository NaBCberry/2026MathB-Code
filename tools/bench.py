# -*- coding: utf-8 -*-
"""离线批量评测：同一批种子把一个算法的每局结果写成 CSV。

用法::

    python tools/bench.py --algorithm p3-baseline --problem 3 --cases 1000
    python tools/bench.py --algorithm p4-v8-geoorder --problem 4 --cases 1000

输出：``bench/<算法id>-p<题号>.csv``，每行一局：

    seed, n_sources, cleared, ratio, avg_locate_clear_s, virtual_total_s,
    n_measure, n_clear, n_clear_miss, wall_s, error

其中 ``avg_locate_clear_s`` 就是论文里的「平均定位清除时间」= 定位清除总时间 ÷
该局被清除的干扰源个数（一局没清掉任何源时留空，不写 inf）。
种子起点固定为 1，**所有算法用同一批种子**，这样第四题各算法之间是可以配对比较的。
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, ".")

import algorithms  # noqa: E402
from archived.mock_arena import MockArena  # noqa: E402

FIELDS = ["seed", "n_sources", "cleared", "ratio", "avg_locate_clear_s",
          "virtual_total_s", "n_measure", "n_clear", "n_clear_miss", "wall_s",
          "error"]


def main() -> int:
    ap = argparse.ArgumentParser(description="离线批量评测一个算法")
    ap.add_argument("--algorithm", required=True)
    ap.add_argument("--problem", type=int, required=True, choices=(3, 4))
    ap.add_argument("--cases", type=int, default=500)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    spec = algorithms.get_spec(args.algorithm)
    out = Path(args.out) if args.out else Path("bench") / f"{args.algorithm}-p{args.problem}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    t_all = time.perf_counter()
    for i in range(args.cases):
        seed = args.seed + i
        t0 = time.perf_counter()
        err = ""
        row = {k: "" for k in FIELDS}
        row["seed"] = seed
        try:
            arena = MockArena(seed=seed, problem=args.problem)
            hunter = algorithms.build_algorithm(args.algorithm, arena, {})
            st = hunter.run()
            n = arena.n_sources
            cleared = st["cleared"]
            vt = float(st.get("虚拟总时间", 0.0))
            row.update({
                "n_sources": n, "cleared": cleared, "ratio": round(cleared / n, 6),
                "avg_locate_clear_s": round(vt / cleared, 3) if cleared else "",
                "virtual_total_s": round(vt, 3),
                "n_measure": st.get("measure次数"), "n_clear": st.get("clear次数"),
                "n_clear_miss": st.get("clear落空次数"),
            })
        except Exception as exc:                       # noqa: BLE001
            err = f"{type(exc).__name__}: {exc}"
        row["wall_s"] = round(time.perf_counter() - t0, 4)
        row["error"] = err
        rows.append(row)
        if (i + 1) % 100 == 0 or i + 1 == args.cases:
            done = [r for r in rows if not r["error"]]
            avg = [r["avg_locate_clear_s"] for r in done if r["avg_locate_clear_s"] != ""]
            print(f"  [{args.algorithm}] {i + 1}/{args.cases} 例  "
                  f"全清率 {sum(1 for r in done if r['cleared'] == r['n_sources']) / max(len(done), 1):.4f}  "
                  f"均值 {sum(avg) / max(len(avg), 1):.1f} s", flush=True)

    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    ok = [r for r in rows if not r["error"]]
    avg = [r["avg_locate_clear_s"] for r in ok if r["avg_locate_clear_s"] != ""]
    print(f"[{args.algorithm}] {spec.name} → {out}")
    print(f"  例数 {len(rows)}  出错 {len(rows) - len(ok)}  全清率 "
          f"{sum(1 for r in ok if r['cleared'] == r['n_sources']) / max(len(ok), 1):.4%}  "
          f"平均定位清除时间 {sum(avg) / max(len(avg), 1):.1f} s  "
          f"总耗时 {time.perf_counter() - t_all:.1f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

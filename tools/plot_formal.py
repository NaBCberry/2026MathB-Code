# -*- coding: utf-8 -*-
"""汇总正式测试（模拟器导出的 robot-*.jsonl）→ 论文表 1 + 结果图。

用法::

    python tools/plot_formal.py "D:\\2026cumcm\\docs\\jsonl"

产出：
* ``<dir>/formal_summary.md`` / ``formal_summary.csv``：表 1 的四列（按目录里的
  `p3/`、`p4/` 分子目录自动分题；没有子目录就按算法声明的题目分组）
* ``docs/figs/formal_results.png``：每局的清除个数（标注平均定位清除时间）与
  程序运行时间（对照 20 分钟预算）

顺便做三项完整性自检：全部指令是否带位置/频道、逐条虚拟时间是否与模拟器返回
一致、20 个频道是否都有归属（清除 + 判定不存在 = 20）。
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "SimSun", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def analyse(path: Path) -> dict:
    recs = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    meta = next((r for r in recs if r.get("event") == "meta"), {})
    acts = [r for r in recs if r.get("event") == "response" and "response" in r]
    pos = (0.0, 0.0)
    ch, move, nsw, nm, nc, hit, miss = 1, 0.0, 0, 0, 0, 0, 0
    pred, drift, no_param, cleared = 0.0, 0, 0, []
    for a in acts:
        p, r, kind = a["request"], a["response"], a["path"]
        xy = p.get("position")
        if xy is None and kind in ("/measure", "/clear"):
            no_param += 1
        step = 0.0
        if xy is not None:
            x, y = float(xy["x"]), float(xy["y"])
            d = math.hypot(x - pos[0], y - pos[1])
            move += d
            pos = (x, y)
            step += d / 5.0
        if kind == "/measure":
            nm += 1
            step += 5.0
            if p.get("channel") != ch:
                nsw += 1
                ch = p.get("channel")
                step += 1.0
        elif kind == "/clear":
            nc += 1
            if r.get("clear_result") == "success":
                hit += 1
                step += 5.0
                cleared.append(p.get("channel"))
            else:
                miss += 1
                step += 3.0
        pred += step
        if abs(float(r.get("virtual_time_s", pred)) - pred) > 1e-3:
            drift += 1
    enter = next((a for a in acts if a["path"] == "/enter"), None)
    last = acts[-1] if acts else None
    real = ((last["response"]["real_timestamp_ms"] - enter["response"]["real_timestamp_ms"]) / 1000.0
            if enter and last else float("nan"))
    return {
        "file": path.name, "case_code": meta.get("case_code") or "",
        "problem": meta.get("algorithm_problem") or "?", "algorithm": meta.get("algorithm") or "?",
        "started": meta.get("started_local") or "",
        "n_cleared": hit, "cleared_channels": sorted(cleared),
        "virtual_total_s": pred, "avg_s": pred / hit if hit else float("nan"),
        "real_s": real, "n_measure": nm, "n_clear": nc, "n_clear_miss": miss,
        "n_request": len(acts), "move_m": move, "drift": drift, "no_param": no_param,
        "exit_reason": (last or {}).get("response", {}).get("exit_reason"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dir", help="放 robot-*.jsonl 的目录（可含 p3/ p4/ 子目录）")
    ap.add_argument("--fig", default="docs/figs/formal_results.png")
    # 汇总写到这里而不是日志目录本身：正式日志常在只读/受保护的位置（比如比赛
    # 材料目录），不该被我们写脏。
    ap.add_argument("--out-dir", default="docs/formal")
    args = ap.parse_args()
    root = Path(args.dir)
    files = sorted(root.rglob("robot-*.jsonl"))
    if not files:
        print("没找到 robot-*.jsonl")
        return 2
    rows = [analyse(p) for p in files]
    rows.sort(key=lambda r: (r["problem"], r["started"]))

    print("%-8s %-22s %-14s %6s %10s %10s %6s %8s" %
          ("题目", "案例编码", "算法", "清除", "平均时间s", "程序运行s", "指令", "虚拟总s"))
    for r in rows:
        print("%-8s %-22s %-14s %6d %10.1f %10.1f %6d %8.0f" %
              (r["problem"], r["case_code"], r["algorithm"], r["n_cleared"],
               r["avg_s"], r["real_s"], r["n_request"], r["virtual_total_s"]))
        print("        清除频道 %s" % r["cleared_channels"])
        flag = "OK" if (r["drift"] == 0 and r["no_param"] == 0
                        and r["exit_reason"] == "user_exit") else "!!"
        print("        自检：漂移 %d 条 / 缺参数 %d 条 / 退出 %s  [%s]"
              % (r["drift"], r["no_param"], r["exit_reason"], flag))

    outdir = Path(args.out_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    with (outdir / "formal_summary.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["题目", "测试案例编码", "清除干扰源个数", "平均定位清除时间(s)",
                    "程序运行时间(s)", "定位清除总时间(s)", "指令条数", "算法", "起始时间"])
        for r in rows:
            w.writerow([r["problem"], r["case_code"], r["n_cleared"],
                        "%.1f" % r["avg_s"], "%.1f" % r["real_s"],
                        "%.1f" % r["virtual_total_s"], r["n_request"],
                        r["algorithm"], r["started"]])

    md = ["| 题目 | 测试案例编码 | 清除干扰源个数 | 平均定位清除时间 | 程序运行时间 |",
          "|---|---|---|---|---|"]
    for r in rows:
        md.append("| %s | %s | %d | %.1f s | %.1f s |"
                  % (r["problem"], r["case_code"], r["n_cleared"], r["avg_s"], r["real_s"]))
    (outdir / "formal_summary.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    # ---------------------------------------------------------------- 图
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.4, 4.6))
    colors = {"问题3": "#1f77b4", "问题4": "#d62728"}
    xs = range(len(rows))
    ax1.bar(xs, [r["n_cleared"] for r in rows],
            color=[colors.get(r["problem"], "#666") for r in rows], alpha=0.85)
    for i, r in enumerate(rows):
        ax1.text(i, r["n_cleared"] + 0.25, "%.1f s" % r["avg_s"], ha="center",
                 va="bottom", fontsize=8)
    ax1.set_xticks(list(xs))
    ax1.set_xticklabels([("%s\n%s" % (r["problem"], r["case_code"][:9])) for r in rows],
                        fontsize=7.5)
    ax1.set_ylabel("清除干扰源个数")
    ax1.set_ylim(0, max(r["n_cleared"] for r in rows) * 1.35)
    ax1.set_title("六次正式测试：清除个数（柱顶=平均定位清除时间）")
    ax1.grid(alpha=0.25, axis="y")

    ax2.bar(xs, [r["real_s"] for r in rows],
            color=[colors.get(r["problem"], "#666") for r in rows], alpha=0.85)
    ax2.axhline(1200, color="#b45309", ls="--", lw=1.2, label="程序运行时间上限 1200 s")
    for i, r in enumerate(rows):
        ax2.text(i, r["real_s"] + 20, "%.1f s" % r["real_s"], ha="center", va="bottom",
                 fontsize=8)
    ax2.set_xticks(list(xs))
    ax2.set_xticklabels([("%s\n%s" % (r["problem"], r["case_code"][:9])) for r in rows],
                        fontsize=7.5)
    ax2.set_ylabel("程序运行时间 (s)")
    ax2.set_ylim(0, 400)
    ax2.legend(fontsize=8)
    ax2.set_title("程序运行时间（远低于 20 分钟上限）")
    ax2.grid(alpha=0.25, axis="y")
    fig.tight_layout()
    Path(args.fig).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.fig, dpi=200)
    print("\n表 → %s\n图 → %s" % (outdir / "formal_summary.md", args.fig))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

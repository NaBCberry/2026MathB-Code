# -*- coding: utf-8 -*-
"""把 bench/*.csv 画成论文可用的分布统计图，并汇总成表。

用法（本机已装 matplotlib）::

    python tools/plot_bench.py
    python tools/plot_bench.py --bench-dir bench --fig-dir docs/figs

产出
----
* ``bench/summary.csv`` / ``bench/summary.md``：每个算法的均值/中位/分位/最坏/全清率
* ``<fig-dir>/`` 下 8 张图：
    p3_hist.png      第三题：平均定位清除时间的分布（直方图＋核密度）
    p3_box.png       第三题：箱线图＋每局散点
    p3_ecdf.png      第三题：经验分布函数（ECDF）
    p4_box.png       第四题：全部算法的箱线图
    p4_hist.png      第四题：主力算法的分布叠加
    p4_ecdf.png      第四题：主力算法的 ECDF
    p4_tradeoff.png  第四题：平均时间 vs 全清率（取舍图）
    all_summary.png  两题汇总：均值±标准差 ＋ 全清率

每局指标 = 该局「定位清除总时间 ÷ 该局清除个数」，与论文定义一致；
一局一个源都没清掉的样本不计入时间分布（图注里会注明条数）。
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, ".")

import numpy as np  # noqa: E402
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "SimSun", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 120

LABELS = {
    "p3-baseline": "P3 基线",
    "p3-v2": "P3 v2",
    "p4-directional": "P4 v1",
    "p4-v2-receding": "P4 v2",
    "p4-v3-residual": "P4 v3",
    "p4-v4-ring1950": "P4 v4",
    "p4-v5-ring1930": "P4 v5",
    "p4-v6-policy": "P4 v6",
    "p4-v7-stationgate": "P4 v7",
    "p4-v8-geoorder": "P4 v8(推荐)",
}
ORDER3 = ["p3-baseline", "p3-v2"]
ORDER4 = ["p4-directional", "p4-v2-receding", "p4-v3-residual", "p4-v4-ring1950",
          "p4-v5-ring1930", "p4-v6-policy", "p4-v7-stationgate", "p4-v8-geoorder"]
MAIN4 = ["p4-v2-receding", "p4-v6-policy", "p4-v7-stationgate", "p4-v8-geoorder"]
COLORS = plt.get_cmap("tab10").colors


def read_csv(path: Path) -> dict:
    """读一个算法的结果；出错局与空值都被剔除。"""
    rows = []
    with path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("error"):
                continue
            out = {"seed": int(r["seed"]), "n_sources": int(r["n_sources"]),
                   "cleared": int(r["cleared"]), "ratio": float(r["ratio"]),
                   "virtual_total_s": float(r["virtual_total_s"]),
                   "n_measure": int(r["n_measure"]), "n_clear": int(r["n_clear"]),
                   "n_clear_miss": int(r["n_clear_miss"])}
            out["avg"] = float(r["avg_locate_clear_s"]) if r["avg_locate_clear_s"] else None
            rows.append(out)
    return {"rows": rows}


def stats_of(d: dict) -> dict:
    rows = d["rows"]
    avgs = np.array([r["avg"] for r in rows if r["avg"] is not None], dtype=float)
    all_clear = sum(1 for r in rows if r["cleared"] == r["n_sources"])
    return {
        "n": len(rows),
        "clear_rate": float(np.mean([r["ratio"] for r in rows])) if rows else 0.0,
        "all_clear_rate": all_clear / len(rows) if rows else 0.0,
        "missing": len(rows) - len(avgs),
        "mean": float(avgs.mean()) if len(avgs) else float("nan"),
        "std": float(avgs.std(ddof=1)) if len(avgs) > 1 else 0.0,
        "median": float(np.median(avgs)) if len(avgs) else float("nan"),
        "p90": float(np.percentile(avgs, 90)) if len(avgs) else float("nan"),
        "p99": float(np.percentile(avgs, 99)) if len(avgs) else float("nan"),
        "worst": float(avgs.max()) if len(avgs) else float("nan"),
        "measure": float(np.mean([r["n_measure"] for r in rows])) if rows else 0.0,
        "avgs": avgs,
    }


def kde(x: np.ndarray, grid: np.ndarray, bw: float | None = None) -> np.ndarray:
    """极简高斯核密度（不依赖 scipy）。"""
    x = np.asarray(x, dtype=float)
    if len(x) < 2:
        return np.zeros_like(grid)
    if bw is None:
        sd = x.std(ddof=1)
        bw = 1.06 * sd * len(x) ** (-1 / 5) if sd > 0 else 1.0
    bw = max(bw, 1e-6)
    z = (grid[:, None] - x[None, :]) / bw
    return np.exp(-0.5 * z ** 2).sum(axis=1) / (len(x) * bw * np.sqrt(2 * np.pi))


def ecdf(x: np.ndarray):
    x = np.sort(np.asarray(x, dtype=float))
    return x, np.arange(1, len(x) + 1) / len(x)


def hist_overlay(ax, series, bins: int, xlabel: str) -> None:
    """直方图（半透明）+ 核密度曲线，用于比较分布形状。"""
    allv = np.concatenate([v for _l, v in series if len(v)])
    lo, hi = np.percentile(allv, 0.5), np.percentile(allv, 99.5)
    edges = np.linspace(lo, hi, bins)
    grid = np.linspace(lo, hi, 400)
    for i, (lab, v) in enumerate(series):
        ax.hist(v, bins=edges, density=True, alpha=0.28, color=COLORS[i % 10],
                label="%s（n=%d）" % (lab, len(v)))
        ax.plot(grid, kde(v, grid), color=COLORS[i % 10], lw=1.8)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("概率密度")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=9)


def box_plot(ax, series, xlabel: str, scatter: bool = True) -> None:
    """箱线图（+每局散点抖动），标签里带全清率。"""
    data = [v for _l, v, _c in series]
    labels = ["%s\n全清率%.1f%%" % (l, c * 100) for l, _v, c in series]
    kw = dict(showmeans=True, widths=0.55,
              meanprops=dict(marker="D", markerfacecolor="#d62728",
                             markeredgecolor="#d62728", markersize=5),
              medianprops=dict(color="#1f77b4", lw=1.6),
              flierprops=dict(marker="o", markersize=2.5, alpha=0.35))
    try:                                      # matplotlib ≥3.9 用 tick_labels
        ax.boxplot(data, tick_labels=labels, **kw)
    except TypeError:                         # 老版本用 labels
        ax.boxplot(data, labels=labels, **kw)
    if scatter:
        rng = np.random.default_rng(2026)
        for i, v in enumerate(data, start=1):
            if not len(v):
                continue
            step = max(len(v) // 400, 1)      # 样本太多就抽稀，免得糊成一片
            vv = v[::step]
            x = i + rng.uniform(-0.16, 0.16, size=len(vv))
            ax.plot(x, vv, ".", ms=1.6, alpha=0.18, color="#334155")
    ax.set_ylabel(xlabel)
    ax.grid(alpha=0.25, axis="y")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench-dir", default="bench")
    ap.add_argument("--fig-dir", default="docs/figs")
    args = ap.parse_args()
    bdir, fdir = Path(args.bench_dir), Path(args.fig_dir)
    fdir.mkdir(parents=True, exist_ok=True)

    data: dict = {}
    for aid in ORDER3 + ORDER4:
        prob = 3 if aid.startswith("p3") else 4
        paths = sorted(bdir.glob("%s-p%d*.csv" % (aid, prob)))
        if not paths:
            print("[跳过] 没有 bench/%s-p%d*.csv" % (aid, prob))
            continue
        rows, seen = [], set()
        for p in paths:                    # 同算法的多批种子（-b2 等）合并，按种子去重
            for r in read_csv(p)["rows"]:
                if r["seed"] in seen:
                    continue
                seen.add(r["seed"])
                rows.append(r)
        print("%-20s 合并 %d 份 CSV，共 %d 例" % (aid, len(paths), len(rows)))
        data[aid] = {"rows": rows}
    if not data:
        print("bench/ 下没有结果，先跑 tools/bench.py")
        return 2
    st = {a: stats_of(d) for a, d in data.items()}

    # ---------------------------------------------------------------- 汇总表
    with (bdir / "summary.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["algorithm", "n", "全部源清除率", "全清局占比", "均值", "标准差",
                    "中位数", "p90", "p99", "最坏", "平均measure", "未计入局数"])
        for a in ORDER3 + ORDER4:
            if a not in st:
                continue
            s = st[a]
            w.writerow([a, s["n"], "%.6f" % s["clear_rate"],
                        "%.6f" % s["all_clear_rate"], "%.2f" % s["mean"],
                        "%.2f" % s["std"], "%.2f" % s["median"], "%.2f" % s["p90"],
                        "%.2f" % s["p99"], "%.2f" % s["worst"],
                        "%.1f" % s["measure"], s["missing"]])

    lines = ["| 算法 | 例数 | 全清局占比 | 平均定位清除时间 (s) | 标准差 | 中位数 | p90 | p99 | 最坏 | 平均 measure |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for a in ORDER3 + ORDER4:
        if a not in st:
            continue
        s = st[a]
        lines.append("| %s | %d | %.2f%% | **%.1f** | %.1f | %.1f | %.1f | %.1f | %.1f | %.1f |"
                     % (LABELS.get(a, a), s["n"], s["all_clear_rate"] * 100, s["mean"],
                        s["std"], s["median"], s["p90"], s["p99"], s["worst"], s["measure"]))
    (bdir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))

    # ---------------------------------------------------------------- 问题3
    s3 = [(LABELS[a], st[a]["avgs"], st[a]["all_clear_rate"]) for a in ORDER3 if a in st]
    if s3:
        fig, ax = plt.subplots(figsize=(7.2, 4.2))
        hist_overlay(ax, [(l, v) for l, v, _c in s3], 44, "平均定位清除时间 (s)")
        ax.set_title("问题3：平均定位清除时间的分布")
        fig.tight_layout()
        fig.savefig(fdir / "p3_hist.png", dpi=200)
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(6.4, 4.6))
        box_plot(ax, s3, "平均定位清除时间 (s)")
        ax.set_title("问题3：分布与离群点")
        fig.tight_layout()
        fig.savefig(fdir / "p3_box.png", dpi=200)
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(6.6, 4.4))
        for i, (l, v, _c) in enumerate(s3):
            x, y = ecdf(v)
            ax.plot(x, y, lw=1.9, color=COLORS[i % 10],
                    label="%s（中位 %.0f s）" % (l, np.median(v)))
        ax.set_xlabel("平均定位清除时间 (s)")
        ax.set_ylabel("累计比例")
        ax.grid(alpha=0.25)
        ax.legend(fontsize=9)
        ax.set_title("问题3：经验分布函数（ECDF）")
        fig.tight_layout()
        fig.savefig(fdir / "p3_ecdf.png", dpi=200)
        plt.close(fig)

    # ---------------------------------------------------------------- 问题4
    s4 = [(LABELS[a], st[a]["avgs"], st[a]["all_clear_rate"]) for a in ORDER4 if a in st]
    if s4:
        fig, ax = plt.subplots(figsize=(9.8, 5.0))
        box_plot(ax, s4, "平均定位清除时间 (s)")
        ax.set_title("问题4：各算法平均定位清除时间的分布（◆=均值，横线=中位数）")
        plt.setp(ax.get_xticklabels(), fontsize=8.5)
        fig.tight_layout()
        fig.savefig(fdir / "p4_box.png", dpi=200)
        plt.close(fig)

        sm = [(LABELS[a], st[a]["avgs"], st[a]["all_clear_rate"]) for a in MAIN4 if a in st]
        if sm:
            fig, ax = plt.subplots(figsize=(7.6, 4.4))
            hist_overlay(ax, [(l, v) for l, v, _c in sm], 44, "平均定位清除时间 (s)")
            ax.set_title("问题4：主力算法（v2 / v6 / v7 / v8）的分布")
            fig.tight_layout()
            fig.savefig(fdir / "p4_hist.png", dpi=200)
            plt.close(fig)

            fig, ax = plt.subplots(figsize=(7.0, 4.4))
            for i, (l, v, _c) in enumerate(sm):
                x, y = ecdf(v)
                ax.plot(x, y, lw=1.9, color=COLORS[i % 10],
                        label="%s（中位 %.0f s）" % (l, np.median(v)))
            ax.set_xlabel("平均定位清除时间 (s)")
            ax.set_ylabel("累计比例")
            ax.grid(alpha=0.25)
            ax.legend(fontsize=9)
            ax.set_title("问题4：经验分布函数（ECDF）")
            fig.tight_layout()
            fig.savefig(fdir / "p4_ecdf.png", dpi=200)
            plt.close(fig)

        fig, ax = plt.subplots(figsize=(7.4, 4.6))
        for i, (l, v, c) in enumerate(s4):
            mu = float(np.mean(v)) if len(v) else float("nan")
            ax.scatter(mu, c * 100, s=90, color=COLORS[i % 10], zorder=3)
            ax.annotate(l, (mu, c * 100), textcoords="offset points",
                        xytext=(6, -3), fontsize=8.5)
        ax.set_xlabel("平均定位清除时间均值 (s)")
        ax.set_ylabel("全清局占比 (%)")
        ax.grid(alpha=0.25)
        ax.set_title("问题4：速度与完备性的取舍（左上更好）")
        fig.tight_layout()
        fig.savefig(fdir / "p4_tradeoff.png", dpi=200)
        plt.close(fig)

    # ---------------------------------------------------------------- 两题汇总
    keys = [a for a in ORDER3 + ORDER4 if a in st]
    fig, ax = plt.subplots(figsize=(10.6, 4.6))
    xs = np.arange(len(keys))
    means = [st[a]["mean"] for a in keys]
    errs = [st[a]["std"] for a in keys]
    ax.bar(xs, means, yerr=errs, capsize=3,
           color=[COLORS[i % 10] for i in range(len(keys))], alpha=0.85)
    top = max(means)
    for i, a in enumerate(keys):
        s = st[a]
        ax.text(i, s["mean"] + s["std"] + top * 0.02,
                "%.0fs\n%.1f%%" % (s["mean"], s["all_clear_rate"] * 100),
                ha="center", va="bottom", fontsize=8)
    ax.set_xticks(xs)
    ax.set_xticklabels([LABELS.get(a, a) for a in keys], rotation=20, ha="right", fontsize=8.5)
    ax.set_ylabel("平均定位清除时间 (s)")
    ax.set_title("各算法平均定位清除时间（柱高=均值，误差棒=标准差，第二行=全清局占比）")
    ax.grid(alpha=0.25, axis="y")
    ax.set_ylim(0, max(m + e for m, e in zip(means, errs)) * 1.25)   # 给柱顶标注留白
    fig.tight_layout()
    fig.savefig(fdir / "all_summary.png", dpi=200)
    plt.close(fig)

    print("\n图已写入 %s/：p3_hist / p3_box / p3_ecdf / p4_box / p4_hist / "
          "p4_ecdf / p4_tradeoff / all_summary .png" % fdir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

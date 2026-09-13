# -*- coding: utf-8 -*-
"""从 logs/robot-*.jsonl 直接算出论文表 1 的四个数字。

题目要求"机器狗程序应自行记录测试过程中的指令序列、响应信息"，论文表 1 要填:

    测试案例编码 | 清除干扰源个数 | 平均定位清除时间 | 程序运行时间

本工具把四列全部算出来（案例编码取自日志第一行 meta 的 case_code；接口不返回它，
要传 --case-code 或事后手抄）。用法::

    python tools/summarize_run.py logs/robot-20260913-151203.jsonl
    python tools/summarize_run.py logs/*.jsonl          # 多份横向对比

口径
----
* 清除干扰源个数 = clear_result == "success" 的不同频道数（同一源只清一次）；
* 定位清除总时间 = 最后一条响应里的 virtual_time_s（含移动/换频道/检测/光学/清除）；
* 平均定位清除时间 = 定位清除总时间 / 清除个数；
* 程序运行时间 = 末条响应的 real_timestamp_ms - 首条 /enter 的 real_timestamp_ms；
* 同时报请求条数，用来估模拟器加密日志的大小（上传上限 2 MB）。
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


def load(path: Path) -> list[dict]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def summarize(path: Path) -> dict:
    recs = load(path)
    meta = next((r for r in recs if r.get("event") == "meta"), {})
    acts = [r for r in recs if r.get("event") == "response" and "response" in r]
    enter = next((r for r in acts if r.get("path") == "/enter"), None)
    last = acts[-1] if acts else None

    # 同一个干扰源只会被成功清除一次（再清返回 no_target_in_range），
    # 所以"成功次数"本身就是"清除个数"；有请求参数时还能列出频道号。
    # 旧日志（没有 request 字段）拿不到频道，只能靠这条性质计数。
    cleared: list = []
    n_success = 0
    miss = 0
    for r in acts:
        if r.get("path") != "/clear":
            continue
        if r["response"].get("clear_result") == "success":
            n_success += 1
            ch = (r.get("request") or {}).get("channel")
            if isinstance(ch, int) and ch not in cleared:
                cleared.append(ch)
        else:
            miss += 1

    t_virtual = float(last["response"].get("virtual_time_s", 0.0)) if last else 0.0
    t_enter = enter["response"].get("real_timestamp_ms") if enter else None
    t_end = last["response"].get("real_timestamp_ms") if last else None
    real_s = ((t_end - t_enter) / 1000.0) if (t_enter and t_end) else None

    n_meas = sum(1 for r in acts if r.get("path") == "/measure")
    n_clear = sum(1 for r in acts if r.get("path") == "/clear")
    has_params = any("position" in (r.get("request") or {}) for r in acts)
    return {
        "file": path.name,
        "case_code": meta.get("case_code") or "(未登记)",
        "robot_id": meta.get("robot_id") or "?",
        "started": meta.get("started_local") or "?",
        "algorithm": meta.get("algorithm") or "(未记录)",
        "params": meta.get("params"),
        "problem": meta.get("problem") or meta.get("algorithm_problem"),
        "n_measure": n_meas,
        "n_request": len(acts),
        "n_cleared": n_success,
        "cleared_channels": sorted(cleared),
        "n_clear": n_clear,
        "n_clear_miss": miss,
        "virtual_total_s": t_virtual,
        "avg_locate_clear_s": (t_virtual / n_success) if n_success else float("inf"),
        "real_runtime_s": real_s,
        "has_request_params": has_params,
        "exit_reason": (last or {}).get("response", {}).get("exit_reason"),
    }


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 2
    rows = []
    for a in args:
        p = Path(a)
        if not p.exists():
            print(f"[跳过] 找不到 {p}")
            continue
        rows.append(summarize(p))
    for r in rows:
        print(f"=== {r['file']} ===")
        print(f"  测试案例编码      : {r['case_code']}")
        print(f"  参赛队号 / 起始    : {r['robot_id']} / {r['started']}")
        prob = r["problem"]
        prob = f"问题{prob}" if isinstance(prob, int) else (prob or "?")
        print(f"  题目 / 算法        : {prob} / {r['algorithm']}")
        print(f"  清除干扰源个数    : {r['n_cleared']}"
              + (f"（频道 {r['cleared_channels']}）" if r["cleared_channels"] else ""))
        print(f"  平均定位清除时间  : {r['avg_locate_clear_s']:.1f} s"
              f"   ← 定位清除总时间 {r['virtual_total_s']:.1f} s")
        if r["real_runtime_s"] is None:
            print("  程序运行时间      : 无法计算（日志里没有 /enter 或 real_timestamp_ms）")
        else:
            print(f"  程序运行时间      : {r['real_runtime_s']:.1f} s"
                  f"   （预算 1200 s，余 {1200 - r['real_runtime_s']:.0f} s）")
        print(f"  指令条数          : measure {r['n_measure']} + clear {r['n_clear']}"
              f"（落空 {r['n_clear_miss']}）= 共 {r['n_request']} 条"
              f"   [加密日志上限 2 MB，正常每条约 0.2-0.5 KB]")
        if not r["has_request_params"]:
            print("  ! 这份日志没有请求参数（position/channel）——旧日志会这样；"
                  "用打了新补丁的 sim_client 重跑一局即可。")
        if r.get("exit_reason") != "user_exit":
            print(f"  ! 退出原因不是 user_exit：{r.get('exit_reason')!r}"
                  "（可能被中止/超时，不算正常完成）")
        print()
    if len(rows) > 1:
        print("文件                          案例编码      清除  平均时间   程序运行时间")
        for r in rows:
            rt = f"{r['real_runtime_s']:.1f} s" if r["real_runtime_s"] is not None else "?"
            print(f"{r['file']:<28}  {str(r['case_code']):<12} {r['n_cleared']:>3}  "
                  f"{r['avg_locate_clear_s']:8.1f} s  {rt:>10}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

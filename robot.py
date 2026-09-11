# -*- coding: utf-8 -*-
"""问题3 的机器狗程序入口：解析参数 → 套上录制/调试外壳 → 跑 algorithms/ 里的算法。

用法::

    python robot.py --robot-id <参赛队号>                    # 跑模拟器（演练/正式测试）
    python robot.py --robot-id demo --dry-run --cases 20     # 离线自测，不联网
    python robot.py --robot-id demo --dry-run --algorithm p3-baseline \
           --params '{"ring_r":1200}'                        # 指定算法与参数

**本文件不实现任何搜索策略**——算法（覆盖式探测 / 交会定位 / 精化逼近 / 滚动巡访清除）
都在 `algorithms/` 下：

* `algorithms/p3_baseline.py` 就是"第三题初版算法"的完整实现；
* 想**新增算法**：在 `algorithms/` 里新建一个模块，不用改本文件；
* 想**改现有算法**：直接改 `algorithms/p3_baseline.py`；
* 算法清单、参数说明、修改对照表：`algorithms/README.md`。

`--trace` 把行为轨迹写成 JSONL 供 `webui.py` 可视化，`--config` 指定调试闸门
（每步延迟 / 断点单步）的配置来源；两者都不需要动算法代码。
"""

from __future__ import annotations

import argparse
import json

import algorithms
from sim_client import BASE_URL, SimulatorClient

# 向后兼容：老代码里的 `from robot import InterferenceHunter` 仍然可用。
from algorithms.p3_baseline import InterferenceHunter  # noqa: F401


# ================================================================== 选算法
def _algorithm_choice(args) -> tuple[str, dict]:
    """解析 --algorithm / --params；缺省用注册表里的默认算法。"""
    algorithm_id = (getattr(args, "algorithm", "") or "").strip() or algorithms.DEFAULT_ID
    raw = (getattr(args, "params", "") or "").strip()
    try:
        params = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        raise ValueError(f"--params 不是合法 JSON（{exc}）；例子：--params "
                         '\'{"ring_r":1200}\'') from exc
    if not isinstance(params, dict):
        raise ValueError('--params 需要是 JSON 对象，例如 --params \'{"ring_r":1200}\'')
    return algorithm_id, params


def build_hunter(sim, args, verbose: bool = False):
    """按 --algorithm / --params 构造策略对象（缺省 = 注册表的默认算法）。"""
    algorithm_id, params = _algorithm_choice(args)
    return algorithms.build_algorithm(algorithm_id, sim, params, verbose=verbose)


# ================================================================== 离线自测
def run_dry_run(args) -> int:
    """用本地模拟环境自测策略，统计"清除比例"与"平均定位清除时间"。

    离线模拟器已归档在 `archived/mock_arena.py`（它只用于自测，正式测试不经过它）。
    """
    try:
        from archived.mock_arena import MockArena
    except ImportError:
        print("缺少 archived/mock_arena.py，无法离线自测。")
        return 2

    try:
        algorithm_id, params = _algorithm_choice(args)
        spec = algorithms.get_spec(algorithm_id)
    except (KeyError, ValueError) as exc:
        print(f"[错误] {exc}")
        return 2
    print(f"算法：{spec.name}（{spec.id} · {spec.problem}）"
          f"    参数覆盖：{params if params else '（用默认值）'}")

    rows = []
    for case in range(args.cases):
        seed = args.seed + case
        arena = MockArena(seed=seed)
        hunter = algorithms.build_algorithm(algorithm_id, arena, params,
                                            verbose=not args.quiet)
        stats = hunter.run()
        total = arena.n_sources
        rows.append((seed, total, stats["cleared"], stats["平均定位清除时间"],
                     stats["虚拟总时间"], stats["measure次数"], stats["clear次数"]))
        print(f"[案例 {case + 1:2d}] seed={seed:5d}  干扰源 {total:2d} 个  "
              f"清除 {stats['cleared']:2d} 个 ({stats['cleared'] / total:6.1%})  "
              f"平均定位清除时间 {stats['平均定位清除时间']:7.1f} s  "
              f"虚拟总时间 {stats['虚拟总时间']:7.1f} s  "
              f"measure {stats['measure次数']:3d} / clear {stats['clear次数']:3d}")
        if stats["备注"]:
            print(f"          备注：{'; '.join(stats['备注'][:3])}")

    n = len(rows)
    rate = sum(r[2] / r[1] for r in rows) / n
    ok = [r for r in rows if r[2]]
    avg = sum(r[3] for r in ok) / max(len(ok), 1)
    print("-" * 96)
    print(f"汇总：{n} 个案例，平均清除比例 {rate:6.2%}，平均定位清除时间 {avg:7.1f} s，"
          f"平均虚拟总时间 {sum(r[4] for r in rows) / n:7.1f} s，"
          f"平均 measure {sum(r[5] for r in rows) / n:5.1f} 次")
    return 0


# ================================================================== 入口
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="问题3：干扰源自动搜索定位与清除")
    p.add_argument("--robot-id", required=True, help="参赛队号（须与模拟器登录队号一致）")
    p.add_argument("--url", default=BASE_URL, help="模拟器接口地址")
    p.add_argument("--log-dir", default="logs", help="行为日志目录（空串表示不写日志）")
    p.add_argument("--dry-run", action="store_true", help="离线自测，不连接模拟器")
    p.add_argument("--cases", type=int, default=10, help="离线自测的案例数")
    p.add_argument("--seed", type=int, default=1, help="离线自测的随机种子起点")
    p.add_argument("--quiet", action="store_true", help="不逐条打印请求/响应")
    p.add_argument("--trace", default="",
                   help="可选：把本次行为轨迹写入该 JSONL（供 webui.py 可视化）")
    p.add_argument("--config", default="config.json",
                   help="调试配置来源（延迟/断点），缺省读 config.json 的 debug 段")
    p.add_argument("--algorithm", default="",
                   help="算法 id（见 algorithms/README.md），缺省用注册表的默认算法")
    p.add_argument("--params", default="",
                   help='算法参数 JSON，覆盖默认值，例如 --params \'{"ring_r":1200}\'')
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if args.dry_run:
        return run_dry_run(args)
    try:
        with SimulatorClient(args.robot_id, args.url,
                             log_dir=(args.log_dir or None),
                             verbose=not args.quiet) as raw:
            sim = raw
            tracer = None
            if args.trace:
                import trace_client
                tracer = trace_client.attach(raw, args.trace, args.config)
                sim = tracer
                if tracer._gate.snapshot()["breakpoint"]["enabled"]:
                    print("[提示] 配置里断点是开着的：直接跑 robot.py 时没人点“下一步”，"
                          "每步会空等到超时才放行。要看单步请改用 "
                          "python webui.py --run --robot-id <参赛队号>")
            try:
                hunter = build_hunter(sim, args, verbose=not args.quiet)
            except (KeyError, ValueError) as exc:
                print(f"[错误] {exc}")
                return 2
            stats = hunter.run()
            if tracer is not None:
                import trace_client
                tracer.finish(stats, trace_client.final_state(hunter))
    except Exception as exc:
        if type(exc).__name__ == "AbortRequested":
            print("[中止] 已在网页上请求中止本次运行（本次测试到此结束）。")
            return 130
        if isinstance(exc, (OSError, RuntimeError)):
            # 倒计时未结束 / 测试已结束 / 未开始，接口会直接关闭；这类失败不消耗测试次数
            print(f"[失败] 与模拟器通信中断：{exc}")
            print("       请确认：模拟器已登录、已点开始测试、界面提示机器狗接口已就绪，")
            print("       且 robot_id 与模拟器当前登录的参赛队号逐字节一致。")
            return 1
        raise
    print("=" * 72)
    for k, v in stats.items():
        print(f"{k:>14}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

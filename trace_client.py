# -*- coding: utf-8 -*-
"""给 robot.py 的会话套一层记录壳，把每一步动作与响应落成 JSONL 行为轨迹。

设计原则：**完全不动 robot.py**。这里提供一个与 SimulatorClient 接口同形的
包装客户端（enter / measure / clear / exit），把内层客户端的每次调用与响应记
录下来，并顺带算出移动距离、换频道耗时、动作耗时等派生量。

命令行用法::

    python trace_client.py --mode mock --seed 1 --out traces/mock-1.jsonl
    python trace_client.py --mode mock --cases 20 --out-dir traces
    python trace_client.py --mode live --robot-id <参赛队号> --out traces/live.jsonl

webui.py 直接调用这里的 run_session()。
"""

from __future__ import annotations

import argparse
import json
import math
import re
import time
from pathlib import Path

from step_gate import AbortRequested

SPEED = 5.0
MEASURE_S = 5.0
SWITCH_S = 1.0
CLEAR_HIT_S = 5.0
CLEAR_MISS_S = 3.0


# ---------------------------------------------------------------- 自定义种子
MAX_SEEDS = 2000                      # 一次最多展开多少个种子（防手滑写 "1-1000000"）
_RANGE_RE = re.compile(r"^(-?\d+)\s*-\s*(-?\d+)$")
_INT_RE = re.compile(r"^-?\d+$")


def parse_seeds(text: str) -> list[int]:
    """把"自定义种子"的写法解析成整数列表（robot.py / webui.py 共用）。

    支持的写法::

        27880            单个
        27880,1031       逗号分隔（中文逗号、顿号也行）
        1 2 3            空格/分号分隔
        1-5              闭区间（含两端，可以倒序写 5-1）
        1-3,27880,-7     混合

    空串返回 `[]`；有看不懂的项、或展开超过 `MAX_SEEDS` 个时抛 `ValueError`，
    由调用方决定怎么提示。
    """
    out: list[int] = []
    for part in re.split(r"[,;、\s]+", (text or "").strip()):
        if not part:
            continue
        m = _RANGE_RE.match(part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            step = 1 if b >= a else -1
            out.extend(range(a, b + step, step))
            if len(out) > MAX_SEEDS:
                raise ValueError(f"种子太多（超过 {MAX_SEEDS} 个），请分批跑")
            continue
        if not _INT_RE.match(part):
            raise ValueError(f"看不懂的种子写法：{part!r}（例：27880 或 27880,1031 或 1-5）")
        out.append(int(part))
    return out


def _finite(value):
    """把 inf/nan 换成 None，保证写出的 JSON 合法。"""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: _finite(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_finite(v) for v in value]
    return value


class TraceRecorder:
    """把一次会话写成 JSONL：首行 meta，末行 summary，中间每行一个动作。"""

    def __init__(self, path: str | Path, meta: dict | None = None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._f = self.path.open("w", encoding="utf-8")
        self._closed = False
        self.seq = 0
        self.t = 0.0
        self.pos = (0.0, 0.0)
        self.cur_channel = 1
        self.totals = {
            "move_m": 0.0, "move_s": 0.0, "switch_s": 0.0,
            "measure_s": 0.0, "clear_s": 0.0,
            "n_measure": 0, "n_clear": 0, "n_switch": 0, "n_clear_miss": 0,
        }
        self.meta = {"arena_radius": 1800.0, "move_speed": SPEED,
                     "started": time.strftime("%Y-%m-%d %H:%M:%S")}
        if meta:
            self.meta.update(meta)
        self._write({"kind": "meta", **self.meta})

    # ---------------------------------------------------------------- 内部
    def _write(self, obj: dict) -> None:
        if self._closed:
            return
        self._f.write(json.dumps(_finite(obj), ensure_ascii=False) + "\n")
        self._f.flush()

    def _move(self, x: float, y: float) -> float:
        d = math.hypot(x - self.pos[0], y - self.pos[1])
        self.pos = (x, y)
        self.totals["move_m"] += d
        self.totals["move_s"] += d / SPEED
        return d

    # ---------------------------------------------------------------- 事件
    def enter(self, resp: dict) -> None:
        self.t = float(resp.get("virtual_time_s", 0.0) or 0.0)
        self.totals["remaining_real_s"] = resp.get("remaining_real_duration_s")
        self._write({"kind": "enter", "seq": 0, "t": self.t,
                     "remaining_real_s": resp.get("remaining_real_duration_s")})

    def measure(self, x: float, y: float, ch: int, resp: dict) -> None:
        d = self._move(x, y)
        switch = SWITCH_S if ch != self.cur_channel else 0.0
        self.cur_channel = ch
        self.seq += 1
        self.totals["n_measure"] += 1
        self.totals["measure_s"] += MEASURE_S
        self.totals["switch_s"] += switch
        self.totals["n_switch"] += 1 if switch else 0
        self.t = float(resp.get("virtual_time_s", self.t) or self.t)
        self._write({"kind": "measure", "seq": self.seq, "x": x, "y": y, "ch": ch,
                     "result": resp.get("measure_result"), "svd": resp.get("svd_deg"),
                     "t": self.t, "move_m": d, "move_s": d / SPEED,
                     "switch_s": switch, "action_s": MEASURE_S})

    def clear(self, x: float, y: float, ch: int, resp: dict) -> None:
        d = self._move(x, y)
        hit = resp.get("clear_result") == "success"
        self.seq += 1
        self.totals["n_clear"] += 1
        self.totals["n_clear_miss"] += 0 if hit else 1
        self.totals["clear_s"] += CLEAR_HIT_S if hit else CLEAR_MISS_S
        self.t = float(resp.get("virtual_time_s", self.t) or self.t)
        self._write({"kind": "clear", "seq": self.seq, "x": x, "y": y, "ch": ch,
                     "result": resp.get("clear_result"), "t": self.t,
                     "move_m": d, "move_s": d / SPEED,
                     "action_s": CLEAR_HIT_S if hit else CLEAR_MISS_S})

    def finish(self, stats: dict | None = None, final_state: dict | None = None) -> None:
        self.totals["virtual_total_s"] = self.t
        self._write({"kind": "summary", "t": self.t,
                     "totals": self.totals, "stats": stats or {},
                     "final_state": final_state or {}})
        self._closed = True
        self._f.close()

    def note(self, obj: dict) -> None:
        """记录一条非动作事件（例如闸门的停/放行），不参与状态表渲染。"""
        self._write(dict(obj, kind=obj.get("kind", "gate")))


class TracingClient:
    """与 SimulatorClient 同形的包装客户端：转发给内层客户端并记录轨迹。

    同时（可选）挂一道 StepGate：在每个动作之前/之后决定是否延迟或停下等人。
    """

    def __init__(self, inner, recorder: TraceRecorder, gate=None) -> None:
        self._inner = inner
        self._rec = recorder
        self._gate = gate

    def enter(self) -> dict:
        if self._gate is not None:
            self._gate.reset_run()          # 新一局：清空计数与中止标志
            self._gate.before("enter", {})
        resp = self._inner.enter()
        self._rec.enter(resp)
        if self._gate is not None:
            self._gate.set_budget(resp.get("remaining_real_duration_s"))
            self._drain_gate()
            self._gate.after("enter", {})
            self._drain_gate()
        return resp

    def measure(self, x: float, y: float, ch: int) -> dict:
        info = {"x": x, "y": y, "channel": ch}
        if self._gate is not None:
            self._gate.before("measure", info)
        resp = self._inner.measure(x, y, ch)
        self._rec.measure(x, y, ch, resp)
        if self._gate is not None:
            self._drain_gate()
            self._gate.after("measure", info)
            self._drain_gate()
        return resp

    def clear(self, x: float, y: float, ch: int) -> dict:
        info = {"x": x, "y": y, "channel": ch}
        if self._gate is not None:
            self._gate.before("clear", info)
        resp = self._inner.clear(x, y, ch)
        self._rec.clear(x, y, ch, resp)
        if self._gate is not None:
            self._drain_gate()
            self._gate.after("clear", info)
            self._drain_gate()
        return resp

    def exit(self) -> dict:
        return self._inner.exit()

    def finish(self, stats: dict | None = None, final_state: dict | None = None) -> None:
        """结束记录（robot.py 用 --trace 时由外部调用）。"""
        self._drain_gate()
        self._rec.finish(stats, final_state)

    def _drain_gate(self) -> None:
        if self._gate is None:
            return
        for note in self._gate.take_notes():
            self._rec.note(note)

    def __enter__(self) -> "TracingClient":
        return self

    def __exit__(self, *_exc) -> None:
        try:
            self._inner.exit()
        except Exception:
            pass


def final_state(hunter) -> dict:
    """只读地取一份策略内部状态，供可视化显示各频道的定位结果（不修改 robot.py）。"""
    out = {}
    for ch, st in hunter.state.items():
        out[str(ch)] = {
            "known": st.known,
            "cleared": st.cleared,
            "n_bearings": len(st.bearings),
            "n_no_signal": len(st.no_signal),
            "near_at": list(st.near_at) if st.near_at else None,
            "center": list(st.center) if st.center else None,
            "radius": st.radius if math.isfinite(st.radius) else None,
        }
    return out


_final_state = final_state          # 兼容旧名字


def run_session(*, mode: str, out: str | Path, seed: int | None = None,
                robot_id: str = "", url: str = "", log_dir: str | None = None,
                problem: int = 3, n_sources: int | None = None,
                n_directional: int | None = None,
                directional_fraction: float | None = None, gate=None,
                algorithm: str = "", params: dict | None = None,
                case_code: str = "") -> dict:
    """跑一局（离线 mock 或真实模拟器），产出 trace 文件，返回统计字典。

    `algorithm` / `params` 选算法与参数（见 algorithms/README.md）；缺省用注册表
    里的默认算法。选了什么会写进 trace 的 meta，回放时一眼能看出来。

    `problem` 只对离线 `mode="mock"` 有意义：3 = 全全向源（默认），4 = 全向 + 定向
    混合。连接真实模拟器时不传这个参数，行为与以前完全一样。

    `case_code` 是模拟器界面上显示的「测试案例编码」（接口不返回），只对实机一局
    有意义：会写进 trace 的 meta 和 `logs/robot-*.jsonl` 的第一行，供填论文表 1
    和把日志文件对上号用。留空就是没登记。
    """
    import algorithms

    algorithm_id = algorithm or algorithms.DEFAULT_ID
    spec = algorithms.get_spec(algorithm_id)
    effective = {**spec.params, **(params or {})}
    algo_meta = {"algorithm": spec.id, "algorithm_name": spec.name,
                 "algorithm_problem": spec.problem, "algorithm_params": effective}

    def build(client):
        return algorithms.build_algorithm(algorithm_id, client, params)

    def note_stations(recorder, hunter, arena_problem):
        """把本局算法"为保证完备性必须巡访的测站"写进 trace。

        第三题与第四题的这套站点完全不同（7 站环 vs 内层 13 + 外环 12），
        网页要按题目把它们标出来；写在 trace 里还能顺带记录"实际用的是哪套布站"
        （各算法可以不一样，例如队友的 29 站 / 35 站版本）。
        """
        try:
            stations = [[float(p[0]), float(p[1])] for p in hunter.survey_stations()]
        except Exception:                     # noqa: BLE001 —— 算法没提供就算了
            return
        recorder.note({"kind": "stations", "stations": stations,
                       "problem": arena_problem, "algorithm": spec.id,
                       "algorithm_name": spec.name})

    if mode == "mock":
        from archived.mock_arena import MockArena      # 离线模拟器已归档
        arena = MockArena(seed=seed, problem=problem, n_sources=n_sources,
                          n_directional=n_directional,
                          directional_fraction=directional_fraction)
        meta = {
            "mode": "mock", "problem": arena.problem, "seed": seed,
            "n_sources": arena.n_sources,
            "n_directional": arena.n_directional,
            "sources": [{"ch": s.channel, "x": s.x, "y": s.y,
                         "radius": s.radius, "direction": s.direction}
                        for s in arena.sources],
            **algo_meta,
        }
        rec = TraceRecorder(out, meta)
        client = TracingClient(arena, rec, gate)
        hunter = build(client)
        note_stations(rec, hunter, arena.problem)
        try:
            stats = hunter.run()
        except AbortRequested as exc:
            client._drain_gate()
            rec.note({"kind": "gate", "action": "abort", "reason": "abort",
                      "message": str(exc)})
            raise
        client._drain_gate()
        rec.finish(stats, _final_state(hunter))
        return stats

    if mode == "live":
        from sim_client import SimulatorClient
        rec = TraceRecorder(out, {"mode": "live", "robot_id": robot_id, "url": url,
                                  "case_code": case_code, **algo_meta})
        # 把算法信息也写进 logs/robot-*.jsonl 的第一行：正式测试的日志要能和
        # "这局跑的哪套算法"对上（trace 的 meta 里有，但那份是另一条链路）。
        inner = SimulatorClient(robot_id, url, log_dir=log_dir, verbose=False,
                                case_code=case_code, extra_meta=algo_meta)
        client = TracingClient(inner, rec, gate)
        try:
            hunter = build(client)
            note_stations(rec, hunter, None)      # 实机：题目由算法自己声明
            try:
                stats = hunter.run()
            except AbortRequested as exc:
                client._drain_gate()
                rec.note({"kind": "gate", "action": "abort", "reason": "abort",
                          "message": str(exc)})
                raise
            client._drain_gate()
            rec.finish(stats, _final_state(hunter))
        finally:
            inner.close()
        return stats

    raise ValueError(f"未知 mode: {mode}")


def attach(inner, trace_path: str | Path, config_path: str | Path = "config.json",
           meta: dict | None = None, gate=None):
    """给任意客户端套上记录壳（robot.py 的 --trace 用）。

    返回 TracingClient；跑完后请调用它的 ``finish(stats, final_state)``。
    """
    from step_gate import StepGate, load_debug_config

    if gate is None:
        gate = StepGate(load_debug_config(config_path))
    rec = TraceRecorder(trace_path, meta or {"mode": "live"})
    return TracingClient(inner, rec, gate)


def main() -> int:
    p = argparse.ArgumentParser(description="记录 robot.py 的行为轨迹（trace）")
    p.add_argument("--mode", choices=("mock", "live"), default="mock")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--cases", type=int, default=1, help="mock 模式下连续跑几个案例")
    p.add_argument("--seeds", default="",
                   help="mock 模式的自定义种子：逗号/空格分隔，支持区间"
                        "（例：27880,1031 或 1-5）；给了它就忽略 --seed/--cases")
    p.add_argument("--problem", type=int, default=3, choices=(3, 4),
                   help="mock 模式的题目：3 = 全向源（默认），4 = 全向 + 定向混合")
    p.add_argument("--out", default="", help="单个 trace 的输出路径")
    p.add_argument("--out-dir", default="traces", help="多案例时的输出目录")
    p.add_argument("--robot-id", default="", help="live 模式必填")
    p.add_argument("--url", default="http://127.0.0.1:2026")
    p.add_argument("--log-dir", default="logs")
    p.add_argument("--algorithm", default="", help="算法 id，缺省用注册表默认算法")
    p.add_argument("--params", default="", help='算法参数 JSON，例如 \'{"ring_r":1200}\'')
    args = p.parse_args()

    params = json.loads(args.params) if args.params else {}

    if args.mode == "mock" and (args.seeds.strip() or args.cases > 1):
        try:
            seeds = parse_seeds(args.seeds) if args.seeds.strip() else [
                args.seed + i for i in range(max(int(args.cases), 0))]
        except ValueError as exc:
            print(f"--seeds 解析失败：{exc}")
            return 2
        if not seeds:
            print("没有要跑的种子：--cases 至少给 1，或用 --seeds 指定。")
            return 2
        for i, seed in enumerate(seeds):
            path = Path(args.out_dir) / f"mock-seed{seed}.jsonl"
            stats = run_session(mode="mock", out=path, seed=seed,
                                algorithm=args.algorithm, params=params,
                                problem=args.problem)
            print(f"[{i + 1}/{len(seeds)}] {path}  清除 {stats['cleared']} 个  "
                  f"平均定位清除时间 {stats['平均定位清除时间']:.1f} s")
        return 0

    out = args.out or str(Path(args.out_dir) / (
        f"mock-seed{args.seed}.jsonl" if args.mode == "mock" else "live.jsonl"))
    stats = run_session(mode=args.mode, out=out, seed=args.seed,
                        robot_id=args.robot_id, url=args.url, log_dir=args.log_dir,
                        algorithm=args.algorithm, params=params,
                        problem=args.problem)
    print(f"trace 已写入 {out}")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

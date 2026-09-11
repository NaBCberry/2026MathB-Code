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
import time
from pathlib import Path

SPEED = 5.0
MEASURE_S = 5.0
SWITCH_S = 1.0
CLEAR_HIT_S = 5.0
CLEAR_MISS_S = 3.0


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


class TracingClient:
    """与 SimulatorClient 同形的包装客户端：转发给内层客户端并记录轨迹。"""

    def __init__(self, inner, recorder: TraceRecorder) -> None:
        self._inner = inner
        self._rec = recorder

    def enter(self) -> dict:
        resp = self._inner.enter()
        self._rec.enter(resp)
        return resp

    def measure(self, x: float, y: float, ch: int) -> dict:
        resp = self._inner.measure(x, y, ch)
        self._rec.measure(x, y, ch, resp)
        return resp

    def clear(self, x: float, y: float, ch: int) -> dict:
        resp = self._inner.clear(x, y, ch)
        self._rec.clear(x, y, ch, resp)
        return resp

    def exit(self) -> dict:
        return self._inner.exit()

    def __enter__(self) -> "TracingClient":
        return self

    def __exit__(self, *_exc) -> None:
        try:
            self._inner.exit()
        except Exception:
            pass


def _final_state(hunter) -> dict:
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


def run_session(*, mode: str, out: str | Path, seed: int | None = None,
                robot_id: str = "", url: str = "", log_dir: str | None = None,
                n_sources: int | None = None,
                directional_fraction: float = 0.0) -> dict:
    """跑一局（离线 mock 或真实模拟器），产出 trace 文件，返回统计字典。"""
    from robot import InterferenceHunter

    if mode == "mock":
        from mock_arena import MockArena
        arena = MockArena(seed=seed, n_sources=n_sources,
                          directional_fraction=directional_fraction)
        meta = {
            "mode": "mock", "seed": seed,
            "n_sources": arena.n_sources,
            "n_directional": arena.n_directional,
            "sources": [{"ch": s.channel, "x": s.x, "y": s.y,
                         "radius": s.radius, "direction": s.direction}
                        for s in arena.sources],
        }
        rec = TraceRecorder(out, meta)
        client = TracingClient(arena, rec)
        hunter = InterferenceHunter(client, verbose=False)
        stats = hunter.run()
        rec.finish(stats, _final_state(hunter))
        return stats

    if mode == "live":
        from sim_client import SimulatorClient
        rec = TraceRecorder(out, {"mode": "live", "robot_id": robot_id, "url": url})
        inner = SimulatorClient(robot_id, url, log_dir=log_dir, verbose=False)
        client = TracingClient(inner, rec)
        try:
            hunter = InterferenceHunter(client, verbose=False)
            stats = hunter.run()
            rec.finish(stats, _final_state(hunter))
        finally:
            inner.close()
        return stats

    raise ValueError(f"未知 mode: {mode}")


def main() -> int:
    p = argparse.ArgumentParser(description="记录 robot.py 的行为轨迹（trace）")
    p.add_argument("--mode", choices=("mock", "live"), default="mock")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--cases", type=int, default=1, help="mock 模式下连续跑几个案例")
    p.add_argument("--out", default="", help="单个 trace 的输出路径")
    p.add_argument("--out-dir", default="traces", help="多案例时的输出目录")
    p.add_argument("--robot-id", default="", help="live 模式必填")
    p.add_argument("--url", default="http://127.0.0.1:2026")
    p.add_argument("--log-dir", default="logs")
    args = p.parse_args()

    if args.mode == "mock" and args.cases > 1:
        for i in range(args.cases):
            seed = args.seed + i
            path = Path(args.out_dir) / f"mock-seed{seed}.jsonl"
            stats = run_session(mode="mock", out=path, seed=seed)
            print(f"[{i + 1}/{args.cases}] {path}  清除 {stats['cleared']} 个  "
                  f"平均定位清除时间 {stats['平均定位清除时间']:.1f} s")
        return 0

    out = args.out or str(Path(args.out_dir) / (
        f"mock-seed{args.seed}.jsonl" if args.mode == "mock" else "live.jsonl"))
    stats = run_session(mode=args.mode, out=out, seed=args.seed,
                        robot_id=args.robot_id, url=args.url, log_dir=args.log_dir)
    print(f"trace 已写入 {out}")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

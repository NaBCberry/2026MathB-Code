# -*- coding: utf-8 -*-
"""可视化 WebUI：把 robot.py 的行为轨迹（trace JSONL）画成网页。

三种用法::

    # 1) 离线生成一批模拟案例并打开可视化（最常用，无需模拟器/网络）
    python webui.py --demo --cases 5

    # 2) 接真实模拟器跑一局，同时网页实时刷新
    python webui.py --run --robot-id <参赛队号>

    # 3) 只看已有的 trace
    python webui.py --serve-only --trace-dir traces

界面内容：20 个频道为列、每一次探测/清除为行的状态表；圆形地图上的机器狗轨迹、
探测点、清除点与定位结果；逐步行动日志；以及汇总指标（含题目要求的
"被清除干扰源个数的比例"与"平均定位清除时间"）。
"""

from __future__ import annotations

import argparse
import json
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import trace_client
import algorithms
from step_gate import StepGate, load_debug_config

ROOT = Path(__file__).resolve().parent
HTML_PATH = ROOT / "webui.html"
CONFIG_PATH = ROOT / "config.json"

STATE = {
    "trace_dir": Path("traces"),
    "running": None,          # 正在跑的任务（trace 文件名）
    "error": None,
    "gate": None,             # StepGate
    "current": None,          # 当前正在看的 trace 名
    "lock": threading.Lock(),
}


# ------------------------------------------------------------------ 数据接口
def list_traces() -> list[dict]:
    d: Path = STATE["trace_dir"]
    if not d.exists():
        return []
    out = []
    for f in sorted(d.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True):
        meta, summary = {}, {}
        try:
            with f.open("r", encoding="utf-8") as fh:
                first = fh.readline()
                if first:
                    meta = json.loads(first)
                last = ""
                for line in fh:
                    if line.strip():
                        last = line
                if last:
                    summary = json.loads(last)
        except (OSError, ValueError):
            pass
        totals = summary.get("totals", {})
        out.append({
            "name": f.name,
            "mtime": time.strftime("%Y-%m-%d %H:%M:%S",
                                   time.localtime(f.stat().st_mtime)),
            "size": f.stat().st_size,
            "mode": meta.get("mode", "?"),
            "seed": meta.get("seed"),
            "problem": meta.get("problem", 3 if meta.get("mode") == "mock" else None),
            "n_sources": meta.get("n_sources"),
            "n_directional": meta.get("n_directional"),
            "cleared": summary.get("stats", {}).get("cleared"),
            "virtual_total_s": totals.get("virtual_total_s"),
        })
    return out


class TraceCache:
    """按字节偏移增量解析 trace：每轮只读新增的那一段，支撑高频轮询。

    轮询时前端带 ``since=<已有事件数>``，这里就只回增量事件，payload 通常为 0 字节。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._st: dict[str, dict] = {}

    def read(self, path: Path, since: int = 0) -> dict:
        key = str(path)
        with self._lock:
            st = self._st.get(key)
            try:
                size = path.stat().st_size
            except OSError:
                raise FileNotFoundError(path.name)
            if st is None:
                st = {"offset": 0, "buf": "", "size": -1,
                      "events": [], "meta": {}, "summary": {}}
                self._st[key] = st
            elif size < st["size"]:                  # 同名文件被新的一局覆盖
                st.update(offset=0, buf="", size=-1, events=[], meta={}, summary={})
            if size != st["size"]:
                with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
                    fh.seek(st["offset"])
                    chunk = fh.read()
                    st["offset"] = fh.tell()
                lines = (st["buf"] + chunk).split("\n")
                st["buf"] = lines.pop()          # 末段可能只写了一半，留到下次
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except ValueError:
                        continue
                    kind = obj.get("kind")
                    if kind == "meta":
                        st["meta"] = obj
                    elif kind == "summary":
                        st["summary"] = obj
                    else:
                        st["events"].append(obj)
                st["size"] = size
            events = st["events"]
            return {"meta": st["meta"], "summary": st["summary"],
                    "events": events[since:], "total": len(events)}


TRACES = TraceCache()


def read_trace(name: str, since: int = 0) -> dict:
    """读一局 trace；since>0 时只返回第 since 条之后的新事件（增量）。"""
    path = (STATE["trace_dir"] / name).resolve()
    if path.parent != STATE["trace_dir"].resolve() or not path.exists():
        raise FileNotFoundError(name)
    out = TRACES.read(path, since)
    out.update({"name": name, "running": STATE["running"]})
    return out


def run_blocking(mode: str, name: str, *, seed: int | None = None, robot_id: str = "",
                 url: str = "http://127.0.0.1:2026", log_dir: str = "logs",
                 algorithm: str = "", params: dict | None = None,
                 problem: int = 3) -> dict | None:
    """同步跑一局并登记状态（在后台线程里调用）。"""
    with STATE["lock"]:
        STATE["running"] = name
        STATE["error"] = None
    try:
        return trace_client.run_session(
            mode=mode, out=STATE["trace_dir"] / name, seed=seed,
            robot_id=robot_id, url=url, log_dir=log_dir, gate=STATE["gate"],
            algorithm=algorithm, params=params, problem=problem)
    except Exception as exc:                          # noqa: BLE001
        STATE["error"] = f"{type(exc).__name__}: {exc}"
        print(f"[webui] {mode} 运行结束：", exc)
        return None
    finally:
        with STATE["lock"]:
            STATE["running"] = None


def start_run(mode: str, *, seed: int | None = None, robot_id: str = "",
              url: str = "http://127.0.0.1:2026", log_dir: str = "logs",
              algorithm: str = "", params: dict | None = None,
              problem: int = 3) -> str:
    """后台跑一局（离线 mock 或实机），返回 trace 文件名。

    `problem` 只影响离线 mock（3 = 全全向源，4 = 全向 + 定向混合）；实机一局仍然写
    `live.jsonl`，参数一个都不多传。
    """
    name = (f"mock-p{4 if problem == 4 else 3}-seed{seed}.jsonl" if mode == "mock"
            else "live.jsonl")
    with STATE["lock"]:
        if STATE["running"]:
            return STATE["running"]
    threading.Thread(target=lambda: run_blocking(mode, name, seed=seed, robot_id=robot_id,
                                                 url=url, log_dir=log_dir,
                                                 algorithm=algorithm, params=params,
                                                 problem=problem),
                     daemon=True).start()
    return name


def algo_payload() -> dict:
    """给网页的算法清单：默认 id + 每个算法的身份、说明、默认参数。"""
    try:
        specs = algorithms.list_specs()
        errors = algorithms.load_errors()
    except Exception as exc:                      # noqa: BLE001 —— 坏插件不该拖垮网页
        return {"default": algorithms.DEFAULT_ID, "algorithms": [], "error": str(exc)}
    return {"default": algorithms.DEFAULT_ID, "algorithms": specs, "errors": errors}


def problem_of(body: dict) -> int:
    """取请求里的"离线题目"号：只认 4，其余（含缺省）都当 3。"""
    try:
        value = int(body.get("problem", 3))
    except (TypeError, ValueError):
        return 3
    return 4 if value == 4 else 3


def save_debug_config(cfg: dict | None, path: Path = CONFIG_PATH) -> None:
    """把调试配置写回 config.json（其余字段原样保留）。"""
    if not cfg:
        return
    raw = {}
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}
    raw["debug"] = cfg
    path.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


# ------------------------------------------------------------------ HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "CUMCM2026B/1.0"

    def log_message(self, *_args) -> None:            # 静音访问日志
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj) -> None:
        self._send(200, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def do_GET(self) -> None:                          # noqa: N802
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path in ("/", "/index.html"):
            if not HTML_PATH.exists():
                self._send(500, "webui.html 缺失".encode("utf-8"),
                           "text/plain; charset=utf-8")
                return
            self._send(200, HTML_PATH.read_bytes(), "text/html; charset=utf-8")
        elif u.path == "/api/traces":
            self._json(list_traces())
        elif u.path == "/api/algorithms":
            self._json(algo_payload())
        elif u.path == "/api/status":
            self._json({"running": STATE["running"], "error": STATE["error"]})
        elif u.path == "/api/gate":
            gate = STATE["gate"]
            self._json({"gate": gate.state() if gate else None,
                        "running": STATE["running"], "error": STATE["error"]})
        elif u.path == "/api/trace":
            name = (q.get("name") or [""])[0]
            try:
                since = int((q.get("since") or ["0"])[0])
            except ValueError:
                since = 0
            try:
                self._json(read_trace(name, max(since, 0)))
            except FileNotFoundError:
                self._send(404, b"not found", "text/plain; charset=utf-8")
        else:
            self._send(404, b"not found", "text/plain; charset=utf-8")

    def do_POST(self) -> None:                         # noqa: N802
        u = urlparse(self.path)
        q = parse_qs(u.query)
        body = self._body()
        if u.path == "/api/new":
            raw = (q.get("seed") or ["0"])[0]
            try:
                seed = int(raw)
            except ValueError:
                seed = 0
            if seed <= 0:
                seed = int(time.time()) % 100000
            problem = problem_of(body)
            self._json({"name": start_run("mock", seed=seed,
                                          algorithm=body.get("algorithm", ""),
                                          params=body.get("params") or None,
                                          problem=problem),
                        "seed": seed, "problem": problem})
        elif u.path == "/api/run":
            mode = body.get("mode", "mock")
            if mode == "live" and not body.get("robot_id"):
                self._send(400, "缺少 robot_id".encode("utf-8"),
                           "text/plain; charset=utf-8")
                return
            # 实机（live）一个参数都不多传：连模拟器的行为与以前完全一致
            extra = {"problem": problem_of(body)} if mode == "mock" else {}
            name = start_run(mode, seed=body.get("seed"),
                             robot_id=body.get("robot_id", ""),
                             url=body.get("url", "http://127.0.0.1:2026"),
                             log_dir=STATE.get("log_dir", "logs"),
                             algorithm=body.get("algorithm", ""),
                             params=body.get("params") or None,
                             **extra)
            self._json({"name": name})
        elif u.path == "/api/gate/step":
            gate = STATE["gate"]
            self._json({"ok": bool(gate and gate.release("manual"))})
        elif u.path == "/api/gate/update":
            gate = STATE["gate"]
            patch = body.get("debug", body)
            cfg = gate.update(patch) if gate else None
            if body.get("save"):
                save_debug_config(cfg)
            self._json({"config": cfg})
        elif u.path == "/api/gate/abort":
            gate = STATE["gate"]
            if gate:
                gate.request_abort()
            self._json({"ok": bool(gate)})
        else:
            self._send(404, b"not found", "text/plain; charset=utf-8")

    def _body(self) -> dict:
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n <= 0:
            return {}
        try:
            data = json.loads(self.rfile.read(n).decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except (ValueError, OSError):
            return {}


class Server(ThreadingHTTPServer):
    daemon_threads = True
    # Windows 下 SO_REUSEADDR 允许两个进程绑同一端口，会出现"以为重启了其实还是旧进程"，
    # 这里显式关掉，端口被占用时直接报错。
    allow_reuse_address = False


# ------------------------------------------------------------------ 入口
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="干扰源定位清除 —— 可视化 WebUI")
    p.add_argument("--demo", action="store_true", help="先生成离线模拟案例再起服务")
    p.add_argument("--run", action="store_true", help="接真实模拟器跑一局（需 --robot-id）")
    p.add_argument("--serve-only", action="store_true", help="只提供已有 trace 的可视化")
    p.add_argument("--cases", type=int, default=3, help="--demo 生成几个案例")
    p.add_argument("--seed", type=int, default=1, help="--demo 的起始随机种子")
    p.add_argument("--problem", type=int, default=3, choices=(3, 4),
                   help="离线案例的题目：3 = 全全向源（默认），4 = 全向 + 定向混合")
    p.add_argument("--robot-id", default="", help="--run 时必填")
    p.add_argument("--url", default="http://127.0.0.1:2026")
    p.add_argument("--log-dir", default="logs")
    p.add_argument("--trace-dir", default="traces")
    p.add_argument("--config", default="config.json",
                   help="调试配置（延迟/断点）来源，缺省读 config.json 的 debug 段")
    p.add_argument("--algorithm", default="",
                   help="算法 id（见 algorithms/README.md）；缺省用注册表默认算法")
    p.add_argument("--params", default="", help='算法参数 JSON，例如 \'{"ring_r":1200}\'')
    p.add_argument("--port", type=int, default=8800)
    p.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    STATE["trace_dir"] = Path(args.trace_dir)
    STATE["log_dir"] = args.log_dir
    STATE["gate"] = StepGate(load_debug_config(args.config))
    try:
        cli_params = json.loads(args.params) if args.params else None
    except ValueError as exc:
        print(f"--params 不是合法 JSON：{exc}")
        return 2
    cli_algo = args.algorithm or algorithms.DEFAULT_ID
    print("算法清单：")
    try:
        specs = algorithms.list_specs()
    except Exception as exc:                      # noqa: BLE001
        print(f"  [警告] 算法加载失败：{exc}")
        specs = []
    for spec in specs:
        marks = []
        if spec["id"] == algorithms.DEFAULT_ID:
            marks.append("默认")
        if spec["id"] == cli_algo:
            marks.append("当前")
        suffix = (" ← " + "、".join(marks)) if marks else ""
        print(f"  {spec['id']:>16}  {spec['name']}（{spec['problem']}）{suffix}")
    if specs and cli_algo not in {s["id"] for s in specs}:
        print(f"  [警告] --algorithm {cli_algo} 不在清单里，运行时会报错。")
    dbg = STATE["gate"].snapshot()
    print("调试闸门：断点%s，延迟%s"
          % ("开" if dbg["breakpoint"]["enabled"] else "关",
             "开" if dbg["delay"]["enabled"] else "关"))

    if args.demo:
        def demo_job() -> None:
            time.sleep(0.8)                     # 先把网页放出来，断点才有地方点
            for i in range(args.cases):
                seed = args.seed + i
                name = f"mock-p{args.problem}-seed{seed}.jsonl"
                print(f"[demo {i + 1}/{args.cases}] 生成 {name} ...")
                stats = run_blocking("mock", name, seed=seed, algorithm=cli_algo,
                                     params=cli_params, problem=args.problem)
                if stats:
                    print(f"   清除 {stats['cleared']} 个，"
                          f"平均定位清除时间 {stats['平均定位清除时间']:.1f} s")

        threading.Thread(target=demo_job, daemon=True).start()
    elif args.run:
        if not args.robot_id:
            print("--run 需要 --robot-id")
            return 2
        print("正在接模拟器跑一局（网页会在有数据后自动刷新）...")
        start_run("live", robot_id=args.robot_id, url=args.url, log_dir=args.log_dir,
                  algorithm=cli_algo, params=cli_params)

    if not list_traces():
        print("trace 目录为空，自动生成一个离线案例 ...")
        start_run("mock", seed=1, algorithm=cli_algo, params=cli_params,
                  problem=args.problem)

    try:
        server = Server(("127.0.0.1", args.port), Handler)
    except OSError as exc:
        print(f"端口 {args.port} 绑定失败：{exc}")
        print(f"可能已有 webui 在运行；换端口重试：python webui.py --port {args.port + 1}")
        return 3
    url = f"http://127.0.0.1:{args.port}/"
    print(f"可视化已启动：{url}")
    print(f"trace 目录：{STATE['trace_dir'].resolve()}")
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

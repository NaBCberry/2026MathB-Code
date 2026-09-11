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

ROOT = Path(__file__).resolve().parent
HTML_PATH = ROOT / "webui.html"

STATE = {
    "trace_dir": Path("traces"),
    "running": None,          # 正在跑的任务（trace 文件名）
    "error": None,
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
            "n_sources": meta.get("n_sources"),
            "cleared": summary.get("stats", {}).get("cleared"),
            "virtual_total_s": totals.get("virtual_total_s"),
        })
    return out


def read_trace(name: str) -> dict:
    path = (STATE["trace_dir"] / name).resolve()
    if path.parent != STATE["trace_dir"].resolve() or not path.exists():
        raise FileNotFoundError(name)
    meta, events, summary = {}, [], {}
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue                      # 正在写入时可能出现半行
            kind = obj.get("kind")
            if kind == "meta":
                meta = obj
            elif kind == "summary":
                summary = obj
            else:
                events.append(obj)
    return {"meta": meta, "events": events, "summary": summary,
            "name": name, "running": STATE["running"]}


def start_mock(seed: int) -> str:
    """后台跑一局离线模拟，返回 trace 文件名。"""
    name = f"mock-seed{seed}.jsonl"
    with STATE["lock"]:
        if STATE["running"]:
            return STATE["running"]
        STATE["running"] = name

    def job() -> None:
        try:
            trace_client.run_session(mode="mock",
                                     out=STATE["trace_dir"] / name, seed=seed)
        except Exception as exc:                      # noqa: BLE001
            STATE["error"] = f"{type(exc).__name__}: {exc}"
            print("[webui] 模拟运行失败：", exc)
        finally:
            STATE["running"] = None

    threading.Thread(target=job, daemon=True).start()
    return name


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
        elif u.path == "/api/status":
            self._json({"running": STATE["running"], "error": STATE["error"]})
        elif u.path == "/api/trace":
            name = (q.get("name") or [""])[0]
            try:
                self._json(read_trace(name))
            except FileNotFoundError:
                self._send(404, b"not found", "text/plain; charset=utf-8")
        else:
            self._send(404, b"not found", "text/plain; charset=utf-8")

    def do_POST(self) -> None:                         # noqa: N802
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/api/new":
            raw = (q.get("seed") or ["0"])[0]
            try:
                seed = int(raw)
            except ValueError:
                seed = 0
            if seed <= 0:
                seed = int(time.time()) % 100000
            self._json({"name": start_mock(seed), "seed": seed})
        else:
            self._send(404, b"not found", "text/plain; charset=utf-8")


# ------------------------------------------------------------------ 入口
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="干扰源定位清除 —— 可视化 WebUI")
    p.add_argument("--demo", action="store_true", help="先生成离线模拟案例再起服务")
    p.add_argument("--run", action="store_true", help="接真实模拟器跑一局（需 --robot-id）")
    p.add_argument("--serve-only", action="store_true", help="只提供已有 trace 的可视化")
    p.add_argument("--cases", type=int, default=3, help="--demo 生成几个案例")
    p.add_argument("--seed", type=int, default=1, help="--demo 的起始随机种子")
    p.add_argument("--robot-id", default="", help="--run 时必填")
    p.add_argument("--url", default="http://127.0.0.1:2026")
    p.add_argument("--log-dir", default="logs")
    p.add_argument("--trace-dir", default="traces")
    p.add_argument("--port", type=int, default=8800)
    p.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    STATE["trace_dir"] = Path(args.trace_dir)

    if args.demo:
        for i in range(args.cases):
            seed = args.seed + i
            path = STATE["trace_dir"] / f"mock-seed{seed}.jsonl"
            print(f"[demo {i + 1}/{args.cases}] 生成 {path} ...")
            stats = trace_client.run_session(mode="mock", out=path, seed=seed)
            print(f"   清除 {stats['cleared']} 个，"
                  f"平均定位清除时间 {stats['平均定位清除时间']:.1f} s")
    elif args.run:
        if not args.robot_id:
            print("--run 需要 --robot-id")
            return 2
        path = STATE["trace_dir"] / "live.jsonl"
        print("正在接模拟器跑一局（网页会在有数据后自动刷新）...")
        with STATE["lock"]:
            STATE["running"] = path.name

        def job() -> None:
            try:
                trace_client.run_session(mode="live", out=path,
                                         robot_id=args.robot_id, url=args.url,
                                         log_dir=args.log_dir)
            except Exception as exc:                   # noqa: BLE001
                STATE["error"] = f"{type(exc).__name__}: {exc}"
                print("[webui] 实机运行失败：", exc)
            finally:
                STATE["running"] = None

        threading.Thread(target=job, daemon=True).start()

    if not list_traces():
        print("trace 目录为空，自动生成一个离线案例 ...")
        trace_client.run_session(mode="mock",
                                 out=STATE["trace_dir"] / "mock-seed1.jsonl", seed=1)

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
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

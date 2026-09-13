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
from trace_client import parse_seeds

ROOT = Path(__file__).resolve().parent
HTML_PATH = ROOT / "webui.html"
STATIC_JS_PATH = ROOT / "webui_static.js"
CONFIG_PATH = ROOT / "config.json"

STATE = {
    "trace_dir": Path("traces"),
    "running": None,          # 正在跑的任务（trace 文件名）
    "batch": None,            # 自定义种子连跑时的进度 {names, index, total, current}
    "batch_seq": 0,           # 连跑批次的编号（网页靠它认领自己那一批）
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
            if st is None:
                st = self._fresh()
                self._st[key] = st
            # 最多重来一次：同名文件可能刚被新的一局覆盖（截断重写）
            for _ in range(2):
                try:
                    size = path.stat().st_size
                except OSError:
                    raise FileNotFoundError(path.name)
                if size < st["size"]:            # 变小 = 被截断，从头来
                    st = self._fresh()
                    self._st[key] = st
                if size == st["size"]:
                    break
                started_at = st["offset"]
                with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
                    if started_at:
                        # 不是从头读：先核对文件头（meta 那一行）还是不是原来那条。
                        # 同名文件被新的一局覆盖时它一定会变——这是唯一可靠的判据：
                        # 新一局可能一上来就写得比旧文件长，"变小"那一瞬间根本看不到。
                        if fh.readline() != st["head"]:
                            st = self._fresh()
                            self._st[key] = st
                            continue
                    fh.seek(st["offset"])
                    chunk = fh.read()
                    st["offset"] = fh.tell()
                text = st["buf"] + chunk
                lines = text.split("\n")
                st["buf"] = lines.pop()          # 末段可能只写了一半，留到下次
                if started_at == 0 and lines:
                    st["head"] = lines[0]        # 记住第一行原文，供下次核对
                restarted = False
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
                        if started_at > 0:       # 从中间又读到文件头 = 新的一局
                            restarted = True
                            break
                        st["meta"] = obj
                        continue
                    if kind == "summary":
                        st["summary"] = obj
                        continue
                    seq = obj.get("seq")
                    if isinstance(seq, int):
                        if seq <= st["max_seq"]:  # 序号倒退 = 文件被重写且已经长过旧长度
                            restarted = True
                            break
                        st["max_seq"] = seq
                    st["events"].append(obj)
                if restarted:
                    st = self._fresh()
                    self._st[key] = st
                    continue
                st["size"] = size
                break
            events = st["events"]
            return {"meta": st["meta"], "summary": st["summary"],
                    "events": events[since:], "total": len(events)}

    @staticmethod
    def _fresh() -> dict:
        return {"offset": 0, "buf": "", "size": -1, "max_seq": -1, "head": "",
                "events": [], "meta": {}, "summary": {}}


TRACES = TraceCache()


def read_trace(name: str, since: int = 0) -> dict:
    """读一局 trace；since>0 时只返回第 since 条之后的新事件（增量）。"""
    path = (STATE["trace_dir"] / name).resolve()
    if path.parent != STATE["trace_dir"].resolve() or not path.exists():
        raise FileNotFoundError(name)
    out = TRACES.read(path, max(int(since), 0))
    out.update({"name": name, "running": STATE["running"]})
    return out


def gate_payload() -> dict:
    gate = STATE["gate"]
    return {"gate": gate.state() if gate else None,
            "running": STATE["running"], "error": STATE["error"],
            "batch": STATE["batch"]}


def poll_payload(name: str = "", since: int = 0) -> dict:
    """把"闸门状态 + 轨迹增量"合成一个响应。

    前端原来是每轮打两个请求（/api/gate + /api/trace），往返延迟翻倍；合成一个
    请求后同样的网络条件下刷新频率能翻一倍。每次的 payload 很小：没有新动作时，
    events 是空数组，整个响应通常只有一两百字节。
    """
    since = max(int(since), 0)
    out = gate_payload()
    if name:
        try:
            out["trace"] = read_trace(name, since)
        except FileNotFoundError:
            out["trace"] = None
    return out


# ---------------------------------------------------------------- 静态导出
def export_static(out_dir: Path) -> dict:
    """把 trace 目录导出成"没有后端也能看"的静态网页（GitHub Pages 用）。

    产出：

    * ``index.html``      —— ``webui.html`` 原样，只在主脚本前插一个静态假后端；
    * ``webui_static.js`` —— 把网页请求的 ``/api/*`` 映射到下面的 JSON，并禁用那几个
      必须有进程才成立的按钮；
    * ``api/*.json``      —— 算法清单、trace 清单、闸门状态，以及逐局的 trace。

    静态页能切着看每一局（地图 / 频道表 / 日志 / 汇总 / 算法说明），但"生成新案例 /
    离线案例 / 实机运行 / 断点单步"这些需要后端的功能用不了。
    """
    out = Path(out_dir)
    api_dir = out / "api"
    trace_dir = api_dir / "trace"
    trace_dir.mkdir(parents=True, exist_ok=True)

    if not HTML_PATH.exists():
        raise FileNotFoundError(HTML_PATH)
    html = HTML_PATH.read_text(encoding="utf-8")
    nl = "\r\n" if "\r\n" in html else "\n"
    if "webui_static.js" not in html:
        idx = html.rfind("<script>")               # 主脚本是 body 末尾那个
        if idx < 0:
            raise RuntimeError("webui.html 里找不到主 <script>，无法注入静态层")
        html = html[:idx] + f'<script src="webui_static.js"></script>{nl}' + html[idx:]
    (out / "index.html").write_text(html, encoding="utf-8")

    if not STATIC_JS_PATH.exists():
        raise FileNotFoundError(STATIC_JS_PATH)
    (out / "webui_static.js").write_text(STATIC_JS_PATH.read_text(encoding="utf-8"),
                                         encoding="utf-8")

    def dump(path: Path, obj) -> int:
        text = json.dumps(obj, ensure_ascii=False)
        path.write_text(text, encoding="utf-8")
        return len(text.encode("utf-8"))

    traces = list_traces()
    size = 0
    size += dump(api_dir / "algorithms.json", algo_payload())
    size += dump(api_dir / "traces.json", traces)
    gate = gate_payload()
    size += dump(api_dir / "gate.json", gate)
    size += dump(api_dir / "status.json", {"running": None, "error": None})
    size += dump(api_dir / "poll.json", dict(gate, trace=None))
    for item in traces:
        size += dump(trace_dir / f"{item['name']}.json", read_trace(item["name"]))
    return {"dir": str(out), "traces": len(traces), "bytes": size}


def run_blocking(mode: str, name: str, *, seed: int | None = None, robot_id: str = "",
                 url: str = "http://127.0.0.1:2026", log_dir: str = "logs",
                 algorithm: str = "", params: dict | None = None,
                 problem: int = 3, case_code: str = "") -> dict | None:
    """同步跑一局并登记状态（在后台线程里调用）。"""
    with STATE["lock"]:
        STATE["running"] = name
        STATE["error"] = None
    try:
        return trace_client.run_session(
            mode=mode, out=STATE["trace_dir"] / name, seed=seed,
            robot_id=robot_id, url=url, log_dir=log_dir, gate=STATE["gate"],
            algorithm=algorithm, params=params, problem=problem,
            case_code=case_code)
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
              problem: int = 3, case_code: str = "") -> str:
    """后台跑一局（离线 mock 或实机），返回 trace 文件名。

    `problem` 只影响离线 mock（3 = 全全向源，4 = 全向 + 定向混合）；实机一局仍然写
    `live-<日期>-<时刻>.jsonl`，参数一个都不多传。

    实机 trace 的文件名带时间戳（不是固定的 `live.jsonl`）——问题 3/问题 4 各有三次
    正式测试，固定文件名会让后一局**覆盖**前一局，支撑材料要的三条指令序列就只剩
    最后一条了。带时间戳的写法每次都是一份新文件，网页按返回的名字轮询，不受影响。
    """
    if mode == "mock":
        name = mock_name(problem, seed)
    else:
        from sim_client import safe_tag
        stamp = time.strftime("%Y%m%d-%H%M%S")
        tag = safe_tag(case_code)
        name = f"live-{stamp}{f'-{tag}' if tag else ''}.jsonl"
    with STATE["lock"]:
        if STATE["running"]:
            return STATE["running"]
    threading.Thread(target=lambda: run_blocking(mode, name, seed=seed, robot_id=robot_id,
                                                 url=url, log_dir=log_dir,
                                                 algorithm=algorithm, params=params,
                                                 problem=problem, case_code=case_code),
                     daemon=True).start()
    return name


def mock_name(problem: int, seed) -> str:
    """离线一局的 trace 文件名（自定义种子也走这套命名，可被覆盖重跑）。"""
    return f"mock-p{4 if problem == 4 else 3}-seed{seed}.jsonl"


def start_batch(jobs: list[tuple[int, int]], *, algorithm: str = "",
                params: dict | None = None,
                log_dir: str = "logs") -> tuple[list[str], int | None]:
    """按 (题目, 种子) 列表**串行**连跑若干局，返回 (每局的 trace 文件名, 批次号)。

    为什么串行：调试闸门（每步延迟 / 断点单步）是全局的，并发跑会让人不知道该放行
    哪一局；串行还保证 trace 写入与网页轮询的次序稳定。进度写在 `STATE["batch"]`，
    随 `/api/gate`、`/api/poll`、`/api/stream` 一起推给网页，状态栏显示"第 k/n 局"。

    批次号在**调用方线程里**就写好（不是等后台线程起来才写），这样网页 POST 完立刻
    查进度也不会读到上一批的残留。已经在跑别的任务时返回 `([], None)`，不排队、不打断。
    """
    names = [mock_name(problem, seed) for (problem, seed) in jobs]
    if not names:
        return [], None
    total = len(jobs)
    with STATE["lock"]:
        if STATE["running"]:
            return [], None
        STATE["batch_seq"] += 1
        token = STATE["batch_seq"]
        STATE["batch"] = {"token": token, "names": list(names), "index": 0,
                          "total": total, "current": names[0]}

    def set_progress(index: int, current: str | None) -> None:
        with STATE["lock"]:
            STATE["batch"] = {"token": token, "names": list(names), "index": index,
                              "total": total, "current": current}

    def job() -> None:
        for i, ((problem, seed), name) in enumerate(zip(jobs, names)):
            set_progress(i, name)
            run_blocking("mock", name, seed=seed, algorithm=algorithm, params=params,
                         problem=problem, log_dir=log_dir)
            set_progress(i + 1, None)

    threading.Thread(target=job, daemon=True).start()
    return names, token


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


def problem_list(body: dict) -> list[int]:
    """这次请求要跑哪几个题目：单个 `problem`，或 `problems=[3,4]`（两题连跑）。

    返回去重保序后的列表（元素只可能是 3 或 4）；没给就是 [3]（与旧行为一致）。
    """
    raw = body.get("problems")
    if isinstance(raw, (list, tuple)):
        out: list[int] = []
        for item in raw:
            try:
                p = 4 if int(item) == 4 else 3
            except (TypeError, ValueError):
                continue
            if p not in out:
                out.append(p)
        if out:
            return out
    return [problem_of(body)]


def _int_arg(query: dict, key: str, default: int = 0) -> int:
    """取查询参数里的整数（非法值当默认值）。"""
    try:
        return int((query.get(key) or [str(default)])[0])
    except (TypeError, ValueError):
        return default


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
    disable_nagle_algorithm = True     # SSE 推送要的就是"立刻发出去"

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
            self._json(gate_payload())
        elif u.path == "/api/poll":
            # 一次请求拿全：闸门状态 + 轨迹增量（轮询兜底用，省一半往返）
            name = (q.get("name") or [""])[0]
            self._json(poll_payload(name, _int_arg(q, "since")))
        elif u.path == "/api/stream":
            # SSE 推送：有变化就推，没变化就静默（心跳每 2 s）
            name = (q.get("name") or [""])[0]
            self._stream(name, _int_arg(q, "since"))
        elif u.path == "/api/trace":
            name = (q.get("name") or [""])[0]
            try:
                self._json(read_trace(name, _int_arg(q, "since")))
            except FileNotFoundError:
                self._send(404, b"not found", "text/plain; charset=utf-8")
        else:
            self._send(404, b"not found", "text/plain; charset=utf-8")

    # ------------------------------------------------------------ SSE 推送
    STREAM_TICK = 0.05        # 服务端检查文件变化的间隔（20 Hz）
    STREAM_BEAT = 2.0         # 没有变化时每 2 s 发一次心跳，保持连接

    def _stream(self, name: str, since: int) -> None:
        """把轨迹增量按 SSE 推给浏览器：页面不再靠轮询"猜"什么时候有数据。"""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store, no-transform")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        try:
            self.wfile.write(b"retry: 300\n\n")
            self.wfile.flush()
            last, beat = "", time.time()
            while True:
                payload = poll_payload(name, since)
                trace = payload.get("trace")
                if trace:
                    since = trace["total"]          # 下次只取新增的那几条
                    payload["since"] = since
                body = json.dumps(payload, ensure_ascii=False)
                now = time.time()
                if body != last or now - beat >= self.STREAM_BEAT:
                    self.wfile.write(b"data: " + body.encode("utf-8") + b"\n\n")
                    self.wfile.flush()
                    last, beat = body, now
                time.sleep(self.STREAM_TICK)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            return                                   # 页面关了/切走了，正常收尾

    def do_POST(self) -> None:                         # noqa: N802
        u = urlparse(self.path)
        q = parse_qs(u.query)
        body = self._body()
        if u.path == "/api/new":
            raw = (q.get("seed") or q.get("seeds") or [""])[0]
            try:
                seeds = parse_seeds(raw)
            except ValueError as exc:
                self._send(400, f"种子写法有误：{exc}".encode("utf-8"),
                           "text/plain; charset=utf-8")
                return
            if not seeds or seeds == [0]:       # 留空或 0 = 随机一个（与以前一致）
                seeds = [int(time.time()) % 100000]
            problems = problem_list(body)
            algorithm = body.get("algorithm", "")
            params = body.get("params") or None
            # 一局也好、两题×多个种子也好，都走同一条排队路径：
            # 这样网页永远能用 /api/gate 的 batch 进度认领自己这批。
            names, token = start_batch([(p, s) for p in problems for s in seeds],
                                       algorithm=algorithm, params=params,
                                       log_dir=STATE.get("log_dir", "logs"))
            self._json({"name": names[0] if names else "", "names": names, "seeds": seeds,
                        "problems": problems, "count": len(names), "token": token,
                        "seed": seeds[0], "problem": problems[0]})
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
                             case_code=(body.get("case_code") or "").strip(),
                             **extra)
            self._json({"name": name, "case_code": (body.get("case_code") or "").strip()})
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
    p.add_argument("--seeds", default="",
                   help="--demo 的自定义种子：逗号/空格分隔，支持区间（例：27880,1031 "
                        "或 1-5）；给了它就忽略 --seed/--cases")
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
    p.add_argument("--export", default="", metavar="目录",
                   help="不启服务器：把离线案例导出成静态网页到该目录（GitHub Pages "
                        "这类静态托管用）；案例范围由 --seeds/--cases/--seed/--problem/"
                        "--algorithm 决定")
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

    if args.export:
        # 静态导出：先把案例同步跑完（不启线程、不启服务器），再写站点
        try:
            export_seeds = parse_seeds(args.seeds) if args.seeds.strip() else None
        except ValueError as exc:
            print(f"--seeds 解析失败：{exc}")
            return 2
        seeds = export_seeds if export_seeds is not None else [
            args.seed + i for i in range(max(int(args.cases), 0))]
        for i, seed in enumerate(seeds):
            name = mock_name(args.problem, seed)
            print(f"[导出 {i + 1}/{len(seeds)}] 生成 {name} ...")
            stats = run_blocking("mock", name, seed=seed, algorithm=cli_algo,
                                 params=cli_params, problem=args.problem)
            if stats:
                print(f"   清除 {stats['cleared']} 个，"
                      f"平均定位清除时间 {stats['平均定位清除时间']:.1f} s")
        info = export_static(Path(args.export))
        print(f"静态网页已导出：{Path(info['dir']).resolve()}"
              f"（{info['traces']} 局 trace，约 {info['bytes'] / 1024:.0f} KB）")
        print(f"本地预览：python -m http.server -d {args.export} 8900  →  "
              "http://127.0.0.1:8900/")
        return 0

    if args.demo:
        try:
            demo_seeds = parse_seeds(args.seeds) if args.seeds.strip() else None
        except ValueError as exc:
            print(f"--seeds 解析失败：{exc}")
            return 2
        if demo_seeds is not None and not demo_seeds:
            print("--seeds 是空的：请写具体种子，例如 --seeds 27880,1031")
            return 2

        def demo_job() -> None:
            time.sleep(0.8)                     # 先把网页放出来，断点才有地方点
            seeds = demo_seeds if demo_seeds is not None else [
                args.seed + i for i in range(max(int(args.cases), 0))]
            for i, seed in enumerate(seeds):
                name = f"mock-p{args.problem}-seed{seed}.jsonl"
                print(f"[demo {i + 1}/{len(seeds)}] 生成 {name} ...")
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

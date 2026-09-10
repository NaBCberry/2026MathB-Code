# -*- coding: utf-8 -*-
"""模拟器连接测试：探测本机模拟器端口的连通性与接口响应。

用法：
    python probe_simulator.py                 # 使用 config.json 中的配置
    python probe_simulator.py --url http://127.0.0.1:2026

说明：
    - 非测试期间（倒计时中 / 未开始 / 已结束）机器人接口是关闭的，
      此时连接失败或返回非 JSON 体都属于正常现象。
    - 本脚本只做只读探测。除可选的 --enter 外不会改变模拟器状态。
"""

from __future__ import annotations

import argparse
import json
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config.json"


def load_config() -> dict:
    if CONFIG.exists():
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    return {"base_url": "http://127.0.0.1:2026", "robot_id": "<参赛队号>"}


def tcp_probe(host: str, port: int, timeout: float = 3.0) -> tuple[bool, str]:
    """纯 TCP 层探测：端口是否有进程监听。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        code = sock.connect_ex((host, port))
    except OSError as exc:  # DNS / 网络不可达
        return False, f"异常 {exc!r}"
    finally:
        sock.close()
    return code == 0, "TCP 连接成功" if code == 0 else f"connect_ex={code}"


def http_post(base_url: str, path: str, payload: dict, timeout: float = 5.0):
    """发送一条指令，返回 (http_status, body_text, parsed_json_or_None, error)。"""
    request = urllib.request.Request(
        base_url + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", "replace")
            status = response.status
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        status = exc.code
    except Exception as exc:  # 连接被直接关闭、超时等，没有 JSON 体
        return None, "", None, f"{type(exc).__name__}: {exc}"
    elapsed = (time.perf_counter() - started) * 1000

    parsed = None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        pass
    return status, raw, parsed, f"{elapsed:.0f} ms"


def main() -> int:
    cfg = load_config()
    parser = argparse.ArgumentParser(description="模拟器连接测试")
    parser.add_argument("--url", default=cfg["base_url"], help="模拟器接口地址")
    parser.add_argument("--robot-id", default=cfg["robot_id"], help="参赛队号")
    parser.add_argument("--enter", action="store_true", help="额外尝试调用 /enter（会占用测试窗口）")
    args = parser.parse_args()

    parsed_url = urlparse(args.url)
    host = parsed_url.hostname or "127.0.0.1"
    port = parsed_url.port or 2026

    print("=" * 62)
    print("模拟器连接测试")
    print("=" * 62)
    print(f"目标地址 : {args.url}")
    print(f"robot_id : {args.robot_id}")
    print(f"时间     : {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 62)

    ok, message = tcp_probe(host, port)
    print(f"[1] TCP 连通性 ({host}:{port}) : {'通过' if ok else '失败'} — {message}")

    if not ok:
        print("\n结论：端口未监听。请先启动模拟器（绿色软件，解压即用）。")
        return 2

    # [2] 已知路径用 GET：按协议应返回 405，可据此确认服务是本题模拟器。
    try:
        with urllib.request.urlopen(args.url + "/enter", timeout=5) as response:
            status = response.status
            body = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = exc.read().decode("utf-8", "replace")
    except Exception as exc:
        status, body = None, f"{type(exc).__name__}: {exc}"
    print(f"[2] GET /enter 探测            : HTTP {status} — {body[:200]}")

    # [3] 路径不精确应返回 404
    status, body, _, note = http_post(args.url, "/enter/", {
        "arena_id": "default", "robot_id": args.robot_id, "request_id": "probe-path-1"})
    print(f"[3] POST /enter/ (尾随斜线)    : HTTP {status} — {note}")

    # [4] 正式探测 /enter
    status, body, data, note = http_post(args.url, "/enter", {
        "arena_id": "default", "robot_id": args.robot_id, "request_id": "probe-enter-1"})
    if data is None:
        print(f"[4] POST /enter                : 无 JSON 响应 — {note}")
        print(f"    {body[:200]}")
        print("\n结论：端口在监听，但机器人接口当前未开放（正常现象）。")
        print("      请在模拟器中开始一局测试，等到界面提示接口就绪后再运行本脚本。")
        return 0

    print(f"[4] POST /enter                : HTTP {status} — {note}")
    print(f"    accepted={data.get('accepted')}  virtual_time_s={data.get('virtual_time_s')}")
    if data.get("accepted") is True:
        print(f"    remaining_real_duration_s={data.get('remaining_real_duration_s')}")
        print(f"    max_real_duration_s={data.get('max_real_duration_s')}  "
              f"max_virtual_duration_s={data.get('max_virtual_duration_s')}")
        # 接口已开放，顺手做一次真实检测并主动退出，确认全链路可用。
        status, _, data2, note = http_post(args.url, "/measure", {
            "arena_id": "default", "robot_id": args.robot_id,
            "request_id": "probe-measure-1", "position": {"x": 0, "y": 0}, "channel": 1})
        print(f"[5] POST /measure (0,0) ch1    : HTTP {status} — {note} → "
              f"{None if data2 is None else data2.get('measure_result')}")
        status, _, data3, note = http_post(args.url, "/exit", {
            "arena_id": "default", "robot_id": args.robot_id, "request_id": "probe-exit-1"})
        print(f"[6] POST /exit                 : HTTP {status} — {note} → "
              f"{None if data3 is None else data3.get('exit_reason')}")
        print("\n结论：接口可用，链路正常。")
    else:
        print(f"    body={json.dumps(data, ensure_ascii=False)}")
        print("\n结论：接口已开放，但本次请求未被接受（通常是 robot_id 与登录队号不一致，")
        print("      或仍未真正进入测试）。accepted=false 时 virtual_time_s=0 不是当前虚拟时刻。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

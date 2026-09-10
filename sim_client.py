# -*- coding: utf-8 -*-
"""无线电干扰源环境模拟器 —— 机器狗端通信客户端（不含任何搜索策略）。

设计目标
--------
1. 严格串行：同一时刻只允许一个未完成动作（协议要求，否则 HTTP 409）。
2. 幂等重试：网络异常时复用原 payload 与原 request_id 重发，绝不生成新 id。
3. 双重校验：同时检查 HTTP 状态码与业务字段 accepted。
4. 全程留痕：每条指令与响应写入日志（模拟器不记录机器狗程序的行为）。
5. 只用标准库：无第三方依赖，离线可跑。

协议要点（来自《模拟器通信接口说明及编程指南》）
------------------------------------------------
- 只有 /measure 与 /clear 会推进虚拟时钟；/enter、/exit 不推进。
- accepted=false 时 virtual_time_s 恒为 0，不代表当前虚拟时刻。
- /clear 的 channel 不会切换测向机当前频道。
- 只有成功的 /measure 才会把测向机当前频道更新为本次 channel。
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------
# 题目给定常量
# --------------------------------------------------------------------------
MOVE_SPEED_MPS = 5.0          # 机器狗移动速度，直线，m/s
MEASURE_ACTION_S = 5.0        # 一次检测动作耗时
CHANNEL_SWITCH_S = 1.0        # 任意两频道间切换耗时
CLEAR_MISS_ACTION_S = 3.0     # 精确定位未发现目标
CLEAR_HIT_ACTION_S = 5.0      # 精确定位 + 激光清除
NEAR_THRESHOLD_M = 5.0        # 距离 ≤5m 且覆盖内 → measure_result="near"
CLEAR_RADIUS_M = 20.0         # 清除成功半径
ARENA_RADIUS_M = 1800.0       # 目标区域半径
MAX_COORD_ABS = 2_000_000.0   # 坐标分量绝对值上限
MAX_BODY_BYTES = 65536        # 请求体上限

CHANNELS = tuple(range(1, 21))          # 频道 1..20
SIGNAL_RESULTS = ("direction", "near", "no_signal")
CLEAR_RESULTS = ("success", "no_target_in_range")


# --------------------------------------------------------------------------
# 异常
# --------------------------------------------------------------------------
class SimulatorError(RuntimeError):
    """模拟器返回了业务失败（HTTP 非 200 或 accepted=false）。"""

    def __init__(self, message: str, *, http_status: int | None = None,
                 payload: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.http_status = http_status
        self.payload = payload or {}


class TransportError(RuntimeError):
    """连接被关闭 / 超时 / 无 JSON 体，属于“连不上”这一类，可原样重试。"""


# --------------------------------------------------------------------------
# 响应数据类
# --------------------------------------------------------------------------
@dataclass
class ActionResponse:
    """一条被接受（accepted=true）的动作响应。"""

    path: str
    http_status: int
    accepted: bool
    virtual_time_s: float
    real_timestamp_ms: float
    raw: dict[str, Any] = field(default_factory=dict)

    # /measure
    @property
    def measure_result(self) -> str | None:
        return self.raw.get("measure_result")

    @property
    def svd_deg(self) -> float | None:
        """示向度。仅 measure_result == "direction" 时有效，且含 ±1° 误差。"""
        if self.measure_result == "direction":
            return self.raw.get("svd_deg")
        return None

    # /clear
    @property
    def clear_result(self) -> str | None:
        return self.raw.get("clear_result")

    # /exit
    @property
    def exit_reason(self) -> str | None:
        return self.raw.get("exit_reason")


@dataclass
class EnterResponse(ActionResponse):
    max_virtual_duration_s: float = 360_000.0
    max_real_duration_s: float = 1200.0
    remaining_real_duration_s: float = 1200.0


# --------------------------------------------------------------------------
# 客户端
# --------------------------------------------------------------------------
class SimulatorClient:
    """机器人接口客户端。

    用法::

        with SimulatorClient("http://127.0.0.1:2026", "T2026xxxxx") as sim:
            info = sim.enter()
            print(info.remaining_real_duration_s)
            r = sim.measure(0, 0, 1)
            ...
            sim.exit()
    """

    def __init__(
        self,
        base_url: str,
        robot_id: str,
        *,
        timeout: float = 5.0,
        retries: int = 3,
        retry_backoff_s: float = 0.5,
        log_dir: str | Path | None = None,
        verbose: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.robot_id = robot_id
        self.timeout = timeout
        self.retries = retries
        self.retry_backoff_s = retry_backoff_s
        self.verbose = verbose

        self.channel: int = 1                # 测向机当前频道，/enter 后为 1
        self.position: tuple[float, float] = (0.0, 0.0)
        self.virtual_time_s: float = 0.0     # 最近一次 accepted=true 的虚拟时刻
        self.remaining_real_s: float = 1200.0
        self._entered = False
        self._exited = False
        self._counter = 0

        # 日志：机器狗程序必须自行记录行为序列
        self.log_path: Path | None = None
        self._log_fp = None
        if log_dir is not None:
            d = Path(log_dir)
            d.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime("%Y%m%d-%H%M%S")
            self.log_path = d / f"robot-{stamp}.jsonl"
            self._log_fp = self.log_path.open("w", encoding="utf-8")

    # ---------------------------------------------------------------- 生命周期
    def __enter__(self) -> "SimulatorClient":
        return self

    def __exit__(self, *exc: object) -> None:
        if self._entered and not self._exited:
            try:
                self.exit()
            except Exception:  # 退出失败不应掩盖原异常
                pass
        self.close()

    def close(self) -> None:
        if self._log_fp is not None:
            self._log_fp.close()
            self._log_fp = None

    # ---------------------------------------------------------------- 内部工具
    def _next_request_id(self, tag: str) -> str:
        self._counter += 1
        return f"{tag}-{self._counter}"

    def _base(self, request_id: str) -> dict[str, Any]:
        return {
            "arena_id": "default",
            "robot_id": self.robot_id,
            "request_id": request_id,
        }

    def _log(self, record: dict[str, Any]) -> None:
        if self._log_fp is not None:
            self._log_fp.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._log_fp.flush()
        if self.verbose:
            print(f"[{record.get('event', '?')}] "
                  f"{ {k: v for k, v in record.items() if k != 'event'} }")

    def _post_raw(self, path: str, payload: dict[str, Any]) -> tuple[int, str]:
        """发送一次 HTTP 请求，返回 (status, 原始响应体)。不做任何重试。"""
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if len(body) > MAX_BODY_BYTES:
            raise ValueError(f"请求体超过 {MAX_BODY_BYTES} 字节：{len(body)}")
        request = urllib.request.Request(
            self.base_url + path,
            data=body,
            headers={"Content-Type": "application/json"},  # 不带 charset
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                return resp.status, resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8", "replace")
        except Exception as exc:
            # 倒计时中 / 接口未开放 / 测试已结束 → 连接被直接关闭，无 JSON 体
            raise TransportError(f"{type(exc).__name__}: {exc}") from exc

    def _call(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """发送动作并在网络层异常时按协议重试（复用同一 payload / request_id）。"""
        request_id = payload["request_id"]
        last_error: Exception | None = None

        for attempt in range(1, self.retries + 1):
            started = time.perf_counter()
            try:
                status, text = self._post_raw(path, payload)
            except TransportError as exc:
                last_error = exc
                self._log({"event": "transport_error", "path": path,
                           "request_id": request_id, "attempt": attempt,
                           "error": str(exc)})
                if attempt < self.retries:
                    self._sleep(self.retry_backoff_s * attempt)
                    continue           # 原样重发，request_id 不变
                raise

            elapsed_ms = (time.perf_counter() - started) * 1000
            try:
                data = json.loads(text)
            except json.JSONDecodeError as exc:
                last_error = TransportError(f"响应不是 JSON：{text[:200]!r}")
                self._log({"event": "bad_json", "path": path, "http_status": status,
                           "request_id": request_id, "attempt": attempt,
                           "body_head": text[:200]})
                if attempt < self.retries:
                    self._sleep(self.retry_backoff_s * attempt)
                    continue
                raise last_error from exc

            self._log({"event": "response", "path": path, "http_status": status,
                       "request_id": request_id, "attempt": attempt,
                       "elapsed_ms": round(elapsed_ms, 1),
                       "accepted": data.get("accepted"),
                       "virtual_time_s": data.get("virtual_time_s"),
                       "payload": data})

            # 400 / 404 / 405 / 409 / 413 / 415 / 429 / 500 都属于程序缺陷或状态错误，
            # 重试无意义，直接抛出。
            if status != 200:
                raise SimulatorError(f"{path} 返回 HTTP {status}: {text[:300]}",
                                     http_status=status, payload=data)

            if data.get("accepted") is not True:
                # 结构合法但未执行：robot_id 不匹配 / 未 /enter / 有未知字段……
                raise SimulatorError(
                    f"{path} accepted=false: {json.dumps(data, ensure_ascii=False)}",
                    http_status=status, payload=data)

            self.virtual_time_s = float(data.get("virtual_time_s", self.virtual_time_s))
            return data

        raise last_error if last_error else RuntimeError("unreachable")

    @staticmethod
    def _sleep(seconds: float) -> None:
        time.sleep(min(seconds, 1.0))

    def _move_cost(self, x: float, y: float) -> float:
        dx, dy = x - self.position[0], y - self.position[1]
        return (dx * dx + dy * dy) ** 0.5 / MOVE_SPEED_MPS

    # ---------------------------------------------------------------- 4 条指令
    def enter(self) -> EnterResponse:
        """POST /enter —— 进入目标区域并开始计时。不推进虚拟时钟。"""
        payload = self._base(self._next_request_id("enter"))
        data = self._call("/enter", payload)
        self._entered = True
        self.channel = 1
        self.position = (0.0, 0.0)
        self.remaining_real_s = float(data.get("remaining_real_duration_s", 1200.0))
        return EnterResponse(
            path="/enter", http_status=200, accepted=True,
            virtual_time_s=float(data.get("virtual_time_s", 0.0)),
            real_timestamp_ms=float(data.get("real_timestamp_ms", 0.0)),
            raw=data,
            max_virtual_duration_s=float(data.get("max_virtual_duration_s", 360000.0)),
            max_real_duration_s=float(data.get("max_real_duration_s", 1200.0)),
            remaining_real_duration_s=self.remaining_real_s,
        )

    def measure(self, x: float, y: float, channel: int) -> ActionResponse:
        """POST /measure —— 移动到 (x, y) 并对 channel 检测。

        虚拟耗时 = 移动耗时 + 频道切换耗时 + 5 秒检测动作耗时。
        成功后测向机当前频道更新为 channel。
        """
        if not 1 <= int(channel) <= 20:
            raise ValueError(f"channel 必须为 1..20 的整数，收到 {channel}")
        request_id = self._next_request_id("measure")
        payload = self._base(request_id)
        payload["position"] = {"x": float(x), "y": float(y)}
        payload["channel"] = int(channel)

        predicted = (self._move_cost(x, y)
                     + (CHANNEL_SWITCH_S if int(channel) != self.channel else 0.0)
                     + MEASURE_ACTION_S)
        data = self._call("/measure", payload)

        self.position = (float(x), float(y))
        self.channel = int(channel)
        return ActionResponse(
            path="/measure", http_status=200, accepted=True,
            virtual_time_s=float(data.get("virtual_time_s", 0.0)),
            real_timestamp_ms=float(data.get("real_timestamp_ms", 0.0)),
            raw={**data, "predicted_cost_s": round(predicted, 6)},
        )

    def clear(self, x: float, y: float, channel: int) -> ActionResponse:
        """POST /clear —— 在 (x, y) 精确定位并清除 channel 干扰源。

        虚拟耗时 = 移动耗时 +（未发现 3 秒 / 成功 5 秒）。
        注意：channel 仅表示目标频道，不切换测向机频道，也不产生切换耗时。
        """
        if not 1 <= int(channel) <= 20:
            raise ValueError(f"channel 必须为 1..20 的整数，收到 {channel}")
        request_id = self._next_request_id("clear")
        payload = self._base(request_id)
        payload["position"] = {"x": float(x), "y": float(y)}
        payload["channel"] = int(channel)

        data = self._call("/clear", payload)
        self.position = (float(x), float(y))
        return ActionResponse(
            path="/clear", http_status=200, accepted=True,
            virtual_time_s=float(data.get("virtual_time_s", 0.0)),
            real_timestamp_ms=float(data.get("real_timestamp_ms", 0.0)),
            raw=data,
        )

    def exit(self) -> ActionResponse:
        """POST /exit —— 主动结束本局测试。不推进虚拟时钟。"""
        payload = self._base(self._next_request_id("exit"))
        data = self._call("/exit", payload)
        self._exited = True
        return ActionResponse(
            path="/exit", http_status=200, accepted=True,
            virtual_time_s=float(data.get("virtual_time_s", 0.0)),
            real_timestamp_ms=float(data.get("real_timestamp_ms", 0.0)),
            raw=data,
        )

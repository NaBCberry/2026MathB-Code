# -*- coding: utf-8 -*-
"""无线电干扰源环境模拟器 —— 机器狗端通信客户端（薄封装，不含任何搜索策略）。

只负责三件容易做错的事
----------------------
1. 串行发送：同一时刻只有一个未完成动作（协议要求，否则 HTTP 409）。
2. 幂等重试：仅对"连不上 / 响应不是 JSON"重试，且复用原 payload 与原 request_id。
3. 双重校验：同时检查 HTTP 状态码与 accepted；每条指令与响应写入 JSONL 日志。

协议要点
--------
- /enter、/exit 不推进虚拟时钟；/measure、/clear 推进。
- accepted=false 时 virtual_time_s 恒为 0，不代表当前虚拟时刻。
- /clear 的 channel 不切换测向机频道；只有成功的 /measure 会更新它。
- 只接受 arena_id / robot_id / request_id / position / channel 五个字段，
  多传字段会返回 HTTP 200 + accepted=false。
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE_URL = "http://127.0.0.1:2026"


class SimulatorClient:
    """4 条指令 /enter、/measure、/clear、/exit 的薄封装，返回模拟器的完整响应 dict。

    用法::

        with SimulatorClient("T2026xxxxxx", log_dir="logs") as sim:
            print(sim.enter()["remaining_real_duration_s"])
            r = sim.measure(0, 0, 1)
            if r["measure_result"] == "direction":
                print(r["svd_deg"])

    ``robot_id`` 是必填参数，必须与模拟器当前登录的参赛队号逐字节一致。
    它不写入任何配置文件，只从命令行/调用方传入，避免被提交进版本库。
    """

    def __init__(self, robot_id: str, base_url: str = BASE_URL, *,
                timeout: float = 5.0, retries: int = 3,
                log_dir: str | Path | None = None, verbose: bool = True) -> None:
        self.base_url = base_url.rstrip("/")
        self.robot_id = robot_id
        self.timeout = timeout
        self.retries = retries
        self.verbose = verbose
        self.log_path: Path | None = None
        self._seq = 0
        self._log = None
        if log_dir is not None:
            d = Path(log_dir)
            d.mkdir(parents=True, exist_ok=True)
            self.log_path = d / f"robot-{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
            self._log = self.log_path.open("w", encoding="utf-8")

    # ---------------------------------------------------------------- 生命周期
    def __enter__(self) -> "SimulatorClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        try:                        # 异常退出时补一次 /exit，别白烧一次正式测试机会
            self.exit()
        except Exception:
            pass
        self.close()

    def close(self) -> None:
        if self._log is not None:
            self._log.close()
            self._log = None

    # ---------------------------------------------------------------- 内部
    def _record(self, record: dict) -> None:
        if self._log is not None:
            self._log.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._log.flush()
        if self.verbose:
            print(record)

    def _post(self, path: str, payload: dict) -> tuple[int, str]:
        """一次 POST，返回 (status, body)。不重试。"""
        request = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.status, response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:   # 400/404/409/413/415/429/500 都带 JSON 体
            return exc.code, exc.read().decode("utf-8", "replace")

    def _call(self, path: str, payload: dict) -> dict:
        """发送动作。仅在"连不上 / 响应不是 JSON"时原样重发（request_id 不变）。"""
        for attempt in range(1, self.retries + 1):
            try:
                status, text = self._post(path, payload)
                data = json.loads(text)
            except (OSError, ValueError) as exc:
                # 倒计时中 / 接口未开放 / 测试已结束 → 连接被直接关闭，没有 JSON 体
                if attempt == self.retries:
                    raise
                self._record({"event": "retry", "path": path,
                              "request_id": payload["request_id"],
                              "attempt": attempt, "error": repr(exc)})
                time.sleep(0.3 * attempt)
                continue

            self._record({"event": "response", "path": path, "http_status": status,
                          "request_id": payload["request_id"], "response": data})
            if status != 200:
                raise RuntimeError(f"{path} 返回 HTTP {status}：{text[:300]}")
            if data.get("accepted") is not True:
                raise RuntimeError(f"{path} accepted=false：{text[:300]}")
            return data
        raise AssertionError("unreachable")

    def _payload(self, tag: str, **extra: object) -> dict:
        self._seq += 1
        return {"arena_id": "default", "robot_id": self.robot_id,
                "request_id": f"{tag}-{self._seq}", **extra}

    # ---------------------------------------------------------------- 4 条指令
    def enter(self) -> dict:
        """进入目标区域。不推进虚拟时钟；响应的 remaining_real_duration_s 是本局现实时间预算。"""
        return self._call("/enter", self._payload("enter"))

    def measure(self, x: float, y: float, channel: int) -> dict:
        """到 (x, y) 检测 channel。返回 measure_result，direction 时附 svd_deg。"""
        return self._call("/measure", self._payload(
            "measure", position={"x": x, "y": y}, channel=channel))

    def clear(self, x: float, y: float, channel: int) -> dict:
        """到 (x, y) 清除 channel 的干扰源。返回 clear_result。"""
        return self._call("/clear", self._payload(
            "clear", position={"x": x, "y": y}, channel=channel))

    def exit(self) -> dict:
        """主动结束本局测试。不推进虚拟时钟。"""
        return self._call("/exit", self._payload("exit"))

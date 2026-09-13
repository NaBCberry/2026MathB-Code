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

日志字段（"机器狗程序应自行记录指令序列、响应信息"这一条靠它）
--------------------------------------------------------
第一行是 meta；之后每个动作一行，**请求与响应一起记**：:

    {"event":"response","ts":1757...,"path":"/measure","http_status":200,
     "request_id":"measure-2",
     "request":{"arena_id":"default","robot_id":"...","request_id":"measure-2",
                "position":{"x":300.0,"y":400.0},"channel":1},
     "response":{"accepted":true,"real_timestamp_ms":...,"virtual_time_s":5.0,
                 "measure_result":"direction","svd_deg":123.4}}

文件名：``robot-<日期>-<时刻>[-<案例编码>].jsonl``（编码里有非法字符会被清掉；
没填编码就退回纯时间戳），例如
``logs/robot-20260913-164042-APGZ-S2EA-QYAZ-QPMR.jsonl``。

* `ts` 是本机时间戳（epoch 秒），`response.real_timestamp_ms` 是模拟器时间戳；
  「程序运行时间」= 末条 `real_timestamp_ms` − 首条 `/enter` 的 `real_timestamp_ms`；
* `request` 里的位置与频道**只有请求里有**（响应不回显），所以必须自己留；
* 案例编码接口不返回，用 `case_code=` 登记或测试后从模拟器日志列表手抄。
  一局跑完直接算表 1 数字：``python tools/summarize_run.py logs/robot-*.jsonl``。
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE_URL = "http://127.0.0.1:2026"


def safe_tag(text: str, maxlen: int = 40) -> str:
    """把案例编码变成能安全放进文件名的片段（去掉 Windows 非法字符与空格）。

    例：``APGZ-S2EA-QYAZ-QPMR`` → ``APGZ-S2EA-QYAZ-QPMR``；
    ``问题 4 / 测试1`` → ``问题4测试1``。空串或全是非法字符时返回 ``""``。
    """
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "", text or "")[:maxlen]


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
                enter_retries: int = 12,
                log_dir: str | Path | None = None, verbose: bool = True,
                case_code: str = "", extra_meta: dict | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.robot_id = robot_id
        self.timeout = timeout
        self.retries = retries
        # /enter 单独给一个更长的重试预算：正式测试里"手快点早了一两秒"（5 秒倒计时
        # 还没走完、接口没开）会让整局直接失败，而这一局是要烧掉一次正式机会的。
        # 12 次、退避封顶 1.5 s ⇒ 约 15 s 的容错窗口，足够覆盖倒计时。
        self.enter_retries = int(enter_retries)
        self.verbose = verbose
        self.case_code = case_code or ""
        self.extra_meta = dict(extra_meta or {})
        self.log_path: Path | None = None
        self._seq = 0
        self._log = None
        if log_dir is not None:
            d = Path(log_dir)
            d.mkdir(parents=True, exist_ok=True)
            # 文件名带上案例编码（有的话）：正式测试导出的一堆日志里能一眼对上
            # 论文表 1 的那一列，不用再靠时间戳猜。没有编码就退回纯时间戳。
            stamp = time.strftime("%Y%m%d-%H%M%S")
            tag = safe_tag(self.case_code)
            self.log_path = d / f"robot-{stamp}{f'-{tag}' if tag else ''}.jsonl"
            self._log = self.log_path.open("w", encoding="utf-8")
            # 第一行 meta：固定队号 / 接口 / 案例编码 / 本机起始时间。
            # 案例编码只出现在模拟器界面上（接口不返回），先写占位，
            # 事后就靠这一行把表 1 的那一列和日志文件对上。
            self._record({
                "event": "meta",
                "robot_id": self.robot_id,
                "base_url": self.base_url,
                "case_code": self.case_code,
                "started_local": time.strftime("%Y-%m-%d %H:%M:%S"),
                "started_epoch": time.time(),
                "log_path": str(self.log_path),
                **self.extra_meta,
            })

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
        n_try = self.enter_retries if path == "/enter" else self.retries
        for attempt in range(1, n_try + 1):
            try:
                status, text = self._post(path, payload)
                data = json.loads(text)
            except (OSError, ValueError) as exc:
                # 倒计时中 / 接口未开放 / 测试已结束 → 连接被直接关闭，没有 JSON 体
                if attempt == n_try:
                    raise
                self._record({"event": "retry", "path": path,
                              "request_id": payload["request_id"],
                              "request": payload, "attempt": attempt,
                              "ts": time.time(), "error": repr(exc)})
                time.sleep(min(0.3 * attempt, 1.5))
                continue

            # 请求与响应一起落盘：光有响应还原不出"在哪儿测的、测的哪个频道"。
            self._record({"event": "response", "ts": time.time(), "path": path,
                          "http_status": status,
                          "request_id": payload["request_id"],
                          "request": payload, "response": data})
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

# -*- coding: utf-8 -*-
"""机器狗搜索 / 定位 / 清除策略（骨架）。

用法：
    python robot.py --robot-id <参赛队号>
    python robot.py --robot-id <参赛队号> --url http://127.0.0.1:2026

参赛队号只从命令行传入，不写入任何文件。
"""

from __future__ import annotations

import argparse

from sim_client import BASE_URL, SimulatorClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="干扰源自动定位与清除")
    parser.add_argument("--robot-id", required=True,
                        help="参赛队号（须与模拟器登录队号逐字节一致）")
    parser.add_argument("--url", default=BASE_URL, help="模拟器接口地址")
    parser.add_argument("--log-dir", default="logs", help="行为日志目录")
    return parser.parse_args()


def run(sim: SimulatorClient) -> None:
    """策略主体：在 /enter 与 /exit 之间实现。"""
    print("本局可用现实时间：", sim.enter()["remaining_real_duration_s"], "秒")

    # TODO: 全局扫频道 → 交会定位 → 逼近 20 m 清除 → 路径规划

    # 退出交给 with 块（异常时也会补一次 /exit），此处不再显式调用


def main() -> None:
    args = parse_args()
    with SimulatorClient(args.robot_id, args.url, log_dir=args.log_dir) as sim:
        run(sim)


if __name__ == "__main__":
    main()

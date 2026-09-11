# -*- coding: utf-8 -*-
"""算法插件的最小接口约定。

一个"算法"就是 `algorithms/` 下的一个模块，需要提供两个模块级名字：

    SPEC  : AlgorithmSpec              —— 算法身份与说明（网页控制台据此展示）
    build : callable(sim, params,       —— 构造算法对象
                     *, verbose=False)

``build`` 返回的对象只需要满足：

    obj.run() -> dict   跑完一整局，返回统计字典（至少含 "cleared"）
    obj.state           可选；各频道的状态，供网页显示"定位结果(估计点±误差)"

``sim`` 是与 ``SimulatorClient`` 同形的客户端（enter/measure/clear/exit）。
**算法里所有动作都必须通过它发出**——行为录制、实时刷新、每步延迟、断点单步
都挂在那一层包装上，绕过去网页就看不到任何东西。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class AlgorithmSpec:
    """算法的身份、说明与可调参数。"""

    id: str                      # 唯一标识，网页/命令行用它选算法
    name: str                    # 中文名，显示在控制台
    problem: str                 # "问题3" / "问题4" / …，用于区分题目
    summary: str                 # 一句话概括
    description: str             # 详细说明（网页上展开显示）
    params: dict = field(default_factory=dict)   # 可调参数默认值（JSON 可序列化）
    entry: str = ""              # 实现位置提示，例如 "algorithms/p3_baseline.py: InterferenceHunter"

    def to_dict(self) -> dict:
        return asdict(self)

# -*- coding: utf-8 -*-
"""新算法模板 —— 复制这个文件改名（别以 `_` 开头）就是一个新算法。

注册表会自动扫描 `algorithms/*.py`：只要模块里有 `SPEC` 和 `build`，
它就会出现在网页控制台的算法下拉框里，**不用改任何其它文件**。

例：`Copy-Item algorithms/_template.py algorithms/p4_directional.py`
"""

from __future__ import annotations

from .base import AlgorithmSpec

SPEC = AlgorithmSpec(
    id="my-algorithm",                     # 唯一 id：网页/命令行用它选算法
    name="我的新算法",                      # 中文名（控制台显示）
    problem="问题4",                        # 用来说明它解决哪一问
    summary="一句话概括",
    description="详细说明：探测怎么布点、怎么定位、怎么排序、终止判据是什么。",
    params={"some_param": 1.0},            # 可调参数默认值（键名随意，JSON 可序列化）
    entry="algorithms/_template.py: MyHunter",
)


# --------------------------------------------------------------------------
# 用法一：复用 robot.py 里现成的策略，只改参数（最省事）
# --------------------------------------------------------------------------
# def build(sim, params=None, *, verbose=False):
#     import robot
#     if params and "some_param" in params:
#         robot.SOME_CONST = params["some_param"]
#     return robot.InterferenceHunter(sim, verbose=verbose)


# --------------------------------------------------------------------------
# 用法二：写一个全新的策略类（下面这个骨架可以直接跑通，虽然很笨）
# --------------------------------------------------------------------------
class MyHunter:
    """最小可用骨架：每站扫全部频道，两个站交会后直接去清。

    要点：
      1. 所有动作只能通过 self.sim（注入的客户端）发出；
      2. run() 返回统计字典，至少要有 "cleared"（被清除个数）；
      3. self.state 可选，供网页显示各频道的定位结果，字段约定见
         trace_client.final_state()：known / cleared / center / radius …… 
    """

    def __init__(self, sim, params: dict | None = None):
        self.sim = sim
        self.params = params or {}
        self.state: dict[int, object] = {}

    def run(self) -> dict:
        self.sim.enter()
        cleared = 0
        # TODO: 你的探测 / 定位 / 清除逻辑，例如：
        #   r = self.sim.measure(x, y, channel)      # 返回 measure_result / svd_deg
        #   self.sim.clear(x, y, channel)            # 返回 clear_result
        self.sim.exit()
        return {"cleared": cleared, "平均定位清除时间": 0.0}


def build(sim, params: dict | None = None, *, verbose: bool = False):
    return MyHunter(sim, params)      # verbose 想用就用，不用就忽略

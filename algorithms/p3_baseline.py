# -*- coding: utf-8 -*-
"""第三题初版算法 —— 覆盖式探测 + 交会定位 + 精化逼近 + 滚动巡访清除。

实现位于 ``robot.py`` 的 ``InterferenceHunter``；本文件只负责**登记与装配**：
给算法起名字、写说明、声明可调参数，并按调用方的参数覆盖 `robot.py` 里对应的
模块级常量（例如探测环半径），这样不用改代码就能在网页上试不同参数。
"""

from __future__ import annotations

from .base import AlgorithmSpec

SPEC = AlgorithmSpec(
    id="p3-baseline",
    name="第三题初版算法",
    problem="问题3",
    summary="覆盖式探测 → 交会定位 → 精化逼近 → 滚动巡访清除",
    description=(
        "【探测】原点 + 半径 1300 m 上均布 6 点共 7 个测站。该布站最大覆盖半径 936 m，"
        "小于有效接收半径下限 1000 m，所以“某频道处处无信号 ⇒ 该频道必不存在”——"
        "这就是“确保全部清除”的停止判据，不依赖猜干扰源总数。\n"
        "【定位】把各测站 ±1° 示向度楔形求交，再与目标圆域、“被检测到 ⇒ 距该站 ≤1500 m”"
        "的圆盘求交；所得定位区域的最小外接圆半径 Rc 是**保证性**误差界（真实源必在圆内）。\n"
        "【精化】Rc > 20 m（清除半径）时，在估计点附近补两个互成 90° 的点。本题是"
        "“同一地点误差固定”的系统误差，最坏情况定位区域最小的交会角约 90°（随机误差 CEP "
        "准则下才是文献常引的 110°）；收敛到 Rc ≤ 20 m 后取圆心清除，一次命中可保证。\n"
        "【巡访】待办池 = {未去的测站} ∪ {待补第二条示向度的频道} ∪ {待清除目标}，"
        "每一步对当前待办集做一次滚动 TSP 取最近的一个——探测、定位、清除共用同一条回路。\n"
        "【实测】离线 200 例：清除比例 100%，平均定位清除时间 ≈ 315 s，"
        "平均每局约 109 次 measure。"
    ),
    params={
        "ring_r": 1300.0,      # 探测环半径（robot.RING_R）
        "good_radius": 60.0,   # 定位区域小到此值就不必再补测（robot.GOOD_RADIUS）
        "max_refine": 6,       # 单目标精化迭代上限（robot.MAX_REFINE）
    },
    entry="robot.py: InterferenceHunter",
)


#: 参数名 → robot.py 里的模块级常量名。
#: 想让它可调，先确认 robot.py 里确实按那个常量取值（见 algorithms/README.md）。
PARAM_CONSTANTS = {
    "ring_r": "RING_R",                  # 探测环半径
    "ring_k": "RING_K",                  # 环上测站数
    "good_radius": "GOOD_RADIUS",        # 定位区域小到它就不补测
    "max_refine": "MAX_REFINE",          # 单目标精化迭代上限
    "max_fallback": "MAX_FALLBACK",      # 清除失败后的兜底试探次数
    "real_time_margin": "REAL_TIME_MARGIN",
}


def build(sim, params: dict | None = None, *, verbose: bool = False):
    """构造策略对象。

    先用 `SPEC.params` 的默认值把 robot.py 的模块级常量复位，再叠加调用方的覆盖值。
    "先复位"这一步是为了让网页上连续跑多局时结果可复现——否则上一局的参数会残留
    到下一局（robot.py 的常量是进程级的）。
    """
    import robot

    effective = {**SPEC.params, **(params or {})}
    for key, value in effective.items():
        attr = PARAM_CONSTANTS.get(key)
        if not attr or not hasattr(robot, attr):
            continue
        if key in ("ring_k", "max_refine", "max_fallback"):     # 整数型常量
            setattr(robot, attr, int(value))
        else:                                                   # 其余是浮点型常量
            setattr(robot, attr, float(value))

    # `InterferenceHunter.refine(ch, max_iter=MAX_REFINE)` 的默认值在函数定义时就
    # 定死了，改模块常量对已定义的函数不起作用，这里同步把默认值换掉。
    max_iter = effective.get("max_refine")
    if isinstance(max_iter, (int, float)):
        robot.InterferenceHunter.refine.__defaults__ = (int(max_iter),)

    return robot.InterferenceHunter(sim, verbose=verbose)

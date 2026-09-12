#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CUMCM 2026 B 题 —— 机器狗控制器【快速响应版 FAST】

【接入本仓库框架】文件末尾有一段"框架适配层"（SPEC / build / transport 桥 / 统计翻译），
它只做登记与接线，上面的控制器本体一行未改。依赖同目录下的两个文件：
`dog_controller_safe.py`（基类 DogController/Config/Ledger/Certificate）与
`route_planner.py`（plan_route/next_task）——缺了它们本模块无法导入，
注册表会在网页上提示 `ModuleNotFoundError`。

相对【兜底完备版 SAFE】(dog_controller_safe.py) 的四项改动，
目标：在不增加漏检率的前提下大幅压缩移动距离（移动占总耗时 ~90%）。

  ① 探测点候选集：固定四环 -> **按覆盖缺口动态生成**
       废弃 600/1200/1800/2000 四环的专程巡回（实测占总移动 45%）。
       只对证书仍未覆盖的格子就地生成候选；边缘格额外生成**场外偏移点**，
       因为自边缘点看，区域内点必落在其"背后"半平面内，无法环绕 ——
       场外点是破除边缘定向盲区的唯一手段（这条安全性不变）。

  ② 顺路扫频：每次到达落点后**原地补测**未解决频道
       位置不变 => 只有检测 5 s + 切换 1 s，**零移动**。
       清除路线的每个落点自动成为探测点，覆盖几乎"免费"获得。

  ③ 巡访调度：滚动时域任务池 + 标准启发式路径规划（见 route_planner.py）
       取代"分类型各自选最近"的做法，消除跨场折返。

  ④ 证书按需触发：有可清除目标时绝不插队去巡环。

【安全不变式，原样保留】
  · ever_detected(ch) 为真的频道**永不可被排除**（证书只回答"没有证据"）
  · 逐频道独立探测历史；visited 记录必须逐频道
  · 边缘定向盲区必须靠**场外**探测点破除
  · 协议红线：坐标有限且 |x|,|y|≤2e6；严格串行；新动作新 request_id；
    同时检查 HTTP 状态与 accepted
"""

from __future__ import annotations

import math
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, ".."))

from route_planner import plan_route, next_task      # noqa: E402
from dog_controller_safe import (          # noqa: E402
    DogController, Config, Ledger, Certificate,
    TRACKED, FIXED, CLEARED, EXCLUDED, SEARCHING, UNKNOWN,
    UNRESOLVED_UNCERTIFIED, R_CLEAR_TRY, R_RECV_MIN, SPEED, R_STAR_COMMIT,
)


class ConfigFast(Config):
    """快速版参数"""
    opportunistic_scan = True     # 顺路扫频
    scan_per_stop_cap = 6         # 每个落点最多补测多少频道（10 时检测开销过大）
    use_rings = False             # 不做固定环巡回
    order_clears = True           # 清除按最近邻排序
    # 问题三（全为全向源）：覆盖判据退化为「任一探测点在 1000 m 内」，
    # 因此**场外环完全无用**（那是专为定向盲区设计的），可整体省掉。
    assume_omni = False
    # 第二探测点基线缩放。SAFE 用 DR-001 的 minimax 解 (812, 643) → |S1S2|≈1036 m,
    # 是为「保证一次命中(R*≤20)」设计的。FAST 有 R_CLEAR_TRY=120 m 的宽松阈值
    # 加逼近/CREEP 兜底，短基线即可，能省下每个目标约 500 m 的专程往返。
    fix_scale = 0.40
    # 沿线接近
    use_homing = False            # 已验证更差，保留代码供参考
    use_batch_fix = False         # batch fix实测不如滚动TSP，默认关
    batch_max_travel = 250.0      # 批量定位行程上限（秒）
    unified_nearest = False       # 实测比"分类型优先级"更差，关闭
    # ---- ⑦ 滚动时域任务池调度 + 覆盖增量剪枝 ----
    survey_ring_r = 1300.0        # 探测环半径：原点+6点，最大覆盖半径 936 m < 1000
    survey_k = 6
    coverage_step = 120.0         # 覆盖自检采样步长（决定剪枝精度）
    scan_needs_gain = True        # 只在能带来新覆盖时才扫未知频道
    rolling_tsp = True            # 待办池统一滚动 TSP
    _unused = None
    refine_before_clear = False   # 我们的精化实现不如基线高效，开启反而更慢
    home_step = 250.0             # 每步前进距离
    max_home_steps = 12           # 单频道接近步数上限


class DogControllerFast(DogController):
    # ---------------- ② 顺路扫频 ----------------
    def __init__(self, transport, robot_id, cfg=None):
        super().__init__(transport, robot_id, cfg)
        # 全向模式下覆盖判据退化：任一探测点在 1000 m 内即覆盖
        if getattr(self.cfg, "assume_omni", False):
            self.cert.omni = True
        # ⑦ 已做过「无信号覆盖扫描」的测站（决定后续扫频是否值得）
        self.stations = []
        self._csamp = None
        self.pending_survey = []

    # ---------------- ⑤ 沿线接近（homing）----------------
    def _do_home(self, ch):
        """
        沿最近方位前进一步并复测。

        与 SAFE 的「专程跑 2 段基线定位、再专程跑去清除」相比，单次行程同时
        完成：① 朝目标推进（本来就必须走）② 复测形成新的基线
        ③ 沿途顺路扫频（每个停点都是免费探测点）。

        误差按地点固定（真机已验证 C1），故沿路径各点误差独立，
        航向误差不累积 -> pursuit 收敛。
        注意：**不可原地复测**（同点误差固定，零信息增益）。
        """
        bs = self.lg.bearings(ch)
        if not bs:
            self.lg.state[ch] = SEARCHING
            return
        _x, _y, b = bs[-1]
        step = getattr(self.cfg, "home_step", 250.0)
        b_r = math.radians(b)
        nx = self.pos[0] + step * math.cos(b_r)
        ny = self.pos[1] + step * math.sin(b_r)
        res, svd = self.measure(nx, ny, ch)
        self.lg.n_fix[ch] += 1

        if res == "near":
            if self.clear(nx, ny, ch) == "success":
                self.lg.state[ch] = CLEARED
            return
        if res == "direction":
            est = self._solve_region(ch)
            if est is not None:
                self.lg.est[ch] = est
                if est[2] <= R_CLEAR_TRY:
                    self.lg.state[ch] = FIXED     # 够准了，下一轮直接清
                    return
            if self.lg.n_fix[ch] >= self.cfg.max_home_steps:
                self.lg.stuck.add(ch)
        elif res == "no_signal":
            # 可能越过目标（几何反转）或落在定向盲侧 -> 换一个横向偏移点
            b2 = b_r + (1.2 if self.lg.n_fix[ch] % 2 else -1.2)
            self.measure(self.pos[0] + step * 0.6 * math.cos(b2),
                         self.pos[1] + step * 0.6 * math.sin(b2), ch)
            if self.lg.n_fix[ch] >= self.cfg.max_home_steps:
                self.lg.stuck.add(ch)
                if self.lg.ever_detected(ch):
                    self.lg.state[ch] = TRACKED

    # ---------------- ⑥ 批量定位行程（去程即扫频）----------------
    def _ideal_second(self, ch):
        """该频道理想第二点：DR-001 minimax 向量按 fix_scale 缩放"""
        bs = self.lg.bearings(ch)
        if not bs:
            return None
        x1, y1, b1 = bs[-1]
        k = getattr(self.cfg, "fix_scale", 1.0)
        u = (math.cos(math.radians(b1)), math.sin(math.radians(b1)))
        v = (math.cos(math.radians(b1 + 90.0)), math.sin(math.radians(b1 + 90.0)))
        sgn = 1.0 if self.lg.n_fix[ch] % 2 == 0 else -1.0
        return (x1 + k * (812.0 * u[0] + sgn * 643.0 * v[0]),
                y1 + k * (812.0 * u[1] + sgn * 643.0 * v[1]))

    def _angles_ok(self, ch, p):
        """在 p 处测量频道 ch 是否能构成良好交会（与已有方位夹角足够）"""
        bs = self.lg.bearings(ch)
        if not bs:
            return True
        x1, y1, _ = bs[-1]
        if math.hypot(p[0] - x1, p[1] - y1) < 30.0:
            return False                       # 太近，等价同点复测
        # 与已有方位线的夹角够大即可（避免共线导致区域无界）
        best = 0.0
        for (bx, by, bdeg) in bs:
            ang = math.degrees(math.atan2(p[1] - by, p[0] - bx)) % 360.0
            d = abs((ang - bdeg + 180.0) % 360.0 - 180.0)
            best = max(best, min(d, 180.0 - d) * 2.0)
        return best >= 25.0

    def _plan_batch_fix(self):
        """
        选一个「批量定位点」：一趟行程同时为尽量多的待定位频道取第二方位。
        这正是「去程即扫频」——把多次专程往返合并为一次。
        评分 = 可服务频道数 / 行程代价（并轻微偏好靠近当前清除目标）
        """
        pend = [c for c in self.lg.unresolved()
                if self.lg.state[c] == TRACKED
                and c not in self.lg.stuck
                and self.lg.n_fix[c] < self.cfg.max_fix_attempts]
        if not pend:
            return None
        best = None
        for src in pend:
            p = self._ideal_second(src)
            if p is None:
                continue
            served = [c for c in pend if self._angles_ok(c, p)]
            if not served:
                continue
            travel = math.hypot(p[0] - self.pos[0], p[1] - self.pos[1]) / SPEED
            # 实测：定位行程平均 1115 m/条，是最大单项开销。给行程设上限，
            # 宁可分多次短行程，也不要一次长途（短行程可与清除路线顺路重合）。
            if travel > self.cfg.batch_max_travel:
                continue
            # 目标优先：若该点方向上也接近某个已定位目标，额外加分（两段行程重合）
            bonus = 0.0
            for c in self.lg.unresolved():
                e = self.lg.est.get(c)
                if e and self.lg.state[c] == FIXED:
                    bonus = max(bonus, 300.0 - min(300.0, math.hypot(
                        p[0] - e[0], p[1] - e[1])))
            score = (len(served) * 1000.0 + bonus) / max(travel + 6.0 * len(served), 1.0)
            if best is None or score > best[0]:
                best = (score, p, served)
        if best is None:
            # 全部超限：退化为「选最近的可用点」，仍比专程远行划算
            for src in pend:
                p = self._ideal_second(src)
                if p is None:
                    continue
                served = [c for c in pend if self._angles_ok(c, p)]
                if not served:
                    continue
                travel = math.hypot(p[0] - self.pos[0],
                                    p[1] - self.pos[1]) / SPEED
                if best is None or travel < best[0]:
                    best = (travel, p, served)
        return best

    def _at_survey_station(self):
        """当前位置是否为指定覆盖测站（原点或环上 6 点）"""
        for (sx, sy) in self._survey_stations():
            if math.hypot(self.pos[0] - sx, self.pos[1] - sy) < 5.0:
                return True
        return False

    def _goto_and_scan(self, px, py):
        """走到覆盖测站并做覆盖式扫描。

        用一个**未测过**的频道发起 measure 以完成位移（measure 自带移动），
        随后 `_scan_unresolved_at_current` 在原地补齐其余频道——零额外移动。
        """
        probe = None
        key = (round(px, 1), round(py, 1))
        for c in self.lg.unresolved():
            if not self.lg.ever_detected(c) and key not in self.visited_probe[c]:
                probe = c
                break
        if probe is None:
            for c in self.lg.unresolved():
                if key not in self.visited_probe[c]:
                    probe = c
                    break
        if probe is not None:
            res, _svd = self.measure(px, py, probe)
            self.visited_probe[probe].add(key)
            if res == "direction":
                self.lg.state[probe] = TRACKED
            elif res == "near":
                if self.clear(px, py, probe) == "success":
                    self.lg.state[probe] = CLEARED
        else:
            # 无可测频道：退化为「移动 + 对已锁定目标测一次」以完成位移
            cand = [c for c in self.lg.unresolved()
                    if self.lg.state[c] in (TRACKED, FIXED)]
            if cand:
                self.measure(px, py, cand[0])
            else:
                self.pos = (px, py)      # 无请求可发时直接记账（不应发生）
        self._scan_unresolved_at_current()

    def _pick_rolling_tsp(self, un):
        """
        异构任务池统一按滚动时域调度。

        tasks = {未去的覆盖测站} ∪ {待补第二个方位的频道} ∪ {待清除目标}
        对当前待办集做 NN+2-opt 排序，**只执行最近的那个**，然后按新信息重排。
        这样探测/定位/清除共用同一条巡访回路，而不是分三段各跑一趟。
        """
        tasks = []
        for p in self.pending_survey:
            tasks.append((p, ("survey", p)))
        for c in un:
            if self.lg.state[c] == TRACKED and len(self.lg.bearings(c)) == 1:
                q = self._ideal_second(c)
                if q is not None:
                    tasks.append((q, ("fix", c)))
        for c in un:
            e = self.lg.est.get(c)
            if (self.lg.state[c] == FIXED and e
                    and c not in self.lg.refine_pending
                    and (e[2] <= (R_STAR_COMMIT
                                  if self.cfg.refine_before_clear
                                  else R_CLEAR_TRY))):
                tasks.append((e[:2], ("clear", c)))
            elif (self.lg.state[c] == FIXED and e
                    and c not in self.lg.stuck
                    and self.lg.n_fix[c] < self.cfg.max_fix_attempts):
                tasks.append((e[:2], ("approach", c)))
        if not tasks:
            return None
        idx = next_task([t[0] for t in tasks], self.pos)
        return tasks[idx][1]

    def _pick_action(self, un):
        """
        【统一最近邻】把所有待办动作放在一起按**行程距离**排序，而不是各类型
        各自打分。实测：分类型打分会让 APPROACH/BATCH/VERIFY 反复横穿全场
        （单局 10+ 条 1000~2100 m 的跨场指令），这是移动距离的最大来源。

        清除动作给 400 m 的优先折扣（它同时推进"发现"和"清除"两件事）。
        """
        cands = []
        cx, cy = self.pos

        def d(p):
            return math.hypot(p[0] - cx, p[1] - cy)

        for c in un:
            e = self.lg.est.get(c)
            if (self.lg.state[c] == FIXED and e and e[2] <= R_CLEAR_TRY
                    and c not in self.lg.refine_pending):
                cands.append((d(e) - 400.0, ("clear", c)))
        pl = self._plan_batch_fix()
        if pl is not None:
            cands.append((d(pl[1]), ("batch", None)))
        for c in un:
            e = self.lg.est.get(c)
            if (self.lg.state[c] == FIXED and e
                    and (e[2] > R_CLEAR_TRY or c in self.lg.refine_pending)
                    and self.lg.n_fix[c] < self.cfg.max_fix_attempts):
                cands.append((d(e), ("approach", c)))
        for c in un:
            if self.lg.state[c] == TRACKED and len(self.lg.bearings(c)) == 1:
                cands.append((d(self.lg.bearings(c)[-1]), ("fix", c)))
        if not cands:
            return None
        cands.sort(key=lambda t: t[0])
        return cands[0][1]

    def _do_batch_fix(self):
        """执行批量定位行程；返回是否取得进展"""
        plan = self._plan_batch_fix()
        if plan is None:
            return False
        _score, p, served = plan
        got = False
        for c in served:
            res, _svd = self.measure(p[0], p[1], c)
            self.lg.n_fix[c] += 1
            if res == "direction":
                got = True
                if self.lg.state[c] in (UNKNOWN, SEARCHING, EXCLUDED):
                    self.lg.state[c] = TRACKED
                if len(self.lg.bearings(c)) >= 2:
                    self._promote(c)          # 升级 FIXED（若区域有界）
            elif res == "near":
                if self.clear(p[0], p[1], c) == "success":
                    self.lg.state[c] = CLEARED
                got = True
        # 该落点顺路扫频（零移动成本）
        self._scan_unresolved_at_current()
        return got

    def _second_point(self, ch, attempt=0):
        """
        覆盖基类版本：把 minimax 基线按 fix_scale 缩放。
        短基线牺牲一点交会精度（R* 变大），但 FAST 的清除阈值宽松且有逼近兜底，
        换来每个目标约 500 m 的移动节省。
        """
        p = super()._second_point(ch, attempt)
        if p is None:
            return None
        bs = self.lg.bearings(ch)
        if not bs:
            return p
        x1, y1, _b = bs[-1]
        k = getattr(self.cfg, "fix_scale", 1.0)
        return (x1 + (p[0] - x1) * k, y1 + (p[1] - y1) * k)

    # ---------------- ⑦ 覆盖增量剪枝 ----------------
    def _coverage_samples(self):
        """覆盖自检采样点（只算一次并缓存）"""
        if getattr(self, "_csamp", None) is None:
            st = self.cfg.coverage_step
            n = int(1800.0 // st) + 1
            pts = []
            for i in range(-n, n + 1):
                for j in range(-n, n + 1):
                    x, y = i * st, j * st
                    if math.hypot(x, y) <= 1800.0:
                        pts.append((x, y))
            self._csamp = pts
        return self._csamp

    def _covered(self, p):
        """采样点 p 是否已被某个"扫过无信号"的测站（1000 m 保守半径）覆盖"""
        for (sx, sy) in self.stations:
            if (p[0] - sx) ** 2 + (p[1] - sy) ** 2 <= R_RECV_MIN ** 2:
                return True
        return False

    def _coverage_gain(self, x, y):
        """把 (x,y) 加为测站能新增覆盖多少个采样点。0 表示该点无信息增量。"""
        g = 0
        for p in self._coverage_samples():
            if (p[0] - x) ** 2 + (p[1] - y) ** 2 <= R_RECV_MIN ** 2 \
                    and not self._covered(p):
                g += 1
        return g

    def _survey_stations(self):
        """覆盖式探测测站：原点 + 半径 survey_ring_r 上均布 survey_k 点。

        该布站最大覆盖半径约 936 m < 有效接收半径下限 1000 m，因此
        「某频道处处无信号 ⇒ 该频道必不存在」——这是完备性的停止判据。
        """
        pts = [(0.0, 0.0)]
        for k in range(self.cfg.survey_k):
            a = 2 * math.pi * k / self.cfg.survey_k
            pts.append((self.cfg.survey_ring_r * math.cos(a),
                        self.cfg.survey_ring_r * math.sin(a)))
        return pts

    def _scan_unresolved_at_current(self):
        """
        在当前点做覆盖式扫描。

        【覆盖增量剪枝】只有当该点能带来**新的覆盖**（覆盖增量 > 0）时才扫未知频道。
        依据：对某频道处处无信号构成"该频道不存在"的覆盖式证据，因此只有能
        扩张证据覆盖范围的点才有信息增量，其余扫描纯属浪费。
        实测：改为"仅在指定测站扫频"后，单局 measure 由 235 次降至 97 次。

        位置不变 => 只消耗 5 s 检测 + 1 s 切换，零移动。
        """
        if not self.cfg.opportunistic_scan:
            return False
        x, y = self.pos
        key = (round(x, 1), round(y, 1))
        gain = self._coverage_gain(x, y) if self.cfg.scan_needs_gain else 1
        if gain <= 0:
            return False                       # 该点无新覆盖 -> 完全不扫
        found = False
        for c in self.lg.unresolved():
            if c in self.lg.stuck or key in self.visited_probe[c]:
                continue
            n_b = len(self.lg.bearings(c))
            if not self.lg.ever_detected(c):
                res, _svd = self.measure(x, y, c)       # 未知频道：补覆盖证据
                self.visited_probe[c].add(key)
                if res == "direction":
                    self.lg.state[c] = TRACKED
                    found = True
                elif res == "near":
                    if self.clear(x, y, c) == "success":
                        self.lg.state[c] = CLEARED
                    found = True
            elif n_b == 1:
                # 单方位频道：仅当该点很可能落在它的有效接收半径内才补测
                bx, by, bdeg = self.lg.bearings(c)[0]
                if self._point_ray_dist((x, y), (bx, by), bdeg) <= 900.0:
                    res, _svd = self.measure(x, y, c)
                    self.visited_probe[c].add(key)
                    if res == "direction":
                        found = True
        if found or gain > 0:
            self.stations.append((x, y))        # 该点成为覆盖测站
        return found

    @staticmethod
    def _point_ray_dist(p, s, phi_deg, max_len=1500.0):
        """点 p 到「以 s 为起点、方位 phi 的射线（限长 max_len）」的距离"""
        ux, uy = math.cos(math.radians(phi_deg)), math.sin(math.radians(phi_deg))
        vx, vy = p[0] - s[0], p[1] - s[1]
        t = vx * ux + vy * uy
        if t < 0:
            return math.hypot(vx, vy)
        if t > max_len:
            t = max_len
        return math.hypot(vx - t * ux, vy - t * uy)

    # ---------------- ① 按缺口生成候选 ----------------
    def _gap_candidates(self):
        """
        只为【证书仍未覆盖的格子】生成候选探测点。
        边缘格（r 较大）额外生成**场外偏移点** —— 破除定向盲区所必需。
        """
        chs = self.lg.unresolved()
        if not chs:
            return []
        out = []
        seen = set()
        for G in self.cert.cells:
            # 该格对任一未解决频道仍有缺口？
            deficit = False
            for c in chs:
                probes = [(px, py) for (px, py, _r, _s)
                          in self.lg.probe_pts[c]]
                if self.cert.miss(G, probes) > 1e-9:
                    deficit = True
                    break
            if not deficit:
                continue
            r = math.hypot(G[0], G[1])
            pts = [G]
            # 场外候选**仅对定向源必要**：自边缘点看，区域内点必落在其背后
            # 半平面内，无法环绕。全向源无此问题，加场外点纯属浪费移动。
            if (not self.cfg.assume_omni) and r > 900.0:
                ux, uy = (G[0] / r, G[1] / r) if r > 1e-9 else (1.0, 0.0)
                for d in (400.0, 800.0):
                    pts.append((G[0] + ux * d, G[1] + uy * d))
            for p in pts:
                k = (round(p[0] / 50.0), round(p[1] / 50.0))   # 50 m 去重
                if k in seen:
                    continue
                seen.add(k)
                out.append(p)
        return out

    def _plan_probe(self):
        """与 SAFE 同契约，但候选取自缺口，且跳过 visited 由逐频道保证"""
        unresolved = self.lg.unresolved()
        if not unresolved:
            return None
        cands = self.candidates if self.cfg.use_rings else self._gap_candidates()
        best = None
        for p in cands:
            near = self._cells_near(p)
            if not near:
                continue
            key = (round(p[0], 1), round(p[1], 1))
            gain = 0.0
            chs = []
            for c in unresolved:
                if key in self.visited_probe[c]:
                    continue
                probes = [(x, y) for (x, y, _r, _s) in self.lg.probe_pts[c]]
                g = sum(self.cert.gain_of_point(G, probes, p) for G in near)
                if g > 1e-9:
                    gain += g
                    chs.append(c)
            if not chs:
                continue
            travel = math.hypot(p[0] - self.pos[0], p[1] - self.pos[1]) / SPEED
            cost = travel + 6.0 * len(chs)          # 检测 5 + 切换 1
            eff = gain / max(cost, 1e-9)
            if best is None or eff > best[0]:
                best = (eff, gain, cost, p, chs)
        return best

    # ---------------- ③ 清除顺序：最近邻 ----------------
    def _pick_target(self, un):
        """从可清除的目标里选**离当前位置最近**的，而非第一个"""
        if not self.cfg.order_clears:
            return None
        best, bd = None, None
        for c in un:
            e = self.lg.est.get(c)
            if not (self.lg.state[c] == FIXED and e and e[2] <= R_CLEAR_TRY
                    and c not in self.lg.refine_pending):
                continue
            d = math.hypot(e[0] - self.pos[0], e[1] - self.pos[1])
            if bd is None or d < bd:
                best, bd = c, d
        return best

    # ---------------- 主循环（覆盖 SAFE 的选择逻辑） ----------------
    def run(self):
        r = self._call("/enter", {}, "enter")
        self.remaining_real = float(r.get("remaining_real_duration_s", 1200))
        budget_real = self.remaining_real

        self.phase_seed()
        # 覆盖式测站：原点 + 半径 survey_ring_r 上 survey_k 点（原点已测，先加入）
        self.stations.append((0.0, 0.0))
        src0 = self._survey_stations()
        self.pending_survey = [(round(px, 3), round(py, 3))
                               for (px, py) in src0 if (px, py) != (0.0, 0.0)]
        # SEED 结束后就地顺路扫一遍（原点落点已是覆盖测站）
        self._scan_unresolved_at_current()

        step = 0
        last_prog = self.lg.n_progress_key()
        stagn = 0
        while step < 20000:
            step += 1
            if self.remaining_real < self.cfg.real_time_reserve_s:
                break
            act = None
            un = [c for c in self.lg.unresolved() if c not in self.lg.stuck]

            # 0) ≥2 方位直接解算
            for c in un:
                if (self.lg.state[c] == TRACKED
                        and len(self.lg.bearings(c)) >= 2):
                    if not self._promote(c):
                        self.lg.n_fix[c] += 1
                        if self.lg.n_fix[c] >= self.cfg.max_fix_attempts:
                            self.lg.stuck.add(c)
                        else:
                            act = ("fix", c)
                    break

            # ⑦ 滚动 TSP：待办池 = {未去的探测站} ∪ {待补第二方位的频道}
            #                    ∪ {待清除目标}，每步重排取第一个
            if act is None and getattr(self.cfg, "rolling_tsp", False):
                act = self._pick_rolling_tsp(un)
            # 统一最近邻：所有待办动作一起比距离，避免跨场横穿
            if act is None and getattr(self.cfg, "unified_nearest", True):
                act = self._pick_action(un)
            # 回退：分类型优先级（与 SAFE 一致）
            if act is None:
                tc = self._pick_target(un)
                if tc is not None:
                    act = ("clear", tc)
            if act is None:
                for c in un:
                    e = self.lg.est.get(c)
                    if (self.lg.state[c] == FIXED and e
                            and e[2] <= R_CLEAR_TRY
                            and c not in self.lg.refine_pending):
                        act = ("clear", c)
                        break
            if act is None:
                for c in un:
                    e = self.lg.est.get(c)
                    if (self.lg.state[c] == FIXED and e
                            and (e[2] > R_CLEAR_TRY
                                 or c in self.lg.refine_pending)
                            and self.lg.n_fix[c] < self.cfg.max_fix_attempts):
                        act = ("approach", c)
                        break
            if act is None and getattr(self.cfg, "use_batch_fix", True):
                if self._plan_batch_fix() is not None:
                    act = ("batch", None)
            if act is None:
                for c in un:
                    if (self.lg.state[c] == TRACKED
                            and len(self.lg.bearings(c)) == 1):
                        act = ("fix", c)
                        break

            if act is None:
                r2 = self.phase_verify()
                if r2 in ("done", "exhausted"):
                    break
            else:
                if act[0] == "survey":
                    px, py = act[1]
                    self._goto_and_scan(px, py)
                    self.pending_survey = [q for q in self.pending_survey
                                           if q != act[1]]
                elif act[0] == "clear":
                    self._try_clear(act[1])
                elif act[0] == "approach":
                    self._do_approach(act[1])
                elif act[0] == "batch":
                    if not self._do_batch_fix():
                        # 批量行程无进展 -> 该批频道标记卡住，避免死循环
                        for c in self.lg.unresolved():
                            if (self.lg.state[c] == TRACKED
                                    and self.lg.n_fix[c] >= 1):
                                self.lg.stuck.add(c)
                elif act[0] == "home":
                    self._do_home(act[1])
                else:
                    self._do_fix(act[1])
                # ② 扫频只发生在**指定覆盖测站**上。
                #    7 个测站已保证 936 m 全覆盖，清除路线上的其他落点再扫无信息增量。
                #    实测：这一点占旧实现 180/220 次 measure（82%），是最大的单项浪费。
                if self._at_survey_station():
                    self._scan_unresolved_at_current()

            prog = self.lg.n_progress_key()
            if prog == last_prog:
                stagn += 1
            else:
                last_prog, stagn = prog, 0
            if stagn >= self.cfg.stagnation_limit:
                break

        self.cert_failed = []
        for c in self.lg.unresolved():
            probes = [(x, y) for (x, y, _r, _s) in self.lg.probe_pts[c]]
            if not self.lg.ever_detected(c) and self.cert.channel_deficit(probes) <= 1e-9:
                self.lg.state[c] = EXCLUDED
            else:
                self.cert_failed.append({
                    "channel": c, "state": self.lg.state[c],
                    "n_bearings": len(self.lg.bearings(c)),
                    "n_probes": len(self.lg.probe_pts[c]),
                 })
                self.lg.state[c] = UNRESOLVED_UNCERTIFIED
        self._call("/exit", {}, "exit")
        return self.report(budget_real)


# ================================================================== 框架适配层
# 以下是接入本仓库框架（algorithms/ 注册表 + robot.py + webui.py 可视化）所需的三样东西：
#   1) `_SimTransport`：把框架注入的 sim 客户端包装成基类要的 transport；
#   2) `SPEC` / `build()`：算法身份与构造入口（注册表按 id 去重，id 必须唯一）；
#   3) `_FrameworkRunner`：把 run() 的返回翻译成框架认识的统计字典，并把 ledaker 状态
#      暴露成 `state` 供网页画各频道的定位结果。
# **控制器本体一行未改**（上面的 DogControllerFast / ConfigFast 保持原样）。
#
# 依赖：`dog_controller_safe.py`（基类 DogController/Config/Ledger/Certificate）与
# `route_planner.py`（plan_route/next_task）必须和本文件放在同一个目录下——
# 本文件顶部已经把该目录加进了 sys.path。


class _SimTransport:
    """sim 客户端 → 队友控制器要的 transport。

    他的基类用 ``self._call("/enter", {}, "enter")`` 这种"给路径 + 请求体、拿回响应
    dict"的写法发指令；本框架的 sim 客户端正好是同一套协议（附件 2 的 4 条 HTTP 接口），
    所以这里一一对应地转过去即可，不需要改他的任何调用。
    """

    def __init__(self, sim):
        self._sim = sim

    def request(self, path: str, payload: dict | None = None, *_a, **_kw) -> dict:
        p = payload or {}
        tail = str(path).rstrip("/").rsplit("/", 1)[-1]
        if tail == "enter":
            return self._sim.enter()
        if tail == "exit":
            return self._sim.exit()
        pos = p.get("position") or {}
        x, y = float(pos.get("x", 0.0)), float(pos.get("y", 0.0))
        ch = int(p.get("channel", 1))
        if tail == "measure":
            return self._sim.measure(x, y, ch)
        if tail == "clear":
            return self._sim.clear(x, y, ch)
        raise ValueError(f"未知指令：{path}")

    # 基类里若用了别的叫法，都指到同一个实现
    post = send = call = request


class _ChannelView:
    """网页 `trace_client.final_state()` 认的那几个字段。"""

    __slots__ = ("known", "cleared", "bearings", "no_signal", "near_at",
                 "center", "radius")

    def __init__(self):
        self.known = False
        self.cleared = False
        self.bearings: list = []
        self.no_signal: list = []
        self.near_at = None
        self.center = None
        self.radius = float("inf")


def _state_from_ledger(lg) -> dict:
    """把队友的 Ledger 读成 ``{频道: 状态}``（只读，不影响他的算法）。"""
    out: dict = {}
    if lg is None:
        return out
    for c in range(1, 21):
        try:
            v = _ChannelView()
            v.known = bool(lg.ever_detected(c))
            v.cleared = (lg.state.get(c) == CLEARED)
            v.bearings = list(lg.bearings(c))
            est = getattr(lg, "est", {}).get(c)
            if est:
                v.center = (float(est[0]), float(est[1]))
                v.radius = float(est[2])
            out[str(c)] = v
        except Exception:          # noqa: BLE001 —— 只读视图，缺字段就当没有
            continue
    return out


def _normalize_report(rep: dict, ctrl) -> dict:
    """把他的报告翻译成框架认的统计键（缺什么就用 Ledger 里的信息补）。"""
    out = dict(rep or {})
    lg = getattr(ctrl, "lg", None)
    cleared_channels: list = []
    n_probes = 0
    if lg is not None:
        try:
            cleared_channels = [c for c in range(1, 21) if lg.state.get(c) == CLEARED]
            n_probes = sum(len(v) for v in getattr(lg, "probe_pts", {}).values())
        except Exception:          # noqa: BLE001
            pass
    out.setdefault("cleared", len(cleared_channels))
    out.setdefault("cleared_channels", cleared_channels)
    out.setdefault("measure次数", n_probes)
    vtot = out.get("虚拟总时间", out.get("virtual_time_s"))
    if vtot is None:
        vtot = float(getattr(ctrl, "virtual_time", 0.0) or 0.0)
        out["虚拟总时间"] = vtot
    if "平均定位清除时间" not in out:
        out["平均定位清除时间"] = (vtot / len(cleared_channels)
                                   if cleared_channels else float("inf"))
    out.setdefault("备注", [])
    return out


class _FrameworkRunner:
    """框架侧要的对象：``run()`` 出统计、``state`` 给网页。"""

    def __init__(self, ctrl, sim, verbose: bool = False):
        self.ctrl = ctrl
        self.sim = sim
        self.verbose = verbose

    def run(self) -> dict:
        return _normalize_report(self.ctrl.run(), self.ctrl)

    @property
    def state(self) -> dict:
        return _state_from_ledger(getattr(self.ctrl, "lg", None))


def _robot_id_of(sim) -> str:
    """框架的 sim 客户端上带的队号（拿不到就给空串，他的控制器只是转发用）。"""
    for obj in (sim, getattr(sim, "inner", None)):
        rid = getattr(obj, "robot_id", "") if obj is not None else ""
        if rid:
            return str(rid)
    return ""


#: 算法身份。id 必须全局唯一，否则注册表会按重复 id 跳过整个模块。
try:                                       # 被 algorithms 注册表导入时走相对导入
    from .base import AlgorithmSpec
except ImportError:                        # 直接把本文件当脚本跑时兜底
    from base import AlgorithmSpec          # type: ignore


SPEC = AlgorithmSpec(
    id="p3-wxm-fast",
    name="第三题 快速响应版（wxm FAST）",
    problem="问题3",
    summary="按覆盖缺口动态布点 → 顺路扫频 → 滚动时域调度 → 证书按需触发",
    description=(
        "【来源】队友的第三题快速响应版（原文件 algorithms/p3_v2.py，控制器本体未改；"
        "本文件末尾只加了框架适配层）。它建在队友自己的 SAFE 控制器之上，依赖同目录的 "
        "`dog_controller_safe.py` 与 `route_planner.py`。\n"
        "【相对 SAFE 版（dog_controller_safe.py）的四项改动，来自本文件原注释】\n"
        "① 探测点候选集：废弃 600/1200/1800/2000 固定四环的专程巡回（实测占总移动 45%），"
        "改成按覆盖证书的缺口就地生成候选；边缘格额外生成**场外偏移点**，因为从边缘点看，"
        "区域内点必落在其背后半平面内、无法环绕——场外点是破除边缘定向盲区的唯一手段。\n"
        "② 顺路扫频：每次到达落点后原地补测未解决频道（只有 5 s 检测 + 1 s 切换，零移动），"
        "清除路线的每个落点自动变成探测点，覆盖几乎免费获得。\n"
        "③ 巡访调度：滚动时域任务池 + 标准启发式路径规划（route_planner.py），"
        "取代“分类型各自选最近”，消除跨场折返。\n"
        "④ 证书按需触发：有可清除目标时绝不插队去巡环。\n"
        "【安全不变式原样保留】ever_detected 为真的频道永不可被排除；逐频道独立探测历史；"
        "边缘定向盲区必须靠场外探测点破除；协议红线（有限坐标、严格串行、新动作新 request_id、"
        "同时检查 HTTP 状态与 accepted）。\n"
        "【框架适配】上面这些行为都由他的控制器实现；本文件末尾的适配层只负责把框架注入的 "
        "sim 客户端包装成他基类要的 transport、把 run() 的返回翻译成统计字典、"
        "并把 Ledger 暴露成网页画图要的 state。"
    ),
    params={
        "survey_ring_r": 1300.0,     # 覆盖探测环半径（原点 + survey_k 点）
        "survey_k": 6,               # 环上点数
        "coverage_step": 120.0,      # 覆盖自检采样步长
        "scan_per_stop_cap": 6,      # 每个落点最多补测几个频道
        "fix_scale": 0.40,           # 第二探测点基线缩放
    },
    entry="algorithms/p3_v2.py: DogControllerFast",
)


def build(sim, params: dict | None = None, *, verbose: bool = False):
    """构造他的控制器：cfg 里能对上的参数就覆盖，其余保持他文件里的默认值。"""
    cfg = ConfigFast()
    for key, value in (params or {}).items():
        if hasattr(cfg, key):
            setattr(cfg, key, value)
    ctrl = DogControllerFast(_SimTransport(sim), _robot_id_of(sim), cfg)
    return _FrameworkRunner(ctrl, sim, verbose=verbose)

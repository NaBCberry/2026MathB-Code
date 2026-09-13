# -*- coding: utf-8 -*-
"""诊断 v8 的"几何绕站"减项到底在哪些案例真正触发。
用法：python tools/diag_v8_activation.py [seed起点] [案例数]
"""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, ".")

import algorithms  # noqa: E402
from archived.mock_arena import MockArena  # noqa: E402

seed0 = int(sys.argv[1]) if len(sys.argv) > 1 else 1
n = int(sys.argv[2]) if len(sys.argv) > 2 else 200

hits_total = 0
cases_hit = []
for i in range(n):
    seed = seed0 + i
    arena = MockArena(seed=seed, problem=4)
    h = algorithms.build_algorithm("p4-v8-geoorder", arena, {})
    h._geo_hits = []
    orig = type(h)._geo_bonus

    def bonus(self, pt, _orig=orig):
        v = _orig(self, pt)
        if v > 0.0:
            self._geo_hits.append((round(self.virtual_time, 1), pt, round(v, 1)))
        return v

    type(h)._geo_bonus = bonus
    try:
        st = h.run()
    finally:
        type(h)._geo_bonus = orig
    if h._geo_hits:
        hits_total += len(h._geo_hits)
        cases_hit.append((seed, len(h._geo_hits), st["cleared"], h._geo_hits[:3]))

print(f"seed {seed0}–{seed0 + n - 1}：{len(cases_hit)}/{n} 个案例触发过几何减项，"
      f"累计 {hits_total} 次")
for seed, k, cleared, sample in cases_hit[:15]:
    print(f"  seed={seed}  触发 {k} 次  清除 {cleared}  例：{sample}")

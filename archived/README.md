# archived —— 归档区

这里放**不参与正式测试**的脚本与旧版本文件。放在这里不等于没用，只是不该占着根目录。

| 文件 | 是什么 | 还能用吗 |
| --- | --- | --- |
| `mock_arena.py` | 本地离线模拟器：按题目规则复刻电磁环境，能读到真值（干扰源个数/位置/接收半径/定向方向），用来在没有模拟器、没有网络时自测"清除比例"与"平均定位清除时间" | **能**。`python robot.py --robot-id demo --dry-run --cases 20` 和网页的"离线案例"都通过 `archived.mock_arena` 调它 |
| `probe_simulator.py` | 模拟器连通性探测脚本（登录/开始测试/接口是否就绪），只读、可选 `--enter` | 能，但需要模拟器在跑。要跑就 `python archived/probe_simulator.py --robot-id <队号>` |
| `robot_v1.py` | 重构前的 `robot.py` 快照：那时算法本体（`InterferenceHunter`）还跟命令行入口挤在同一个文件里 | 只是留档/回滚参考，**不要直接跑**；算法本体已移到 `algorithms/p3_baseline.py`，入口是本目录上一级的 `robot.py` |

## 为什么这么放

根目录只留"跑得起来的成品"：`robot.py`（入口）、`sim_client.py`（通信）、
`algorithms/`（算法本体）、`trace_client.py` / `step_gate.py` / `webui.py`（录制、
调试与可视化）。算法相关的旧文件、离线自测环境、连通性探测脚本都归到本目录。

## 注意事项

- `archived/` 是一个 Python 包（有 `__init__.py`），所以 `import archived.mock_arena` 可用；
  但**别**在正式测试路径里依赖它——正式测试只该走 `sim_client` + `algorithms`。
- 归档文件不会跟着算法一起更新。改了 `algorithms/p3_baseline.py` 之后，
  `robot_v1.py` 里还是老代码，那是它的用途（对照/回滚），不是 bug。

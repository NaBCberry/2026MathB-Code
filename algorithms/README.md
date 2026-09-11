# 算法注册表：怎么加、怎么改、怎么切

## 它是干什么的

`algorithms/` 下的每个 `.py` 文件就是一个可选算法。注册表自动扫描这个目录，
把带 `SPEC` 与 `build` 的模块列进网页控制台的"算法"下拉框，以及命令行的
`--algorithm` 参数。**加算法不用改网页、不用改注册表本身。**

当前有：

| id | 名称 | 题目 | 实现位置 |
| --- | --- | --- | --- |
| `p3-baseline` | 第三题初版算法 | 问题3 | `algorithms/p3_baseline.py: InterferenceHunter` |

## 三条使用路径

```bash
# 1) 离线自测（最快，用来调参/比较算法）
python robot.py --robot-id demo --dry-run --cases 50 \
       --algorithm p3-baseline --params '{"ring_r":1200}'

# 2) 网页控制台：起服务后在"算法"下拉里选，右侧会显示算法说明与默认参数
python webui.py --serve-only          # 或者 webui.py --run --robot-id <队号>

# 3) 直接指定算法接模拟器跑一局
python webui.py --run --robot-id <参赛队号> --algorithm p3-baseline
```

网页控制台里"实机运行 / 离线案例"两个按钮都用**当前选中的算法**；参数框里的 JSON
会原样传给算法（留空则用默认值）。每局 trace 的 meta 里会记下算法 id 与名称，
所以事后回放也知道是哪套算法跑的。

## 新增一个算法

1. 复制模板：`algorithms/_template.py` → `algorithms/<你的名字>.py`（**不要**以 `_` 开头）。
2. 在文件里改 `SPEC`：`id`（唯一）、`name`、`problem`、`summary`、`description`、`params`。
3. 实现 `build(sim, params, *, verbose=False)`，返回一个带 `run()` 的对象。
4. 刷新网页（下拉框是每次打开页面时拉取的）即可选用；也可以直接用
   `python webui.py --run --robot-id <队号> --algorithm <你的id>`。

如果新算法是"改一改第三题那套"，最省事的是复用现成实现：

```python
from . import p3_baseline          # 复用第三题那套实现


def build(sim, params=None, *, verbose=False):
    p3_baseline.RING_R = (params or {}).get("ring_r", 1600.0)   # 只改参数
    return p3_baseline.InterferenceHunter(sim, verbose=verbose)
```

只有在要换掉探测/定位/排序的**做法**时，才需要自己写一个类。

## 参数是怎么生效的

`params` 只覆盖 `build()` 里显式写下的键，别的键会被忽略（不会报错）。第三题那套是
用"改本模块的模块级常量"实现的，对照表在 `algorithms/p3_baseline.py` 的
`PARAM_CONSTANTS`：

| 参数 | `p3_baseline.py` 里的常量 | 含义 |
| --- | --- | --- |
| `ring_r` | `RING_R` | 探测环半径（默认 1300 m，覆盖半径 936 m < 1000 m） |
| `ring_k` | `RING_K` | 环上测站数（默认 6） |
| `good_radius` | `GOOD_RADIUS` | 定位区域外接圆小到此值就不必再补测（默认 60 m） |
| `max_refine` | `MAX_REFINE` | 单目标精化迭代上限（默认 6） |
| `max_fallback` | `MAX_FALLBACK` | 清除失败后的兜底试探次数（默认 6） |
| `real_time_margin` | `REAL_TIME_MARGIN` | 现实时间安全余量（默认 20 s） |

两个容易踩的坑：

- **不要把 `ring_r` 调到覆盖半径 ≥ 1000 m**（约 > 1333 m 就危险）。判据是"某频道处处
  无信号 ⇒ 必不存在"，覆盖半径必须小于有效接收半径下限 1000 m 才成立；调大了会
  漏掉真源，看起来"跑得快"其实没清干净。
- `InterferenceHunter.refine(ch, max_iter=MAX_REFINE)` 的默认值在**函数定义时**就定死
  了，光改模块常量没用，`build()` 里额外把函数的默认值也换了。你写新算法时如果也用
  "默认参数捕获常量"的写法，记得处理同样的问题——或者让函数在调用时现读常量。

每次 `build()` 会先用 `SPEC.params` 把常量复位、再叠加本次覆盖值，所以网页上连着跑
多局，上一局的参数不会残留到下一局。

## 修改现有算法

第三题那套的实现就在 `algorithms/p3_baseline.py`（`InterferenceHunter`），对照表：

| 想改什么 | 改哪里 |
| --- | --- |
| 探测站怎么布置 | `InterferenceHunter.survey_stations()`；`_worth_measuring()` 决定某站测哪些频道 |
| 探测与清除的先后、巡访顺序 | `run()` 里待办池的构造与挑选 |
| 交会定位算法 | `_refresh_region()` + `clip_wedge` / `clip_disc` / `min_enclosing_circle` |
| 只有一条示向度时选第二点 | `_ray_intervals()`（用 no_signal 收窄射线区间）、`_second_points()` |
| 精化逼近到 20 m 内 | `refine()`、`clear_channel()` |
| **完备性/停止判据** | `unknown_channels()`、`_covered()`、`_coverage_gain()`、`SAMPLES`，以及 `survey_stations()` 的覆盖半径 |
| 物理常量 | `algorithms/p3_baseline.py` 顶部常量区 |

改完之后，`algorithms/p3_baseline.py` 里 `params` 的键（`ring_r` / `good_radius` /
`max_refine` …）要跟同一文件 `PARAM_CONSTANTS` 里的常量名对得上；对不上就在那张表里
补一条。别改根目录的 `robot.py`——它只是入口，不含策略。

## 问题4 改造点

问题4 多了定向干扰源（有效覆盖角度 180°，定向方向未知），需要改三处：

1. **探测布站**：定向源只在其半平面内可测，因此"距离覆盖"不够，还要满足"包围条件"
   ——对区域内任一点 p，p 必须落在"距 p ≤ 1000 m 的测站"的凸包内。数值结果：内层用
   间距 1000 m 的六边形格点 13 个，另加半径 1900 m、12 等分的外环，共 25 站可做到零
   漏检（814 万组"位置×方向"全部可覆盖）。外环是必要的：位于区域边界、朝外的定向源，
   在目标区域内部任何位置都测不到它。
2. **定位**：`no_signal` 不再等于"距离超限"，还可能是"不在定向覆盖范围内"，因此不能
   再拿 `no_signal` 反推距离；示向度楔形交会本身仍然成立（只要测到过）。
3. **终局判据**：`near` 也要求"位于有效覆盖角度范围内"，从背面靠近会返回 `no_signal`，
   所以不能等 `near`；但 `/clear` 在 20 m 内不受定向朝向限制，因此以"`clear` 成功"
   作为终局。

按上面的步骤新建一个算法模块（例如 `algorithms/p4_directional.py`），网页控制台与
`--algorithm` 都能直接切换过去，不必改动 `robot.py`。

## 写算法时必须遵守的三条

1. **动作只走注入的 `sim`**：`self.sim.measure(x, y, ch)` / `self.sim.clear(x, y, ch)`。
   行为录制、网页实时刷新、每步延迟、断点单步全挂在这个包装客户端上；自己发 HTTP
   或绕开它，网页就什么都看不到。
2. **严格串行**，一次一个动作。开线程并发发指令会被模拟器拒（HTTP 409），轨迹也会乱。
3. **别在算法里 `time.sleep`**：那会真吃掉 20 分钟的现实预算，网页上也看不出原因。
   需要放慢节奏就用 `config.json` 里的 `debug.delay`，或者用控制台的断点单步。

## 可选：让网页显示各频道的定位结果

`trace_client.final_state()` 会读算法对象的 `state` 属性（可选）。写成
`{频道号: 状态对象}`，状态对象里认这几个字段（缺失就当作没有）：

`known`（是否测到过信号）、`cleared`、`n_bearings`、`n_no_signal`、
`near_at`、`center`（估计点 (x, y)）、`radius`（保证误差界）。

有了 `center` / `radius`，地图上会画出"定位结果（圆 = 保证误差界）"，
"频道终态"表格里也会填上"定位结果(估计点 ± 保证误差)"一列；没有这个属性不影响运行。

## 常见问题

- **下拉框里没有我的算法**：文件名以 `_` 开头会被跳过；或者模块里没有同时定义
  `SPEC`（必须是 `AlgorithmSpec` 实例）与 `build`。启动时会打印导入错误。
- **两个算法 id 撞了**：`load_all()` 会直接报错并指出冲突的模块名。
- **参数没生效**：参数是"覆盖模块级常量"的方式实现的，键名要在 `build()` 的
  `mapping` 里；用 `--params '{"ring_r":1200}'` 试一下，跑完看网页上的轨迹即可确认。
- **动作数暴涨**：加密行为日志有 2MB 上限、幂等记录也有上限（HTTP 429）。
  新算法如果一局要发几千条指令，先在演练里量一下日志大小。

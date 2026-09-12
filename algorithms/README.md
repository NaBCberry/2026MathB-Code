# 算法注册表：怎么加、怎么改、怎么切

## 它是干什么的

`algorithms/` 下的每个 `.py` 文件就是一个可选算法。注册表自动扫描这个目录，
把带 `SPEC` 与 `build` 的模块列进网页控制台的"算法"下拉框，以及命令行的
`--algorithm` 参数。**加算法不用改网页、不用改注册表本身。**

当前有：

| id | 名称 | 题目 | 实现位置 |
| --- | --- | --- | --- |
| `p3-baseline` | 第三题初版算法 | 问题3 | `algorithms/p3_baseline.py: InterferenceHunter` |
| `p4-directional` | 第四题导航算法 | 问题4 | `algorithms/p4_directional.py: P4Hunter` |
| `p4-v2-receding` | 第四题 v2 滚动时域算法 | 问题4 | `algorithms/p4_v2_receding.py: P4V2Hunter` |
| `p4-wxm-v1` | 第四题定向鲁棒算法 | 问题4 | `algorithms/p4_wxm_v1.py: InterferenceHunter` |
| `p4-wxm-v2` | 第四题定向鲁棒算法 v2（29 站） | 问题4 | `algorithms/p4_wxm_v2.py: InterferenceHunter` |

## 把队友交付的算法接进来（最小改动）

队友给一个 `.py` 丢进 `algorithms/` 之后，通常只需要动**登记块**三行，算法本体一行不用改：

1. `SPEC.id` 换成全局唯一的（别和现有算法重名）。**这是最容易踩的坑**：一旦 `id` 抄成
   别人的，注册表会按"重复 id"把整个模块跳过，网页上只留一条 ⚠ 告警，下拉框里看不到它。
2. `SPEC.name` 写清楚（同题多套算法时，名字里带上作者/版本，方便在网页下拉里区分）。
3. `SPEC.entry` 指向**他自己的文件**，别留着从别人那里复制来的路径。

再确认两件事：`build(sim, params=None, *, verbose=False)` 签名一致、返回的对象有
`run()`；动作全部走注入的 `sim`。参数覆盖那套（把 params 写回模块级常量）他的
`build()` 里一般已经写好了，不用重复实现。

> 注：队友的文件如果被编辑器标了**只读属性**，改之前先去掉
> （PowerShell：`Set-ItemProperty <文件> -Name IsReadOnly -Value $false`）。

### 第四题现有三套算法 + 一条对照基线（离线模拟器，自动生成定向源）

| 算法 | 清除比例 | 平均定位清除时间 | 平均 measure | 说明 |
| --- | --- | --- | --- | --- |
| `p3-baseline`（第三题算法跑第四题环境） | 74% | 437 s | 124 | 对照基线：它的停止判据在定向源下不成立 |
| `p4-directional` | 99.83%（100 例） | 642 s | 300 | 25 站包围布站 + 自适应逼近 + `/clear` 铺清兜底 |
| `p4-wxm-v1` | **100%**（50 例） | 749 s | 379 | 队友方案：35 站三环布站（独立复核：10.1 万组位置×方向零漏检） |
| `p4-wxm-v2` | 99.69%（50 例，2 个源没清掉） | 665 s | 320 | 队友方案精简版：29 站（原点+900m×10+1830m×18，独立复核 305 万组零漏检），里程更省 |
| `p4-v2-receding` | 100%（10 例，样本还少） | 593 s | 296 | 滚动时域版本 |

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

**离线第四题环境已经就绪**，写算法时不用等模拟器：

```bash
# 第四题环境自测（全向 + 定向混合）
python robot.py --robot-id demo --dry-run --cases 20 --problem 4 --algorithm <你的id>

# 网页里：调试控制台最左"离线题目"选"第四题"，再点"生成新案例/离线案例"
python webui.py --serve-only
```

用第三题那套（`p3-baseline`）跑第四题环境时，清除比例只有 **60%~80%**——因为它的
停止判据依赖"处处无信号 ⇒ 该频道不存在"，而定向源的 `no_signal` 可能只是"不在覆盖
角度内"，这条推理在第四题不成立（见上面的改造点 2）。`--dry-run --problem 4`
正好可以量化这个差距，当作对照基线。

上面三条已经实现在 **`algorithms/p4_directional.py`（p4-directional）** 里，
离线 100 例的清除比例 **99.83%**（对照：p3-baseline 跑第四题环境约 74%）。

## 第四题的停止判据（"完全覆盖"的定向版）

第三题的停止判据是"做过无信号检测的测站，其 1000 m 圆盘盖满全区"。第四题不能照抄，
因为定向源的 `no_signal` 还可能是"在盲区"，但**可以把它升级成"包围"**：

> 对区域内每一点 p，p 必须落在"距 p ≤ 1000 m 的**无信号测站**"的**凸包**内。

理由：若 p 在凸包里，任何发射方向都会至少罩住其中一个测站（半平面是凸的，不可能把
凸包里的 p 隔在外面），与它返回 `no_signal` 矛盾。这是"确保全部清除"在第四题里
唯一可执行的版本，`P4Hunter._exclusion_ok()` 就是它。

### 边界必要条件（更直观、也更好查）

把上面的条件只看**圆上各点 + 朝外方向**，就得到一个廉价的必要条件：

> 对圆上每一点 p，**向外切线半平面** `{s : (s−p)·p̂ ≥ 0}` 与 `|s−p| ≤ 1000 m` 的
> 交集里，至少要有一个测站。

否则一个位于边界、朝外发射的定向源就永远测不到——区域内部的任何点都满足
`(s−p)·p̂ < 0`，这正是"外环不能省"的原因。实测（720 个边界点）：

| 布站 | 不满足的边界点数 | 全域漏检率 |
| --- | --- | --- |
| 内层 13 站 | 720 / 720 | 5.97% |
| 内层 13 + 外环 6 站 | 270 / 720 | 0.13% |
| 内层 13 + 外环 **12 站**（当前） | **0 / 720** | **0.00%** |

外环半径 1900 m 时，"有测站在向外半平面内"要求最近的外环站与边界点的夹角
`|Δθ| ≤ arccos(1800/1900) = 18.6°`，即外环间距 ≤ 37°、至少 10 站；12 站（30°）
留了余量。**但边界条件只是必要条件**：从 25 站里随便摘掉一个内层站，边界条件仍然
满足（0/720），全域却出现 0.02%~2.25% 的漏检。所以 `_exclusion_ok()` 拿它当**快速
预筛**（先过边界、再算全域凸包），而不是最终的停止判据。每局结束时会输出
`布站自检：边界 720 点向外切线均有测站` 这一行，方便写论文时直接引用。

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

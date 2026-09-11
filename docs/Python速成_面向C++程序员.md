# Python 速成 · 面向 C++ 程序员

> 为 2026 CUMCM B 题（无线电干扰源定位与清除）配套编写
> 目标：**30 分钟能读懂本项目全部代码，2 小时能自己写 `robot.py` 的策略**
> 配套阅读：`docs/编程手册.md`（协议与接口速查）

---

## 怎么用这份文档

| 部分 | 内容 | 什么时候看 |
|---|---|---|
| **Part 1** | 速成正文，逐个概念对照 C++ | 先通读一遍（约 30 分钟） |
| **Part 2** | 速查表（语法 / 容器 / 字符串 / 内置函数 / math） | 写代码时随手查 |
| **Part 3** | 编写辅助手册（规范、调试、报错对照、项目骨架） | 动手写 `robot.py` 时看 |
| **Part 4** | 本项目常用代码片段（几何计算等） | 直接复制 |

> **不想读长文？** 直接跳到 **Part 3.8「与 C++ 的 20 个致命差异」**，那是最容易踩的坑。

---

# Part 1　速成正文

## 1.1 变量：标签，不是盒子

```cpp
// C++：声明类型，分配盒子
int x = 5;
```

```python
# Python：没有声明，名字只是贴在对象上的标签
x = 5
x = "现在可以是字符串"
x = [1, 2, 3]
```

**关键差异**：C++ 的变量是"装值的盒子"，Python 的名字是"贴在对象上的标签"。所以：

```python
a = [1, 2, 3]
b = a            # ← 不是拷贝！a 和 b 指向同一个 list
b.append(4)
print(a)         # [1, 2, 3, 4]  ← a 也变了！
```

C++ 里 `vector<int> b = a;` 是**深拷贝**，Python 里 `b = a` 是**加一个别名**。要拷贝必须显式：

```python
b = a.copy()            # 浅拷贝（等价 a[:] 或 list(a)）
b = list(a)             # 同上
import copy
b = copy.deepcopy(a)    # 深拷贝（嵌套结构用这个）
```

**整数是无限的**（没有溢出）：

```python
print(2 ** 100)     # 1267650600228229401496703205376
```

## 1.2 缩进就是语法——没有花括号

```cpp
if (x > 0) {
    y = 1;
} else {
    y = 2;
}
```

```python
if x > 0:
    y = 1
else:
    y = 2
```

规则：

- **冒号 `:`** 开启一个块，**缩进**决定块的范围，块结束靠"缩进退回去"
- 官方风格：**每级 4 个空格**（本项目 `.vscode/settings.json` 已配好 `editor.insertSpaces: true`）
- **绝对不要混用 Tab 和空格** → `TabError`
- 空块不能留空，要写 `pass`

```python
if x > 0:
    pass          # ← 占位，什么都不做
```

**没有块作用域**——这是 C++ 程序员最容易忽略的：

```cpp
for (int i = 0; i < 3; ++i) { }
// cout << i;   // ❌ 编译错误，i 出了作用域就没了
```

```python
for i in range(3):
    pass
print(i)          # ✅ 2 —— i 泄漏到外层了
```

## 1.3 语句结尾与其它基础

| C++ | Python |
|---|---|
| 语句结尾 `;` | **换行**（`;` 可写但没人写） |
| `int x = 5;` | `x = 5` |
| `i++` / `++i` | ❌ 不存在 → `i += 1` |
| `const int N = 20;` | `N = 20`（约定全大写 = "别改"） |
| `nullptr` | `None` |
| `true` / `false` | `True` / `False` |
| `// 注释`、`/* */` | `# 注释`（`"""..."""` 当多行字符串用） |
| `x ? a : b` | `a if x else b` |

一行写多条语句用 `;`：

```python
a = 1; b = 2      # 合法，但不推荐
```

## 1.4 运算符

| 运算 | C++ | Python | 注意 |
|---|---|---|---|
| 除法 | `7 / 2 == 3`（int 除 int） | `7 / 2 == 3.5` | **Python 的 `/` 永远返回 float** |
| 整除 | `7 / 2` | `7 // 2 == 3` | |
| 取模 | `7 % 2 == 1` | `7 % 2 == 1` | |
| 幂 | `pow(2,10)` | `2 ** 10` | |
| 逻辑与 | `&&` | `and` | |
| 逻辑或 | `\|\|` | `or` | |
| 逻辑非 | `!` | `not` | |
| 位运算 | `& \| ^ ~ << >>` | 一样 | 但**优先级不同**，建议加括号 |
| 相等 | `==` | `==`（**值**相等） | 另有 `is`（**同一对象**） |
| 不等于 | `!=` | `!=` | |

**⚠️ 负数整除 / 取模与 C++ 不同**（C++ 向零截断，Python 向下取整）：

```python
-7 // 2       # -4   （C++ 是 -3）
-7 % 2        #  1   （C++ 是 -1）
```

**⚠️ `is` 和 `==` 不要混用**：

```python
a = [1, 2]
b = [1, 2]
a == b        # True  —— 值相等
a is b        # False —— 不是同一个对象

x = None
if x is None:     # ✅ 判 None 一律用 is
    ...
if x == None:     # ⚠️ 能跑，但不是好习惯
    ...
```

## 1.5 真假值（truthy / falsy）

Python 里**任何对象**都能当条件用。以下都是**假**：

```python
False, None, 0, 0.0, "", [], {}, set(), tuple()
```

```python
if my_list:            # ✅ 空列表 → False，非空 → True
    print("有内容")

if len(my_list) > 0:   # 也能用，但不够 Pythonic
    ...
```

**注意 `0` 是假**——数值判断要写清楚：

```python
speed = 0
if speed:              # ❌ 0 会被当假，逻辑错！
    ...
if speed > 0:          # ✅ 明确
    ...
```

## 1.6 四种常用容器

| C++ | Python | 有序 | 可变 | 可重复 | 字面量 |
|---|---|---|---|---|---|
| `std::vector<T>` | `list` | ✅ | ✅ | ✅ | `[1, 2, 3]` |
| `std::tuple<A,B>` | `tuple` | ✅ | ❌ | ✅ | `(1, 2)` |
| `std::unordered_map<K,V>` | `dict` | ✅(3.7+ 插入序) | ✅ | 键唯一 | `{"a": 1}` |
| `std::unordered_set<T>` | `set` | ❌ | ✅ | ❌ | `{1, 2, 3}` |

### list（≈ vector）

```python
xs = [3, 1, 2]
xs.append(4)          # push_back
xs.pop()              # pop_back → 返回 4
xs.pop(0)             # 删除下标 0
xs.insert(0, 99)      # 在 0 位置插入
xs[0]                 # 读
xs[-1]                # 读最后一个！（负数下标，C++ 没有）
len(xs)               # size()
xs.sort()             # 就地排序（类似 std::sort）
ys = sorted(xs)       # 返回排序后的新 list，不改原表
xs.sort(key=lambda v: -v)   # 按自定义键排，等价 C++ 的 comp lambda
99 in xs              # 包含判断（O(n)）
xs + [5, 6]           # 拼接（新 list）
xs * 3                # 重复
sum(xs), max(xs), min(xs)
```

### tuple（定长的、不可变的）

```python
p = (300.0, 400.0)
x, y = p              # ← 解包（C++ 的 std::tie / 结构化绑定）
dx, dy = (1, 2)
```

**注意单元素 tuple 要加逗号**：

```python
t = (1)      # ❌ 这是整数 1
t = (1,)     # ✅ 这才是 tuple
```

### dict（≈ unordered_map）

```python
d = {"x": 300, "y": 400}
d["x"]                # 读，键不存在 → KeyError
d.get("z")            # ✅ 键不存在返回 None，不报错
d.get("z", 0)         # ✅ 键不存在返回默认值 0
d["z"] = 5            # 写入/覆盖
del d["z"]            # 删除
"x" in d              # 键存在判断
d.keys(), d.values(), d.items()    # 键 / 值 / (键,值) 对的视图
for k, v in d.items():             # ← 遍历键值对（C++ 的结构化绑定）
    print(k, v)
```

**JSON 就是这个结构**——所以模拟器响应天生就是 dict：

```python
r = sim.measure(0, 0, 1)          # r 是 dict
r["measure_result"]               # 'direction' / 'near' / 'no_signal'
r.get("svd_deg")                  # 只有 direction 时才有这个键 → 用 get 更安全
```

### set（≈ unordered_set）

```python
s = {1, 2, 3}
s.add(4)
s.discard(1)          # 删除（不存在也不报错）；remove 会报错
a | b                 # 并集
a & b                 # 交集
a - b                 # 差集
```

## 1.7 字符串

**字符串是不可变的**——所有"修改"都返回新字符串：

```python
s = "hello"
s.upper()             # 返回 "HELLO"，s 本身没变
s = s.upper()         # 要改就得重新赋值
```

常用方法（都返回新值）：

```python
s.strip()             # 去首尾空白
s.split(",")          # 切分成 list
",".join(["a", "b"])  # 拼成 "a,b"    ← 注意是「分隔符.join(列表)」
s.replace("a", "b")
s.startswith("he"), s.endswith("lo")
s.find("ll")          # 返回下标，找不到返回 -1
s.lower() / s.upper()
s.zfill(5)            # "42" → "00042"
len(s)
```

### f-string（最常用的格式化手段）

```python
name, n = "频道", 7
print(f"正在检测 {name} {n}")          # 正在检测 频道 7
print(f"{3.14159:.2f}")                # 3.14      保留 2 位小数
print(f"{n:03d}")                      # 007       补零到 3 位
print(f"{n:>6}")                       #      7    右对齐宽 6
print(f"{0.1234:.1%}")                 # 12.3%     百分比
print(f"{1234567:,}")                  # 1,234,567
print(f"{x=}")                         # x=42      ← 调试神器，3.8+ 自动打印变量名
```

对照 C++ 的 `std::format` / `printf`：

| C++ | Python |
|---|---|
| `printf("%.2f", v)` | `f"{v:.2f}"` |
| `printf("%d", n)` | `f"{n}"` 或 `f"{n:d}"` |
| `printf("%03d", n)` | `f"{n:03d}"` |
| `std::to_string(n)` | `str(n)` |
| `std::stoi(s)` | `int(s)` |
| `std::stod(s)` | `float(s)` |

## 1.8 控制流

**`if` / `elif` / `else`**（注意是 `elif` 不是 `else if`）：

```python
if x > 0:
    ...
elif x == 0:
    ...
else:
    ...
```

**没有 C 风格 for**，只有 `for ... in ...`：

```cpp
for (int i = 0; i < 10; ++i) { ... }
```

```python
for i in range(10):           # 0..9
    ...

for i in range(2, 10, 3):     # 2, 5, 8      (start, stop, step)
    ...

for v in [3, 1, 2]:           # 直接遍历元素
    ...

for i, v in enumerate([3, 1, 2]):     # 同时拿下标和值
    print(i, v)                # 0 3 / 1 1 / 2 2

for a, b in zip([1, 2], [3, 4]):      # 并行遍历（C++ 没有直接对应）
    print(a, b)                # 1 3 / 2 4

for k, v in d.items():        # 遍历字典
    ...
```

`range(a, b)` **左闭右开**：`range(0, 5)` → 0,1,2,3,4（跟 C++ 的 `i < n` 一致）。

**`while`** 与 C++ 相同：

```python
while not done:
    ...
    if timeout:
        break
else:                 # ← 循环没被 break 过才执行（很少用）
    ...
```

`break` / `continue` 用法与 C++ 相同。

**没有 `switch`**（3.10+ 有 `match`，本项目用不上，用 `if/elif` 就行）。

## 1.9 函数

```python
def 函数名(参数: 类型 = 默认值, *args, 命名参数=默认值, **kwargs) -> 返回类型:
    return 值
```

详细对照见 `docs/编程手册.md` 附录 B。这里只列最容易错的：

```python
def f(a, b=0):
    return a + b

f(1, 2)          # ✅ 位置传参
f(1, b=2)        # ✅ 命名传参（C++ 没有）
f(a=1, b=2)      # ✅
f(b=2, a=1)      # ✅ 顺序无关
```

**⚠️ 可变默认参数（Python 特有陷阱）**：

```python
def bad(x, acc=[]):          # ❌ 默认值只求值一次，所有调用共享同一个 list
    acc.append(x)
    return acc

def good(x, acc=None):       # ✅ 标准写法
    if acc is None:
        acc = []
    acc.append(x)
    return acc
```

**返回多个值**其实是返回 tuple：

```python
def divmod2(a, b):
    return a // b, a % b     # 返回一个 tuple

q, r = divmod2(7, 2)         # 解包
```

## 1.10 类

```cpp
class Dog {
    int x;
public:
    Dog(int x) : x(x) {}
    int bark() { return x; }
};
```

```python
class Dog:
    def __init__(self, x):        # 构造函数（第一参数必须是 self）
        self.x = x                # 成员变量不需要声明，赋值即创建

    def bark(self):               # self 必须显式写在参数表
        return self.x
```

```python
d = Dog(3)
d.bark()                          # 自动把 d 传给 self
```

| C++ | Python |
|---|---|
| `this` 隐式 | `self` 显式，必须是第一个参数 |
| `class A { public: int x; };` | `self.x = ...`（在 `__init__` 里赋值） |
| `private:` / `protected:` | 无关键字；约定 `_x` 表示"内部用"（只是约定） |
| `static int f();` | `@staticmethod` |
| 运算符重载 `operator+` | `__add__`、`__len__` 等**双下划线方法** |
| `std::cout << obj` | `def __repr__(self)` |
| 拷贝构造 / `=` | `__copy__` / `__deepcopy__`（少用） |
| 虚函数 / 多继承 | 普通方法默认可覆写；`class A(B):` 继承 |

本项目的 `SimulatorClient` 就是这个结构：

```python
class SimulatorClient:
    def __init__(self, robot_id, base_url=BASE_URL, *, timeout=5.0, log_dir=None):
        self.robot_id = robot_id           # 存成成员变量
        self._seq = 0                      # 下划线开头 = 内部用
        ...
    def measure(self, x, y, channel):
        ...
```

## 1.11 异常（≈ try/catch）

```cpp
try { ... }
catch (const std::runtime_error& e) { ... }
```

```python
try:
    x = int("abc")
except ValueError as e:        # 只捕获这个类型的异常
    print("转换失败", e)
except (KeyError, IndexError): # 多个类型一起捕获
    ...
except Exception as e:         # 兜底（≈ catch(...)，但能拿到对象）
    ...
else:
    ...                        # 没出异常才执行（少用）
finally:
    ...                        # 无论如何都执行（≈ C++ 的 finally，但 Python 更常用 with）
```

**主动抛异常**：

```python
raise ValueError(f"channel 必须是 1..20，收到 {channel}")
```

**常用内置异常**（对照 C++）：

| Python | 类比 C++ | 何时出现 |
|---|---|---|
| `ValueError` | `std::invalid_argument` | 类型对但值不对，如 `int("abc")` |
| `TypeError` | 编译期就拦住了 | 类型不匹配，如 `1 + "a"` |
| `KeyError` | `map::at` 抛的 | 字典键不存在 |
| `IndexError` | 越界（C++ 是 UB） | 下标越界 |
| `AttributeError` | 空指针解引用 | 访问不存在的属性 |
| `ZeroDivisionError` | 除零（C++ 是 UB） | 除以 0 |
| `FileNotFoundError` | 打开文件失败 | |
| `RuntimeError` | `std::runtime_error` | 通用运行时错误 |

**EAFP 风格**：Python 倾向于"先做了再说，出错再处理"，而不是 C++ 的"先检查再做"。

```cpp
// C++：先检查（LBYL）
if (m.count(key)) { v = m[key]; }
```

```python
# Python：先尝试（EAFP）
try:
    v = m[key]
except KeyError:
    v = default

# 或者用更 Pythonic 的写法
v = m.get(key, default)
```

## 1.12 模块与导入

```python
import math                        # 用 math.pi
from math import pi, sqrt          # 直接用 pi
from pathlib import Path           # 最常用
import numpy as np                 # 起别名
from sim_client import SimulatorClient, BASE_URL   # 导入自己写的模块
```

**没有头文件**。`import sim_client` 就是去找 `sim_client.py`（当前目录下）。

**`if __name__ == "__main__":`** 是本项目每个脚本结尾的固定套路：

```python
def main():
    ...

if __name__ == "__main__":    # ← 直接运行本文件时才执行
    main()                    #   被别的文件 import 时不执行
```

## 1.13 推导式（写起来很快，读起来也快）

C++ 里要写循环的事，Python 一行搞定：

```python
xs = [1, 2, 3, 4, 5]

squares = [x * x for x in xs]              # [1, 4, 9, 16, 25]
evens   = [x for x in xs if x % 2 == 0]    # [2, 4]
d = {x: x * x for x in xs}                 # {1:1, 2:4, ...}
s = {x % 3 for x in xs}                    # {0, 1, 2}

# 等价于
squares = []
for x in xs:
    squares.append(x * x)
```

对照 C++20：

```cpp
auto evens = xs | std::views::filter([](int x){ return x % 2 == 0; });
```

**别写太复杂**——超过一层 `for` + 一个 `if` 就老老实实写循环。

## 1.14 切片（C++ 没有，非常好用）

```python
xs = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]

xs[2:5]      # [2, 3, 4]        左闭右开
xs[:3]       # [0, 1, 2]        从头
xs[7:]       # [7, 8, 9]        到尾
xs[-3:]      # [7, 8, 9]        最后 3 个
xs[::2]      # [0, 2, 4, 6, 8]  隔一个取
xs[::-1]     # [9, 8, ..., 0]   反转（经典技巧）

s = "abcdef"
s[1:4]       # "bcd"
```

`range` 也可以：`list(range(10))[::3]` → `[0, 3, 6, 9]`。

## 1.15 `with` 语句（≈ RAII）

C++ 用 RAII 自动释放资源，Python 用 `with`：

```cpp
{
    std::ofstream f("a.txt");
    f << "hello";
}   // ← 出作用域自动关闭
```

```python
with open("a.txt", "w", encoding="utf-8") as f:
    f.write("hello")
# ← 出块自动关闭，即使中间抛异常也会关
```

本项目里：

```python
with SimulatorClient(robot_id, log_dir="logs") as sim:
    sim.enter()
    ...
# ← 出块自动补一次 /exit 并关闭日志文件
```

能这么用，是因为类实现了 `__enter__` / `__exit__`。

## 1.16 迭代器与生成器（了解即可）

```python
for line in open("a.txt", encoding="utf-8"):    # 大文件不用一次读进内存
    print(line)
```

```python
def count_up(n):
    for i in range(n):
        yield i          # ← yield 让函数变成"生成器"，每次产出一个值

for v in count_up(3):
    print(v)
```

C++ 里对应的概念是输入迭代器 / `std::generator`（C++23）。本项目基本用不到，知道 `for x in something` 可以遍历任何可迭代对象就行。

## 1.17 装饰器（知道长什么样就行）

```python
@staticmethod
def f():
    ...

@dataclass
class Point:
    x: float
    y: float
```

`@xxx` 放在函数/类定义上面，作用是"包装"它。等价于 `f = xxx(f)`。

本项目里会见到 `@staticmethod`（≈ C++ 静态成员函数）。

---

# Part 2　速查表

## 2.1 语法骨架

```python
# ── 变量 ──
x = 1                # 无声明
x, y = 1, 2          # 多重赋值
a = b = 0            # 链式

# ── 判断 ──
if cond:
    ...
elif cond2:
    ...
else:
    ...

# ── 循环 ──
for i in range(10):            # 0..9
for i in range(1, 11):         # 1..10
for i in range(0, 100, 5):     # 0,5,...,95
for x in seq:
for i, x in enumerate(seq):
for a, b in zip(s1, s2):
while cond:

# ── 函数 ──
def f(a, b=0, *args, c=1, **kwargs) -> int:
    return a + b

# ── 类 ──
class A:
    def __init__(self, x):
        self.x = x
    def m(self):
        return self.x

# ── 异常 ──
try:
    ...
except ValueError as e:
    ...
finally:
    ...

# ── 入口 ──
if __name__ == "__main__":
    main()
```

## 2.2 容器操作

| 操作 | list | tuple | dict | set |
|---|---|---|---|---|
| 建立 | `[1,2]` | `(1,2)` | `{"a":1}` | `{1,2}` |
| 空 | `[]` | `()` | `{}` | `set()` |
| 取元素 | `xs[0]` `xs[-1]` | 同左 | `d["a"]` | — |
| 长度 | `len(xs)` | `len(t)` | `len(d)` | `len(s)` |
| 增 | `xs.append(v)` | ❌ 不可变 | `d[k]=v` | `s.add(v)` |
| 删 | `xs.pop()` `del xs[0]` `xs.remove(v)` | ❌ | `del d[k]` `d.pop(k)` | `s.discard(v)` |
| 查 | `v in xs` | `v in t` | `k in d` | `v in s` |
| 安全查 | — | — | `d.get(k, 默认值)` | — |
| 遍历 | `for v in xs` | 同左 | `for k,v in d.items()` | `for v in s` |
| 排序 | `xs.sort()` / `sorted(xs)` | — | — | — |
| 拷贝 | `xs.copy()` / `copy.deepcopy` | 天然安全 | `d.copy()` | `s.copy()` |

## 2.3 字符串方法（都返回新串，不改自身）

```python
s.strip()  s.lstrip()  s.rstrip()
s.split(",")              # → list
",".join(xs)              # list → str
s.replace(a, b)           # 默认替换全部
s.upper()  s.lower()
s.startswith(p)  s.endswith(p)
s.find(sub)               # 找不到 → -1
s.index(sub)              # 找不到 → 抛 ValueError
s.count(sub)
s.zfill(4)
len(s)
s.isdigit()  s.isalpha()  s.isspace()
```

## 2.4 内置函数（不用 import）

```python
len(x)  abs(x)  round(x, 2)  min(...)  max(...)  sum(xs)
sorted(it, key=..., reverse=True)
reversed(it)  enumerate(it, start=0)  zip(a, b)
list(it)  tuple(it)  set(it)  dict(it)  str(v)  int(v)  float(v)  bool(v)
range(a, b, step)
any(it)  all(it)                # 有任一为真 / 全为真
print(...)  input(...)  type(v)  isinstance(v, T)
```

## 2.5 `math` 模块（本项目高频）

```python
import math

math.pi              # 3.141592653589793
math.e
math.sqrt(x)         # 平方根
math.hypot(dx, dy)   # ★ sqrt(dx²+dy²)，算距离专用
math.atan2(dy, dx)   # ★ 返回弧度，范围 (-π, π]
math.radians(deg)    # 度 → 弧度
math.degrees(rad)    # 弧度 → 度
math.sin/cos/tan(x)  # x 是弧度！不是角度！
math.floor(x)  math.ceil(x)  math.trunc(x)
math.isclose(a, b, rel_tol=1e-9)    # ★ 浮点比较
math.inf             # 无穷大
math.nan             # 非数
```

**⚠️ 三角函数吃弧度不吃角度**：

```python
df = 90
dx = math.cos(df)           # ❌ 错！把 90 当弧度算
dx = math.cos(math.radians(df))   # ✅
```

**⚠️ 浮点数不要用 `==` 比**：

```python
if a == b:                          # ❌ 0.1+0.2 != 0.3
if math.isclose(a, b, abs_tol=1e-9):  # ✅
```

## 2.6 常用标准库

```python
import json                                   # JSON 读写
json.loads('{"a":1}')                         # str → dict
json.dumps(d, ensure_ascii=False, indent=2)   # dict → str（中文不转义）

from pathlib import Path                      # 路径（优于 os.path）
p = Path("logs") / "a.jsonl"                  # 用 / 拼路径
p.parent.mkdir(parents=True, exist_ok=True)
p.exists()  p.read_text(encoding="utf-8")  p.write_text("x", encoding="utf-8")

import argparse                               # 命令行参数
import time
time.time()  time.sleep(0.1)  time.strftime("%Y%m%d-%H%M%S")
import random
random.random()  random.uniform(a, b)  random.choice(seq)  random.shuffle(xs)
import itertools
itertools.product(a, b)                       # 笛卡尔积
import collections
collections.Counter(xs)  collections.defaultdict(list)
```

---

# Part 3　编写辅助手册

## 3.1 命名规范（PEP 8）

| 对象 | 风格 | 例 |
|---|---|---|
| 变量 / 函数 | `snake_case` | `robot_id`, `parse_args` |
| 常量 | `UPPER_SNAKE` | `BASE_URL`, `MOVE_SPEED_MPS` |
| 类 | `PascalCase` | `SimulatorClient` |
| 内部用 | 前导下划线 | `self._seq`, `_payload` |
| 模块 / 文件 | `snake_case.py` | `sim_client.py` |

C++ 的 `camelCase` / `mCamelCase` / `kConstant` 在 Python 里都不用。

## 3.2 本项目代码风格约定

- **每级 4 空格缩进**（已在 `.vscode/settings.json` 配好）
- **文件编码 UTF-8**，中文注释直接写，不用转义
- **文件结尾必须有换行**
- 函数之间**空 2 行**，类方法之间**空 1 行**
- **行宽 ≤ 100 字符**
- 类型标注**能写就写**，但别为它纠结（详见 `编程手册.md` 附录 A）
- 每次调用模拟器接口都**必须**留下日志（`sim_client` 已自动做）

## 3.3 调试三板斧

### ① `print` 大法（最实用）

```python
print(f"{x=} {y=}")                     # 自动打印变量名和值
print(f"测量结果={r['measure_result']} 虚拟时刻={r['virtual_time_s']}")
```

### ② `breakpoint()` 断点（≈ C++ 的 `__debugbreak()`）

```python
for i in range(100):
    do_something(i)
    if i == 7:
        breakpoint()      # ← 程序在这里暂停，进入调试器
```

暂停后可以：

| 命令 | 作用 |
|---|---|
| `n` | 下一行（step over） |
| `s` | 进入函数（step into） |
| `c` | 继续（continue） |
| `p 表达式` | 打印表达式的值（print） |
| `pp 表达式` | 漂亮打印 |
| `w` | 打印调用栈（where） |
| `l` | 列出当前附近代码（list） |
| `q` | 退出调试 |

### ③ VSCode 图形断点（推荐）

- 在行号左边**点一下**就是断点（红点）
- **F5** 启动调试
- **F10** 单步跳过、**F11** 单步进入、**F5** 继续
- 左侧"变量"面板看当前所有变量，"监视"面板加自定义表达式
- **Shift+F5** 停止

本项目已配好 4 套 F5 配置（见 `编程手册.md` 1.4）。

## 3.4 报错信息对照表

| 报错 | 意思 | 怎么修 |
|---|---|---|
| `IndentationError: expected an indented block` | 该缩进的地方没缩进 | 冒号后面要缩进 |
| `TabError: inconsistent use of tabs and spaces` | Tab 和空格混用 | 全文替换成 4 空格（VSCode 右下角可"转换缩进"） |
| `SyntaxError: invalid syntax` | 语法错 | 看**上一行**是不是漏了括号/冒号 |
| `NameError: name 'x' is not defined` | 变量没定义 / 拼错 | 检查拼写、检查是否忘了 `import` |
| `UnboundLocalError` | 函数里给外部变量赋值了，它变成局部变量 | 加 `global x` 或改设计（**强烈建议改设计**） |
| `TypeError: unsupported operand type(s) for +: 'int' and 'str'` | 类型不匹配 | `1 + "2"` → `1 + int("2")` |
| `TypeError: 'NoneType' object is not subscriptable` | 对 `None` 取了下标 | 函数返回了 `None`（多半是 `dict.get()` 没给默认值） |
| `KeyError: 'svd_deg'` | 字典没这个键 | 先判 `measure_result == "direction"`，或用 `.get()` |
| `IndexError: list index out of range` | 越界（C++ 是 UB，Python 会报错——**这是好事**） | 检查下标范围；`xs[-1]` 是最后一个 |
| `AttributeError: 'dict' object has no attribute 'measure_result'` | 把 dict 当对象用 | 用 `d["measure_result"]` |
| `ValueError: could not convert string to float: 'abc'` | 转换失败 | 先校验格式，或 `try/except` |
| `ZeroDivisionError` | 除以 0 | 加判断 |
| `FileNotFoundError` | 文件/目录不存在 | 用 `Path(...).parent.mkdir(parents=True, exist_ok=True)` |
| `ModuleNotFoundError: No module named 'xxx'` | 没装库 / 文件名写错 | `python -m pip install xxx` |
| `RecursionError: maximum recursion depth exceeded` | 递归太深 | 改成循环，或加记忆化 |
| `KeyboardInterrupt` | 你按了 Ctrl+C | — |

## 3.5 与 C++ 的 20 个致命差异（★ 收藏这段）

| # | C++ | Python | 坑 |
|---|---|---|---|
| 1 | `b = a` 是深拷贝 | `b = a` 只是**加别名** | 改 `b` 会改到 `a`！要拷必须 `.copy()` |
| 2 | `for(int i=0;i<n;++i)` | `for i in range(n)` | 没有 `i++`，用 `i += 1` |
| 3 | `7/2 == 3` | `7/2 == 3.5` | 整除要写 `7 // 2` |
| 4 | `-7/2 == -3` | `-7//2 == -4` | 负数整除/取模方向不同 |
| 5 | `{}` 块，循环变量出块即销毁 | 缩进定块，**循环变量泄漏到外层** | 循环后 `i` 还在 |
| 6 | `default: vector<int> v = {}`（每次调用求值） | 默认参数**只求值一次** | `def f(acc=[])` 是灾难 |
| 7 | 重载函数名可以相同 | **不能重载**，后者覆盖前者 | |
| 8 | `nullptr` | `None` | 判空用 `is None`，不是 `==` |
| 9 | `0` 和 `false` 是不同东西但可互换 | 空容器、空串、`0` **统统是假** | `if count:` 在 count=0 时是假 |
| 10 | `a == b` 比内容 | `==` 比内容，`is` 比身份 | 判 `None` 用 `is`，判数值用 `==` |
| 11 | 函数内赋值不影响外部 | **在函数里赋值就变成局部变量** | `UnboundLocalError`；改设计别用 `global` |
| 12 | 编译期检查类型 | **运行到那行才报错** | 多写 `print`、多跑 |
| 13 | `catch(...)` 兜底常见 | **别乱用 `except Exception`** | 会吞掉自己的 bug，让调试变难 |
| 14 | 数组越界是 UB | 抛 `IndexError` | 这是 Python 的优势，别怕 |
| 15 | 没有内建字典字面量 | `{"k": v}` 直接写 | 天然对应 JSON |
| 16 | `std::sort(v.begin(), v.end())` | `v.sort()`（就地） / `sorted(v)`（新表） | 别把返值当原地操作 |
| 17 | 字符串是 `char` 数组 | 字符串**不可变** | `s[0] = 'x'` 报错，要 `s = "x" + s[1:]` |
| 18 | `x ? a : b` | `a if x else b` | 顺序反过来了 |
| 19 | `&&` `\|\|` `!` | `and` `or` `not` | 混着写会 `SyntaxError` |
| 20 | 花括号 `{}` 定块 | **冒号 + 缩进** | Tab/空格混用直接崩 |

## 3.6 `robot.py` 推荐骨架

```python
# -*- coding: utf-8 -*-
"""机器狗搜索 / 定位 / 清除策略。"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass, field

from sim_client import BASE_URL, SimulatorClient

# ── 常量（题目给定，别改）──────────────────────────
MOVE_SPEED_MPS = 5.0
MEASURE_ACTION_S = 5.0
CHANNEL_SWITCH_S = 1.0
CLEAR_RADIUS_M = 20.0
NEAR_THRESHOLD_M = 5.0
ARENA_RADIUS_M = 1800.0
CHANNELS = range(1, 21)


# ── 数据结构 ─────────────────────────────────────
@dataclass
class Target:
    """一个待处理/已处理的干扰源。"""
    channel: int
    pos: tuple[float, float] | None = None      # 估计位置，None = 还没定位
    cleared: bool = False
    bearings: list[tuple[tuple[float, float], float]] = field(default_factory=list)


# ── 世界模型（策略层自己维护，sim_client 不管这些）──
class World:
    def __init__(self) -> None:
        self.pos: tuple[float, float] = (0.0, 0.0)   # 机器狗当前坐标
        self.channel: int = 1                         # 测向机当前频道
        self.vtime: float = 0.0                       # 虚拟时刻
        self.targets: dict[int, Target] = {c: Target(c) for c in CHANNELS}

    def move_cost(self, x: float, y: float) -> float:
        return math.hypot(x - self.pos[0], y - self.pos[1]) / MOVE_SPEED_MPS


# ── 动作封装：每个动作都同步世界模型 ──────────────
class Robot:
    def __init__(self, sim: SimulatorClient) -> None:
        self.sim = sim
        self.w = World()

    def measure(self, x: float, y: float, channel: int) -> dict:
        r = self.sim.measure(x, y, channel)
        self.w.pos = (x, y)
        self.w.channel = channel          # ★ 只有 /measure 会改当前频道
        self.w.vtime = r["virtual_time_s"]
        return r

    def clear(self, x: float, y: float, channel: int) -> dict:
        r = self.sim.clear(x, y, channel)
        self.w.pos = (x, y)
        self.w.vtime = r["virtual_time_s"]   # ★ /clear 不改当前频道
        return r


# ── 策略主体 ─────────────────────────────────────
def run(sim: SimulatorClient) -> None:
    print("本局可用现实时间：", sim.enter()["remaining_real_duration_s"], "秒")
    robot = Robot(sim)

    # TODO: ① 全局扫频道建存在性地图
    #       ② 用两点示向度交会定位
    #       ③ 逼近到 20 m 内 /clear
    #       ④ 决定下一个目标（最近邻 / TSP）


# ── 入口（固定套路）───────────────────────────────
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="干扰源自动定位与清除")
    parser.add_argument("--robot-id", required=True, help="参赛队号")
    parser.add_argument("--url", default=BASE_URL, help="模拟器接口地址")
    parser.add_argument("--log-dir", default="logs", help="行为日志目录")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with SimulatorClient(args.robot_id, args.url, log_dir=args.log_dir) as sim:
        run(sim)


if __name__ == "__main__":
    main()
```

> 注意 `World` 里为什么要存 `self.channel`：**`/clear` 不会切换测向机频道**，
> 只有成功的 `/measure` 才会。这个坑写在 `编程手册.md` 的常见坑速查表里。

## 3.7 自测小技巧

写策略时，先用**离线小测试**验证纯计算部分，再连模拟器。

仓库里已经有一份**可直接跑的现成测试：`geom_selftest.py`** —— 它逐条验证了 Part 4 的全部几何函数：

```powershell
python geom_selftest.py
```

```
4.1 dist            OK   (0,0)->(300,400) = 500 m
4.2 bearing         OK   东0/北90/西180/南270/东北45
4.5 intersect       OK   交点/平行/身后 三种情况都对
4.7 least_squares   OK   真值(700.0,-300.0) 估计(696.2,-302.5) 误差 4.6 m
全部通过 ✅
```

自己加一个测试文件也很简单：

```python
# test_geom.py —— 不联网，直接 python test_geom.py
from robot import intersect_bearings, bearing

def main():
    assert abs(bearing((0, 0), (100, 100)) - 45.0) < 1e-9
    p = intersect_bearings((0, 0), 45.0, (200, 0), 135.0)
    assert p is not None and abs(p[0] - 100.0) < 1e-6, p
    print("全部通过")

if __name__ == "__main__":
    main()
```

`assert 条件, 信息` —— 条件不成立就抛 `AssertionError` 并打印信息。

## 3.8 VSCode 快捷键（Python 常用）

| 快捷键 | 作用 |
|---|---|
| `F5` | 开始调试（本项目已配 4 套配置） |
| `Shift+F5` | 停止调试 |
| `F9` | 加/取消断点 |
| `F10` / `F11` | 单步跳过 / 单步进入 |
| `Ctrl+Shift+P` | 命令面板（万能入口） |
| `Ctrl+P` | 快速打开文件 |
| `Ctrl+Shift+F` | 全局搜索 |
| `F2` | 重命名符号（跨文件自动改） |
| `Shift+Alt+F` | 格式化文档 |
| `Ctrl+/` | 注释/取消注释 |
| `Alt+↑/↓` | 上下移动整行 |
| `Shift+Alt+↓` | 向下复制整行 |
| `Ctrl+Shift+O` | 跳到文件内的符号（函数/类） |

---

# Part 4　本项目常用代码片段

> 直接复制到 `robot.py` 用。都符合题目坐标约定：**x 正东，y 正北，方位角正东 0°、逆时针为正、范围 [0°, 360°)**。
>
> ✅ **下面全部函数已被 `geom_selftest.py` 验证过**，可直接 `python geom_selftest.py` 复现。

## 4.1 距离

```python
import math

def dist(p: tuple[float, float], q: tuple[float, float]) -> float:
    """两点直线距离（米）。"""
    return math.hypot(q[0] - p[0], q[1] - p[1])
```

## 4.2 方位角

```python
def bearing(p: tuple[float, float], q: tuple[float, float]) -> float:
    """从 p 指向 q 的方位角，单位度，范围 [0, 360)。"""
    return math.degrees(math.atan2(q[1] - p[1], q[0] - p[0])) % 360.0
```

## 4.3 角度归一化与夹角

```python
def wrap360(a: float) -> float:
    """把角度折到 [0, 360)。"""
    return a % 360.0

def angle_diff(a: float, b: float) -> float:
    """a 相对 b 的最小夹角，范围 [-180, 180)。正数表示 a 在 b 逆时针方向。"""
    return (a - b + 180.0) % 360.0 - 180.0
```

## 4.4 沿方位角前进

```python
def step_from(p: tuple[float, float], bearing_deg: float,
              distance: float) -> tuple[float, float]:
    """从 p 沿方位角 bearing_deg 前进 distance 米后的坐标。"""
    r = math.radians(bearing_deg)
    return (p[0] + distance * math.cos(r), p[1] + distance * math.sin(r))
```

## 4.5 两条示向度射线求交（交会定位核心）

```python
def intersect_bearings(p1: tuple[float, float], a1: float,
                       p2: tuple[float, float], a2: float
                       ) -> tuple[float, float] | None:
    """两条示向度射线的交点。平行或退化时返回 None。

    返回 None 或者 t <= 0 时说明几何不好（两站夹角太小 / 交点在身后），
    应该换检测点重新测。
    """
    d1 = (math.cos(math.radians(a1)), math.sin(math.radians(a1)))
    d2 = (math.cos(math.radians(a2)), math.sin(math.radians(a2)))
    den = d1[0] * d2[1] - d1[1] * d2[0]          # d1 × d2
    if abs(den) < 1e-12:
        return None                               # 平行
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]         # D = S2 - S1
    t = (dx * d2[1] - dy * d2[0]) / den           # (D × d2) / (d1 × d2)
    if t <= 0:
        return None                               # 交点在 S1 背后
    return (p1[0] + t * d1[0], p1[1] + t * d1[1])
```

## 4.6 交会质量评估（选第二个检测点用）

```python
def intersection_quality(a1: float, a2: float) -> float:
    """两条示向度的夹角评分，越接近 90° 越好（返回 sin 值，1.0 为最佳）。

    问题 2 选第二个检测点：让两站示向度夹角尽量接近 90°。
    """
    return abs(math.sin(math.radians(angle_diff(a1, a2))))
```

## 4.7 最小二乘交会（多点定位，比两点更稳）

```python
def locate_least_squares(
    samples: list[tuple[tuple[float, float], float]]
) -> tuple[float, float]:
    """多个检测点的示向度交会：最小化各点到射线的垂距平方和。

    samples: [(检测点坐标, 示向度), ...]，至少 2 组。
    用简单的梯度下降 + 线性求解混合法；数据量小，够用。
    """
    # 初始猜测：两两交会的均值
    guesses = []
    for i in range(len(samples)):
        for j in range(i + 1, len(samples)):
            p = intersect_bearings(*samples[i], *samples[j])
            if p is not None:
                guesses.append(p)
    if not guesses:
        raise ValueError("所有射线两两平行，无法定位")
    x = sum(g[0] for g in guesses) / len(guesses)
    y = sum(g[1] for g in guesses) / len(guesses)

    # 高斯-牛顿迭代（每步解 2x2 法方程）
    for _ in range(50):
        a11 = a12 = a22 = b1 = b2 = 0.0
        for (px, py), ang in samples:
            r = math.radians(ang)
            nx, ny = -math.sin(r), math.cos(r)        # 射线法向
            d = nx * (x - px) + ny * (y - py)         # 垂距
            # ∂d/∂x = nx, ∂d/∂y = ny
            a11 += nx * nx
            a12 += nx * ny
            a22 += ny * ny
            b1 += -nx * d
            b2 += -ny * d
        det = a11 * a22 - a12 * a12
        if abs(det) < 1e-15:
            break
        dx = (a22 * b1 - a12 * b2) / det
        dy = (a11 * b2 - a12 * b1) / det
        x += dx
        y += dy
        if math.hypot(dx, dy) < 1e-6:
            break
    return (x, y)
```

## 4.8 生成扫描航点（覆盖式搜索）

```python
def spiral_waypoints(rmax: float, spacing: float) -> list[tuple[float, float]]:
    """阿基米德螺线覆盖航点，从原点向外，相邻圈间距 spacing 米。

    rmax=1800 时，spacing 必须 <= 2*1000 才保证不漏（有效接收半径最小 1000 m）。
    """
    pts: list[tuple[float, float]] = []
    r = 0.0
    theta = 0.0
    while r <= rmax:
        pts.append((r * math.cos(theta), r * math.sin(theta)))
        r += 20.0                          # 采样步长
        theta = 2 * math.pi * r / spacing  # ★ 螺线方程
    return pts
```

## 4.9 最近邻路径（简易 TSP）

```python
def nearest_neighbor_order(start: tuple[float, float],
                           targets: list[tuple[float, float]]
                           ) -> list[tuple[float, float]]:
    """从 start 出发，每次挑最近的未访问目标。"""
    remaining = list(targets)
    order: list[tuple[float, float]] = []
    cur = start
    while remaining:
        nxt = min(remaining, key=lambda t: dist(cur, t))
        remaining.remove(nxt)
        order.append(nxt)
        cur = nxt
    return order
```

## 4.10 安全调用模拟器（把接口异常包一层）

```python
def safe_measure(sim: SimulatorClient, x: float, y: float, channel: int) -> str:
    """返回 'direction' / 'near' / 'no_signal'；接口异常时重试一次。"""
    for attempt in range(2):
        try:
            r = sim.measure(x, y, channel)
            return r["measure_result"]
        except (OSError, ValueError) as e:
            print(f"检测失败（第 {attempt + 1} 次）：{e}")
    raise RuntimeError("检测连续失败，检查模拟器是否在跑")
```

---

## 附：学习路线（如果你只有 2 小时）

| 时间 | 做什么 |
|---|---|
| 0:00–0:20 | 读 Part 1.1–1.8（变量、缩进、容器、控制流） |
| 0:20–0:40 | 读 Part 3.5「与 C++ 的 20 个致命差异」，**重点记第 1、3、5、6、9、11 条** |
| 0:40–1:00 | 读 Part 1.9–1.12（函数、类、异常、模块） |
| 1:00–1:20 | 打开 `sim_client.py` 逐行读一遍，对照 Part 1 理解 |
| 1:20–1:40 | 复制 Part 4.1–4.5 的几何函数到 `robot.py`，跑 `python geom_selftest.py` 确认无误 |
| 1:40–2:00 | 写"扫一遍 20 个频道并打印结果"的最小策略，连模拟器演练测试跑一次 |

> **最重要的建议**：不要先啃完整本手册再动手。**边查边写**，Part 2 的速查表就是为了这个。

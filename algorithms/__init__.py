# -*- coding: utf-8 -*-
"""算法注册表：网页控制台与命令行都通过它来选算法、建算法。

加一个新算法 = 在 `algorithms/` 下新建一个模块（文件名别以 `_` 开头），
在里面定义 `SPEC` 与 `build` 即可，**不需要改这里**，也不需要改网页代码。
具体见 `algorithms/README.md` 与 `algorithms/_template.py`。
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
from pathlib import Path

from .base import AlgorithmSpec

DEFAULT_ID = "p3-baseline"

_SPECS: dict[str, AlgorithmSpec] = {}
_BUILDERS: dict[str, object] = {}
_MTIMES: dict[str, float] = {}
_ERRORS: dict[str, str] = {}


def load_all(force: bool = True) -> None:
    """扫描并导入 algorithms/ 下的算法模块（文件名以 `_` 开头的跳过）。

    每次调用都重新扫目录：新加的文件会立刻出现，改过的文件会热重载（按 mtime 判断），
    所以网页上"改完刷新页面就能用"，不必重启 webui.py。导入失败的模块会被记进
    ``load_errors()`` 而不会连累其它算法。
    """
    pkg_dir = Path(__file__).resolve().parent
    specs: dict[str, AlgorithmSpec] = {}
    builders: dict[str, object] = {}
    errors: dict[str, str] = {}
    seen: set[str] = set()
    for mod in pkgutil.iter_modules([str(pkg_dir)]):
        if mod.name.startswith("_") or mod.name == "base":
            continue
        full = f"{__name__}.{mod.name}"
        seen.add(full)
        try:
            path = pkg_dir / f"{mod.name}.py"
            mtime = path.stat().st_mtime if path.exists() else 0.0
            module = sys.modules.get(full)
            prev = _MTIMES.get(full)
            if module is None:
                module = importlib.import_module(full)   # 本进程第一次加载
            elif prev is not None and prev != mtime:
                module = importlib.reload(module)       # 源码被改过：热重载
            # prev is None：别处已经 import 过这个模块，直接沿用，不要重复加载
            # （重复加载会造出第二份类对象，`from robot import InterferenceHunter` 会指到旧的）
            _MTIMES[full] = mtime
        except Exception as exc:                        # noqa: BLE001
            errors[mod.name] = f"{type(exc).__name__}: {exc}"
            continue
        spec = getattr(module, "SPEC", None)
        build = getattr(module, "build", None)
        if not isinstance(spec, AlgorithmSpec) or not callable(build):
            errors[mod.name] = ("模块里缺少 SPEC（AlgorithmSpec 实例）或 build 函数，"
                                "已跳过")
            continue
        if spec.id in specs:
            errors[mod.name] = f"算法 id 与前面某个模块重复：{spec.id}"
            continue
        specs[spec.id] = spec
        builders[spec.id] = build
    for stale in set(_MTIMES) - seen:            # 模块被删掉了
        _MTIMES.pop(stale, None)
    _SPECS.clear()
    _SPECS.update(specs)
    _BUILDERS.clear()
    _BUILDERS.update(builders)
    _ERRORS.clear()
    _ERRORS.update(errors)


def load_errors() -> dict[str, str]:
    """扫描时跳过的模块 → 原因（给网页提示用）。"""
    load_all()
    return dict(_ERRORS)


def list_specs() -> list[dict]:
    """给网页用的算法清单。"""
    load_all()
    order = sorted(_SPECS.values(), key=lambda s: (s.problem, s.id))
    return [s.to_dict() for s in order]


def get_spec(algorithm_id: str) -> AlgorithmSpec:
    load_all()
    if algorithm_id not in _SPECS:
        raise KeyError(f"未知算法：{algorithm_id}；可选：{sorted(_SPECS)}")
    return _SPECS[algorithm_id]


def build_algorithm(algorithm_id: str, sim, params: dict | None = None,
                    verbose: bool = False):
    """按 id 构造算法对象；params 覆盖该算法的默认参数。"""
    get_spec(algorithm_id)
    build = _BUILDERS[algorithm_id]
    return build(sim, params or {}, verbose=verbose)   # type: ignore[operator]

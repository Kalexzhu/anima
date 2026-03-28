"""
core/cognitive_modules/runner.py — ModuleRunner（ThreadPoolExecutor 并发调度）

使用方式：
  runner = ModuleRunner(modules)
  outputs = runner.run_all(ctx)           # 运行所有模块
  outputs = runner.run_selected(ctx, ["reactive", "daydream"])  # 只运行指定模块

返回：dict[module_name → list[DES moments]]

TODO（Deferred）：
  - 触发条件调优：为每个模块设定触发阈值（情绪范围、叙事线索状态等），
    目前通过 run_selected() 在调用侧手动控制
  - 模块间同轮内影响：reactive 先跑后，输出追加进其他模块的 context
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FutureTimeoutError

from .base import CognitiveModule, ModuleContext

# 单模块最长等待时间（秒）；超时后该模块输出空列表，不阻塞整体
_MODULE_TIMEOUT_S = 90


class ModuleRunner:
    def __init__(self, modules: list[CognitiveModule], max_workers: int = 6):
        self._modules = modules
        self._max_workers = max_workers
        self._module_map: dict[str, CognitiveModule] = {m.name: m for m in modules}

    def run_all(self, ctx: ModuleContext) -> dict[str, list[dict]]:
        """并发运行所有已注册模块。"""
        return self._run(self._modules, ctx)

    def run_selected(self, ctx: ModuleContext, names: list[str]) -> dict[str, list[dict]]:
        """只运行指定名称的模块（名称不存在则跳过）。"""
        selected = [self._module_map[n] for n in names if n in self._module_map]
        return self._run(selected, ctx)

    def _run(self, modules: list[CognitiveModule], ctx: ModuleContext) -> dict[str, list[dict]]:
        results: dict[str, list[dict]] = {}

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            future_to_name = {
                executor.submit(module.run, ctx): module.name
                for module in modules
            }
            try:
                for future in as_completed(future_to_name, timeout=_MODULE_TIMEOUT_S * len(modules)):
                    name = future_to_name[future]
                    try:
                        moments = future.result(timeout=_MODULE_TIMEOUT_S)
                        results[name] = moments if moments else []
                    except FutureTimeoutError:
                        print(f"[ModuleRunner] 模块 {name} 超时（>{_MODULE_TIMEOUT_S}s），跳过")
                        results[name] = []
                    except Exception as e:
                        print(f"[ModuleRunner] 模块 {name} 异常：{e}")
                        results[name] = []
            except FutureTimeoutError:
                # 还未完成的模块整体超时
                for future, name in future_to_name.items():
                    if name not in results:
                        print(f"[ModuleRunner] 模块 {name} 整体超时，跳过")
                        results[name] = []

        return results

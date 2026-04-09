"""
core/cognitive_modules/base.py — CognitiveModule ABC + ModuleContext 统一数据结构

数据流：
  run_cognitive_cycle()
    → Perception / Emotion / Memory / Reasoning（共享预处理）
    → ModuleContext（统一上下文封装）
    → ModuleRunner.run_all()
        → 各模块 .run(ctx) 并发执行
    → dict[module_name → list[DES moments]]
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.profile import PersonProfile
    from core.thought import ThoughtState
    from core.behavior import BehaviorState


@dataclass
class ModuleContext:
    """每轮认知循环的统一输入数据结构，传入所有认知模块。"""

    profile: "PersonProfile"
    state: "ThoughtState"         # 含上轮情绪向量、上轮思维文本、tick 号
    event: str                    # 当前环境事件（可为空字符串）
    behavior: "BehaviorState | None"

    # 共享预处理层输出（在模块运行前已完成）
    perceived: str                # 感知层：当前注意焦点
    memory_fragment: str          # 记忆层：激活的相关记忆
    reasoning: str                # 推理层：内心逻辑推演

    # Trunk 层注入：当前 tick 选中的主干情境描述（可选）
    # 格式：「当前主干情境[work]：方案被否后的去留——…」
    # 供 rumination / philosophy / self_eval / future 作为认知焦点锚点
    active_trunk_context: str = ""

    # C3：次级主干渗透——第二高分 Trunk 的 context_str（可为空）
    # 供 rumination / self_eval / philosophy 在 anchor 构建时注入背景，模拟跨域渗透
    secondary_trunk_context: str = ""

    # 上轮所有模块的输出（跨轮次影响机制）
    # {module_name: [{"type": ..., "content": ...}, ...]}
    prev_tick_outputs: "dict[str, list[dict]]" = field(default_factory=dict)

    # 上轮所有模块生成的 voice_intrusion 内容（跨模块去重用）
    # 注入各 FragmentModule 的 prompt，禁止重复相同声音侵入
    recent_voice_contents: "list[str]" = field(default_factory=list)

    # 本轮预采样的记忆列表（由 run_cognitive_cycle 统一采样一次，传入所有模块）
    # 保证同一 tick 内 perception / B1 / B2 看到相同的记忆组合
    memory_sample: "list[dict]" = field(default_factory=list)


class CognitiveModule(ABC):
    """所有认知模块的基类。"""

    name: str
    module_type: str  # "fragment" | "chain"

    @abstractmethod
    def run(self, ctx: ModuleContext) -> list[dict]:
        """
        执行本模块，返回 DES moment JSON 列表。
        每个 moment 格式：{"type": "...", "content": "...", "source": "（仅 voice_intrusion）"}
        失败时返回空列表，不抛异常。
        """

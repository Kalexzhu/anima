"""
twin/twin.py — CognitiveTwin 主类（接口定义）

将 PersonProfile 封装为持久化认知运行时。
Phase 2 时实现具体逻辑，当前为接口占位。

设想使用方式：

    twin = CognitiveTwin.from_profile("examples/demo_profile.json")

    # 在特定情境下运行
    result = twin.simulate(
        situation="刚刚收到晋升通知，独自走在回家路上",
        physical_state="有点激动，又有点茫然",
        ticks=5,
    )

    # 跨情境对比同一个人
    twin.compare(
        scenarios=[
            {"situation": "收到表扬后独自走在路上", "physical_state": "平静"},
            {"situation": "被朋友误解后独自走在路上", "physical_state": "心里堵"},
        ]
    )
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import json

from core.profile import PersonProfile
from core.emotion import EmotionState
from core.thought import ThoughtState
from core.memory import MemoryManager


@dataclass
class SimulationResult:
    """一次情境模拟的完整结果。"""
    situation: str
    physical_state: str
    ticks: List[Dict[str, Any]]       # 每轮的 tick_record
    final_state: Optional[ThoughtState] = None


class CognitiveTwin:
    """
    认知数字分身。
    持久化封装一个人的 PersonProfile + 记忆系统。
    """

    def __init__(self, profile: PersonProfile):
        self.profile = profile
        self._memory: Optional[MemoryManager] = None

    @classmethod
    def from_profile_file(cls, path: str) -> "CognitiveTwin":
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        profile = PersonProfile(**data)
        twin = cls(profile)
        twin._init_memory()
        return twin

    @classmethod
    def from_profile(cls, profile: PersonProfile) -> "CognitiveTwin":
        twin = cls(profile)
        twin._init_memory()
        return twin

    def _init_memory(self):
        self._memory = MemoryManager()
        self._memory.load_from_profile(self.profile.memories)

    def simulate(
        self,
        situation: str,
        physical_state: str,
        ticks: int = 5,
        initial_event: str = "",
    ) -> SimulationResult:
        """
        在指定情境下运行认知循环。
        Phase 2 实现。
        """
        raise NotImplementedError(
            "CognitiveTwin.simulate() 将在 Phase 2 实现。"
            "当前请使用 run.py 直接运行，修改 examples/*.json 中的 current_situation。"
        )

    def compare(self, scenarios: List[Dict[str, str]]) -> List[SimulationResult]:
        """
        对比同一个人在不同情境下的思维差异。
        Phase 2 实现。
        """
        raise NotImplementedError("CognitiveTwin.compare() 将在 Phase 2 实现。")

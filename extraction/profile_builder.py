"""
extraction/profile_builder.py — Profile 合成器（接口定义）

接收多路提取结果，合并矛盾，评估置信度，输出 PersonProfile。

Phase 3 时实现具体逻辑，当前为接口占位。
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Any, Literal

from core.profile import PersonProfile


Confidence = Literal["high", "medium", "low"]


@dataclass
class FieldEvidence:
    """某个 Profile 字段的推断依据。"""
    value: Any
    confidence: Confidence
    sources: List[str] = field(default_factory=list)  # 来源句子列表
    contradictions: List[str] = field(default_factory=list)  # 与之矛盾的证据


@dataclass
class RawExtractionResult:
    """
    各路提取器输出的原始结果。
    键为 PersonProfile 字段名，值为 FieldEvidence 列表（可能来自多个来源）。
    """
    fields: Dict[str, List[FieldEvidence]] = field(default_factory=dict)

    def add(self, field_name: str, value: Any, confidence: Confidence, source: str):
        if field_name not in self.fields:
            self.fields[field_name] = []
        self.fields[field_name].append(
            FieldEvidence(value=value, confidence=confidence, sources=[source])
        )


class ProfileBuilder:
    """
    合成器：将多路 RawExtractionResult 合并为最终 PersonProfile。

    Phase 3 实现要点：
      1. 同字段多次出现 → 按置信度加权合并
      2. 矛盾检测 → 高置信度矛盾写入 cognitive_biases
      3. 空缺字段 → 标记为 low confidence，触发 interviewer 追问
    """

    def build(self, results: List[RawExtractionResult], base_name: str = "未命名") -> PersonProfile:
        """
        Phase 3 实现。
        当前返回空 PersonProfile 作为接口占位。
        """
        raise NotImplementedError(
            "ProfileBuilder.build() 将在 Phase 3 实现。"
            "当前请直接编写 examples/*.json 作为 PersonProfile 输入。"
        )

    def _merge_list_field(self, evidences: List[FieldEvidence]) -> List[str]:
        """合并列表型字段（personality_traits / core_values / cognitive_biases）。"""
        seen = {}
        for ev in sorted(evidences, key=lambda e: {"high": 3, "medium": 2, "low": 1}[e.confidence], reverse=True):
            v = ev.value
            if isinstance(v, str) and v not in seen:
                seen[v] = ev.confidence
        return list(seen.keys())

    def _detect_contradictions(self, evidences: List[FieldEvidence]) -> List[str]:
        """简单矛盾检测：同字段存在 high confidence 的对立值。"""
        # Phase 3 实现
        return []

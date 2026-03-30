"""
ThoughtState — 某一时刻的思维快照。
包含思维文本、情绪向量、循环轮次。
"""

from dataclasses import dataclass, field
from core.emotion import EmotionState


@dataclass
class ThoughtState:
    text: str                          # 当前思维流文本
    emotion: EmotionState              # 情绪向量（独立参数）
    tick: int = 0                      # 当前循环轮次
    last_event: str = ""               # 触发本轮的环境事件（可为空）
    perceived: str = ""                # 感知层输出（注意焦点）
    memory_fragment: str = ""          # 记忆层激活内容
    reasoning: str = ""                # 推理层内心推断
    conclusion: str | None = None      # B2 锚点链结论（微决定/新认识），供 writeback 使用
    suppression_pressure: float = 0.0  # B2：情绪积压压力（0~1），超过 0.8 触发 release 事件

    def summary(self) -> str:
        dominant = self.emotion.dominant()
        intensity = self.emotion.intensity
        return (
            f"[tick={self.tick}] intensity={intensity:.2f} dominant={dominant}\n"
            f"event: {self.last_event or '(none)'}\n"
            f"thought: {self.text[:120]}{'...' if len(self.text) > 120 else ''}"
        )

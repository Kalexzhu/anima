"""
EmotionState — 情绪向量，系统中的独立参数。
基于 Plutchik 情绪轮的 8 个基础维度。
intensity = 偏离平静基线的 L2 范数。
"""

from dataclasses import dataclass, field
from typing import Dict
import math


@dataclass
class EmotionState:
    # Plutchik 8 维基础情绪，范围 0.0 ~ 1.0
    anger: float = 0.0        # 愤怒
    fear: float = 0.0         # 恐惧
    joy: float = 0.0          # 喜悦
    sadness: float = 0.0      # 悲伤
    surprise: float = 0.0     # 惊讶
    disgust: float = 0.0      # 厌恶
    anticipation: float = 0.0 # 期待
    trust: float = 0.0        # 信任

    @property
    def intensity(self) -> float:
        """偏离平静基线（全零）的 L2 范数，范围 0.0 ~ 1.0"""
        values = [
            self.anger, self.fear, self.joy, self.sadness,
            self.surprise, self.disgust, self.anticipation, self.trust,
        ]
        return math.sqrt(sum(v ** 2 for v in values) / len(values))

    def dominant(self) -> str:
        """返回当前最强烈的情绪名称"""
        emotions = {
            "anger": self.anger, "fear": self.fear, "joy": self.joy,
            "sadness": self.sadness, "surprise": self.surprise,
            "disgust": self.disgust, "anticipation": self.anticipation,
            "trust": self.trust,
        }
        return max(emotions, key=emotions.get)

    def to_dict(self) -> Dict[str, float]:
        return {
            "anger": self.anger, "fear": self.fear, "joy": self.joy,
            "sadness": self.sadness, "surprise": self.surprise,
            "disgust": self.disgust, "anticipation": self.anticipation,
            "trust": self.trust, "intensity": self.intensity,
        }

    def update_from_dict(self, d: Dict[str, float]) -> "EmotionState":
        """返回新的 EmotionState，所有值 clamp 到 [0, 1]"""
        def clamp(v): return max(0.0, min(1.0, float(v)))
        return EmotionState(
            anger=clamp(d.get("anger", self.anger)),
            fear=clamp(d.get("fear", self.fear)),
            joy=clamp(d.get("joy", self.joy)),
            sadness=clamp(d.get("sadness", self.sadness)),
            surprise=clamp(d.get("surprise", self.surprise)),
            disgust=clamp(d.get("disgust", self.disgust)),
            anticipation=clamp(d.get("anticipation", self.anticipation)),
            trust=clamp(d.get("trust", self.trust)),
        )

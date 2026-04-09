"""
core/emotion_utils.py — 情绪向量通用工具函数。

从 memory.py 提取，供 memory.py 和 tick_history.py 共用。
"""

from __future__ import annotations
from typing import Dict

EMOTION_DIMS = ["anger", "fear", "joy", "sadness", "surprise", "disgust", "anticipation", "trust"]
NEGATIVE_DIMS = {"anger", "fear", "sadness", "disgust"}
POSITIVE_DIMS = {"joy", "trust", "anticipation"}


def emotion_cosine(vec_a: Dict[str, float], vec_b: Dict[str, float]) -> float:
    """计算两个情绪向量的余弦相似度，返回 0.0 ~ 1.0。"""
    if not vec_a or not vec_b:
        return 0.0
    import math
    dot = sum(vec_a.get(d, 0.0) * vec_b.get(d, 0.0) for d in EMOTION_DIMS)
    mag_a = math.sqrt(sum(vec_a.get(d, 0.0) ** 2 for d in EMOTION_DIMS)) or 1e-9
    mag_b = math.sqrt(sum(vec_b.get(d, 0.0) ** 2 for d in EMOTION_DIMS)) or 1e-9
    return dot / (mag_a * mag_b)


def emotion_to_vec(emotion: "EmotionState") -> Dict[str, float]:
    """EmotionState → dict 向量（用于相似度计算）。"""
    return {d: getattr(emotion, d, 0.0) for d in EMOTION_DIMS}

"""
core/drift_sampler.py — Drift 游荡方向采样器。

基于情绪状态，从 9 种 mind-wandering 方向中加权随机采样。

学术依据：
  Killingsworth & Gilbert (2010), Christoff et al. (2016, Nature Reviews Neuroscience),
  Smallwood & Schooler (2006), Maillet et al. (2017)

权重计算：
  final_weight[cat] = max(base × char_modifier + Σ(emotion_value × multiplier), 0.01)
  → 归一化 → random.choices 采样
"""

from __future__ import annotations
import random

# ── 类别定义 ────────────────────────────────────────────────────────────────────

DRIFT_CATEGORIES = [
    "daydream",        # 白日梦/欲望幻想
    "philosophy",      # 哲学/存在性探讨
    "aesthetic",       # 创意/审美联想
    "future",          # 未来规划/预期想象
    "positive_memory", # 正向记忆回溯
    "social_rehearsal",# 假设社交场景（演练/复盘对话）
    "self_eval",       # 自我评估
    "counterfactual",  # 反事实思考（"要是当时……"）
    "rumination",      # 反刍
]

_ZH_NAMES: dict[str, str] = {
    "daydream":        "白日梦/欲望幻想",
    "philosophy":      "哲学/存在性探讨",
    "aesthetic":       "创意/审美联想",
    "future":          "未来规划/预期想象",
    "positive_memory": "正向记忆回溯",
    "social_rehearsal":"假设社交场景",
    "self_eval":       "自我评估",
    "counterfactual":  "反事实思考",
    "rumination":      "反刍",
}

# ── 基础权重（情绪全零时的"空白游荡"分布）──────────────────────────────────────

_BASE_WEIGHTS: dict[str, float] = {
    "daydream":         0.20,  # DMN 最自然激活方向
    "philosophy":       0.18,  # 平静才有余力思考意义
    "aesthetic":        0.15,  # 低压时审美感知更活跃
    "future":           0.12,  # 前瞻性思维是 MW 最高频类型
    "positive_memory":  0.12,  # 放松时正向记忆浮现
    "social_rehearsal": 0.10,  # 平和状态下轻松社交想象
    "self_eval":        0.07,
    "counterfactual":   0.04,  # 无情绪触发时很少发生
    "rumination":       0.02,  # 无情绪时不容易陷入
}

# ── 林晓雨角色特异性修正（乘在基础权重上）──────────────────────────────────────

_CHARACTER_MODIFIERS: dict[str, float] = {
    "rumination":       1.4,   # 过度自责、习惯独自承受
    "social_rehearsal": 1.3,   # 高度共情、会事后复盘
    "aesthetic":        1.3,   # 画画和攒歌单的爱好
    "daydream":         1.2,   # desires[] 里有明确的克制欲望
    "counterfactual":   1.2,   # 完美主义者容易"改剧本"
    "philosophy":       0.8,   # 较少纯粹哲学漫游
}

# ── 情绪乘数矩阵 ─────────────────────────────────────────────────────────────────
# 格式：{category: {emotion_key: multiplier}}
# 正值 → 该情绪拉高此方向权重，负值 → 压低

_EMOTION_MULTIPLIERS: dict[str, dict[str, float]] = {
    "rumination": {
        "anger": 1.2, "fear": 1.5, "joy": -1.0, "sadness": 2.0,
        "surprise": 0.3, "disgust": 1.0, "anticipation": -0.5, "trust": -0.8,
    },
    "positive_memory": {
        "anger": -0.3, "fear": -0.3, "joy": 2.5, "sadness": 1.8,
        "surprise": 0.3, "disgust": -0.5, "anticipation": 0.5, "trust": 1.5,
    },
    "future": {
        "anger": 1.0, "fear": 2.0, "joy": 1.2, "sadness": -0.5,
        "surprise": 1.2, "disgust": 0.3, "anticipation": 2.5, "trust": 0.8,
    },
    "counterfactual": {
        "anger": 2.5, "fear": 1.5, "joy": -0.5, "sadness": 0.8,
        "surprise": 2.0, "disgust": 1.2, "anticipation": 0.3, "trust": -0.5,
    },
    "social_rehearsal": {
        "anger": 2.5, "fear": 2.0, "joy": 1.0, "sadness": 0.5,
        "surprise": 1.0, "disgust": 0.8, "anticipation": 1.0, "trust": 1.8,
    },
    "daydream": {
        "anger": -0.5, "fear": -0.3, "joy": 2.0, "sadness": 0.8,
        "surprise": 0.5, "disgust": -0.5, "anticipation": 2.0, "trust": 1.5,
    },
    "self_eval": {
        "anger": 1.0, "fear": 1.2, "joy": 0.3, "sadness": 1.5,
        "surprise": 1.5, "disgust": 2.0, "anticipation": 0.3, "trust": 0.3,
    },
    "philosophy": {
        "anger": 0.8, "fear": 0.7, "joy": 0.5, "sadness": 1.5,
        "surprise": 1.5, "disgust": 1.5, "anticipation": 0.5, "trust": 0.5,
    },
    "aesthetic": {
        "anger": -0.3, "fear": -0.5, "joy": 2.0, "sadness": -0.3,
        "surprise": 0.7, "disgust": -0.5, "anticipation": 1.0, "trust": 1.5,
    },
}


def sample_drift_category(emotion_dict: dict) -> str:
    """
    基于情绪向量加权采样 drift 方向，返回中文名称。

    Args:
        emotion_dict: EmotionState.to_dict() 的输出（含或不含 intensity 键均可）
    """
    values = {k: v for k, v in emotion_dict.items() if k != "intensity"}

    weights: dict[str, float] = {}
    for cat in DRIFT_CATEGORIES:
        w = _BASE_WEIGHTS[cat] * _CHARACTER_MODIFIERS.get(cat, 1.0)
        for emo, mult in _EMOTION_MULTIPLIERS.get(cat, {}).items():
            w += values.get(emo, 0.0) * mult
        weights[cat] = max(w, 0.01)  # 截断，保留最小概率

    total = sum(weights.values())
    probs = [weights[cat] / total for cat in DRIFT_CATEGORIES]
    chosen = random.choices(DRIFT_CATEGORIES, weights=probs, k=1)[0]
    return _ZH_NAMES[chosen]

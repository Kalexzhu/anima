"""
core/occ.py — OCC (Ortony-Clore-Collins) 认知评价模型。

将事件的认知解读映射到 Plutchik 8D 情绪向量。

数据流：
  感知内容 + 人物档案
      │
      ▼  LLM (cognitive_engine.emotion_layer 调用)
  OCCAppraisal（6 个评价维度）
      │
      ▼  occ_to_plutchik()        ← 确定性公式，无随机性
  Plutchik 原始向量
      │
      ▼  apply_personality_modifiers()   ← 认知偏差加权
  修正后向量
      │
      ▼  blend_with_prev_state()  ← 情绪惯性平滑
  最终 EmotionState 输入值
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List

from core.emotion_utils import EMOTION_DIMS

_NEGATIVE_DIMS = {"anger", "fear", "sadness", "disgust"}


# ── OCCAppraisal ───────────────────────────────────────────────────────────────

@dataclass
class OCCAppraisal:
    """OCC 认知评价：6 个维度描述事件对人物的心理意义。"""
    desirability: float      # 事件结果的渴望程度，-1（极不想要）~ +1（极想要）
    goal_relevance: float    # 与当前目标的相关程度，0 ~ 1
    causal_agent: str        # 因果主体："self" / "other" / "world"
    praiseworthiness: float  # 行为主体的道德评价，-1（应谴责）~ +1（值得赞美）
    unexpectedness: float    # 事件的意外程度，0（完全预料）~ 1（完全意外）
    proximity: float         # 与自身的心理距离，0（遥远/抽象）~ 1（切身相关）


# ── OCC → Plutchik 映射 ────────────────────────────────────────────────────────

def occ_to_plutchik(a: OCCAppraisal) -> Dict[str, float]:
    """
    将 OCC 认知评价确定性地映射到 Plutchik 8D 情绪向量。

    映射逻辑：
      desirability < 0  → sadness（受阻）+ fear（威胁，unexpectedness 放大）
      desirability > 0  → joy + trust（确定感）+ anticipation（期待）
      unexpectedness    → surprise（与情绪强度共同驱动）
      causal_agent=other, praiseworthiness < 0  → anger + disgust（他人做错）
      causal_agent=other, praiseworthiness > 0  → trust（他人做对）
      causal_agent=self,  praiseworthiness < 0  → disgust + fear（自我惩罚）
      causal_agent=self,  praiseworthiness > 0  → trust + anticipation（自我肯定）
    """
    d    = a.desirability
    g    = a.goal_relevance
    p    = a.praiseworthiness
    u    = a.unexpectedness
    prox = a.proximity

    r: Dict[str, float] = {dim: 0.0 for dim in EMOTION_DIMS}

    # 事件结果评价
    if d < 0:
        r["sadness"]      += abs(d) * g * prox * (1 - u * 0.3)
        r["fear"]         += abs(d) * g * prox * u * 0.6
    else:
        r["joy"]          += d * g * prox
        r["trust"]        += d * g * 0.3
        r["anticipation"] += d * g * 0.2

    # 意外程度（独立贡献 surprise）
    r["surprise"] += u * abs(d) * g * 0.8

    # 行为主体评价
    if a.causal_agent == "other":
        if p < 0:
            r["anger"]   += abs(p) * g * prox * 0.8
            r["disgust"] += abs(p) * g * 0.4
        elif p > 0:
            r["trust"]   += p * g * 0.7
    elif a.causal_agent == "self":
        if p < 0:
            r["disgust"]      += abs(p) * 0.5
            r["fear"]         += abs(p) * 0.3
        elif p > 0:
            r["trust"]        += p * 0.4
            r["anticipation"] += p * 0.3

    return {k: min(1.0, v) for k, v in r.items()}


# ── 认知偏差修正器 ────────────────────────────────────────────────────────────

# key: 认知偏差关键词（子串匹配）→ value: 各情绪维度的乘数
# "all_negative" 是特殊键，对所有负向维度（anger/fear/sadness/disgust）统一乘
BIAS_MODIFIERS: Dict[str, Dict[str, float]] = {
    "灾难化":     {"fear": 1.4, "sadness": 1.3, "anticipation": 0.7},
    "过度自责":   {"disgust": 1.5, "fear": 1.2, "anger": 0.7},   # 0.4→0.7：自责者仍有愤怒，只是压抑一部分
    "非黑即白":   {"all_negative": 1.3, "trust": 0.6},
    "归咎于自己": {"fear": 1.3, "disgust": 1.2},
    "回避冲突":   {"anger": 0.3, "fear": 1.2, "sadness": 1.1},
}


def apply_personality_modifiers(
    plutchik: Dict[str, float],
    cognitive_biases: List[str],
) -> Dict[str, float]:
    """
    根据人物认知偏差列表，对 Plutchik 向量做加权修正。

    匹配规则：只要偏差描述包含 BIAS_MODIFIERS 的 key（子串），就触发对应修正。
    多个偏差叠加时乘数连乘。
    结果 clamp 到 [0, 1]。
    """
    result = dict(plutchik)

    for bias_str in cognitive_biases:
        for keyword, modifiers in BIAS_MODIFIERS.items():
            if keyword not in bias_str:
                continue
            for dim, multiplier in modifiers.items():
                if dim == "all_negative":
                    for neg_dim in _NEGATIVE_DIMS:
                        result[neg_dim] = min(1.0, result.get(neg_dim, 0.0) * multiplier)
                else:
                    result[dim] = min(1.0, result.get(dim, 0.0) * multiplier)

    return result


# ── 情绪惯性平滑 ──────────────────────────────────────────────────────────────

def blend_with_prev_state(
    new: Dict[str, float],
    prev: Dict[str, float],
    decay: float = 0.4,
) -> Dict[str, float]:
    """
    将新情绪向量与前一轮融合，模拟情绪惯性。

    blended[dim] = decay * prev[dim] + (1 - decay) * new[dim]

    decay=0.0 → 完全采用新情绪（无惯性）
    decay=1.0 → 完全保留旧情绪（无变化）
    decay=0.4 → 60% 新 + 40% 旧（默认）

    Critical gap fix: decay 强制 clamp 到 [0, 1]。
    """
    decay = max(0.0, min(1.0, decay))
    return {
        dim: max(0.0, min(1.0,
            decay * prev.get(dim, 0.0) + (1 - decay) * new.get(dim, 0.0)
        ))
        for dim in EMOTION_DIMS
    }


# ── LLM Prompt 模板（供 cognitive_engine 使用）────────────────────────────────

OCC_SYSTEM_PROMPT = (
    "你是认知评价模型。根据人物性格和当前感知，输出 OCC 认知评价的 6 个维度。\n"
    "只返回一个 JSON 对象，不要任何其他文字、代码块或解释：\n"
    '{"desirability": 0.0, "goal_relevance": 0.0, "causal_agent": "world", '
    '"praiseworthiness": 0.0, "unexpectedness": 0.0, "proximity": 0.0}\n'
    "字段说明：\n"
    "  desirability:     -1（极不想要）~ +1（极想要），描述事件结果对人物的好坏\n"
    "  goal_relevance:   0~1，此事件与人物当前目标/在意的事物的相关程度\n"
    "  causal_agent:     'self'（自己导致）/ 'other'（他人导致）/ 'world'（环境/命运）\n"
    "                    注意：causal_agent 按客观事实判断，不受人物主观归因偏差影响。\n"
    "                    他人的行为（如领导当众否定、前伴侣离开）即使人物倾向自责，\n"
    "                    causal_agent 仍应判为 'other'。\n"
    "  praiseworthiness: -1（应谴责）~ +1（值得赞美），针对 causal_agent 的道德评价\n"
    "  unexpectedness:   0（完全预料中）~ 1（完全意外）\n"
    "  proximity:        0（遥远抽象）~ 1（切身相关）"
)


def parse_occ_response(raw: str) -> OCCAppraisal | None:
    """
    从 LLM 原始输出解析 OCCAppraisal。
    失败时返回 None（调用方 fallback 到前一轮情绪状态，并打印警告）。
    """
    import json, re
    try:
        m = re.search(r'\{[^{}]+\}', raw, re.DOTALL)
        if m:
            d = json.loads(m.group())
        elif "```" in raw:
            d = json.loads(raw.split("```")[1].lstrip("json").strip())
        else:
            d = json.loads(raw)

        return OCCAppraisal(
            desirability=float(d.get("desirability", 0.0)),
            goal_relevance=float(d.get("goal_relevance", 0.0)),
            causal_agent=str(d.get("causal_agent", "world")),
            praiseworthiness=float(d.get("praiseworthiness", 0.0)),
            unexpectedness=float(d.get("unexpectedness", 0.0)),
            proximity=float(d.get("proximity", 1.0)),
        )
    except Exception:
        return None


# ── DUTIR 方向校准 ──────────────────────────────────────────────────────────────

def apply_dutir_calibration(
    blended: dict[str, float],
    event_text: str,
    perceived_text: str,
) -> dict[str, float]:
    """
    若 OCC 主导情绪方向与 DUTIR 方向不一致，修正主导维度：
      - 压低 OCC 错误主导 × 0.3
      - 拉高 DUTIR 指示维度 + 0.3（capped 1.0）
    """
    from core.emotion_utils import NEGATIVE_DIMS, POSITIVE_DIMS

    combined = f"{event_text} {perceived_text}".strip()
    if not combined:
        return blended

    try:
        from core.dutir_loader import get_dominant_emotions
        dutir_top_list = get_dominant_emotions(combined, top_n=1)
        if not dutir_top_list:
            return blended
        dutir_top = dutir_top_list[0]
    except Exception:
        return blended

    dims = {k: v for k, v in blended.items() if k in NEGATIVE_DIMS | POSITIVE_DIMS}
    if not dims:
        return blended
    occ_top = max(dims, key=dims.get)

    occ_neg = occ_top in NEGATIVE_DIMS
    dutir_neg = dutir_top in NEGATIVE_DIMS

    if occ_neg == dutir_neg:
        return blended

    result = dict(blended)
    result[occ_top] = result[occ_top] * 0.3
    result[dutir_top] = min(1.0, result.get(dutir_top, 0.0) + 0.3)
    print(
        f"[DUTIR] 方向修正：{occ_top}({blended[occ_top]:.2f}→{result[occ_top]:.2f})"
        f" → {dutir_top}({blended.get(dutir_top, 0):.2f}→{result[dutir_top]:.2f})"
    )
    return result

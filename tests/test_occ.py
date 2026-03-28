"""
tests/test_occ.py — OCC 模型单元测试

覆盖范围：
  T-OCC-1  ~ T-OCC-6  : occ_to_plutchik 映射方向性
  T-BIAS-1 ~ T-BIAS-3 : apply_personality_modifiers 偏差加权
  T-BLEND-1 ~ T-BLEND-2: blend_with_prev_state 情绪惯性
  T-SENS-1 ~ T-SENS-4  : 参数敏感性（单调性验证）
"""

import pytest
from core.occ import (
    OCCAppraisal,
    occ_to_plutchik,
    apply_personality_modifiers,
    blend_with_prev_state,
    parse_occ_response,
    EMOTION_DIMS,
)


def _appraisal(**kwargs) -> OCCAppraisal:
    defaults = dict(
        desirability=0.0, goal_relevance=0.5,
        causal_agent="world", praiseworthiness=0.0,
        unexpectedness=0.0, proximity=0.5,
    )
    defaults.update(kwargs)
    return OCCAppraisal(**defaults)


# ── T-OCC-1: 负面事件 → sadness 主导 ────────────────────────────────────────

def test_negative_desirability_produces_sadness():
    """T-OCC-1: 坏事（desirability=-1）应产生 sadness，不产生 joy。"""
    a = _appraisal(desirability=-1.0, goal_relevance=1.0, proximity=1.0)
    r = occ_to_plutchik(a)
    assert r["sadness"] > 0.3
    assert r["joy"] == 0.0


# ── T-OCC-2: 正面事件 → joy 主导 ─────────────────────────────────────────────

def test_positive_desirability_produces_joy():
    """T-OCC-2: 好事（desirability=+1）应产生 joy，不产生 sadness。"""
    a = _appraisal(desirability=1.0, goal_relevance=1.0, proximity=1.0)
    r = occ_to_plutchik(a)
    assert r["joy"] > 0.3
    assert r["sadness"] == 0.0


# ── T-OCC-3: 他人做错 → anger ────────────────────────────────────────────────

def test_other_blame_produces_anger():
    """T-OCC-3: 他人做错事（causal_agent=other, praiseworthiness=-1）应产生 anger。"""
    a = _appraisal(
        desirability=-0.5, goal_relevance=0.8,
        causal_agent="other", praiseworthiness=-1.0, proximity=1.0,
    )
    r = occ_to_plutchik(a)
    assert r["anger"] > 0.3


# ── T-OCC-4: 意外事件 → surprise ─────────────────────────────────────────────

def test_unexpectedness_produces_surprise():
    """T-OCC-4: 意外程度高（unexpectedness=1）应产生 surprise。"""
    a = _appraisal(
        desirability=-0.5, goal_relevance=0.8,
        unexpectedness=1.0, proximity=1.0,
    )
    r = occ_to_plutchik(a)
    assert r["surprise"] > 0.2


# ── T-OCC-5: 自我批评 → disgust ──────────────────────────────────────────────

def test_self_blame_produces_disgust():
    """T-OCC-5: 自己做错事（causal_agent=self, praiseworthiness=-1）应产生 disgust。"""
    a = _appraisal(causal_agent="self", praiseworthiness=-1.0)
    r = occ_to_plutchik(a)
    assert r["disgust"] > 0.2


# ── T-OCC-6: 所有输出在 [0, 1] 范围内 ───────────────────────────────────────

def test_output_bounds():
    """T-OCC-6: 任何输入组合输出均在 [0, 1]。"""
    cases = [
        _appraisal(desirability=1.0, goal_relevance=1.0, praiseworthiness=1.0,
                   unexpectedness=1.0, proximity=1.0, causal_agent="other"),
        _appraisal(desirability=-1.0, goal_relevance=1.0, praiseworthiness=-1.0,
                   unexpectedness=1.0, proximity=1.0, causal_agent="self"),
        _appraisal(),  # 全默认（中性）
    ]
    for a in cases:
        r = occ_to_plutchik(a)
        for dim in EMOTION_DIMS:
            assert 0.0 <= r[dim] <= 1.0, f"dim={dim} out of bounds: {r[dim]}"


# ── T-BIAS-1: 灾难化放大恐惧 ─────────────────────────────────────────────────

def test_bias_catastrophizing_amplifies_fear():
    """T-BIAS-1: '灾难化' 偏差应放大 fear，降低 anticipation。"""
    base = {d: 0.0 for d in EMOTION_DIMS}
    base["fear"] = 0.4
    base["anticipation"] = 0.5

    result = apply_personality_modifiers(base, ["灾难化思维"])
    assert result["fear"] > base["fear"]
    assert result["anticipation"] < base["anticipation"]


# ── T-BIAS-2: 回避冲突抑制愤怒 ───────────────────────────────────────────────

def test_bias_conflict_avoidance_suppresses_anger():
    """T-BIAS-2: '回避冲突' 偏差应抑制 anger，不影响 joy。"""
    base = {d: 0.0 for d in EMOTION_DIMS}
    base["anger"] = 0.6
    base["joy"] = 0.4

    result = apply_personality_modifiers(base, ["回避冲突"])
    assert result["anger"] < base["anger"]
    assert result["joy"] == pytest.approx(base["joy"])


# ── T-BIAS-3: 无匹配偏差不修改输出 ─────────────────────────────────────────

def test_bias_no_match_returns_unchanged():
    """T-BIAS-3: 偏差列表无匹配时，输出与输入完全一致。"""
    base = {d: 0.3 for d in EMOTION_DIMS}
    result = apply_personality_modifiers(base, ["不存在的偏差"])
    for dim in EMOTION_DIMS:
        assert result[dim] == pytest.approx(base[dim])


# ── T-BLEND-1: 正常混合 ──────────────────────────────────────────────────────

def test_blend_normal():
    """T-BLEND-1: decay=0.4 时，结果应是 40% 旧 + 60% 新。"""
    new  = {d: 1.0 for d in EMOTION_DIMS}
    prev = {d: 0.0 for d in EMOTION_DIMS}
    result = blend_with_prev_state(new, prev, decay=0.4)
    for dim in EMOTION_DIMS:
        assert result[dim] == pytest.approx(0.6, abs=1e-6)


# ── T-BLEND-2: decay 越界 clamp ───────────────────────────────────────────────

def test_blend_decay_clamp():
    """T-BLEND-2: decay > 1 应 clamp 到 1.0（完全保留旧状态），不抛出异常。"""
    new  = {d: 1.0 for d in EMOTION_DIMS}
    prev = {d: 0.2 for d in EMOTION_DIMS}

    result_gt1 = blend_with_prev_state(new, prev, decay=2.0)  # clamp to 1.0
    result_lt0 = blend_with_prev_state(new, prev, decay=-1.0)  # clamp to 0.0

    for dim in EMOTION_DIMS:
        # decay=2.0 clamped to 1.0 → fully prev
        assert result_gt1[dim] == pytest.approx(0.2, abs=1e-6)
        # decay=-1.0 clamped to 0.0 → fully new
        assert result_lt0[dim] == pytest.approx(1.0, abs=1e-6)


# ── T-SENS-1: desirability 单调性 ────────────────────────────────────────────

def test_sensitivity_desirability_joy_monotone():
    """T-SENS-1: desirability 增大时，joy 单调递增，sadness 单调递减。"""
    d_values = [-1.0, -0.5, 0.0, 0.5, 1.0]
    joy_values    = []
    sadness_values = []
    for d in d_values:
        r = occ_to_plutchik(_appraisal(desirability=d, goal_relevance=1.0, proximity=1.0))
        joy_values.append(r["joy"])
        sadness_values.append(r["sadness"])

    for i in range(len(d_values) - 1):
        assert joy_values[i] <= joy_values[i + 1], (
            f"joy 非单调：d={d_values[i]}→{d_values[i+1]}, "
            f"joy={joy_values[i]}→{joy_values[i+1]}"
        )
        assert sadness_values[i] >= sadness_values[i + 1], (
            f"sadness 非单调：d={d_values[i]}→{d_values[i+1]}, "
            f"sadness={sadness_values[i]}→{sadness_values[i+1]}"
        )


# ── T-SENS-2: goal_relevance 放大效果 ────────────────────────────────────────

def test_sensitivity_goal_relevance_amplifies():
    """T-SENS-2: goal_relevance 增大时，所有非零情绪维度单调增大（不减小）。"""
    g_values = [0.0, 0.3, 0.6, 1.0]
    base_appraisal = dict(desirability=-0.8, causal_agent="other",
                          praiseworthiness=-0.5, unexpectedness=0.5, proximity=1.0)
    prev_r = None
    for g in g_values:
        r = occ_to_plutchik(_appraisal(goal_relevance=g, **base_appraisal))
        if prev_r is not None:
            for dim in EMOTION_DIMS:
                assert r[dim] >= prev_r[dim] - 1e-9, (
                    f"dim={dim} 随 goal_relevance 增大而减小：{prev_r[dim]}→{r[dim]}"
                )
        prev_r = r


# ── T-SENS-3: proximity 放大效果 ─────────────────────────────────────────────

def test_sensitivity_proximity_amplifies():
    """T-SENS-3: proximity 增大时，主要情绪维度单调增大。"""
    prox_values = [0.0, 0.3, 0.7, 1.0]
    joy_values = []
    for prox in prox_values:
        r = occ_to_plutchik(_appraisal(desirability=0.8, goal_relevance=0.8, proximity=prox))
        joy_values.append(r["joy"])

    for i in range(len(prox_values) - 1):
        assert joy_values[i] <= joy_values[i + 1], (
            f"joy 随 proximity 增大而减小：{joy_values[i]}→{joy_values[i+1]}"
        )


# ── T-SENS-4: unexpectedness 放大 surprise ───────────────────────────────────

def test_sensitivity_unexpectedness_amplifies_surprise():
    """T-SENS-4: unexpectedness 增大时，surprise 单调递增。"""
    u_values = [0.0, 0.25, 0.5, 0.75, 1.0]
    surprise_values = []
    for u in u_values:
        r = occ_to_plutchik(_appraisal(
            desirability=-0.5, goal_relevance=0.8, proximity=1.0, unexpectedness=u
        ))
        surprise_values.append(r["surprise"])

    for i in range(len(u_values) - 1):
        assert surprise_values[i] <= surprise_values[i + 1], (
            f"surprise 随 unexpectedness 增大而减小：{surprise_values[i]}→{surprise_values[i+1]}"
        )


# ── T-OCC-7: parse_occ_response 正常解析 ─────────────────────────────────────

def test_parse_occ_valid_json():
    """T-OCC-7: 标准 JSON 字符串能正确解析为 OCCAppraisal。"""
    raw = '{"desirability": -0.8, "goal_relevance": 0.9, "causal_agent": "other", "praiseworthiness": -0.6, "unexpectedness": 0.3, "proximity": 0.7}'
    appraisal = parse_occ_response(raw)
    assert appraisal is not None
    assert appraisal.desirability == pytest.approx(-0.8)
    assert appraisal.causal_agent == "other"


def test_parse_occ_with_code_fence():
    """T-OCC-7b: LLM 包裹在代码块中的 JSON 也能正确解析。"""
    raw = '```json\n{"desirability": 0.5, "goal_relevance": 0.6, "causal_agent": "self", "praiseworthiness": 0.3, "unexpectedness": 0.2, "proximity": 0.9}\n```'
    appraisal = parse_occ_response(raw)
    assert appraisal is not None
    assert appraisal.desirability == pytest.approx(0.5)


def test_parse_occ_invalid_returns_none():
    """T-OCC-7c: 无法解析时返回 None，不抛出异常。"""
    assert parse_occ_response("这不是 JSON") is None
    assert parse_occ_response("") is None

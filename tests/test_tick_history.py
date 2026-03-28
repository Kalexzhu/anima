"""
tests/test_tick_history.py — TickHistoryStore + LayerContext 单元测试（T1-T7）
"""

import json
import os
import tempfile

import pytest

from core.emotion import EmotionState
from core.thought import ThoughtState
from core.tick_history import LayerContext, TickHistoryStore, TickSnapshot


def _make_state(tick: int, **emotion_kwargs) -> ThoughtState:
    """构造测试用 ThoughtState，情绪值通过 kwargs 指定。"""
    return ThoughtState(
        text=f"thought at tick {tick}",
        emotion=EmotionState(**emotion_kwargs),
        tick=tick,
        perceived=f"perceived at tick {tick}",
        reasoning=f"reasoning at tick {tick}",
    )


# ── T1: TickSnapshot 字段裁剪 ──────────────────────────────────────────────────

def test_tick_snapshot_from_state():
    """T1: ThoughtState → TickSnapshot 只保留 tick/emotion/perceived/reasoning。"""
    state = _make_state(5, fear=0.8, joy=0.1)
    with tempfile.TemporaryDirectory() as tmpdir:
        store = TickHistoryStore(profile_name="test", output_dir=tmpdir)
        store.append(state)

    snap = store._snapshots[0]
    assert snap.tick == 5
    assert snap.emotion.fear == pytest.approx(0.8)
    assert snap.perceived == "perceived at tick 5"
    assert snap.reasoning == "reasoning at tick 5"
    # text 不应出现在 TickSnapshot 中
    assert not hasattr(snap, "text")


# ── T2: 普鲁斯特效应（核心测试）──────────────────────────────────────────────

def test_attention_retrieval_by_emotion():
    """
    T2: 高恐惧情境应召回高恐惧历史快照，而非高喜悦快照。
    这是认知残差的核心验证：普鲁斯特效应是否真正触发。
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        store = TickHistoryStore(profile_name="test", output_dir=tmpdir)
        store.append(_make_state(1, fear=0.9, joy=0.0))   # 高恐惧历史
        store.append(_make_state(2, joy=0.9, fear=0.0))   # 高喜悦历史
        store.append(_make_state(3, fear=0.7, sadness=0.3))  # 中恐惧历史

        current_fear = EmotionState(fear=0.8)
        ctx = store.retrieve(current_fear, top_k=1)

    assert len(ctx.snapshots) == 1
    assert ctx.snapshots[0].tick == 1          # tick=1 是最高恐惧
    assert ctx.snapshots[0].emotion.fear == pytest.approx(0.9)
    assert ctx.weights[0] > 0.8               # 余弦相似度应较高


# ── T3: 空 history 不报错 ─────────────────────────────────────────────────────

def test_attention_retrieval_empty_history():
    """T3: history 为空时 retrieve 返回空 LayerContext，不抛异常。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = TickHistoryStore(profile_name="test", output_dir=tmpdir)
        ctx = store.retrieve(EmotionState(fear=0.5), top_k=3)

    assert ctx.is_empty()
    assert ctx.to_prompt_block() == ""


# ── T4: 全零情绪退化为最近 top_k ──────────────────────────────────────────────

def test_attention_retrieval_zero_emotion():
    """T4: 当前情绪全零时，返回最近 top_k 条（退化路径），不报错。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = TickHistoryStore(profile_name="test", output_dir=tmpdir)
        for i in range(5):
            store.append(_make_state(i, fear=float(i) * 0.1))

        ctx = store.retrieve(EmotionState(), top_k=3)  # 全零情绪

    assert len(ctx.snapshots) == 3
    # 退化路径返回最近 3 条（tick 2, 3, 4）
    ticks = {s.tick for s in ctx.snapshots}
    assert ticks == {2, 3, 4}


# ── T5: jsonl 持久化 ──────────────────────────────────────────────────────────

def test_jsonl_persistence():
    """T5: append 后 jsonl 可读回，字段完整。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = TickHistoryStore(profile_name="alice", output_dir=tmpdir)
        store.append(_make_state(1, fear=0.6, sadness=0.3))
        store.append(_make_state(2, joy=0.8))

        jsonl_path = os.path.join(tmpdir, "alice_tick_history.jsonl")
        assert os.path.exists(jsonl_path)

        with open(jsonl_path, encoding="utf-8") as f:
            lines = [json.loads(l) for l in f if l.strip()]

    assert len(lines) == 2
    assert lines[0]["tick"] == 1
    assert lines[0]["emotion"]["fear"] == pytest.approx(0.6)
    assert lines[0]["perceived"] == "perceived at tick 1"
    assert lines[0]["reasoning"] == "reasoning at tick 1"
    assert "text" not in lines[0]            # text 不应写入 jsonl


# ── T6: LayerContext prompt 格式 ──────────────────────────────────────────────

def test_layer_context_prompt_format():
    """T6: LayerContext.to_prompt_block() 输出包含关键信息且格式可读。"""
    snap = TickSnapshot(
        tick=3,
        emotion=EmotionState(fear=0.75),
        perceived="看到了黑暗的走廊",
        reasoning="感觉有危险，想逃",
    )
    ctx = LayerContext(snapshots=[snap], weights=[0.92])
    block = ctx.to_prompt_block()

    assert "情绪共鸣" in block
    assert "tick=3" in block
    assert "0.92" in block
    assert "黑暗的走廊" in block
    assert "想逃" in block


# ── T7: history < top_k 不报错 ───────────────────────────────────────────────

def test_history_less_than_topk():
    """T7: history 只有 2 条，top_k=5，应返回 2 条不报错。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = TickHistoryStore(profile_name="test", output_dir=tmpdir)
        store.append(_make_state(1, fear=0.5))
        store.append(_make_state(2, anger=0.6))

        ctx = store.retrieve(EmotionState(fear=0.4), top_k=5)

    assert len(ctx.snapshots) == 2
    assert len(ctx.weights) == 2

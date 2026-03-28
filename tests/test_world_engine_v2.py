"""
tests/test_world_engine_v2.py — WorldEngine v2 单元测试

覆盖范围：
  T-WE-1: dramatic 事件在情绪超阈值时触发
  T-WE-2: dramatic 冷却保护（触发后不立即重复）
  T-WE-3: drift 检测（情绪稳定 → [DRIFT] 前缀）
  T-WE-4: drift 触发后清空历史，不连续触发
  T-WE-5: subtle 兜底（平静太久）
  T-WE-6: 事件历史加载失败 → 静默降级为空历史
"""

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from core.emotion import EmotionState
from core.profile import PersonProfile
from core.thought import ThoughtState
from core.world_engine import WorldEngine


def _make_profile(name="test", relationships=None) -> PersonProfile:
    return PersonProfile(
        name=name,
        age=25,
        current_situation="测试处境",
        relationships=relationships or [],
    )


def _make_state(intensity_target: float = 0.0) -> ThoughtState:
    """
    构造情绪强度 = intensity_target 的 ThoughtState。
    EmotionState intensity = sqrt(sum(v^2)/8)，
    全维度相等时 intensity = v，故直接将所有维度设为 intensity_target。
    """
    emotion = EmotionState(
        anger=intensity_target, fear=intensity_target, joy=intensity_target,
        sadness=intensity_target, surprise=intensity_target, disgust=intensity_target,
        anticipation=intensity_target, trust=intensity_target,
    )
    return ThoughtState(text="test thought", emotion=emotion, tick=1)


def _make_engine(profile=None, **kwargs) -> WorldEngine:
    profile = profile or _make_profile()
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = WorldEngine(profile, output_dir=tmpdir, **kwargs)
        engine._tmpdir = tmpdir  # keep reference
    return engine


def _make_engine_in_dir(tmpdir: str, profile=None, **kwargs) -> WorldEngine:
    profile = profile or _make_profile()
    return WorldEngine(profile, output_dir=tmpdir, **kwargs)


# ── T-WE-1: dramatic 在情绪超阈值时触发 ─────────────────────────────────────

def test_dramatic_triggered_above_threshold():
    """T-WE-1: emotion.intensity > threshold → _decide_event 选 dramatic。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = _make_engine_in_dir(tmpdir, threshold=0.45)
        state = _make_state(intensity_target=0.9)

        with patch.object(engine, "_generate_event", return_value="dramatic event") as mock_gen:
            result = engine._decide_event(state)

        mock_gen.assert_called_once_with(state, "dramatic", behavior=None)
        assert result == "dramatic event"


# ── T-WE-2: dramatic 冷却保护 ────────────────────────────────────────────────

def test_dramatic_cooldown_set_after_trigger():
    """T-WE-2: dramatic 触发后，_dramatic_cooldown 应被设置为 dramatic_cooldown_max。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = _make_engine_in_dir(tmpdir, threshold=0.45, dramatic_cooldown=2)
        state = _make_state(intensity_target=0.9)

        with patch.object(engine, "_generate_event", return_value="event"):
            engine._decide_event(state)

        assert engine._dramatic_cooldown == 2


def test_dramatic_not_triggered_during_cooldown():
    """T-WE-2b: _dramatic_cooldown > 0 时，高情绪不应触发 dramatic。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = _make_engine_in_dir(tmpdir, threshold=0.45, dramatic_cooldown=2)
        engine._dramatic_cooldown = 1  # 仍在冷却中
        state = _make_state(intensity_target=0.9)

        with patch.object(engine, "_generate_event", return_value="not dramatic") as mock_gen:
            engine._decide_event(state)

        # 不应以 "dramatic" 模式调用
        for call_args in mock_gen.call_args_list:
            assert call_args[0][1] != "dramatic", "冷却期内不应触发 dramatic"


def test_dramatic_fires_again_after_cooldown():
    """T-WE-2b: 冷却结束（cooldown=0）后，高情绪应再次触发 dramatic。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = _make_engine_in_dir(tmpdir, threshold=0.45, dramatic_cooldown=2)
        engine._dramatic_cooldown = 0  # 冷却已结束
        state = _make_state(intensity_target=0.9)

        with patch.object(engine, "_generate_event", return_value="new dramatic") as mock_gen:
            result = engine._decide_event(state)

        mock_gen.assert_called_once_with(state, "dramatic", behavior=None)
        assert result == "new dramatic"


# ── T-WE-3: drift 检测 ────────────────────────────────────────────────────────

def test_drift_detected_with_stable_emotions():
    """T-WE-3: 情绪长期平稳（delta < threshold）→ _decide_event 返回 [DRIFT] 前缀。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = _make_engine_in_dir(
            tmpdir, threshold=0.45, drift_stability_threshold=0.05, drift_stability_ticks=3
        )
        # 注入稳定的情绪历史（全部约 0.2，变化 < 0.05）
        engine._intensity_history = [0.20, 0.21, 0.20]
        engine._dramatic_cooldown = 2  # 确保 dramatic 不触发

        state = _make_state(intensity_target=0.2)

        with patch.object(engine, "_generate_event", return_value="内省念头"):
            result = engine._decide_event(state)

        assert result.startswith("[DRIFT]")
        assert "内省念头" in result


# ── T-WE-4: drift 触发后清空历史 ─────────────────────────────────────────────

def test_drift_clears_intensity_history():
    """T-WE-4: drift 触发后 _intensity_history 应被清空，避免连续触发。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = _make_engine_in_dir(
            tmpdir, threshold=0.45, drift_stability_threshold=0.05, drift_stability_ticks=3
        )
        engine._intensity_history = [0.20, 0.21, 0.20]
        engine._dramatic_cooldown = 2

        state = _make_state(intensity_target=0.2)

        with patch.object(engine, "_generate_event", return_value="内省"):
            engine._decide_event(state)

        assert engine._intensity_history == []


# ── T-WE-5: subtle 兜底 ──────────────────────────────────────────────────────

def test_subtle_triggered_when_calm_too_long():
    """T-WE-5: 超过 calm_interval 轮无事件 → subtle 触发。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = _make_engine_in_dir(tmpdir, threshold=0.45, calm_interval=3)
        engine._ticks_since_last_event = 3
        engine._dramatic_cooldown = 2  # 确保 dramatic 不触发
        # 情绪历史不足（不触发 drift）
        engine._intensity_history = [0.1]

        state = _make_state(intensity_target=0.1)  # 低情绪，不触发 dramatic 或 relational

        with patch.object(engine, "_generate_event", return_value="细节") as mock_gen:
            result = engine._decide_event(state)

        mock_gen.assert_called_once_with(state, "subtle", behavior=None)
        assert result == "细节"


# ── T-WE-6: 事件历史加载失败静默降级 ─────────────────────────────────────────

def test_load_history_failure_degrades_gracefully():
    """T-WE-6: event_history.jsonl 损坏时，_load_history 静默降级为空历史。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # 写入损坏的 jsonl 文件
        history_path = os.path.join(tmpdir, "test_event_history.jsonl")
        with open(history_path, "w") as f:
            f.write("{ broken json }\nnot json at all\n")

        engine = _make_engine_in_dir(tmpdir, profile=_make_profile(name="test"))
        assert engine._event_history == []


# ── T-WE-7: 事件历史跨轮次持久化 ────────────────────────────────────────────

def test_event_history_persisted_to_jsonl():
    """T-WE-7: tick() 产生事件后，事件应写入 jsonl 文件。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = _make_engine_in_dir(tmpdir, threshold=0.45, profile=_make_profile(name="test"))
        state = _make_state(intensity_target=0.9)

        with patch.object(engine, "_generate_event", return_value="测试事件"):
            engine.tick(state)

        history_path = os.path.join(tmpdir, "test_event_history.jsonl")
        assert os.path.exists(history_path)
        with open(history_path, encoding="utf-8") as f:
            lines = [json.loads(l) for l in f if l.strip()]
        assert len(lines) == 1
        assert lines[0]["event"] == "测试事件"

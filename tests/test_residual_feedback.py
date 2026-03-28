"""
tests/test_residual_feedback.py — ResidualFeedback 单元测试

覆盖范围：
  T-RF-1: 历史不足 MIN_TICKS 时跳过更新
  T-RF-2: 高频 perceived 实体写入 relationships
  T-RF-3: 原子写入（temp + rename）保证文件完整
  T-RF-4: 已有关系不重复写入
"""

import json
import os
import tempfile

import pytest

from core.residual_feedback import ResidualFeedback, MIN_TICKS


def _make_profile(tmpdir: str, extra: dict = None) -> str:
    """创建临时 profile JSON，返回路径。"""
    data = {
        "name": "测试人物",
        "age": 25,
        "personality_traits": ["内向"],
        "core_values": ["诚实"],
        "cognitive_biases": [],
        "memories": [],
        "current_situation": "测试处境",
        "current_physical_state": "",
        "relationships": [],
    }
    if extra:
        data.update(extra)
    path = os.path.join(tmpdir, "profile.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return path


def _make_tick_history(tmpdir: str, ticks: list) -> str:
    """创建临时 tick_history.jsonl，返回路径。"""
    path = os.path.join(tmpdir, "tick_history.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        for t in ticks:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    return path


# ── T-RF-1: 历史不足时跳过 ───────────────────────────────────────────────────

def test_skip_when_insufficient_ticks():
    """T-RF-1: 历史轮次 < MIN_TICKS 时，analyze_and_update 不修改 profile，返回空字典。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        profile_path = _make_profile(tmpdir)
        # 只写 MIN_TICKS - 1 条
        ticks = [{"perceived": "小明", "reasoning": "很担心", "last_event": ""}
                 for _ in range(MIN_TICKS - 1)]
        history_path = _make_tick_history(tmpdir, ticks)

        rf = ResidualFeedback(profile_path)
        updates = rf.analyze_and_update(history_path)

        assert updates == {}
        # profile 未被修改（relationships 仍为空）
        with open(profile_path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["relationships"] == []


# ── T-RF-2: 高频实体写入 relationships ───────────────────────────────────────

def test_high_frequency_entity_added_to_relationships():
    """T-RF-2: perceived 中高频出现的名词（>30% ticks）应被写入 relationships。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        profile_path = _make_profile(tmpdir)

        # 构造 10 条 ticks，"小明" 出现 8 次（80%）
        ticks = []
        for i in range(10):
            perceived = "小明走过来了" if i < 8 else "天空很蓝"
            ticks.append({"perceived": perceived, "reasoning": "", "last_event": ""})

        history_path = _make_tick_history(tmpdir, ticks)

        rf = ResidualFeedback(profile_path)
        updates = rf.analyze_and_update(history_path)

        # 验证 updates 中有 relationships
        assert "relationships" in updates

        # 验证 profile 文件被更新
        with open(profile_path, encoding="utf-8") as f:
            data = json.load(f)
        rel_names = [r.get("name", "") for r in data["relationships"]]
        assert any("小明" in name for name in rel_names)


# ── T-RF-3: 原子写入 ─────────────────────────────────────────────────────────

def test_atomic_write_produces_valid_json():
    """T-RF-3: analyze_and_update 写入后，profile JSON 必须可正常解析。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        profile_path = _make_profile(tmpdir)

        ticks = [{"perceived": "妈妈叫我", "reasoning": "很愧疚", "last_event": ""}
                 for _ in range(10)]
        history_path = _make_tick_history(tmpdir, ticks)

        rf = ResidualFeedback(profile_path)
        rf.analyze_and_update(history_path)

        # 文件必须是合法 JSON
        with open(profile_path, encoding="utf-8") as f:
            data = json.load(f)
        assert "name" in data


# ── T-RF-4: 已有关系不重复写入 ───────────────────────────────────────────────

def test_existing_relationship_not_duplicated():
    """T-RF-4: 若 '小明' 已在 relationships 中，不应重复添加。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        existing_rel = [{"name": "小明", "role": "朋友", "valence": 0.5,
                         "power_dynamic": "", "unresolved_conflicts": [], "typical_phrases": []}]
        profile_path = _make_profile(tmpdir, extra={"relationships": existing_rel})

        ticks = [{"perceived": "小明走过来了", "reasoning": "", "last_event": ""}
                 for _ in range(10)]
        history_path = _make_tick_history(tmpdir, ticks)

        rf = ResidualFeedback(profile_path)
        rf.analyze_and_update(history_path)

        with open(profile_path, encoding="utf-8") as f:
            data = json.load(f)

        # 小明只应出现一次
        xiaoming_entries = [r for r in data["relationships"] if "小明" in r.get("name", "")]
        assert len(xiaoming_entries) == 1

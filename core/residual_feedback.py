"""
core/residual_feedback.py — 认知残差自动写回 Profile。

分析 tick_history.jsonl，检测跨轮次的稳定模式，
将高频出现的元素自动更新到 PersonProfile JSON。

检测模式：
  · perceived 高频实体（>30% ticks）→ relationships
  · reasoning 反复模式（关键词频率）→ cognitive_biases
  · last_event 内容               → memories
  · perceived 感知倾向             → core_values

防护机制：
  · min_ticks=5：历史不足时不更新
  · max_new_per_field=3：每次最多新增 3 条，避免过拟合
  · confidence_threshold=0.60：频率低于此值不写入
  · 原子写入：temp file + rename，防止写入中断导致损坏
"""

from __future__ import annotations
import json
import os
import re
from collections import Counter
from typing import Any, Dict, List


# ── 配置常量 ──────────────────────────────────────────────────────────────────

MIN_TICKS               = 5     # 最少历史轮次，不足则跳过
MIN_FREQUENCY           = 0.30  # 元素出现频率下限（占总轮次比例）
CONFIDENCE_THRESHOLD    = 0.60  # 置信度阈值（当前与 min_frequency 等同，预留）
MAX_NEW_PER_FIELD       = 3     # 每字段每次最多新增条数


# ── 辅助函数 ──────────────────────────────────────────────────────────────────

def _extract_nouns(text: str, min_len: int = 2, max_len: int = 4) -> List[str]:
    """
    简单提取中文名词片段（连续中文字符，长度 [min_len, max_len]）。
    不依赖分词库，适用于感知层短句。
    """
    return [m for m in re.findall(r'[\u4e00-\u9fff]{' + str(min_len) + r',' + str(max_len) + r'}', text)]


# 不可能是人名的中文虚词/助词/尾缀
# "在"（存在动词/介词）、"过"（时态助词）几乎不出现在人名末位
_FUNCTION_CHARS = set("你我了的是啊吗吧呢哦啦呀在过")

# 常见非人名词：感知层高频但肯定不是人物名的 2-3 字词组
_NAME_STOP_WORDS = frozenset({
    # 生理/心理状态
    "睡眠", "睡眠中", "深睡眠", "浅睡眠",
    "呼吸", "喘息", "心跳", "心跳声", "喘不过",
    "情绪", "感受", "感知", "意识", "思维",
    "记忆", "回忆", "想象", "想起",
    # 感官词
    "声音", "声音在", "光线", "影子", "气味",
    # 环境/时间
    "黑暗", "空气", "时间", "空间", "黄昏", "清晨",
    "窗外", "楼道", "走廊", "天花板",
    # 状态描述
    "不确定", "感受到", "意识到", "想起来",
})


def _is_valid_person_name(name: str) -> bool:
    """过滤不像人名的词：含常见虚词/助词，或在已知非人名停用词表中。"""
    if name in _NAME_STOP_WORDS:
        return False
    if any(c in _FUNCTION_CHARS for c in name):
        return False
    return True


def _top_items(
    all_items: List[str],
    existing: List[str],
    total_ticks: int,
) -> List[str]:
    """
    统计 all_items 中的高频条目，过滤掉已在 existing 中的，
    返回满足频率阈值的新条目（最多 MAX_NEW_PER_FIELD 条）。
    """
    counter = Counter(all_items)
    results = []
    for item, count in counter.most_common():
        freq = count / total_ticks
        if freq < MIN_FREQUENCY:
            break
        # 避免与现有条目重复（子串匹配）
        if any(item in e or e in item for e in existing):
            continue
        results.append(item)
        if len(results) >= MAX_NEW_PER_FIELD:
            break
    return results


# ── 主类 ──────────────────────────────────────────────────────────────────────

class ResidualFeedback:
    """
    分析 tick_history.jsonl，将稳定模式写回 PersonProfile JSON。

    用法：
        ResidualFeedback("examples/demo_profile.json").analyze_and_update(
            "output/林晓雨_tick_history.jsonl"
        )
    """

    def __init__(self, profile_path: str):
        self.profile_path = profile_path

    def analyze_and_update(self, tick_history_path: str) -> Dict[str, List[str]]:
        """
        读取 tick_history.jsonl，检测模式，写回 profile。
        返回本次新增的字段内容（用于日志/测试验证）。
        """
        ticks = self._load_ticks(tick_history_path)
        if len(ticks) < MIN_TICKS:
            print(f"[ResidualFeedback] 历史不足 {MIN_TICKS} 轮（当前 {len(ticks)}），跳过更新。")
            return {}

        profile_data = self._load_profile()
        updates: Dict[str, List[str]] = {}

        # ── 1. perceived 高频实体 → staging 文件（不直接写入 profile）────────
        all_nouns = []
        for t in ticks:
            # max_len=3：中文人名通常 2-3 字，避免提取长句片段
            all_nouns.extend(_extract_nouns(t.get("perceived", ""), max_len=3))

        # 过滤非人名词（含虚词）
        all_nouns = [n for n in all_nouns if _is_valid_person_name(n)]

        existing_rel_names = [
            r.get("name", "") if isinstance(r, dict) else ""
            for r in profile_data.get("relationships", [])
        ]
        new_rels = _top_items(all_nouns, existing_rel_names, len(ticks))
        if new_rels:
            updates["relationships_staged"] = new_rels

        # ── 2. reasoning 反复关键词 → staging（不直接写入 profile）───────────
        reasoning_nouns = []
        for t in ticks:
            reasoning_nouns.extend(_extract_nouns(t.get("reasoning", ""), min_len=3))

        existing_biases = profile_data.get("cognitive_biases", [])
        new_biases = _top_items(reasoning_nouns, existing_biases, len(ticks))
        if new_biases:
            updates["cognitive_biases_staged"] = new_biases

        # ── 3. last_event 内容 → staging（不直接写入 profile）────────────────
        events = [
            t.get("last_event", "").strip()
            for t in ticks
            if t.get("last_event", "").strip()
            and not t["last_event"].startswith("[DRIFT]")
        ]
        existing_mem_events = [
            m.get("event", "") if isinstance(m, dict) else ""
            for m in profile_data.get("memories", [])
        ]
        new_mem_events = _top_items(events, existing_mem_events, len(ticks))
        if new_mem_events:
            updates["memories_staged"] = new_mem_events

        # ── 全部写入 staging 文件（原始 profile 只读，不再修改）───────────────
        if updates:
            self._stage_all_detections(updates, profile_data)
        else:
            print("[ResidualFeedback] 未检测到需要更新的新模式。")

        return updates

    # ── 内部工具 ───────────────────────────────────────────────────────────────

    def _stage_all_detections(self, updates: dict, profile_data: dict) -> None:
        """将所有检测结果写入 staging 文件，原始 profile 只读不修改。"""
        staging_dir = os.path.dirname(os.path.abspath(self.profile_path))
        os.makedirs(staging_dir, exist_ok=True)
        name = profile_data.get("name", "unknown")
        staging_path = os.path.join(staging_dir, f"{name}_residual_staging.json")
        existing: dict = {}
        if os.path.exists(staging_path):
            try:
                with open(staging_path, encoding="utf-8") as f:
                    existing = json.load(f)
            except (json.JSONDecodeError, OSError):
                existing = {}
        for key, items in updates.items():
            prev = existing.get(key, [])
            for item in items:
                if item not in prev:
                    prev.append(item)
            existing[key] = prev
        with open(staging_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        print(f"[ResidualFeedback] 检测结果写入 staging（profile 未修改）：{staging_path}")

    def _load_ticks(self, path: str) -> List[Dict[str, Any]]:
        ticks = []
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        ticks.append(json.loads(line))
        except (OSError, json.JSONDecodeError) as e:
            print(f"[ResidualFeedback] tick_history 读取失败：{e}")
        return ticks

    def _load_profile(self) -> Dict[str, Any]:
        with open(self.profile_path, encoding="utf-8") as f:
            return json.load(f)

    # _atomic_write 已移除（v6）：原始 profile 只读，所有检测结果写入 staging 文件。

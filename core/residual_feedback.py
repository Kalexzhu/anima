"""
core/residual_feedback.py — 认知残差模式检测（只读分析，不修改原始 Profile）。

分析 tick_history.jsonl，检测跨轮次的稳定模式，
将检测结果写入 staging 文件供人工审阅。原始 Profile 永远不被修改。

检测维度：
  · perceived 高频实体    → relationships_staged
  · reasoning 反复关键词  → cognitive_biases_staged
  · last_event 重复事件   → memories_staged

防护机制：
  · min_ticks=5：历史不足时不分析
  · max_new_per_field=3：每维度每次最多检出 3 条
  · min_frequency=0.30：频率低于 30% 的模式不报告

输出：
  output/{profile_name}_residual_staging.json（增量追加，不覆盖）
"""

from __future__ import annotations
import json
import os
import re
from collections import Counter
from typing import Any, Dict, List


# ── 配置常量 ──────────────────────────────────────────────────────────────────

MIN_TICKS           = 5     # 最少历史轮次，不足则跳过
MIN_FREQUENCY       = 0.30  # 元素出现频率下限（占总轮次比例）
MAX_NEW_PER_FIELD   = 3     # 每维度每次最多检出条数


# ── 辅助函数 ──────────────────────────────────────────────────────────────────

def _extract_nouns(text: str, min_len: int = 2, max_len: int = 4) -> List[str]:
    """
    简单提取中文名词片段（连续中文字符，长度 [min_len, max_len]）。
    不依赖分词库，适用于感知层短句。
    """
    return [m for m in re.findall(r'[\u4e00-\u9fff]{' + str(min_len) + r',' + str(max_len) + r'}', text)]


_FUNCTION_CHARS = set("你我了的是啊吗吧呢哦啦呀在过")

_NAME_STOP_WORDS = frozenset({
    "睡眠", "睡眠中", "深睡眠", "浅睡眠",
    "呼吸", "喘息", "心跳", "心跳声", "喘不过",
    "情绪", "感受", "感知", "意识", "思维",
    "记忆", "回忆", "想象", "想起",
    "声音", "声音在", "光线", "影子", "气味",
    "黑暗", "空气", "时间", "空间", "黄昏", "清晨",
    "窗外", "楼道", "走廊", "天花板",
    "不确定", "感受到", "意识到", "想起来",
})


def _is_valid_person_name(name: str) -> bool:
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
    统计高频条目，过滤已存在的，返回满足频率阈值的新条目。
    """
    counter = Counter(all_items)
    results = []
    for item, count in counter.most_common():
        freq = count / total_ticks
        if freq < MIN_FREQUENCY:
            break
        if any(item in e or e in item for e in existing):
            continue
        results.append(item)
        if len(results) >= MAX_NEW_PER_FIELD:
            break
    return results


# ── 主类 ──────────────────────────────────────────────────────────────────────

class ResidualFeedback:
    """
    分析 tick_history.jsonl 中的稳定模式，写入 staging 文件。
    原始 Profile 只读，不做任何修改。

    用法：
        detections = ResidualFeedback(
            profile_path="examples/demo_profile.json",
            output_dir="output",
        ).analyze("output/林晓雨_tick_history.jsonl")
    """

    def __init__(self, profile_path: str, output_dir: str = "output"):
        self.profile_path = profile_path
        self.output_dir = output_dir

    def analyze(self, tick_history_path: str) -> Dict[str, List[str]]:
        """
        读取 tick_history，检测模式，写入 staging 文件。
        返回本次检出的内容（用于日志/测试）。
        """
        ticks = self._load_ticks(tick_history_path)
        if len(ticks) < MIN_TICKS:
            print(f"[ResidualFeedback] 历史不足 {MIN_TICKS} 轮（当前 {len(ticks)}），跳过。")
            return {}

        profile_data = self._load_profile()
        detections: Dict[str, List[str]] = {}

        # ── 1. perceived 高频实体 → relationships_staged ─────────────────────
        all_nouns = []
        for t in ticks:
            all_nouns.extend(_extract_nouns(t.get("perceived", ""), max_len=3))
        all_nouns = [n for n in all_nouns if _is_valid_person_name(n)]

        existing_rel_names = [
            r.get("name", "") if isinstance(r, dict) else ""
            for r in profile_data.get("relationships", [])
        ]
        new_rels = _top_items(all_nouns, existing_rel_names, len(ticks))
        if new_rels:
            detections["relationships_staged"] = new_rels

        # ── 2. reasoning 反复关键词 → cognitive_biases_staged ────────────────
        reasoning_nouns = []
        for t in ticks:
            reasoning_nouns.extend(_extract_nouns(t.get("reasoning", ""), min_len=3))

        existing_biases = profile_data.get("cognitive_biases", [])
        new_biases = _top_items(reasoning_nouns, existing_biases, len(ticks))
        if new_biases:
            detections["cognitive_biases_staged"] = new_biases

        # ── 3. last_event 重复事件 → memories_staged ─────────────────────────
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
        new_events = _top_items(events, existing_mem_events, len(ticks))
        if new_events:
            detections["memories_staged"] = new_events

        # ── 写入 staging ─────────────────────────────────────────────────────
        if detections:
            self._write_staging(detections, profile_data.get("name", "unknown"))
        else:
            print("[ResidualFeedback] 未检测到新模式。")

        return detections

    # ── 兼容旧调用签名 ────────────────────────────────────────────────────────

    def analyze_and_update(self, tick_history_path: str) -> Dict[str, List[str]]:
        """兼容旧调用。等同于 analyze()。"""
        return self.analyze(tick_history_path)

    # ── 内部工具 ───────────────────────────────────────────────────────────────

    def _write_staging(self, detections: dict, profile_name: str) -> None:
        """将检测结果增量写入 staging 文件。"""
        os.makedirs(self.output_dir, exist_ok=True)
        staging_path = os.path.join(self.output_dir, f"{profile_name}_residual_staging.json")

        existing: dict = {}
        if os.path.exists(staging_path):
            try:
                with open(staging_path, encoding="utf-8") as f:
                    existing = json.load(f)
            except (json.JSONDecodeError, OSError):
                existing = {}

        for key, items in detections.items():
            prev = existing.get(key, [])
            for item in items:
                if item not in prev:
                    prev.append(item)
            existing[key] = prev

        with open(staging_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        print(f"[ResidualFeedback] 检测结果写入 staging：{staging_path}")

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

"""
core/emotion_constraint.py — 情绪约束生成与验证。

系统流程：
  1. EmotionConstraintBuilder.build(event_text, perceived_text)
     → 查 DUTIR 词典，得到候选情绪集合（不强制方向，避免词义歧义）
     → 查历史统计日志，若同类事件 ≥20 条则用统计 prior
     → 输出 EmotionConstraint

  2. EmotionValidator.validate(llm_output, constraint, prev_emotion)
     → 检查：单次变化量是否在上限内？
     → 检查：若有候选集合，主导情绪是否在其中？
     → 不满足时裁剪修正，打印 WARNING

  3. log_emotion_event() 每次 emotion_layer 调用后 append 写入
     output/event_emotion_log.jsonl（统计积累用）

设计原则：
  - 约束是「软约束」：LLM 输出的情绪方向优先，词典负责防止极端异常
  - 词典覆盖率低时（命中词 < 2），约束退化为只限制单次变化量上限
  - 统计 prior 在 ≥20 条同类事件后逐渐生效，置信度线性上升
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from core.dutir_loader import score_text, get_dominant_emotions, get_hit_words, PLUTCHIK_DIMS

_LOG_PATH = Path(__file__).parent.parent / "output" / "event_emotion_log.jsonl"
_MAX_SINGLE_DELTA = 0.6
_STATS_MIN_SAMPLES = 20
_KEYWORD_OVERLAP_THRESHOLD = 0.4


@dataclass
class EmotionConstraint:
    """
    情绪约束对象。

    candidate_emotions: 词典分析出的情绪候选集合，空列表表示不限制方向
    max_deltas:         各维度单次最大变化量（硬性上限）
    source:             约束来源 dictionary / statistics / none
    confidence:         置信度 0.0~1.0
    hit_words:          命中的词典词，用于日志
    stats_sample_count: 同类事件历史记录数
    """
    candidate_emotions: List[str] = field(default_factory=list)
    max_deltas: Dict[str, float] = field(default_factory=lambda: {d: _MAX_SINGLE_DELTA for d in PLUTCHIK_DIMS})
    source: str = "none"
    confidence: float = 0.0
    hit_words: List = field(default_factory=list)
    stats_sample_count: int = 0


class EmotionConstraintBuilder:

    def build(self, event_text: str, perceived_text: str = "") -> EmotionConstraint:
        """
        根据事件文本和感知文本构建情绪约束。
        优先级：统计 prior（≥20条）> 词典约束 > 无约束
        """
        combined = f"{event_text} {perceived_text}".strip()
        if not combined:
            return EmotionConstraint(source="none")

        dict_scores = score_text(combined)
        hit_words = get_hit_words(combined)
        candidate_emotions = get_dominant_emotions(combined, top_n=3)

        # 优先用统计 prior
        stats_constraint = self._query_stats(hit_words)
        if stats_constraint is not None:
            return stats_constraint

        # 词典约束（命中词 ≥ 2 才有效）
        if len(hit_words) >= 2:
            max_deltas = {
                dim: min(_MAX_SINGLE_DELTA, max(0.1, dict_scores.get(dim, 0.0) * 1.2 + 0.15))
                for dim in PLUTCHIK_DIMS
            }
            return EmotionConstraint(
                candidate_emotions=candidate_emotions,
                max_deltas=max_deltas,
                source="dictionary",
                confidence=0.5,
                hit_words=hit_words,
            )

        # 词典命中不足，只保留硬性上限
        return EmotionConstraint(
            candidate_emotions=[],
            max_deltas={d: _MAX_SINGLE_DELTA for d in PLUTCHIK_DIMS},
            source="none",
            confidence=0.0,
            hit_words=hit_words,
        )

    def _query_stats(self, hit_words: list) -> Optional[EmotionConstraint]:
        if not _LOG_PATH.exists() or not hit_words:
            return None

        query_keywords = set(w for w, _, _ in hit_words)
        matching_records = []

        try:
            with open(_LOG_PATH, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    record = json.loads(line)
                    record_keywords = set(record.get("event_keywords", []))
                    if not record_keywords:
                        continue
                    overlap = len(query_keywords & record_keywords) / len(query_keywords | record_keywords)
                    if overlap >= _KEYWORD_OVERLAP_THRESHOLD:
                        matching_records.append(record)
        except (json.JSONDecodeError, OSError):
            return None

        if len(matching_records) < _STATS_MIN_SAMPLES:
            return None

        dim_values: Dict[str, List[float]] = {d: [] for d in PLUTCHIK_DIMS}
        for record in matching_records:
            output = record.get("plutchik_output", {})
            for dim in PLUTCHIK_DIMS:
                if dim in output:
                    dim_values[dim].append(float(output[dim]))

        means, stds = {}, {}
        for dim in PLUTCHIK_DIMS:
            vals = dim_values[dim]
            if vals:
                means[dim] = sum(vals) / len(vals)
                variance = sum((v - means[dim]) ** 2 for v in vals) / len(vals)
                stds[dim] = math.sqrt(variance)
            else:
                means[dim] = 0.0
                stds[dim] = 0.1

        candidate_emotions = [
            d for d in sorted(means, key=means.get, reverse=True)[:2]
            if means[d] > 0.05
        ]
        max_deltas = {
            dim: min(_MAX_SINGLE_DELTA, means[dim] + 2 * stds[dim] + 0.1)
            for dim in PLUTCHIK_DIMS
        }

        return EmotionConstraint(
            candidate_emotions=candidate_emotions,
            max_deltas=max_deltas,
            source="statistics",
            confidence=min(0.95, 0.5 + len(matching_records) * 0.01),
            stats_sample_count=len(matching_records),
        )


class EmotionValidator:

    def validate(
        self,
        llm_output: Dict[str, float],
        constraint: EmotionConstraint,
        prev_emotion: Dict[str, float],
    ) -> tuple[Dict[str, float], bool]:
        """
        校验并修正 LLM 输出的情绪向量。

        Args:
            llm_output:   LLM 生成的情绪向量 {dim: value}
            constraint:   EmotionConstraintBuilder 生成的约束
            prev_emotion: 上一轮情绪向量（用于计算 delta）

        Returns:
            (corrected_output, was_corrected)
            was_corrected=True 表示发生了修正，调用方应打印 WARNING
        """
        corrected = dict(llm_output)
        was_corrected = False

        # 1. 单次变化量上限（硬性约束，始终生效）
        for dim in PLUTCHIK_DIMS:
            if dim not in corrected:
                continue
            prev_val = prev_emotion.get(dim, 0.0)
            delta = corrected[dim] - prev_val
            max_delta = constraint.max_deltas.get(dim, _MAX_SINGLE_DELTA)
            if abs(delta) > max_delta:
                corrected[dim] = prev_val + math.copysign(max_delta, delta)
                corrected[dim] = max(0.0, min(1.0, corrected[dim]))
                was_corrected = True

        # 2. 方向约束（软约束，仅在有候选集合且置信度 ≥ 0.5 时生效）
        if constraint.candidate_emotions and constraint.confidence >= 0.5:
            dominant_dim = max(
                (d for d in PLUTCHIK_DIMS if d in corrected),
                key=lambda d: corrected[d],
                default=None,
            )
            if dominant_dim and dominant_dim not in constraint.candidate_emotions:
                # LLM 主导情绪不在候选集合内：降权到候选集合最高值以下
                candidate_max = max(
                    corrected.get(d, 0.0) for d in constraint.candidate_emotions
                ) if constraint.candidate_emotions else 0.0
                if corrected[dominant_dim] > candidate_max + 0.1:
                    corrected[dominant_dim] = max(0.0, candidate_max - 0.05)
                    was_corrected = True

        return corrected, was_corrected


def log_emotion_event(
    event_keywords: List[str],
    plutchik_output: Dict[str, float],
    intensity: float,
    was_corrected: bool,
    correction_reason: Optional[str] = None,
) -> None:
    """
    将本次 emotion_layer 结果 append 写入 event_emotion_log.jsonl。
    用于统计 prior 的数据积累。
    """
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "event_keywords": event_keywords,
        "plutchik_output": {k: round(v, 4) for k, v in plutchik_output.items()},
        "intensity": round(intensity, 4),
        "was_corrected": was_corrected,
        "correction_reason": correction_reason,
    }
    with open(_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

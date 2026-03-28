"""
core/tick_history.py — 认知残差：运行时 tick 历史存储与注意力检索。

设计思路（对应 Kimi AttnRes 论文）：
  标准做法：每层只看上一层压缩后的混合状态
  本模块：当前认知循环可"回头看"所有历史 tick 的精确输出，
          检索权重由当前情绪状态动态决定（情绪余弦相似度）

数据流：
  run_cognitive_cycle()
      │
      ├─ emotion_layer()          → new_emotion
      ├─ tick_store.retrieve(new_emotion)  → LayerContext（top-K 历史快照）
      ├─ reasoning_layer(layer_ctx)
      ├─ arbiter_layer_stream(layer_ctx)
      └─ tick_store.append(new_state)  → 持久化到 jsonl

普鲁斯特效应：
  当前情绪（如高恐惧）→ 优先召回过去高恐惧时刻的感知与推断
  不是语义检索，而是情绪状态共振触发的精确历史回溯

持久化：
  output/{profile_name}_tick_history.jsonl（append-only）
  每条记录只写 tick/emotion/perceived/reasoning，不写完整 text（太长）
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple, Optional, TYPE_CHECKING

from core.emotion_utils import emotion_cosine, emotion_to_vec, EMOTION_DIMS

if TYPE_CHECKING:
    from core.emotion import EmotionState
    from core.thought import ThoughtState


# ── TickSnapshot ───────────────────────────────────────────────────────────────

@dataclass
class TickSnapshot:
    """
    一次认知循环的精简快照，用于 attention 检索和 prompt 注入。
    只保留 attention 计算和上下文注入所需的 4 个字段：
      - emotion: 用于余弦相似度计算（attention key）
      - perceived: 感知层输出（注入 reasoning 提供"当时看到了什么"）
      - reasoning: 推理层内心推断（注入 arbiter 提供"当时的内在逻辑"）
      - tick: 用于排序和日志
    不保存 text（太长）和 memory_fragment（传记记忆不需要跨 tick 回溯）。
    """
    tick: int
    emotion: "EmotionState"
    perceived: str
    reasoning: str

    def to_dict(self) -> dict:
        return {
            "tick": self.tick,
            "emotion": self.emotion.to_dict(),
            "perceived": self.perceived,
            "reasoning": self.reasoning,
        }

    def to_prompt_line(self, weight: float) -> str:
        """格式化为 prompt 注入的单行描述。"""
        dominant = self.emotion.dominant()
        intensity = self.emotion.intensity
        return (
            f"[历史 tick={self.tick}, {dominant}={intensity:.2f}, 相似度={weight:.2f}]\n"
            f"  当时感知：{self.perceived[:80]}\n"
            f"  当时推断：{self.reasoning[:100]}"
        )


# ── LayerContext ───────────────────────────────────────────────────────────────

@dataclass
class LayerContext:
    """
    注意力检索结果，传入 reasoning_layer 和 arbiter_layer_stream。
    snapshots 和 weights 一一对应，按相似度降序排列。
    """
    snapshots: List[TickSnapshot] = field(default_factory=list)
    weights: List[float] = field(default_factory=list)

    def is_empty(self) -> bool:
        return len(self.snapshots) == 0

    def to_prompt_block(self) -> str:
        """
        格式化为可直接注入 prompt 的文本块。
        空历史时返回空字符串，不在 prompt 中添加无意义的章节标题。
        """
        if self.is_empty():
            return ""
        lines = ["情绪共鸣的历史时刻（由当前情绪动态召回）："]
        for snap, weight in zip(self.snapshots, self.weights):
            lines.append(snap.to_prompt_line(weight))
        return "\n".join(lines)


# ── TickHistoryStore ───────────────────────────────────────────────────────────

class TickHistoryStore:
    """
    运行时 tick 历史存储，跨认知循环持续存在。
    由 run.py 在循环前创建，传入每次 run_cognitive_cycle 调用。

    注意：这是运行时历史（当前 session 的 tick 快照），
    不同于 MemoryManager 存储的传记记忆（人物档案中的过去经历）。
    """

    def __init__(self, profile_name: str = "default", output_dir: str = "output"):
        self._snapshots: List[TickSnapshot] = []
        self._jsonl_path = Path(output_dir) / f"{profile_name}_tick_history.jsonl"
        self._jsonl_path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, state: "ThoughtState") -> None:
        """
        从 ThoughtState 提取 TickSnapshot 并存储。
        同时 append 到 jsonl（写入失败不中断循环，只打印警告）。
        """
        snap = TickSnapshot(
            tick=state.tick,
            emotion=state.emotion,
            perceived=state.perceived,
            reasoning=state.reasoning,
        )
        self._snapshots.append(snap)
        self._write_jsonl(snap)

    def retrieve(
        self,
        current_emotion: "EmotionState",
        top_k: int = 3,
    ) -> LayerContext:
        """
        基于情绪余弦相似度检索最相关的历史快照（普鲁斯特效应）。

        当 history 为空时返回空 LayerContext（不报错）。
        当 current_emotion 全零时，所有相似度为 0，退化为返回最近 top_k 条。

        Args:
            current_emotion: 当前情绪状态（attention query）
            top_k: 返回快照数量上限

        Returns:
            LayerContext，按相似度降序排列
        """
        if not self._snapshots:
            return LayerContext()

        current_vec = emotion_to_vec(current_emotion)
        is_zero_emotion = all(v < 1e-6 for v in current_vec.values())

        if is_zero_emotion:
            # 退化路径：全零情绪无法做余弦相似度，返回最近 top_k 条
            recent = self._snapshots[-top_k:]
            return LayerContext(
                snapshots=recent,
                weights=[0.0] * len(recent),
            )

        scored: List[Tuple[float, TickSnapshot]] = []
        for snap in self._snapshots:
            hist_vec = emotion_to_vec(snap.emotion)
            score = emotion_cosine(current_vec, hist_vec)
            scored.append((score, snap))

        scored.sort(key=lambda x: -x[0])
        top = scored[:top_k]

        return LayerContext(
            snapshots=[s for _, s in top],
            weights=[w for w, _ in top],
        )

    def __len__(self) -> int:
        return len(self._snapshots)

    def _write_jsonl(self, snap: TickSnapshot) -> None:
        try:
            with open(self._jsonl_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(snap.to_dict(), ensure_ascii=False) + "\n")
        except OSError as e:
            print(f"[TickHistoryStore] WARNING: jsonl 写入失败，跳过持久化: {e}")

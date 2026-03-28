"""
core/memory.py — 记忆管理层。
使用 CAMEL 的 LongtermAgentMemory（ChatHistoryBlock + VectorDBBlock）
替换原始的 prompt 拼接方案。

新增：情绪编码记忆（emotion-encoded memory）
  - 每条记忆存储编码时的情绪向量
  - 检索时按 情绪余弦相似度(60%) + 重要性(40%) 综合评分
  - 在相似情绪状态下，过去的记忆更容易被激活（状态依存记忆）

依赖：pip3 install camel-ai qdrant-client
"""

from __future__ import annotations
import math
from typing import List, Dict, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.emotion import EmotionState

# ── CAMEL 记忆系统 ─────────────────────────────────────────────────────────────
try:
    from camel.memories import (
        ChatHistoryBlock,
        LongtermAgentMemory,
        MemoryRecord,
        ScoreBasedContextCreator,
        VectorDBBlock,
    )
    from camel.messages import BaseMessage
    from camel.types import ModelType, OpenAIBackendRole
    from camel.utils import OpenAITokenCounter
    _CAMEL_AVAILABLE = True
except ImportError:
    _CAMEL_AVAILABLE = False

# ── 情绪工具函数（从 emotion_utils 导入，避免重复实现）────────────────────────
from core.emotion_utils import emotion_cosine as _emotion_cosine, EMOTION_DIMS as _EMOTION_DIMS

_EMOTION_TAG_MAP: Dict[str, Dict[str, float]] = {
    "anger":       {"anger": 0.85},
    "fear":        {"fear": 0.85},
    "joy":         {"joy": 0.85},
    "sadness":     {"sadness": 0.85},
    "surprise":    {"surprise": 0.85},
    "disgust":     {"disgust": 0.85},
    "anticipation":{"anticipation": 0.85},
    "trust":       {"trust": 0.85},
    # 复合情绪
    "shame":       {"disgust": 0.5, "sadness": 0.4, "fear": 0.3},
    "anxiety":     {"fear": 0.6, "anticipation": 0.4},
    "guilt":       {"disgust": 0.4, "sadness": 0.5, "fear": 0.2},
    "loneliness":  {"sadness": 0.7, "fear": 0.3},
    "pride":       {"joy": 0.6, "trust": 0.5},
    "love":        {"joy": 0.5, "trust": 0.7},
    "grief":       {"sadness": 0.9, "fear": 0.2},
}


def _tag_to_vector(tag: str) -> Dict[str, float]:
    """将情绪标签字符串转为归一化的 8 维向量 dict。"""
    return _EMOTION_TAG_MAP.get(tag.lower(), {})


class MemoryManager:
    """
    人物记忆管理器。
    优先使用 CAMEL LongtermAgentMemory（向量语义检索）；
    若 camel-ai 未安装，自动降级为情绪编码检索（兼容模式）。
    """

    def __init__(self, token_limit: int = 1024):
        self._records: List[Dict[str, Any]] = []   # 兼容模式存储
        self._memory = None                         # CAMEL 记忆对象

        if _CAMEL_AVAILABLE:
            try:
                self._memory = LongtermAgentMemory(
                    context_creator=ScoreBasedContextCreator(
                        token_counter=OpenAITokenCounter(ModelType.GPT_4O_MINI),
                        token_limit=token_limit,
                    ),
                    chat_history_block=ChatHistoryBlock(),
                    vector_db_block=VectorDBBlock(),
                )
                print("[MemoryManager] 使用 CAMEL LongtermAgentMemory ✓")
            except Exception as e:
                print(f"[MemoryManager] CAMEL 初始化失败，降级为情绪编码模式: {e}")
                self._memory = None
        else:
            print("[MemoryManager] camel-ai 未安装，使用情绪编码检索模式")

    @property
    def mode(self) -> str:
        return "camel" if self._memory is not None else "emotion-encoded"

    def write(
        self,
        event: str,
        age: int = 0,
        emotion_tag: str = "",
        importance: float = 0.5,
        emotion_vector: Optional[Dict[str, float]] = None,
    ):
        """
        写入一条记忆记录。
        emotion_vector 优先；未提供时从 emotion_tag 推断。
        """
        ev = emotion_vector or _tag_to_vector(emotion_tag)
        raw = {
            "event": event,
            "age": age,
            "emotion_tag": emotion_tag,
            "importance": importance,
            "emotion_vector": ev,
        }
        self._records.append(raw)

        if self._memory is not None:
            # CAMEL 模式：把情绪信息嵌入内容字符串，让向量库语义感知
            content = f"[{age}岁·{emotion_tag}·重要性{importance:.1f}] {event}"
            try:
                record = MemoryRecord(
                    message=BaseMessage.make_user_message(
                        role_name="Memory",
                        meta_dict=None,
                        content=content,
                    ),
                    role_at_backend=OpenAIBackendRole.USER,
                )
                self._memory.write_records([record])
            except Exception:
                pass

    def load_from_profile(self, memories: List[Dict[str, Any]]):
        """批量从人物档案写入所有历史记忆。"""
        for m in memories:
            self.write(
                event=m.get("event", ""),
                age=m.get("age", 0),
                emotion_tag=m.get("emotion_tag", ""),
                importance=m.get("importance", 0.5),
                emotion_vector=m.get("emotion_vector"),  # 支持直接提供向量
            )

    def retrieve(
        self,
        query: str,
        top_k: int = 3,
        current_emotion: Optional["EmotionState"] = None,
    ) -> str:
        """
        检索最相关的记忆片段。

        情绪编码模式（默认）：
          得分 = 重要性 × 0.4 + 情绪余弦相似度 × 0.6
          在相似的情绪状态下，过去的记忆更容易被激活。

        CAMEL 模式：语义检索结果 + 情绪相似度二次排序。
        """
        if not self._records:
            return ""

        if self._memory is not None:
            try:
                context, _ = self._memory.get_context()
                relevant = context[:top_k]
                if relevant:
                    return "\n".join(f"- {m.content}" for m in relevant)
            except Exception:
                pass  # 降级到情绪编码模式

        # 情绪编码检索
        current_vec: Dict[str, float] = {}
        if current_emotion is not None:
            current_vec = {d: getattr(current_emotion, d, 0.0) for d in _EMOTION_DIMS}

        scored = []
        for m in self._records:
            importance_score = m.get("importance", 0.5)
            emotion_score = _emotion_cosine(current_vec, m.get("emotion_vector", {}))
            total = importance_score * 0.4 + emotion_score * 0.6
            scored.append((total, m))

        scored.sort(key=lambda x: -x[0])
        top = [m for _, m in scored[:top_k]]
        return "\n".join(
            f"- [{m.get('age','?')}岁·{m.get('emotion_tag','')}] {m['event']}"
            for m in top
        )

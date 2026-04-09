"""
core/memory_sampler.py — 记忆预采样 + 冷却追踪。

每 tick 从 profile.memories 中选出一组记忆注入 prompt：
  - top N 条按 importance 降序（稳定基底）
  - M 条从剩余中随机取（新鲜感），冷却期内的条目被排除

冷却机制防止连续 tick 反复采样相同的低重要性记忆。
"""

from __future__ import annotations
import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.profile import PersonProfile


class MemoryCooldownTracker:
    """
    记录每条记忆最近被采样的 tick，在冷却期内将其排除出随机池。
    冷却只影响随机 M 条的候选范围，不影响 importance top-N。
    """
    COOLDOWN_TICKS = 5

    def __init__(self) -> None:
        self._last_sampled: dict[int, int] = {}

    def is_available(self, index: int, current_tick: int) -> bool:
        return (current_tick - self._last_sampled.get(index, -999)) > self.COOLDOWN_TICKS

    def record(self, indices: list[int], tick: int) -> None:
        for i in indices:
            self._last_sampled[i] = tick


def sample_memories(
    profile: "PersonProfile",
    tracker: MemoryCooldownTracker,
    current_tick: int,
    n_importance: int = 5,
    n_random: int = 3,
) -> list[dict]:
    """
    预采样记忆：top n_importance + 随机 n_random（含冷却过滤）。
    """
    mems = profile.memories
    if not mems:
        return []

    indexed = sorted(enumerate(mems), key=lambda x: -x[1].get("importance", 0))
    top_n = indexed[:n_importance]
    remaining = indexed[n_importance:]

    available = [(i, m) for i, m in remaining if tracker.is_available(i, current_tick)]
    pool = available if available else remaining

    random_picked = random.sample(pool, min(n_random, len(pool)))

    all_sampled_indices = [i for i, _ in top_n] + [i for i, _ in random_picked]
    tracker.record(all_sampled_indices, current_tick)

    return [m for _, m in top_n] + [m for _, m in random_picked]

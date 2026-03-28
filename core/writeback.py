"""
core/writeback.py — 5轮批量记忆写回。

每轮 B2 输出的 conclusion 暂存于此，每 5 轮由 LLM 自动审查，
将符合准入条件的结论写入 profile.memories。
"""

from __future__ import annotations
import json
import re
from core.profile import PersonProfile
from agents.base_agent import claude_call

_FLUSH_INTERVAL = 5  # 每隔多少轮审查一次

_SYS_REVIEW = (
    "你是记忆筛选器。从候选结论中选出值得长期保留的条目。\n\n"
    "写入条件（必须同时满足）：\n"
    "  1. 角色做出了具体的行动微决定（去哪/做什么/不做什么）\n"
    "  2. 结论是行动导向，不是情绪评估或自我认识\n\n"
    "不写入：情绪陈述、自我否定/内耗结论（「我是拖累」「我做不到」类）、与现有记忆高度重复的内容。\n\n"
    "输出严格 JSON（不加代码块）:{\"selected\": [\"结论1\", \"结论2\"]}\n"
    "如果没有值得写入的，输出：{\"selected\": []}"
)


class WritebackManager:
    """
    收集每轮 B2 产出的 conclusion，每 FLUSH_INTERVAL 轮批量写入 profile.memories。
    """

    def __init__(self, profile: PersonProfile):
        self.profile = profile
        self._pending: list[dict] = []  # [{"tick": int, "conclusion": str}]

    def add_candidate(self, tick: int, conclusion: str | None) -> None:
        if conclusion:
            self._pending.append({"tick": tick, "conclusion": conclusion})

    def maybe_flush(self, current_tick: int) -> bool:
        """每 FLUSH_INTERVAL 轮调用一次审查。返回是否执行了写回。"""
        if current_tick % _FLUSH_INTERVAL != 0 or not self._pending:
            return False
        self._flush()
        self._pending.clear()
        return True

    def _flush(self) -> None:
        candidates = self._pending
        if not candidates:
            return

        existing_summary = "；".join(
            m.get("event", "")[:30]
            for m in self.profile.memories[-5:]
        )
        candidates_text = "\n".join(
            f"- 轮次{c['tick']}：{c['conclusion']}"
            for c in candidates
        )
        prompt = (
            f"现有记忆摘要（最近5条）：{existing_summary or '无'}\n\n"
            f"候选结论：\n{candidates_text}\n\n"
            "请按准入规则筛选，输出 JSON。"
        )

        raw = claude_call(prompt, system=_SYS_REVIEW, max_tokens=256)
        try:
            m = re.search(r'\{.*\}', raw, re.DOTALL)
            if not m:
                print(f"[Writeback] 解析失败，raw={raw[:80]!r}")
                return
            data = json.loads(m.group())
            selected: list[str] = data.get("selected", [])
            for conclusion in selected:
                self.profile.memories.append({
                    "event": conclusion,
                    "age": self.profile.age,
                    "emotion_tag": "neutral",
                    "importance": 0.5,
                })
            if selected:
                print(f"[Writeback] 写入 {len(selected)} 条记忆：{selected}")
            else:
                print("[Writeback] 本批次无值得写入的结论")
        except Exception as e:
            print(f"[Writeback] 写回异常：{e}")

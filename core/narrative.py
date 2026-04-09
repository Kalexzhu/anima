"""
core/narrative.py — 叙事线索管理器

维护角色当前的"故事线索"列表，驱动 WorldEngine 推进叙事而非响应情绪。

数据流：
  narrative_state.json
       ↓ get_top_thread()
  WorldEngine → 推进该线索的事件
       ↓
  ThoughtState { conclusion }
       ↓
  process_action() → 关闭/新建线索 → narrative_state.json
"""

import json
import os

from agents.base_agent import claude_call

_SYS_ACTION_JUDGE = (
    "你是叙事逻辑判断员。"
    "根据角色的行动决定，判断哪些线索被推进或关闭，是否产生新线索。"
    "只输出纯 JSON，不加任何解释或 markdown 代码块。"
)


class NarrativeThreadManager:
    def __init__(self, state_path: str):
        self._path = state_path
        self._threads: list[dict] = []
        self._thread_cooldowns: dict[str, int] = {}  # thread_id → 下次可用的 tick
        self._load()

    # ── 持久化 ────────────────────────────────────────────────────────────────

    def _load(self) -> None:
        if not os.path.exists(self._path):
            return
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
            self._threads = data.get("threads", [])
        except (OSError, json.JSONDecodeError) as e:
            print(f"[NarrativeThreadManager] 加载失败，从空线索开始：{e}")
            self._threads = []

    def save(self) -> None:
        """原子写入，防止写入中途崩溃导致文件损坏。"""
        dir_ = os.path.dirname(self._path)
        if dir_:
            os.makedirs(dir_, exist_ok=True)
        tmp = self._path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"threads": self._threads}, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self._path)
        except OSError as e:
            print(f"[NarrativeThreadManager] 写入失败：{e}")

    # ── 查询 ──────────────────────────────────────────────────────────────────

    def get_active_threads(self) -> list[dict]:
        """返回所有 status=open 的线索，按 urgency 降序。"""
        return sorted(
            [t for t in self._threads if t["status"] == "open"],
            key=lambda t: t["urgency"],
            reverse=True,
        )

    def get_top_thread(self, current_tick: int = 0) -> dict | None:
        """返回最高 urgency 的 open 线索，跳过冷却中的线索。"""
        active = [
            t for t in self.get_active_threads()
            if self._thread_cooldowns.get(t["id"], 0) <= current_tick
        ]
        return active[0] if active else None

    def mark_thread_used(self, thread_id: str, current_tick: int, cooldown_ticks: int = 3) -> None:
        """标记线索已用于事件生成，设置冷却期（默认3轮内不再选中）。"""
        self._thread_cooldowns[thread_id] = current_tick + cooldown_ticks

    # ── 状态更新 ──────────────────────────────────────────────────────────────

    def tick_urgency(self) -> None:
        """每轮自动递增所有 open 线索的 urgency，上限 1.0。"""
        for t in self._threads:
            if t["status"] == "open":
                t["urgency"] = min(1.0, t["urgency"] + 0.05)

    def add_thread(self, description: str, category: str, urgency: float, tick: int) -> None:
        """新建一条叙事线索。"""
        new_id = self._next_id()
        self._threads.append({
            "id": new_id,
            "description": description,
            "category": category,
            "urgency": min(1.0, max(0.0, urgency)),
            "status": "open",
            "tick_opened": tick,
            "tick_resolved": None,
            "resolution": None,
        })
        print(f"[NarrativeThreadManager] 新线索 {new_id}：{description[:50]}")

    def _close_thread(self, thread_id: str, resolution: str, current_tick: int) -> None:
        for t in self._threads:
            if t["id"] == thread_id and t["status"] == "open":
                t["status"] = "resolved"
                t["tick_resolved"] = current_tick
                t["resolution"] = resolution
                print(f"[NarrativeThreadManager] 关闭线索 {thread_id}：{t['description'][:50]}")
                return

    def _next_id(self) -> str:
        """生成下一个线索 ID（t001 格式）。"""
        existing = set()
        for t in self._threads:
            tid = t.get("id", "")
            if tid.startswith("t") and tid[1:].isdigit():
                existing.add(int(tid[1:]))
        n = 1
        while n in existing:
            n += 1
        return f"t{n:03d}"

    # ── 行动处理 ──────────────────────────────────────────────────────────────

    def process_action(self, conclusion: str, current_tick: int) -> None:
        """
        角色行动结论 → LLM 判断 → 关闭/新建线索。
        立刻执行，不等 write-back 批次。
        """
        if not conclusion or not conclusion.strip():
            return
        active = self.get_active_threads()
        if not active:
            return

        threads_block = "\n".join(
            f"  {t['id']}: {t['description']}"
            for t in active
        )
        prompt = (
            f"当前活跃线索列表：\n{threads_block}\n\n"
            f"角色刚做出的行动决定：{conclusion}\n\n"
            "判断：\n"
            "1. 这个行动是否关闭了某条线索？（要求：直接处理了该线索的核心矛盾）\n"
            "2. 这个行动是否产生了新的待处理情况？（要求：真实世界会有后果的行动）\n\n"
            "输出纯 JSON（不加代码块）：\n"
            '{"close": ["t001"], "resolution": {"t001": "简述结局"}, '
            '"open": [{"description": "...", "category": "work", "urgency": 0.5}]}\n'
            "close 和 open 均可为空列表。category 只能是：work / relationship / family / self / desire"
        )

        for attempt in range(3):
            try:
                raw = claude_call(prompt, system=_SYS_ACTION_JUDGE, max_tokens=512)
                result = _parse_json(raw)
                if result is None:
                    continue
                for tid in result.get("close", []):
                    resolutions = result.get("resolution", {})
                    res_text = resolutions.get(tid, "行动后自然关闭")
                    self._close_thread(tid, res_text, current_tick)
                for new_t in result.get("open", []):
                    desc = new_t.get("description", "")
                    cat = new_t.get("category", "self")
                    urg = float(new_t.get("urgency", 0.4))
                    if desc:
                        self.add_thread(desc, cat, urg, current_tick)
                return
            except Exception as e:
                if attempt == 2:
                    print(f"[NarrativeThreadManager] process_action 失败：{e}")

    # ── 调试展示 ──────────────────────────────────────────────────────────────

    def summary_line(self) -> str:
        """返回一行线索摘要，用于终端打印。"""
        active = self.get_active_threads()
        if not active:
            return "（所有线索已关闭）"
        top = active[0]
        rest = f" + {len(active) - 1} 条" if len(active) > 1 else ""
        return f"[{top['category']}] {top['description'][:30]}… urgency={top['urgency']:.2f}{rest}"


from core.json_utils import parse_json_object as _parse_json  # noqa: E402

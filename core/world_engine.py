"""
core/world_engine.py — 世界生成引擎 v4（叙事线索驱动）。

v4 变更（相对 v3）：
  · _decide_event 改为叙事线索驱动：优先推进最高urgency线索，所有线索关闭时才生成开放性事件
  · 新增 _generate_thread_event()：根据线索描述生成推进该线索的事件
  · 新增 _generate_open_event()：所有线索关闭时生成新发现/机会类事件
  · 接受可选 thread_mgr 参数；无 thread_mgr 时退回 v3 情绪驱动逻辑（兼容）
  · 旧 _generate_event() 保留，供 _generate_open_event 复用
"""

import json
import os
import random
import config  # 确保 .env 已加载
from core.profile import PersonProfile, Relationship
from core.thought import ThoughtState
from agents.base_agent import claude_call
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.behavior import BehaviorState
    from core.narrative import NarrativeThreadManager
    from core.world_state import WorldState

_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

INTENSITY_THRESHOLD = 0.45
CALM_TICK_INTERVAL  = 3


class WorldEngine:
    def __init__(
        self,
        profile: PersonProfile,
        threshold: float = INTENSITY_THRESHOLD,
        calm_interval: int = CALM_TICK_INTERVAL,
        dramatic_cooldown: int = 2,
        event_history_window: int = 10,
        rel_appear_threshold: float = 0.3,
        rel_appear_slope: float = 0.7,
        output_dir: str = "output",
        thread_mgr: "NarrativeThreadManager | None" = None,
        world_state: "WorldState | None" = None,
    ):
        self.profile = profile
        self.threshold = threshold
        self.calm_interval = calm_interval
        self._dramatic_cooldown_max = dramatic_cooldown
        self._event_history_window = event_history_window
        self._rel_threshold = rel_appear_threshold
        self._rel_slope = rel_appear_slope
        self.thread_mgr = thread_mgr
        self.world_state = world_state

        # 运行时状态
        self._ticks_since_last_event = 0
        self._dramatic_cooldown = 0
        self._event_history: list[str] = []

        # 跨轮次持久化
        safe_name = profile.name.replace(" ", "_")
        os.makedirs(output_dir, exist_ok=True)
        self._history_path = os.path.join(output_dir, f"{safe_name}_event_history.jsonl")
        self._load_history()

    # ── 持久化 ─────────────────────────────────────────────────────────────────

    def _load_history(self) -> None:
        """从 jsonl 加载历史事件。失败时静默降级为空历史（critical gap fix）。"""
        try:
            if not os.path.exists(self._history_path):
                return
            with open(self._history_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        entry = json.loads(line)
                        self._event_history.append(entry.get("event", ""))
            self._event_history = self._event_history[-self._event_history_window:]
        except (OSError, json.JSONDecodeError) as e:
            print(f"[WorldEngine] 事件历史加载失败，从空历史开始：{e}")
            self._event_history = []

    def _append_history(self, event: str) -> None:
        """追加事件到内存历史和 jsonl 文件。"""
        self._event_history.append(event)
        if len(self._event_history) > self._event_history_window:
            self._event_history.pop(0)
        try:
            with open(self._history_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"event": event}, ensure_ascii=False) + "\n")
        except OSError as e:
            print(f"[WorldEngine] 事件历史写入失败：{e}")

    # ── 触发逻辑 ───────────────────────────────────────────────────────────────

    def _rel_appear_prob(self, intensity: float) -> float:
        """关系登场概率：线性公式，intensity 在 [threshold, 1.0] 区间内线性增长。"""
        return max(0.0, (intensity - self._rel_threshold) / self._rel_slope)

    def _pick_relationship(self, intensity: float) -> Relationship | None:
        """
        根据情绪强度选取登场的关系对象。
        intensity > threshold → 负向关系（冲突）优先；否则随机。
        """
        rels = self.profile.relationship_objects
        if not rels:
            return None
        if intensity > self.threshold:
            neg = [r for r in rels if r.valence < -0.1]
            pool = neg if neg else rels
        else:
            pool = rels
        return random.choice(pool)

    # ── 主接口 ─────────────────────────────────────────────────────────────────

    def tick(self, state: ThoughtState, behavior: "BehaviorState | None" = None) -> str:
        """每轮认知循环后调用。返回事件字符串（空字符串表示本轮无事件）。"""
        self._ticks_since_last_event += 1
        self._dramatic_cooldown = max(0, self._dramatic_cooldown - 1)

        # 睡眠中不推进外部事件——让 drift 层自由运转
        if behavior is not None and getattr(behavior, "sleep_state", None) == "ASLEEP":
            return ""

        event = self._decide_event(state, behavior)
        if event:
            self._append_history(event)
            self._ticks_since_last_event = 0
        return event

    def _decide_event(self, state: ThoughtState, behavior: "BehaviorState | None" = None) -> str:
        # ── 叙事线索驱动（v4）──────────────────────────────────────────────────
        if self.thread_mgr is not None:
            thread = self.thread_mgr.get_top_thread(current_tick=state.tick)
            if thread:
                intensity = state.emotion.intensity
                tone = "pressing" if intensity > 0.5 else "quiet"
                result = self._generate_thread_event(thread, state, behavior, tone)
                if result:
                    self.thread_mgr.mark_thread_used(thread["id"], state.tick)
                return result
            else:
                # 所有线索已关闭：检查是否触发正向事件，否则生成开放性事件
                pos_score = state.emotion.joy + state.emotion.trust + state.emotion.anticipation
                if (self._ticks_since_last_event >= self.calm_interval
                        and pos_score > 0.2
                        and state.emotion.intensity <= self.threshold):
                    return self._generate_positive_event(state, behavior)
                return self._generate_open_event(state, behavior)

        # ── 旧情绪驱动逻辑（无 thread_mgr 时兼容回退）──────────────────────────
        intensity = state.emotion.intensity

        # 1. Dramatic（情绪峰值，有冷却保护）
        if intensity > self.threshold and self._dramatic_cooldown == 0:
            self._dramatic_cooldown = self._dramatic_cooldown_max
            return self._generate_event(state, "dramatic", behavior=behavior)

        # 2. Relational（概率触发，关系人物登场）
        prob = self._rel_appear_prob(intensity)
        if prob > 0 and random.random() < prob:
            rel = self._pick_relationship(intensity)
            if rel:
                return self._generate_event(state, "relational", relationship=rel, behavior=behavior)

        # 3. Subtle（平静太久的兜底）
        if self._ticks_since_last_event >= self.calm_interval:
            return self._generate_event(state, "subtle", behavior=behavior)

        return ""

    # ── 叙事线索事件生成 ───────────────────────────────────────────────────────

    def _generate_thread_event(
        self,
        thread: dict,
        state: ThoughtState,
        behavior: "BehaviorState | None",
        tone: str,
    ) -> str:
        """生成一件推进指定线索的事件。"""
        history_block = ""
        if self._event_history:
            recent = self._event_history[-5:]
            history_block = (
                "【已发生事件（禁止重复相同人物、地点、对话内容）】\n"
                + "\n".join(f"  · {e}" for e in recent)
                + "\n\n"
            )

        context_parts = []
        if behavior:
            context_parts.append(
                f"当前时间：{behavior.wall_clock_time}，地点：{behavior.location}，活动：{behavior.activity}"
            )
        context_parts.append(
            f"人物当前情绪：{state.emotion.dominant()}（强度{state.emotion.intensity:.2f}）"
        )

        rich_context = "\n".join(context_parts) + "\n\n" if context_parts else ""

        # 行动方向：由 WorldState 根据 thread urgency 推导
        if self.world_state is not None:
            action_type, action_hint = self.world_state.get_action_directive(thread["urgency"])
            trunk_id, trunk_context = self.world_state.get_trunk_context(state.emotion, state.tick)
        else:
            # 兼容回退：沿用旧 tone 逻辑
            action_hint = (
                "这件事带有迫切感，直接触发线索的核心矛盾。"
                if tone == "pressing"
                else "这件事是线索的静默回响，可以是间接提醒或环境触发的联想。"
            )
            trunk_context = ""
            trunk_id = None

        trunk_block = (
            f"{trunk_context}\n事件应与此主干所在域（工作/感情/家庭等）有关联，或形成对比。\n"
            if trunk_context else ""
        )

        system = (
            "你是事件记录员。用第三人称平白陈述发生了什么，不加感受描写，不加修辞。"
            "直接输出内容，不加任何前缀或解释。"
        )
        user = (
            f"人物：{self.profile.name}，{self.profile.current_situation}\n"
            + rich_context
            + trunk_block
            + f"正在推进的故事线索：{thread['description']}（urgency={thread['urgency']:.2f}，类别={thread['category']}）\n"
            + f"近期思维片段：{state.text[-100:] if state.text else '（初始）'}\n\n"
            + history_block
            + f"任务：生成一件与这条线索直接相关的事。{action_hint}\n"
            "1~2句话，纯事实陈述，不写感受，不写情绪暗示。"
            "可以是：线索的直接发展、相关人物出现、环境触发对线索的联想。"
        )

        for _attempt in range(4):
            try:
                result = claude_call(user, system=system, max_tokens=512)
                # 事件生成成功后标记 Trunk 被激活
                if result and trunk_id and self.world_state is not None:
                    self.world_state.mark_trunk_activated(trunk_id, state.tick)
                return result
            except Exception as e:
                if _attempt == 3:
                    print(f"[WorldEngine] 线索事件生成失败: {e}")
        return ""

    def _generate_open_event(
        self,
        state: ThoughtState,
        behavior: "BehaviorState | None",
    ) -> str:
        """所有线索已关闭时，生成开放性事件（新发现/机会/日常）。"""
        history_block = ""
        if self._event_history:
            recent = self._event_history[-5:]
            history_block = (
                "【已发生事件（禁止重复相同人物、地点、对话内容）】\n"
                + "\n".join(f"  · {e}" for e in recent)
                + "\n\n"
            )

        context_parts = []
        if behavior:
            context_parts.append(
                f"当前时间：{behavior.wall_clock_time}，地点：{behavior.location}，活动：{behavior.activity}"
            )
        rich_context = "\n".join(context_parts) + "\n\n" if context_parts else ""

        trunk_block = ""
        trunk_id = None
        if self.world_state is not None:
            trunk_id, trunk_context = self.world_state.get_trunk_context(state.emotion, state.tick)
            if trunk_context:
                trunk_block = (
                    f"{trunk_context}\n事件应与此主干所在域（工作/感情/家庭等）有关联，或形成对比。\n"
                )

        system = (
            "你是事件记录员。用第三人称平白陈述发生了什么，不加感受描写，不加修辞。"
            "直接输出内容，不加任何前缀或解释。"
        )
        user = (
            f"人物：{self.profile.name}，{self.profile.current_situation}\n"
            + rich_context
            + trunk_block
            + f"当前思维片段：{state.text[-100:] if state.text else '（初始）'}\n\n"
            + history_block
            + "任务：生成一件日常小事或新的发现/机会。1~2句话，纯事实陈述。"
        )

        for _attempt in range(4):
            try:
                result = claude_call(user, system=system, max_tokens=512)
                if result and trunk_id and self.world_state is not None:
                    self.world_state.mark_trunk_activated(trunk_id, state.tick)
                return result
            except Exception as e:
                if _attempt == 3:
                    print(f"[WorldEngine] 开放事件生成失败: {e}")
        return ""

    def _generate_positive_event(
        self,
        state: ThoughtState,
        behavior: "BehaviorState | None",
    ) -> str:
        """A2：正向事件——情绪平静且有正向残余时，生成细小喘息型事件。
        触发条件：joy + trust + anticipation > 0.2，且情绪强度不在峰值。
        风格：细小、不戏剧化、来自外部环境或非核心关系（路人/天气/物件）。
        """
        history_block = ""
        if self._event_history:
            recent = self._event_history[-5:]
            history_block = (
                "【已发生事件（禁止重复相同人物、地点、对话内容）】\n"
                + "\n".join(f"  · {e}" for e in recent)
                + "\n\n"
            )

        context_parts = []
        if behavior:
            context_parts.append(
                f"当前时间：{behavior.wall_clock_time}，地点：{behavior.location}，活动：{behavior.activity}"
            )
        context_parts.append(
            f"正向情绪：joy={state.emotion.joy:.2f} trust={state.emotion.trust:.2f} anticipation={state.emotion.anticipation:.2f}"
        )
        rich_context = "\n".join(context_parts) + "\n\n" if context_parts else ""

        system = (
            "你是事件记录员。用第三人称平白陈述发生了什么，不加感受描写，不加修辞。"
            "直接输出内容，不加任何前缀或解释。"
        )
        user = (
            f"人物：{self.profile.name}，{self.profile.current_situation}\n"
            + rich_context
            + f"当前思维片段：{state.text[-100:] if state.text else '（初始）'}\n\n"
            + history_block
            + "任务：生成一件细小的正向时刻。要求：\n"
            "- 来自外部环境或非核心关系（路人/天气/物件/偶然发现），不涉及人物的核心矛盾\n"
            "- 不解决任何问题，只是短暂的喘息或意外的小惊喜\n"
            "- 1~2句话，纯事实陈述，不写情绪"
        )

        for _attempt in range(4):
            try:
                return claude_call(user, system=system, max_tokens=512)
            except Exception as e:
                if _attempt == 3:
                    print(f"[WorldEngine] 正向事件生成失败: {e}")
        return ""

    # ── 事件生成 ───────────────────────────────────────────────────────────────

    def _generate_event(
        self,
        state: ThoughtState,
        mode: str,
        relationship: Relationship | None = None,
        behavior: "BehaviorState | None" = None,
    ) -> str:
        history_block = ""
        if self._event_history:
            recent = self._event_history[-5:]
            history_block = (
                "【已发生事件（禁止重复相同人物、地点、对话内容）】\n"
                + "\n".join(f"  · {e}" for e in recent)
                + "\n\n"
            )

        # 富上下文：时间/地点/情绪/最近推理
        context_parts = []
        if behavior:
            context_parts.append(f"当前时间：{behavior.wall_clock_time}，地点：{behavior.location}，活动：{behavior.activity}")
        context_parts.append(
            f"主导情绪：{state.emotion.dominant()}（强度{state.emotion.intensity:.2f}）"
        )
        if state.reasoning:
            context_parts.append(f"最近内心推断：{state.reasoning[:150]}")
        rich_context = "\n".join(context_parts) + "\n\n" if context_parts else ""

        if mode == "dramatic":
            instruction = (
                f"情绪强度 {state.emotion.intensity:.2f}。"
                "发生了一件外部事件。只写事实：什么人/物/消息出现了，做了什么或说了什么。"
                "1~2句话，不写人物感受，不写情绪暗示。"
            )
        elif mode == "relational" and relationship:
            instruction = (
                f"{relationship.name}出现了或被提及。"
                "只写事实：Ta做了什么、说了什么、或出现在哪里。"
                "1~2句话，不写感受，不写关系描述。"
            )
        else:  # subtle
            instruction = (
                "一个环境细节或日常小事。只写发生了什么：什么东西在动、谁做了什么、出现了什么声音或物体。"
                "1~2句话，纯事实陈述。"
            )

        system = (
            "你是事件记录员。用第三人称平白陈述发生了什么，不加感受描写，不加修辞。"
            "直接输出内容，不加任何前缀或解释。"
        )
        user = (
            f"人物：{self.profile.name}，{self.profile.current_situation}\n"
            + rich_context
            + f"当前思维片段：{state.text[-150:] if state.text else '（初始）'}\n"
            + history_block
            + f"任务：{instruction}"
        )

        for _attempt in range(4):
            try:
                return claude_call(user, system=system, max_tokens=512)
            except Exception as e:
                if _attempt == 3:
                    print(f"[WorldEngine] 事件生成失败: {e}")
        return ""

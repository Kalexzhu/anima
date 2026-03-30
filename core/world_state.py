"""
core/world_state.py — 世界状态管理器 (Phase A)

管理人物当前的「主干情境」（Trunk）：持续数周到数月的底层心理张力，
为 WorldEngine 的事件生成提供叙事主题骨架和行动方向。

Branch 层（NarrativeThreadManager）保持不变，WorldState 在其上层工作。

关键职责：
  1. 从 PersonProfile 提取 2~4 个 Trunk 情境（首次运行时一次性 LLM 调用）
  2. 每 tick 对 Trunk 进行 urgency 自然衰退和 phase 状态转移
  3. 为 WorldEngine 提供：当前最相关的 Trunk 摘要 + 事件行动方向（action_type）

叙事时间归一化：所有速率以「per narrative hour」定义，
  乘以 tick_duration_hours 后使用，确保换 tick 频率时行为一致。
"""

from __future__ import annotations

import json
import math
import os
import random
from dataclasses import dataclass, asdict
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.emotion import EmotionState
    from core.profile import PersonProfile

from agents.base_agent import claude_call


# ── 常量 ──────────────────────────────────────────────────────────────────────

# 生命域：Trunk 必须属于某个域，同域只保留 urgency 最高的一个
VALID_DOMAINS = frozenset({
    "work",         # 职业/工作
    "romance",      # 感情/恋爱
    "family",       # 家庭关系
    "identity",     # 自我认同/人生方向
    "friendship",   # 友情/社交
    "health",       # 身心健康
    "finance",      # 经济/财务
    "home",         # 居住/归属地
})

VALID_TAGS = frozenset({
    "career", "identity", "loss", "conflict", "uncertainty",
    "connection", "isolation", "achievement", "relationship",
    "family", "purpose", "freedom", "control", "belonging",
})

_TAG_EMOTION_MAP: dict[str, list[str]] = {
    "career":       ["anticipation", "fear", "joy"],
    "identity":     ["fear", "sadness", "trust"],
    "loss":         ["sadness", "fear"],
    "conflict":     ["anger", "disgust", "fear"],
    "uncertainty":  ["anticipation", "fear"],
    "connection":   ["trust", "joy"],
    "isolation":    ["sadness", "anger"],
    "achievement":  ["joy", "trust", "anticipation"],
    "relationship": ["trust", "fear", "joy"],
    "family":       ["trust", "anger", "sadness"],
    "purpose":      ["anticipation", "sadness"],
    "freedom":      ["joy", "anticipation", "anger"],
    "control":      ["fear", "anticipation", "anger"],
    "belonging":    ["trust", "sadness", "joy"],
}

# phase → (action_type, 事件生成指令)
PHASE_TO_ACTION: dict[str, tuple[str, str] | None] = {
    "latent":      None,
    "emerging":    ("open",       "轻轻触碰这个主题，让它出现在感知边缘，不必直接呈现"),
    "developing":  ("complicate", "让情况变得更复杂，增加一个新的障碍或纠葛"),
    "critical":    ("escalate",   "把张力推到顶点，这件事今天不得不面对"),
    "confronting": ("confront",   "正面冲突或直接面对，不回避"),
    "resolving":   ("resolve",    "开始松动，有迹象表明这件事即将被处理"),
}

# Trunk urgency 自然衰退（per narrative hour）
# 2h/tick 时：每轮衰退 0.006×2 = 0.012，~50 轮从 0.6 衰退到 0
_TRUNK_DECAY_PER_HOUR = 0.006

# Phase 前进阈值（urgency 超过时向前一步）
_PHASE_FORWARD: dict[str, tuple[str, float]] = {
    "latent":      ("emerging",    0.25),
    "emerging":    ("developing",  0.45),
    "developing":  ("critical",    0.70),
    "critical":    ("confronting", 0.90),
}

# Phase 回退阈值（urgency 低于时向后一步）
_PHASE_BACKWARD: dict[str, tuple[str, float]] = {
    "confronting": ("critical",    0.75),
    "critical":    ("developing",  0.50),
    "developing":  ("emerging",    0.30),
    "emerging":    ("latent",      0.15),
}


# ── 数据结构 ──────────────────────────────────────────────────────────────────

@dataclass
class Situation:
    id: str
    title: str                   # 简短标签（4~8字）
    description: str             # 一句话描述，注入 prompt
    phase: str                   # latent / emerging / developing / critical / confronting / resolving
    domain: str                  # 生命域：work / romance / family / identity / ...
    tags: list[str]              # 情绪共鸣 key，来自 VALID_TAGS
    urgency: float               # 0.0~1.0
    created_tick: int
    last_activated_tick: int
    activation_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Situation":
        return cls(
            id=str(d["id"]),
            title=str(d.get("title", "未知张力")),
            description=str(d.get("description", "")),
            phase=d.get("phase", "developing") if d.get("phase") in PHASE_TO_ACTION else "developing",
            domain=str(d.get("domain", "identity")),
            tags=[t for t in d.get("tags", []) if t in VALID_TAGS],
            urgency=float(d.get("urgency", 0.4)),
            created_tick=int(d.get("created_tick", 0)),
            last_activated_tick=int(d.get("last_activated_tick", 0)),
            activation_count=int(d.get("activation_count", 0)),
        )


# ── WorldState ────────────────────────────────────────────────────────────────

class WorldState:
    """
    情境树（Trunk 层）管理器。

    供 WorldEngine 使用的两个核心接口：
      get_trunk_context(emotion)  → (trunk_id | None, context_str)
      get_action_directive(thread_urgency) → (action_type, action_hint)
    """

    def __init__(self, state_path: str):
        self._path = state_path
        self.trunks: list[Situation] = []
        self._load()

    # ── 持久化 ────────────────────────────────────────────────────────────────

    def _load(self) -> None:
        if not os.path.exists(self._path):
            return
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
            self.trunks = [Situation.from_dict(s) for s in data.get("trunks", [])]
        except (OSError, json.JSONDecodeError) as e:
            print(f"[WorldState] 加载失败，从空状态开始：{e}")
            self.trunks = []

    def save(self) -> None:
        dir_ = os.path.dirname(self._path)
        if dir_:
            os.makedirs(dir_, exist_ok=True)
        tmp = self._path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"trunks": [s.to_dict() for s in self.trunks]}, f,
                          ensure_ascii=False, indent=2)
            os.replace(tmp, self._path)
        except OSError as e:
            print(f"[WorldState] 写入失败：{e}")

    # ── 初始化 ────────────────────────────────────────────────────────────────

    def init_trunks(self, profile: "PersonProfile") -> None:
        """从 PersonProfile 提取主干情境（一次性 LLM 调用）。trunks 非空时跳过。"""
        if self.trunks:
            return
        print("[WorldState] 提取主干情境（首次运行）…")
        self.trunks = _extract_trunks(profile)
        self.save()
        for t in self.trunks:
            print(f"  [Trunk] {t.title}（{t.phase}，urgency={t.urgency:.2f}）: {t.description[:40]}")

    # ── 每 tick 更新 ──────────────────────────────────────────────────────────

    def tick_update(self, tick: int, tick_duration_hours: float = 2.0) -> None:
        """每 tick 末尾调用：衰退 urgency，更新 phase。"""
        decay = _TRUNK_DECAY_PER_HOUR * tick_duration_hours
        for trunk in self.trunks:
            trunk.urgency = max(0.0, trunk.urgency - decay)
            _update_phase(trunk)

    # ── 对外接口（供 WorldEngine 使用）───────────────────────────────────────

    def get_trunk_context(self, emotion: "EmotionState", current_tick: int = 0) -> tuple[Optional[str], str]:
        """
        返回当前最相关 Trunk 的 (trunk_id, 一行描述)。
        若所有 Trunk 均处于 latent 阶段，返回 (None, "")。

        选择策略：Softmax 概率加权 + Recency Penalty。
        - Softmax 保留 urgency 优先级，但不 Winner-Take-All，高urgency只是"更可能"被选
        - Recency Penalty 惩罚刚被激活的 Trunk，强制"换气"，自然产生多线轮替
        """
        active = [t for t in self.trunks if t.phase != "latent"]
        if not active:
            return None, ""

        if len(active) == 1:
            best = active[0]
        else:
            # Recency Penalty：距上次激活越近，得分折扣越大；半衰期 4 tick
            _RECENCY_HALFLIFE = 4.0
            _RECENCY_WEIGHT   = 0.75  # 最大折扣75%（刚激活后的下一轮几乎不会再选）
            # Softmax 温度：越低越确定性，越高越均匀；0.25 在"有偏好但不锁死"之间
            _TEMPERATURE      = 0.25

            scores = []
            for t in active:
                base = _score_trunk(t, emotion)
                ticks_since = current_tick - t.last_activated_tick
                recency_penalty = math.exp(-ticks_since / _RECENCY_HALFLIFE)
                adjusted = base * (1.0 - _RECENCY_WEIGHT * recency_penalty)
                scores.append(max(adjusted, 1e-6))

            # Softmax（数值稳定版）
            max_s = max(scores)
            exps = [math.exp((s - max_s) / _TEMPERATURE) for s in scores]
            total = sum(exps)
            probs = [e / total for e in exps]
            best = random.choices(active, weights=probs, k=1)[0]

        action = PHASE_TO_ACTION.get(best.phase)
        phase_hint = f"（{action[1][:10]}）" if action else ""
        context = f"当前主干情境[{best.domain}]：{best.title}——{best.description}{phase_hint}"
        return best.id, context

    def get_action_directive(self, thread_urgency: float) -> tuple[str, str]:
        """
        根据 Branch urgency 推导本次事件行动方向。
        返回 (action_type, action_hint)。
        urgency 单调映射到 phase，phase 映射到 action。
        """
        phase = _urgency_to_phase(thread_urgency)
        entry = PHASE_TO_ACTION.get(phase)
        if entry is None:
            return "open", "生成一件日常小事，轻轻触动主题边缘"
        return entry

    def mark_trunk_activated(self, trunk_id: str, tick: int) -> None:
        """事件生成后调用，记录 Trunk 被提及，略微提升其 urgency。"""
        for t in self.trunks:
            if t.id == trunk_id:
                t.last_activated_tick = tick
                t.activation_count += 1
                t.urgency = min(1.0, t.urgency + 0.04)
                _update_phase(t)
                return

    def summary_line(self) -> str:
        active = [t for t in self.trunks if t.phase != "latent"]
        if not active:
            return "（所有主干潜伏）"
        top = max(active, key=lambda t: t.urgency)
        rest = f" +{len(active)-1}" if len(active) > 1 else ""
        return f"[{top.phase}] {top.title} urgency={top.urgency:.2f}{rest}"


# ── 内部工具函数 ──────────────────────────────────────────────────────────────

def _emotion_resonance(tags: list[str], emotion: "EmotionState") -> float:
    """情绪共鸣分数：情境主题与当前情绪状态的匹配程度。"""
    scores = []
    for tag in tags:
        for emo_name in _TAG_EMOTION_MAP.get(tag, []):
            scores.append(getattr(emotion, emo_name, 0.0))
    return sum(scores) / max(len(scores), 1)


def _score_trunk(trunk: Situation, emotion: "EmotionState") -> float:
    resonance = _emotion_resonance(trunk.tags, emotion)
    phase_w = {
        "latent": 0.0, "emerging": 0.4, "developing": 0.7,
        "critical": 1.0, "confronting": 0.9, "resolving": 0.5,
    }.get(trunk.phase, 0.5)
    return trunk.urgency * (0.5 + 0.5 * resonance) * phase_w


def _update_phase(s: Situation) -> None:
    """根据 urgency 单步更新 phase（双向，不可跳级）。"""
    # 向前
    forward = _PHASE_FORWARD.get(s.phase)
    if forward and s.urgency >= forward[1]:
        s.phase = forward[0]
        return
    # 向后
    backward = _PHASE_BACKWARD.get(s.phase)
    if backward and s.urgency < backward[1]:
        s.phase = backward[0]


def _urgency_to_phase(urgency: float) -> str:
    """Branch urgency（单调递增）映射到 phase，用于推导 action_type。"""
    if urgency < 0.25:
        return "emerging"
    elif urgency < 0.55:
        return "developing"
    elif urgency < 0.80:
        return "critical"
    else:
        return "confronting"


def _extract_trunks(profile: "PersonProfile") -> list[Situation]:
    """一次性 LLM 调用，从 profile 提取 2~4 个主干情境。失败时返回空列表。

    设计原则：
    - 每个 Trunk 必须属于不同的生命域（domain），强制正交
    - 描述的是具体的"未竟之事"，不是心理元主题
    - 同一个人的 3 个 Trunk 应该能生成完全不同类型的事件
    """
    rels_block = ""
    if profile.relationships:
        rels_block = "关键关系：" + "、".join(
            f"{r.get('name', '')}（{r.get('role', '')}）"
            for r in profile.relationships[:4]
        ) + "\n"

    memories_block = ""
    if profile.memories:
        top_mems = sorted(profile.memories, key=lambda m: -m.get("importance", 0))[:5]
        memories_block = "重要记忆：" + "；".join(m["event"][:30] for m in top_mems) + "\n"

    valid_domains_str = "、".join(sorted(VALID_DOMAINS))

    prompt = (
        f"人物：{profile.name}，{profile.age}岁\n"
        f"当前处境：{profile.current_situation}\n"
        f"性格：{', '.join(profile.personality_traits[:4])}\n"
        f"核心价值观：{', '.join(profile.core_values[:4])}\n"
        f"认知偏差：{', '.join(profile.cognitive_biases[:3])}\n"
        + rels_block
        + memories_block
        + "\n"
        "任务：从以上档案中，识别这个人物当前正在经历的 2~4 个主要生命领域的未竟之事。\n"
        "\n"
        "重要原则：\n"
        "1. 每个 Trunk 必须属于不同的生命域（domain），绝对不允许两个 Trunk 属于同一个域\n"
        "2. description 描述的是这个域里**具体的、未解决的处境**，而不是抽象的心理模式\n"
        "   - 好的例子：「做了两周的方案被当众否定，她不知道继续做这份工作的意义在哪」\n"
        "   - 坏的例子：「努力换不来认可，使她对自身价值产生根本性怀疑」（这是心理模式，不是处境）\n"
        "3. 三个 Trunk 应该能各自独立生成完全不同类型的外部事件\n"
        "   - 工作 Trunk → 工作场景的事件（会议、同事、邮件、项目）\n"
        "   - 感情 Trunk → 感情场景的事件（前任联系、约会、回忆触发）\n"
        "   - 自我 Trunk → 内心场景的事件（选择节点、生活方式、归属感）\n"
        "\n"
        "对每个 Trunk 输出以下字段：\n"
        '{"domain": "work", "title": "4~8字标题", '
        '"description": "一句话描述这个域里具体的未竟之事（不超过40字）", '
        '"tags": ["tag1", "tag2"], "phase": "developing", "urgency": 0.5}\n\n'
        f"domain 只能从以下选择（每个 Trunk 必须不同）：{valid_domains_str}\n"
        f"tags 只能从以下选择（可多选）：{', '.join(sorted(VALID_TAGS))}\n"
        "phase 只能是：latent / emerging / developing / critical\n"
        "urgency 范围 0.2~0.7（这件事在生活中被搁置得越久、越迫切，urgency 越高）\n\n"
        "输出纯 JSON 数组，不加代码块或解释。示例：\n"
        '[{"domain":"work","title":"方案被否后的方向感","description":"做了两周的方案被当众否定，她不知道留下来还是离开",'
        '"tags":["career","uncertainty"],"phase":"critical","urgency":0.65}]'
    )

    system = (
        "你是人生阶段分析员。根据人物档案识别其当前正在经历的各个生命领域的具体处境。"
        "每个生命域必须不同，描述要具体到可以独立生成事件，不要写心理元主题。"
        "只输出纯 JSON 数组，不加任何说明或 markdown 代码块。"
    )

    for attempt in range(3):
        try:
            raw = claude_call(prompt, system=system, max_tokens=1000)
            raw = raw.strip()
            if raw.startswith("```"):
                lines = raw.split("\n")
                raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            items = json.loads(raw)
            if not isinstance(items, list) or not items:
                continue

            # 构建 Situation 列表，同时做域去重（同域保留 urgency 最高的）
            seen_domains: dict[str, Situation] = {}
            for item in items[:6]:  # 最多处理6个，去重后留2~4
                domain = str(item.get("domain", "identity"))
                if domain not in VALID_DOMAINS:
                    domain = "identity"
                s = Situation(
                    id="",  # 稍后赋值
                    title=str(item.get("title", "未知处境"))[:12],
                    description=str(item.get("description", "")),
                    phase=item.get("phase", "developing") if item.get("phase") in PHASE_TO_ACTION else "developing",
                    domain=domain,
                    tags=[t for t in item.get("tags", []) if t in VALID_TAGS],
                    urgency=max(0.2, min(0.7, float(item.get("urgency", 0.4)))),
                    created_tick=0,
                    last_activated_tick=0,
                    activation_count=0,
                )
                # 同域去重：保留 urgency 更高的
                if domain not in seen_domains or s.urgency > seen_domains[domain].urgency:
                    seen_domains[domain] = s

            trunks = list(seen_domains.values())
            # 按 urgency 降序，最多取 4 个，重新分配 id
            trunks.sort(key=lambda t: -t.urgency)
            trunks = trunks[:4]
            for i, t in enumerate(trunks):
                t.id = f"trunk_{i+1:02d}"

            if trunks:
                return trunks
        except Exception as e:
            if attempt == 2:
                print(f"[WorldState] Trunk 提取失败，使用空主干：{e}")
    return []

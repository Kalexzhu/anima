"""
core/cognitive_engine.py — 内部认知引擎 v5（多模块并发架构）。

v5 变更（相对 v4）：
  - Arbiter B1/B2/B3 封装为 ReactiveModule
  - drift_layer 拆解为 9 个独立 DriftModule（rumination / self_eval / philosophy /
    aesthetic / counterfactual / positive_memory / daydream / future / social_rehearsal）
  - ModuleRunner（ThreadPoolExecutor）并发调度：reactive + 1~2 个 drift 模块
  - prev_tick_outputs 跨轮传递，实现模块间影响机制
  - 新增 narrative_thread 参数，传入 ModuleContext

v4 遗留（保留）：
  - perception / emotion / memory / reasoning 四个共享预处理层不变
  - DUTIR 校准、OCC 评估、被动衰退逻辑不变
  - 梦境简化循环（ASLEEP）不变
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from core.profile import PersonProfile
from core.emotion import EmotionState
from core.thought import ThoughtState
from core.memory import MemoryManager
from core.behavior import behavior_layer, BehaviorState
from core.tick_history import TickHistoryStore, LayerContext
from core.emotion_constraint import EmotionConstraintBuilder, EmotionValidator, log_emotion_event
from core.emotion_descriptor import get_emotion_description
from core.drift_sampler import sample_drift_category, DRIFT_CATEGORIES
from core.occ import (
    OCCAppraisal, OCC_SYSTEM_PROMPT, parse_occ_response,
    occ_to_plutchik, apply_personality_modifiers, blend_with_prev_state,
)
from agents.base_agent import fast_call, claude_call
from core.cognitive_modules import (
    ModuleContext, ModuleRunner, ReactiveModule, create_drift_modules,
)
from core.cognitive_modules.base import CognitiveModule

_constraint_builder = EmotionConstraintBuilder()
_validator = EmotionValidator()

# ── 记忆冷却追踪器 ────────────────────────────────────────────────────────────────

class MemoryCooldownTracker:
    """
    记录每条记忆最近被采样的 tick，在冷却期内将其排除出随机池。
    冷却只影响随机三条的候选范围，不影响 importance top-5。
    """
    COOLDOWN_TICKS = 5

    def __init__(self) -> None:
        self._last_sampled: dict[int, int] = {}  # memory_index → last tick number

    def is_available(self, index: int, current_tick: int) -> bool:
        return (current_tick - self._last_sampled.get(index, -999)) > self.COOLDOWN_TICKS

    def record(self, indices: list[int], tick: int) -> None:
        for i in indices:
            self._last_sampled[i] = tick


_cooldown_tracker = MemoryCooldownTracker()


def _sample_memories(
    profile: "PersonProfile",
    tracker: MemoryCooldownTracker,
    current_tick: int,
    n_importance: int = 5,
    n_random: int = 3,
) -> list[dict]:
    """
    预采样记忆：
      - top n_importance 条按 importance 降序（每轮稳定）
      - n_random 条从剩余中随机取，冷却期内的条目被排除出随机池
      - 若随机池因冷却全部耗尽，则从完整剩余中回退随机取（防止池枯竭）
      - 记录本轮采样 indices 进 tracker
    """
    import random as _random
    mems = profile.memories
    if not mems:
        return []

    indexed = sorted(enumerate(mems), key=lambda x: -x[1].get("importance", 0))
    top_n = indexed[:n_importance]
    remaining = indexed[n_importance:]

    available = [(i, m) for i, m in remaining if tracker.is_available(i, current_tick)]
    pool = available if available else remaining  # 冷却全满时回退到全部剩余

    random_picked = _random.sample(pool, min(n_random, len(pool)))

    all_sampled_indices = [i for i, _ in top_n] + [i for i, _ in random_picked]
    tracker.record(all_sampled_indices, current_tick)

    return [m for _, m in top_n] + [m for _, m in random_picked]

# ── 模块 Runner 初始化（模块池全局共享）──────────────────────────────────────────
_reactive_module = ReactiveModule()
_drift_modules: list[CognitiveModule] = create_drift_modules()
_drift_module_map: dict[str, CognitiveModule] = {m.name: m for m in _drift_modules}
_module_runner = ModuleRunner([_reactive_module] + _drift_modules, max_workers=6)

_PASSIVE_DECAY = 0.7   # 清醒时每小时衰减 30%（约3轮强度减半）
_SLEEP_DECAY   = 0.95  # 睡眠时每小时衰减 5%（8小时后保留 ~66%）

# ── 测试模式开关 ────────────────────────────────────────────────────────────────
_TEST_ALL_MODULES = True   # True = 每轮运行全部 drift 模块（不经 drift_sampler 采样）；False = 采样模式（暂封存）

_NEGATIVE_DIMS = {"anger", "fear", "sadness", "disgust"}
_POSITIVE_DIMS = {"joy", "trust", "anticipation"}


# ── 各层 system prompt ──────────────────────────────────────────────────────────

_SYS_PERCEPTION = (
    "你是感知过滤器。根据人物性格和当前关系网络，判断这个人对当前事件的注意焦点。"
    "注意：在情绪激动时，重要他人（父母、前伴侣、权威人物）容易在脑中浮现。"
    "只输出一句话（≤60字），描述这个人注意到了什么，或者谁的形象/话语闪过了脑海。"
    "不要解释，不要其他内容。"
)

_SYS_REASONING = (
    "你是认知推理器。根据人物价值观、认知偏差，以及脑中响起的他人声音，生成内心的逻辑推演。"
    "使用第一人称内心独白，不超过80字。不要解释，直接输出内心的话。"
    "如果有'他人声音'，那些话会像鬼魅一样干扰推断。"
)

_SYS_DREAM = (
    "你正在模拟一个人的梦境。梦境是碎片化的、非线性的，混合了白天的残留记忆和欲望。"
    "以第一人称描述梦中的场景、人物或情绪感受，60~120字。不要标注「这是梦」。"
)


# ── 关系图谱工具函数 ────────────────────────────────────────────────────────────

def _build_relationship_context(profile: PersonProfile, emotion_intensity: float) -> str:
    rel_objs = profile.relationship_objects
    if not rel_objs:
        return ""
    lines = ["重要关系网络（这些人此刻可能浮现在脑海中）："]
    for r in rel_objs:
        line = f"  · {r.to_prompt_line()}"
        if emotion_intensity > 0.3 and r.typical_phrases:
            phrases = "、".join(f'"{p}"' for p in r.typical_phrases[:2])
            line += f"\n    Ta的声音：{phrases}"
        lines.append(line)
    return "\n".join(lines)


def _get_inner_voices(profile: PersonProfile, emotion_intensity: float) -> str:
    if emotion_intensity < 0.2:
        return ""
    voices = []
    for r in profile.relationship_objects:
        if r.valence < -0.1 and r.typical_phrases:
            phrases = "、".join(f'"{p}"' for p in r.typical_phrases[:2])
            voices.append(f"{r.name}的声音：{phrases}")
        elif r.valence > 0.5 and r.typical_phrases and emotion_intensity > 0.4:
            voices.append(f"（渴望）{r.name}会怎么看我……")
    return "\n".join(voices)


# ── DUTIR 方向校准 ──────────────────────────────────────────────────────────────

def _apply_dutir_calibration(
    blended: dict[str, float],
    event_text: str,
    perceived_text: str,
) -> dict[str, float]:
    """
    若 OCC 主导情绪方向与 DUTIR 方向不一致，修正主导维度：
      - 压低 OCC 错误主导 × 0.3
      - 拉高 DUTIR 指示维度 + 0.3（capped 1.0）
    """
    combined = f"{event_text} {perceived_text}".strip()
    if not combined:
        return blended

    try:
        from core.dutir_loader import get_dominant_emotions
        dutir_top_list = get_dominant_emotions(combined, top_n=1)
        if not dutir_top_list:
            return blended
        dutir_top = dutir_top_list[0]
    except Exception:
        return blended

    dims = {k: v for k, v in blended.items() if k in _NEGATIVE_DIMS | _POSITIVE_DIMS}
    if not dims:
        return blended
    occ_top = max(dims, key=dims.get)

    occ_neg = occ_top in _NEGATIVE_DIMS
    dutir_neg = dutir_top in _NEGATIVE_DIMS

    if occ_neg == dutir_neg:
        return blended  # 方向一致

    result = dict(blended)
    result[occ_top] = result[occ_top] * 0.3
    result[dutir_top] = min(1.0, result.get(dutir_top, 0.0) + 0.3)
    print(
        f"[DUTIR] 方向修正：{occ_top}({blended[occ_top]:.2f}→{result[occ_top]:.2f})"
        f" → {dutir_top}({blended.get(dutir_top, 0):.2f}→{result[dutir_top]:.2f})"
    )
    return result


# ── Layer 1: Perception ────────────────────────────────────────────────────────

def perception_layer(
    profile: PersonProfile,
    event: str,
    state: ThoughtState,
    behavior: BehaviorState | None = None,
    memory_sample: list | None = None,
) -> str:
    rel_context = _build_relationship_context(profile, state.emotion.intensity)
    base = f"人物档案：\n{profile.to_prompt_context(memory_override=memory_sample)}\n\n"
    if rel_context:
        base += f"{rel_context}\n\n"
    location_ctx = ""
    if behavior:
        location_ctx = f"当前时间：{behavior.wall_clock_time}，地点：{behavior.location}，活动：{behavior.activity}\n"
    prompt = (
        base
        + location_ctx
        + f"当前事件：{event or '无新事件，时间在流逝'}\n"
        + f"上一轮思维片段：{state.text[-150:] if state.text else '（初始状态）'}"
    )
    return fast_call(prompt, system=_SYS_PERCEPTION)


# ── Layer 2: Emotion（OCC + DUTIR 校准 + 被动衰退）────────────────────────────

def emotion_layer(profile: PersonProfile, perceived: str, state: ThoughtState) -> EmotionState:
    """
    OCC 四步：LLM → occ_to_plutchik → personality_modifiers → blend
    校准步：DUTIR 方向校验（方向不一致则修正主导维度）
    之后在 run_cognitive_cycle 中施加被动衰退 × 0.7。
    """
    prompt = (
        f"人物性格：{', '.join(profile.personality_traits)}\n"
        f"核心价值观：{', '.join(profile.core_values)}\n"
        f"认知偏差：{', '.join(profile.cognitive_biases)}\n"
        f"当前感知：{perceived}\n"
        f"当前情绪基线：{json.dumps(state.emotion.to_dict(), ensure_ascii=False)}"
    )
    raw = fast_call(prompt, system=OCC_SYSTEM_PROMPT)
    appraisal = parse_occ_response(raw)
    if appraisal is None:
        print(f"[OCC] 解析失败，保留前一轮情绪。raw={raw[:100]!r}")
        return state.emotion

    plutchik = occ_to_plutchik(appraisal)
    plutchik = apply_personality_modifiers(plutchik, profile.cognitive_biases)
    prev_dict = {k: v for k, v in state.emotion.to_dict().items() if k != "intensity"}
    # 自适应 decay：情绪越强，对新信号的抵抗越大（高峰情绪难以被单一事件扭转）
    intensity = state.emotion.intensity
    adaptive_decay = min(0.65, 0.4 + 0.25 * min(1.0, intensity / 0.5))
    blended = blend_with_prev_state(plutchik, prev_dict, decay=adaptive_decay)

    # DUTIR 方向校准（正式接入，之前只记录日志）
    blended = _apply_dutir_calibration(blended, state.last_event, perceived)

    new_emotion = state.emotion.update_from_dict(blended)

    # DUTIR 审计日志
    constraint = _constraint_builder.build(
        event_text=state.last_event,
        perceived_text=perceived,
    )
    log_emotion_event(
        event_keywords=[w for w, _, _ in constraint.hit_words],
        plutchik_output={k: v for k, v in new_emotion.to_dict().items() if k != "intensity"},
        intensity=new_emotion.intensity,
        was_corrected=False,
        correction_reason=None,
    )
    return new_emotion


# ── Layer 3: Memory ────────────────────────────────────────────────────────────

def memory_layer(
    memory_manager: MemoryManager,
    perceived: str,
    emotion: EmotionState,
) -> str:
    return memory_manager.retrieve(query=perceived, top_k=3, current_emotion=emotion)


# ── Layer 4: Reasoning（claude）────────────────────────────────────────────────

def reasoning_layer(
    profile: PersonProfile,
    perceived: str,
    emotion: EmotionState,
    memory_fragment: str,
    layer_ctx: LayerContext | None = None,
    behavior: BehaviorState | None = None,
) -> str:
    inner_voices = _get_inner_voices(profile, emotion.intensity)
    location_ctx = ""
    if behavior:
        location_ctx = f"\n此刻位于：{behavior.location}，正在：{behavior.activity}（{behavior.wall_clock_time}）"

    emotion_desc = get_emotion_description(emotion.to_dict())

    prompt = (
        f"价值观：{', '.join(profile.core_values)}\n"
        f"认知偏差：{', '.join(profile.cognitive_biases)}\n"
        f"感知到：{perceived}\n"
        f"激活的记忆：{memory_fragment or '无'}\n"
        f"情绪状态：{emotion_desc}"
        + location_ctx
    )
    if inner_voices:
        prompt += f"\n\n此刻脑中响起的他人声音：\n{inner_voices}"
    if layer_ctx and not layer_ctx.is_empty():
        prompt += f"\n\n{layer_ctx.to_prompt_block()}"

    return claude_call(prompt, system=_SYS_REASONING, max_tokens=512)


# ── 梦境生成（ASLEEP 简化循环）─────────────────────────────────────────────────
    """B3：确定性代码渲染，无 LLM 调用。"""
    lines = []
    for m in moments:
        t = m.get("type", "")
        content = m.get("content", "").strip()
        if not content:
            continue
        if t == "unsymbolized":
            lines.append(f"〔{content}〕")
        elif t == "voice_intrusion":
            source = m.get("source", "")
            # 防御：source 可能含声音描述（"张明，男声，普通话"），只取第一个逗号前的人名
            name = source.split("，")[0].split(",")[0].strip()
            # 剥掉 LLM 可能自带的外层「」，避免双层括号
            inner = re.sub(r"^「+|」+$", "", content).strip()
            if name:
                lines.append(f"{name}说，「{inner}」")
            else:
                lines.append(f"「{inner}」")
        elif t == "compressed_speech":
            if content and content[-1] not in "——…？！。":
                content += "——"
            lines.append(content)
        else:  # visual_fragment, body_sensation, intrusion, expanded_speech
            lines.append(content)
    return "\n".join(lines)


# ── 梦境生成（ASLEEP 简化循环）─────────────────────────────────────────────────

def _dream_arbiter(
    profile: PersonProfile,
    behavior: BehaviorState,
    event: str,
    prev_state: ThoughtState,
    dream_history: list[str] | None = None,
) -> str:
    """ASLEEP 状态下的简化循环：直接输出梦境文本。"""
    prev_text = prev_state.text[-150:] if prev_state.text else "（无）"

    # 历史梦境意象去重：最多取前 3 段，告知模型已用过的核心意象
    history_ctx = ""
    if dream_history:
        snippets = [t[:60] for t in dream_history[-3:]]
        history_ctx = "\n已出现过的梦境意象（必须完全回避这些场景和意象）：" + "；".join(snippets)

    prompt = (
        f"人物：{profile.name}\n"
        f"入睡时间：{behavior.wall_clock_time}\n"
        f"今日处境：{profile.current_situation}\n"
        f"睡前残留情绪：{prev_state.emotion.dominant()}（强度{prev_state.emotion.intensity:.2f}）\n"
        f"前一段意识内容（场景和意象必须与之不同）：{prev_text}"
        + history_ctx
    )
    return fast_call(prompt, system=_SYS_DREAM, max_tokens=256)


# ── 被动衰退 ────────────────────────────────────────────────────────────────────

def _apply_decay(emotion: EmotionState, factor: float = _PASSIVE_DECAY) -> EmotionState:
    """被动情绪衰退：所有维度 × factor（默认 PASSIVE_DECAY）。"""
    d = emotion.to_dict()
    return emotion.update_from_dict({
        k: v * factor
        for k, v in d.items()
        if k != "intensity"
    })


# B2：情绪积压-释放常量
_SUPPRESSION_HIGH_THRESHOLD = 0.4   # 情绪维度超过此值视为"高"
_SUPPRESSION_BIAS_KEYWORDS = ("情绪抑制", "情绪压抑", "压抑情绪")
_SUPPRESSION_RELEASE_THRESHOLD = 0.8  # 积压超过此值触发 release
_SUPPRESSION_RESET_VALUE = 0.2       # release 后压力重置到此值


def _is_suppressing(profile: "PersonProfile", behavior: "BehaviorState | None", emotion: EmotionState) -> bool:
    """B2：判断角色是否处于情绪压抑状态。"""
    high_neg = emotion.sadness > _SUPPRESSION_HIGH_THRESHOLD or emotion.fear > _SUPPRESSION_HIGH_THRESHOLD
    if not high_neg:
        return False
    # 性格中包含压抑倾向
    for bias in getattr(profile, "cognitive_biases", []):
        if any(kw in bias for kw in _SUPPRESSION_BIAS_KEYWORDS):
            return True
    # 行为活动中包含压抑关键词
    if behavior and any(kw in getattr(behavior, "activity", "") for kw in ("忍", "压", "憋", "强撑")):
        return True
    return False


def _update_suppression_pressure(
    state: "ThoughtState",
    profile: "PersonProfile",
    behavior: "BehaviorState | None",
    new_emotion: EmotionState,
    module_outputs: dict,
) -> float:
    """B2：更新情绪积压压力值，返回新的 pressure。"""
    pressure = state.suppression_pressure
    # 检查是否有自然表达（reactive 模块有 expanded_speech 输出）
    has_expression = any(
        m.get("type") == "expanded_speech"
        for m in module_outputs.get("reactive", [])
    )
    if has_expression:
        pressure = max(0.0, pressure - 0.15)
    elif _is_suppressing(profile, behavior, new_emotion):
        pressure = min(1.0, pressure + 0.08)
    else:
        pressure = min(1.0, pressure + 0.01)
    return pressure


# ── 主入口（非流式）────────────────────────────────────────────────────────────

def _extract_conclusion(reactive_moments: list[dict]) -> str | None:
    """从 reactive 模块输出里取出 _meta moment 中的 conclusion。"""
    for m in reactive_moments:
        if m.get("_meta"):
            return m.get("_conclusion")
    return None


def _render_moments(moments: list[dict]) -> str:
    """将 moments 列表渲染为文本行（换行符连接）。
    voice_intrusion → "name说，「content」"
    unsymbolized    → "〔content〕"
    其余             → content 原样
    """
    lines = []
    for m in moments:
        mtype = m.get("type", "")
        content = (m.get("content") or "").strip()
        source = (m.get("source") or "").strip()
        if not content:
            continue
        if mtype == "voice_intrusion" and source:
            lines.append(f"{source}说，「{content}」")
        elif mtype == "unsymbolized":
            lines.append(f"〔{content}〕")
        else:
            lines.append(content)
    return "\n".join(lines)


def _render_all_outputs(module_outputs: dict[str, list[dict]]) -> str:
    """
    渲染所有模块输出为文本流（无标签，写入文件用）。
    reactive 输出在前（主思维流），drift 模块输出以 '……' 分隔追加。
    _meta 标记的 moment 过滤掉（不渲染）。
    """
    sections: list[str] = []

    reactive_moments = [m for m in module_outputs.get("reactive", []) if not m.get("_meta")]
    if reactive_moments:
        sections.append(_render_moments(reactive_moments))

    drift_order = [
        "rumination", "self_eval", "philosophy", "aesthetic",
        "counterfactual", "positive_memory", "daydream", "future",
        "social_rehearsal", "imagery",
    ]
    for name in drift_order:
        if name not in module_outputs:
            continue
        moments = [m for m in module_outputs[name] if not m.get("_meta")]
        if not moments:
            continue
        rendered = _render_moments(moments)
        if rendered.strip():
            sections.append(rendered)

    return "\n\n……\n\n".join(sections)


def render_all_outputs_labeled(module_outputs: dict[str, list[dict]]) -> str:
    """
    渲染所有模块输出为带标签文本（终端评估用）。
    格式：== 模块名 ==\n{内容}
    """
    sections: list[str] = []

    reactive_moments = [m for m in module_outputs.get("reactive", []) if not m.get("_meta")]
    if reactive_moments:
        rendered = _render_moments(reactive_moments)
        if rendered.strip():
            sections.append(f"== reactive ==\n{rendered}")

    drift_order = [
        "rumination", "self_eval", "philosophy", "aesthetic",
        "counterfactual", "positive_memory", "daydream", "future",
        "social_rehearsal", "imagery",
    ]
    for name in drift_order:
        if name not in module_outputs:
            continue
        moments = [m for m in module_outputs[name] if not m.get("_meta")]
        if not moments:
            continue
        rendered = _render_moments(moments)
        if rendered.strip():
            sections.append(f"== {name} ==\n{rendered}")

    return "\n\n".join(sections)


def run_cognitive_cycle(
    profile: PersonProfile,
    state: ThoughtState,
    memory_manager: MemoryManager,
    event: str = "",
    tick_store: TickHistoryStore | None = None,
    prev_tick_outputs: dict | None = None,
    narrative_thread: dict | None = None,
    behavior_override: "BehaviorState | None" = None,
    tick_duration_hours: float | None = None,
    active_trunk_context: str = "",
    prev_sleep_state: str = "",
    secondary_trunk_context: str = "",
) -> tuple[ThoughtState, BehaviorState, dict]:
    """
    执行一轮完整认知循环，返回 (ThoughtState, BehaviorState)。

    Layer 0 → behavior_layer（行为预测 + 睡眠状态判定）
    AWAKE：5层共享预处理 + ModuleRunner（reactive + 1~2 drift 模块）
    ASLEEP：简化循环（直出梦境文本）

    新增参数：
      prev_tick_outputs     — 上轮所有模块输出，传入 ModuleContext 供影响机制使用
      narrative_thread      — 当前最高优先级叙事线索（可选）
      active_trunk_context  — 当前 tick 选中的主干情境描述，供 drift 模块作为认知焦点
    """
    from agents.base_agent import set_output_language
    set_output_language(getattr(profile, "output_language", "zh"))

    import time

    current_tick = state.tick + 1

    # ── 记忆预采样（本轮唯一一次，保证所有层看到相同记忆组合）──────────────────
    memory_sample = _sample_memories(profile, _cooldown_tracker, current_tick)

    # ── Layer 0: Behavior ──────────────────────────────────────────────────────
    if behavior_override is not None:
        behavior = behavior_override
    else:
        behavior = behavior_layer(
            profile, current_tick,
            state.emotion.intensity, state.emotion.dominant(),
        )

    # ── ASLEEP 简化循环 ────────────────────────────────────────────────────────
    if behavior.sleep_state == "ASLEEP":
        _decay_base = _SLEEP_DECAY  # B1：睡眠时衰减更慢，保留情绪底色
        _decay_factor = _decay_base ** tick_duration_hours if tick_duration_hours is not None else _decay_base
        decayed = _apply_decay(state.emotion, factor=_decay_factor)
        # 每个睡眠 tick 生成梦境碎片（fast_call，轻量）
        try:
            # 从 tick_store 提取本次睡眠段已有的梦境文本（去重用）
            prior_dreams: list[str] = []
            if tick_store is not None:
                for ts in tick_store:
                    if ts.perceived == "（睡眠中）" and ts.text and ts.text != "（睡眠中）":
                        prior_dreams.append(ts.text)
            dream_text = _dream_arbiter(profile, behavior, event, state, dream_history=prior_dreams)
        except Exception as e:
            print(f"[dream] 生成失败：{e}")
            dream_text = "（睡眠中）"
        new_state = ThoughtState(
            text=dream_text,
            emotion=decayed,
            tick=current_tick,
            last_event=event,
            perceived="（睡眠中）",
            memory_fragment="",
            reasoning="",
            conclusion=None,
        )
        if tick_store is not None:
            tick_store.append(new_state)
        return new_state, behavior, {}

    # ── AWAKE 共享预处理层 ─────────────────────────────────────────────────────
    perceived = perception_layer(profile, event, state, behavior, memory_sample=memory_sample)
    time.sleep(0.3)
    new_emotion = emotion_layer(profile, perceived, state)
    time.sleep(0.3)

    # 被动衰退（时长感知：2h tick 衰退 30%，10min tick 仅衰退 ~6%）
    _decay_factor = _PASSIVE_DECAY ** tick_duration_hours if tick_duration_hours is not None else _PASSIVE_DECAY
    new_emotion = _apply_decay(new_emotion, factor=_decay_factor)

    # B3：清晨情绪特征——ASLEEP→AWAKE 切换后第一 tick 轻微上调 fear/sadness
    if prev_sleep_state == "ASLEEP" and behavior.sleep_state == "AWAKE":
        wakeup_boost = {
            "fear": new_emotion.fear + 0.08,
            "sadness": new_emotion.sadness + 0.05,
        }
        new_emotion = new_emotion.update_from_dict(wakeup_boost)

    # 认知残差检索
    layer_ctx = tick_store.retrieve(new_emotion) if tick_store else None

    mem_fragment = memory_layer(memory_manager, perceived, new_emotion)
    reasoning = reasoning_layer(profile, perceived, new_emotion, mem_fragment, layer_ctx, behavior)

    # ── ModuleRunner：reactive + drift 模块 ────────────────────────────────────
    emo_dict = new_emotion.to_dict()
    max_dim = max((v for k, v in emo_dict.items() if k != "intensity"), default=0.0)

    if _TEST_ALL_MODULES:
        # 测试模式：全部 drift 模块均运行，供逐模块评估
        selected_drift = [m.name for m in _drift_modules]
    else:
        # 正常模式：采样 drift 方向（中文名 → 英文 key）
        _ZH_TO_EN = {
            "白日梦/欲望幻想": "daydream",
            "哲学/存在性探讨": "philosophy",
            "创意/审美联想": "aesthetic",
            "未来规划/预期想象": "future",
            "正向记忆回溯": "positive_memory",
            "假设社交场景": "social_rehearsal",
            "自我评估": "self_eval",
            "反事实思考": "counterfactual",
            "反刍": "rumination",
        }
        selected_drift = [_ZH_TO_EN.get(sample_drift_category(emo_dict), "daydream")]
        if max_dim < 0.3:
            second_en = _ZH_TO_EN.get(sample_drift_category(emo_dict), "")
            if second_en and second_en not in selected_drift:
                selected_drift.append(second_en)

    modules_to_run = ["reactive"] + selected_drift

    # 提取上轮所有 voice_intrusion 内容，供跨模块去重
    _recent_voices: list[str] = []
    for _mouts in (prev_tick_outputs or {}).values():
        for _m in _mouts:
            if _m.get("type") == "voice_intrusion" and _m.get("content"):
                _recent_voices.append(_m["content"][:40])

    ctx = ModuleContext(
        profile=profile,
        state=state,
        event=event,
        behavior=behavior,
        perceived=perceived,
        memory_fragment=mem_fragment,
        reasoning=reasoning,
        narrative_thread=narrative_thread,
        prev_tick_outputs=prev_tick_outputs or {},
        memory_sample=memory_sample,
        active_trunk_context=active_trunk_context,
        secondary_trunk_context=secondary_trunk_context,
        recent_voice_contents=_recent_voices,
    )

    module_outputs = _module_runner.run_selected(ctx, modules_to_run)

    # ── 提取结论 + 渲染思维流 ──────────────────────────────────────────────────
    conclusion = _extract_conclusion(module_outputs.get("reactive", []))
    full_thought = _render_all_outputs(module_outputs)

    if not full_thought.strip():
        full_thought = "(empty)"

    # B2：更新情绪积压压力
    new_pressure = _update_suppression_pressure(state, profile, behavior, new_emotion, module_outputs)

    new_state = ThoughtState(
        text=full_thought,
        emotion=new_emotion,
        tick=current_tick,
        last_event=event,
        perceived=perceived,
        memory_fragment=mem_fragment,
        reasoning=reasoning,
        conclusion=conclusion,
        suppression_pressure=new_pressure,
    )

    if tick_store is not None:
        tick_store.append(new_state)

    return new_state, behavior, module_outputs

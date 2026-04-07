"""
core/cognitive_modules/drift.py — DriftModule（9 个漂移认知模块实例）

每个实例对应一种 mind-wandering 方向，学术依据见 drift_sampler.py。

模块分类：
  片段型（Fragment）：rumination / self_eval / philosophy /
                      aesthetic / counterfactual / positive_memory
  链条型（Chain）：   daydream / future / social_rehearsal

链条型机制：
  step N 的 content 显式传入 step N+1 的 prompt，
  实现"咖啡链条"等非反应式扩散联想。

所有模块失败时静默返回 []，不抛异常。
"""

from __future__ import annotations

import json
import random
import re
from abc import abstractmethod
from typing import Callable

from agents.base_agent import claude_call
from core.emotion_descriptor import get_emotion_description
from .base import CognitiveModule, ModuleContext

# ── 公共 JSON 解析 ────────────────────────────────────────────────────────────

def _parse_moments(raw: str) -> list[dict]:
    """从 LLM 输出提取 moments 列表，支持 json_repair 容错。"""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            data = json.loads(m.group())
            if isinstance(data, dict) and "moments" in data:
                return data["moments"] or []
    except Exception:
        pass
    try:
        from json_repair import repair_json
        data = json.loads(repair_json(text))
        if isinstance(data, dict):
            return data.get("moments", [])
    except Exception:
        pass
    return []


# ── 片段型模块基类 ──────────────────────────────────────────────────────────────

_FRAGMENT_OUTPUT_FMT = (
    "\n\n输出严格 JSON（不加代码块）：\n"
    '{"moments": [{"type": "...", "content": "..."}]}\n'
    "禁止隐喻、诗意修辞、情绪分析。JSON字符串内部引用人话用「」。"
)

_DES_TYPES = (
    "可用时刻类型：compressed_speech（极短内语片段）/ visual_fragment（视觉画面）"
    "/ unsymbolized（无语言的模糊认知）/ body_sensation（先于语言的身体感知）"
    "/ voice_intrusion（他人声音侵入，需 source 字段，source 只填人名如「李杨」，禁止填声调语速等描述）"
    "/ expanded_speech（完整内语，最多1次）\n"
    "出现具体人物时用人名，不用「他/她/对方」代词。"
)


class FragmentModule(CognitiveModule):
    """
    片段型模块：单次 LLM 调用，生成 2~4 个互相独立的 DES moments。
    """

    module_type = "fragment"

    def __init__(
        self,
        name: str,
        system_prompt: str,
        moment_count: str,
        get_anchor: Callable[[ModuleContext], str],
    ):
        self.name = name
        self._system = system_prompt
        self._moment_count = moment_count  # e.g. "2~4"
        self._get_anchor = get_anchor

    def run(self, ctx: ModuleContext) -> list[dict]:
        anchor = self._get_anchor(ctx)
        if not anchor:
            return []

        emotion_desc = get_emotion_description(ctx.state.emotion.to_dict())
        location_ctx = ""
        if ctx.behavior:
            location_ctx = (
                f"\n当前时间：{ctx.behavior.wall_clock_time}，"
                f"地点：{ctx.behavior.location}"
            )

        # 上轮同模块输出摘要（影响机制）
        prev_output = ctx.prev_tick_outputs.get(self.name, [])
        prev_ctx = ""
        if prev_output:
            sample = prev_output[:2]
            prev_ctx = "\n\n上轮该模块输出摘要（必须引入新视角，禁止重复以下内容）：" + "；".join(
                m.get("content", "")[:30] for m in sample if "content" in m
            )

        # 跨模块 voice_intrusion 去重（避免同一声音在不同模块反复出现）
        voice_dedup_ctx = ""
        if ctx.recent_voice_contents:
            voice_dedup_ctx = "\n\n上轮已出现的声音侵入（禁止重复相同内容）：" + "；".join(
                v for v in ctx.recent_voice_contents[:4]
            )

        # 背景事件着色（松散语境，不要求模块直接响应）
        event_ctx = ""
        if getattr(ctx, "event", None):
            event_ctx = f"\n当前背景事件（作为松散着色，不必直接响应）：{ctx.event}"

        fingerprint = ctx.profile.to_cognitive_fingerprint()

        user = (
            f"人物：{ctx.profile.name}，{ctx.profile.age}岁\n"
            f"处境：{ctx.profile.current_situation}\n"
            + (f"{fingerprint}\n" if fingerprint else "")
            + f"情绪：{emotion_desc}"
            + location_ctx
            + event_ctx
            + f"\n\n锚点：{anchor}"
            + prev_ctx
            + voice_dedup_ctx
            + f"\n\n生成 {self._moment_count} 个时刻。{_DES_TYPES}"
        )

        for _attempt in range(2):
            try:
                raw = claude_call(user, system=self._system + _FRAGMENT_OUTPUT_FMT, max_tokens=512)
                moments = _parse_moments(raw)
                if moments:
                    return moments
            except Exception as e:
                if _attempt == 1:
                    print(f"[{self.name}] 生成失败：{e}")
        return []


# ── 链条型模块基类 ──────────────────────────────────────────────────────────────

_CHAIN_STEP_FMT = (
    "\n\n生成 1 个时刻。"
    "输出严格 JSON（不加代码块）：{\"moments\": [{\"type\": \"...\", \"content\": \"...\"}]}\n"
    "禁止隐喻、情绪分析。"
)


class ChainModule(CognitiveModule):
    """
    链条型模块：step N 的 content 显式传入 step N+1，顺序展开。
    学术依据：Collins & Loftus (1975) 扩散激活链。
    """

    module_type = "chain"

    def __init__(
        self,
        name: str,
        step_system: str,
        chain_length: int,
        get_anchor: Callable[[ModuleContext], str],
    ):
        self.name = name
        self._step_system = step_system
        self._chain_length = chain_length
        self._get_anchor = get_anchor

    def run(self, ctx: ModuleContext) -> list[dict]:
        anchor = self._get_anchor(ctx)
        if not anchor:
            return []

        emotion_desc = get_emotion_description(ctx.state.emotion.to_dict())
        location_ctx = ""
        if ctx.behavior:
            location_ctx = (
                f"当前时间：{ctx.behavior.wall_clock_time}，"
                f"地点：{ctx.behavior.location}\n"
            )

        moments: list[dict] = []
        prev_step = anchor

        for step_n in range(1, self._chain_length + 1):
            user = self._build_step_prompt(ctx, prev_step, step_n, emotion_desc, location_ctx)
            for _attempt in range(2):
                try:
                    raw = claude_call(
                        user,
                        system=self._step_system + _CHAIN_STEP_FMT,
                        max_tokens=256,
                    )
                    new_moments = _parse_moments(raw)
                    if new_moments:
                        moment = new_moments[0]
                        moments.append(moment)
                        prev_step = moment.get("content", prev_step)
                        break
                except Exception as e:
                    if _attempt == 1:
                        print(f"[{self.name}] step {step_n} 失败：{e}")

        return moments

    def _build_step_prompt(
        self,
        ctx: ModuleContext,
        prev_step: str,
        step_n: int,
        emotion_desc: str,
        location_ctx: str,
    ) -> str:
        fingerprint = ctx.profile.to_cognitive_fingerprint()
        event_ctx = ""
        if getattr(ctx, "event", None):
            event_ctx = f"当前背景事件（作为松散着色，不必直接响应）：{ctx.event}\n"
        return (
            f"人物：{ctx.profile.name}，{ctx.profile.age}岁\n"
            f"处境：{ctx.profile.current_situation}\n"
            + (f"{fingerprint}\n" if fingerprint else "")
            + location_ctx
            + event_ctx
            + f"情绪：{emotion_desc}\n\n"
            f"链条第 {step_n}/{self._chain_length} 步。\n"
            f"上一步内容：{prev_step}\n"
        )


# ── 工厂函数：创建全部 9 个模块实例 ─────────────────────────────────────────────

def create_drift_modules() -> list[CognitiveModule]:
    """返回 9 个漂移模块实例（不含 reactive）。"""

    modules: list[CognitiveModule] = []

    # ── 1. rumination（反刍）────────────────────────────────────────────────
    modules.append(FragmentModule(
        name="rumination",
        system_prompt=(
            "你在模拟角色「反刍」模式的思维片段（Nolen-Hoeksema, 1991）。\n"
            "核心规则：\n"
            "- 同一内容必须出现 2 次以上（显性循环），每次允许微变形，核心情感不变\n"
            "- 禁止出现解决方向或行动意图\n"
            "- 身体感知优先（胸口、手、喉咙）——反刍在身体里有根\n"
            "- 优先类型：body_sensation、compressed_speech"
        ),
        moment_count="3~4",
        get_anchor=lambda ctx: (
            (ctx.active_trunk_context + ("\n（背景：" + ctx.secondary_trunk_context + "）" if ctx.secondary_trunk_context else ""))
            or (random.choice(ctx.profile.rumination_anchors)
                if ctx.profile.rumination_anchors
                else ctx.perceived[:30])
        ),
    ))

    # ── 2. self_eval（自我评估）──────────────────────────────────────────────
    modules.append(FragmentModule(
        name="self_eval",
        system_prompt=(
            "你在模拟角色「自我评估」模式的思维片段（medial PFC 自我参照加工）。\n"
            "核心规则：\n"
            "- 以第三人称视角观察自己的行为模式（「她总是……」「她又……」）\n"
            "- 每个时刻必须绑定具体证据（记忆片段或当下事件）\n"
            "- 禁止情绪评判，只允许观察性陈述\n"
            "- 禁止给行为模式命名或贴标签（禁止「权威定论吸收」「过度用力」一类学术/治疗师语言）\n"
            "- 优先类型：unsymbolized、expanded_speech"
        ),
        moment_count="2~3",
        get_anchor=lambda ctx: (
            (ctx.active_trunk_context + ("\n（背景：" + ctx.secondary_trunk_context + "）" if ctx.secondary_trunk_context else ""))
            or (random.choice(ctx.profile.self_eval_patterns)
                if ctx.profile.self_eval_patterns
                else "")
        ),
    ))

    # ── 3. philosophy（哲学探讨）────────────────────────────────────────────
    modules.append(FragmentModule(
        name="philosophy",
        system_prompt=(
            "你在模拟角色「哲学/存在性探讨」模式的思维片段（Smallwood, 叙事认同建构）。\n"
            "核心规则：\n"
            "- 从具体处境出发，每步向上一个抽象层级\n"
            "- 结尾必须停在无答案的问题上，禁止给结论\n"
            "- 语调冷静，带追问而非受苦\n"
            "- 优先类型：unsymbolized、expanded_speech"
        ),
        moment_count="2~4",
        get_anchor=lambda ctx: (
            (ctx.active_trunk_context + ("\n（背景：" + ctx.secondary_trunk_context + "）" if ctx.secondary_trunk_context else ""))
            or (random.choice(ctx.profile.philosophy_seeds)
                if ctx.profile.philosophy_seeds
                else ctx.profile.current_situation[:30])
        ),
    ))

    # ── 4. aesthetic（审美联想）──────────────────────────────────────────────
    modules.append(FragmentModule(
        name="aesthetic",
        system_prompt=(
            "你在模拟角色「创意/审美联想」模式的思维片段（Dijksterhuis & Meurs, 2006）。\n"
            "核心规则：\n"
            "- 完全不含情绪内容\n"
            "- 关注形式：比例、节奏、颜色、排列、密度\n"
            "- 联想可以跨领域（地铁灯带间距 → 某画面的构图）\n"
            "- 允许 unsymbolized 感知（「有什么东西是对的」）\n"
            "- 优先类型：visual_fragment、unsymbolized"
        ),
        moment_count="2~3",
        get_anchor=lambda ctx: (
            random.choice(ctx.profile.aesthetic_sensitivities)
            if ctx.profile.aesthetic_sensitivities
            else ""
        ),
    ))

    # ── 5. counterfactual（反事实思考）──────────────────────────────────────
    modules.append(FragmentModule(
        name="counterfactual",
        system_prompt=(
            "你在模拟角色「反事实思考」模式的思维片段（Roese, 1997）。\n"
            "核心规则：\n"
            "- 必须有清晰的「如果当时……」分叉点\n"
            "- 从分叉点展开另一条时间线，不停留在情感\n"
            "- 上行（更好的另一种结果）或下行（幸好没有）均可\n"
            "- 优先类型：compressed_speech、visual_fragment"
        ),
        moment_count="2~3",
        get_anchor=lambda ctx: (
            random.choice(ctx.profile.counterfactual_nodes)
            if ctx.profile.counterfactual_nodes
            else ""
        ),
    ))

    # ── 6. positive_memory（正向记忆回溯）───────────────────────────────────
    def _get_positive_memory_anchor(ctx: ModuleContext) -> str:
        """从 profile.memories 里找情绪标签正向的记忆，fallback 到第一条。"""
        pos_tags = {"joy", "trust", "anticipation", "love", "pride", "gratitude"}
        mems = ctx.profile.memories
        positive = [
            m for m in mems
            if m.get("emotion_tag", "").lower() in pos_tags
        ]
        chosen = random.choice(positive) if positive else (mems[0] if mems else None)
        if not chosen:
            return ""
        age = chosen.get("age", "")
        return f"[{age}岁] {chosen.get('event', '')}"

    modules.append(FragmentModule(
        name="positive_memory",
        system_prompt=(
            "你在模拟角色「正向记忆回溯」模式的思维片段（DMN 自传体记忆激活）。\n"
            "核心规则：\n"
            "- 必须绑定具体时间/地点\n"
            "- 感官细节优先（颜色、声音、气味、触感）\n"
            "- 不分析记忆，只呈现记忆本身\n"
            "- 禁止将记忆与当下处境比较（比较是 rumination 的领域）\n"
            "- 若出现 voice_intrusion，source 只填说话人名字（如「主管」「张明」），禁止填声调、语速、性别等描述\n"
            "- 优先类型：visual_fragment、body_sensation"
        ),
        moment_count="2~3",
        get_anchor=_get_positive_memory_anchor,
    ))

    # ── 7. daydream（白日梦/欲望联想链）────────────────────────────────────
    modules.append(ChainModule(
        name="daydream",
        step_system=(
            "你在模拟角色「白日梦」链条（Killingsworth & Gilbert, 2010，DMN 享乐性方向）。\n"
            "核心规则：\n"
            "- 高度感官化（气味、光线、触感、温度）\n"
            "- 完全禁止情绪分析和自我评判\n"
            "- 每步通过一步联想自然延伸（感官→类别→记忆→决定→计划）\n"
            "- 每步必须在感官维度（光线/触感/声音/气味/温度）或空间位置上与上一步明确区分，禁止在同一场景内连续停留\n"
            "- 优先类型：visual_fragment、body_sensation"
        ),
        chain_length=4,
        get_anchor=lambda ctx: (
            random.choice(ctx.profile.daydream_anchors)
            if ctx.profile.daydream_anchors
            else (random.choice(ctx.profile.desires) if ctx.profile.desires else "")
        ),
    ))

    # ── 8. future（未来规划/预期想象链）────────────────────────────────────
    modules.append(ChainModule(
        name="future",
        step_system=(
            "你在模拟角色「情境性未来思维」链条（Atance & O'Neill, 2001，心理时间旅行）。\n"
            "核心规则：\n"
            "- 必须是「脑中到达那个未来场景」的画面，不是规划如何到达\n"
            "- 时间跨度严格限于当天结束前（今天晚些时候）或最远明天，禁止超过24小时\n"
            "- 必须有具体时间/地点（今晚、明天早上）和感官细节（光线、声音、温度）\n"
            "- 每步必须切换到不同的时间节点或感官角度，禁止在同一时间/地点连续停留，禁止重复上一步已出现的具体物件\n"
            "- 可以包含对他人反应的预期（建模对方表情/语气）\n"
            "- 严格禁止：操作步骤、待办项、行动序列（「先做X再做Y」类内容）\n"
            "- 优先类型：visual_fragment、body_sensation"
        ),
        chain_length=3,
        get_anchor=lambda ctx: (
            (ctx.active_trunk_context + "\n" + random.choice(ctx.profile.desires))
            if ctx.active_trunk_context and ctx.profile.desires
            else (ctx.active_trunk_context
                  or (random.choice(ctx.profile.desires)
                      if ctx.profile.desires
                      else ctx.profile.current_situation[:30]))
        ),
    ))

    # ── 9. social_rehearsal（社交排演链）────────────────────────────────────
    def _get_social_pending_anchor(ctx: ModuleContext) -> str:
        """从 social_pending 随机取一条未处理的社交情境，fallback 到关系网络。"""
        pending = ctx.profile.social_pending
        if pending:
            item = random.choice(pending)
            person = item.get("person", "")
            unresolved = item.get("unresolved", "")
            return f"{person}（{unresolved}）"
        rels = ctx.profile.relationship_objects
        if rels:
            r = rels[0]
            return f"{r.name}（{r.role}）"
        return ""

    modules.append(ChainModule(
        name="social_rehearsal",
        step_system=(
            "你在模拟角色「假设社交场景排演」链条（Lieberman, 2007，心智化网络）。\n"
            "核心规则：\n"
            "- 链条：我说什么 → Ta的反应 → 我再说什么 → 结果\n"
            "- 【主角自己说的话】：用 compressed_speech 或 expanded_speech 类型，不加任何姓名标注，就是主角脑中自己的话\n"
            "- 【对方说的话】：用 voice_intrusion 类型，source 填对方名字（如「LeBron」「Vanessa」），禁止填声调、语速等描述\n"
            "- 建模对方的心理状态和可能反应\n"
            "- 出现具体人物时用人名，不用「他/她/对方」代词\n"
            "- 对话内容必须来自 profile 中已存在的关系人物，禁止虚构新人名\n"
            "- 优先类型：compressed_speech（主角话）、voice_intrusion（对方话）"
        ),
        chain_length=4,
        get_anchor=_get_social_pending_anchor,
    ))

    # ── 10. imagery（意识边缘意象）──────────────────────────────────────────
    modules.append(FragmentModule(
        name="imagery",
        system_prompt=(
            "你在模拟角色意识边缘自发浮现的感知画面（非梦境，是清醒状态下的意象闪现）。\n"
            "这些画面碎片化、非线性，混合了白天的残留记忆、欲望和身体感知。\n"
            "核心规则：\n"
            "- 不加任何情绪分析、叙事连接、或解释\n"
            "- 不标注画面来源（不写「梦里」「想象」「脑中」）\n"
            "- 感官丰富：光线、色彩、质感、气味、温度\n"
            "- 允许超现实并置（两个不相关元素突然同框），但禁止堆砌修辞\n"
            "- 优先类型：visual_fragment、body_sensation"
        ),
        moment_count="1~2",
        get_anchor=lambda ctx: (
            random.choice(ctx.profile.imagery_seeds)
            if ctx.profile.imagery_seeds
            else (ctx.perceived[:30] if ctx.perceived else ctx.profile.current_situation[:20])
        ),
    ))

    return modules

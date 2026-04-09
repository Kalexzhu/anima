"""
core/cognitive_modules/reactive.py — ReactiveModule

唯一感知并直接响应当前事件的模块（原 B1+B2+B3 逻辑）。

学术定位：
  - 情绪反应式认知，直接由外部事件驱动
  - 高情绪时输出量多，低情绪时可输出极少
  - 唯一会产生 conclusion（微决定/行动意图）的模块
"""

from __future__ import annotations

import json
import re

from agents.base_agent import claude_call
from core.emotion_descriptor import get_emotion_description
from .base import CognitiveModule, ModuleContext

# ── ReactiveModule 复用 cognitive_engine 里的 B1/B2 prompts ──────────────────

_SYS_B1 = (
    "你的任务是找出角色「此刻脑子里最可能浮现的那件具体事」。\n"
    "优先级规则：当前事件不为空时，锚点必须与当前事件直接相关；"
    "只有当前事件为空或极度日常时，才从 profile 长期偏好中选取锚点。\n"
    "必须输出 JSON，不加任何解释或代码块：\n"
    '{"anchor": "具体的事/人/物/欲望（10字以内）", '
    '"anchor_type": "person|task|desire|memory|worry", '
    '"trigger": "为什么此刻浮现（一句话）"}'
)

_SYS_B2 = (
    "你在为角色生成内心思维时刻序列。这不是文学创作，是心理模拟。\n\n"
    "时刻类型说明：\n"
    "- compressed_speech：极短内语片段（1-5字），常是未完成句，如「道歉——」「他——」\n"
    "- visual_fragment：脑中一闪而过的视觉画面，不加任何修辞\n"
    "- unsymbolized：知道自己在想某件事，但没有词也没有图——有清晰认知但无语言形式\n"
    "- body_sensation：身体感知，先于语言出现，如「胸口有点什么」「手有些凉」\n"
    "- intrusion：突然闯入的不相关念头，平淡随机，如「周报明天要发」\n"
    "- voice_intrusion：某人声音侵入，直接引用原话，需填 source 字段\n"
    "- expanded_speech：完整内语句，全序列最多出现1次，content 严格不超过15字，禁止连接词（但是/虽然/因此/于是/不过）\n\n"
    "约束：\n"
    "- 5~7个时刻，从锚点出发，每跳必须落在具体名词/事/记忆上\n"
    "- 禁止隐喻、感官叠加、诗意修辞\n"
    "- 总字数不少于200字\n"
    "- JSON字符串内部如需引用人话，用「」括号，禁止使用英文双引号\n\n"
    "write_back 准入规则（必须同时满足）：\n"
    "  角色做出了具体的微决定（去哪/做什么/不做什么）\n"
    "  结论必须是行动导向，不得是情绪评估或自我认识\n\n"
    "输出严格 JSON（不加代码块）：\n"
    '{"moments": [{"type": "...", "content": "...", "source": "（仅 voice_intrusion 填写，其余省略此字段）"}], '
    '"conclusion": "..." or null, "write_back": true or false}'
)


def _parse_json(raw: str) -> dict | None:
    try:
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            return json.loads(m.group())
        return json.loads(raw)
    except Exception:
        pass
    try:
        from json_repair import repair_json
        result = json.loads(repair_json(raw))
        if isinstance(result, dict):
            return result
    except Exception:
        pass
    return None


class ReactiveModule(CognitiveModule):
    """
    情绪反应式模块（原 B1+B2+B3）。

    特殊字段（非标准 DES moment）：
      result["_conclusion"] — 微决定文本，供 cognitive_engine 提取
      result["_write_back"] — 是否满足写回条件
    这两个字段附在返回列表的最后一个伪 moment 里传递，
    在 ModuleRunner 层过滤掉，只在 cognitive_engine 显式读取。
    """

    name = "reactive"
    module_type = "fragment"

    def run(self, ctx: ModuleContext) -> list[dict]:
        emotion_desc = get_emotion_description(ctx.state.emotion.to_dict())
        profile = ctx.profile
        behavior = ctx.behavior

        desires = profile.desires
        hobbies = profile.hobbies
        desires_ctx = ""
        if desires or hobbies:
            items = desires[:3] + hobbies[:2]
            desires_ctx = f"\n人物内心欲望/兴趣（可作为锚点素材）：{'；'.join(items)}"

        location_ctx = ""
        if behavior:
            location_ctx = f"\n当前时间：{behavior.wall_clock_time}，地点：{behavior.location}"

        prev_thought = ctx.state.text[-200:] if ctx.state.text else ""

        # 上一轮已出现的 voice_intrusion，提取出来禁止重复
        prev_voices: list[str] = []
        for moments_list in (ctx.prev_tick_outputs or {}).values():
            for m in (moments_list or []):
                if m.get("type") == "voice_intrusion" and m.get("content"):
                    inner = re.sub(r"^「+|」+$", "", m["content"]).strip()
                    if inner:
                        prev_voices.append(inner)

        # ── B1：锚点选择 ───────────────────────────────────────────────────
        b1_user = (
            f"【当前事件（优先参考）】{ctx.event or '无'}\n"
            f"感知焦点：{ctx.perceived}\n"
            f"情绪状态：{emotion_desc}"
            + location_ctx
            + f"\n\n人物档案：\n{profile.to_prompt_context(memory_override=ctx.memory_sample or None)}\n"
            f"激活记忆：{ctx.memory_fragment or '无'}"
            + desires_ctx
        )
        if prev_thought:
            b1_user += f"\n上一轮思维（避免重复）：{prev_thought}"
        if prev_voices:
            b1_user += f"\n【禁止重复的侵入声音（上轮已出现，本轮必须换其他内容）】：{'；'.join(prev_voices[:4])}"

        b1_raw = claude_call(b1_user, system=_SYS_B1, max_tokens=150)
        b1_data = _parse_json(b1_raw)
        anchor = b1_data.get("anchor", ctx.perceived[:20]) if b1_data else ctx.perceived[:20]
        trigger = b1_data.get("trigger", "") if b1_data else ""

        # ── B2：链条生成 ────────────────────────────────────────────────────
        b2_system = _SYS_B2 + f"\n\n人物档案：\n{profile.to_prompt_context(memory_override=ctx.memory_sample or None)}"
        b2_user = (
            f"锚点：{anchor}（浮现原因：{trigger}）\n"
            f"情绪状态：{emotion_desc}\n"
            f"内心推断：{ctx.reasoning}"
            + location_ctx
        )

        b2_raw = claude_call(b2_user, system=b2_system, max_tokens=2048)
        b2_data = _parse_json(b2_raw)

        if not b2_data or "moments" not in b2_data:
            print(f"[ReactiveModule] B2 JSON 解析失败，raw={b2_raw[:80]!r}")
            # fallback：把原文包成一个 expanded_speech moment
            return [{"type": "expanded_speech", "content": b2_raw[:60]}]

        moments = b2_data.get("moments", [])
        conclusion = b2_data.get("conclusion")
        write_back = b2_data.get("write_back", False)
        if conclusion and not write_back:
            conclusion = None

        # 把 conclusion 附在最后一个特殊 moment 里（_meta 前缀，渲染时过滤）
        if conclusion:
            moments.append({"_meta": True, "_conclusion": conclusion})

        return moments

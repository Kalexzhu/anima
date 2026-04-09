"""
core/renderer.py — DES moments → 意识流文本渲染。

将认知模块输出的 DES moment 列表渲染为可读文本。
纯确定性代码，不调用 LLM。

两种模式：
  - render_all_outputs()       → 无标签连续文本（写入文件用）
  - render_all_outputs_labeled() → 带模块名标签（终端评估用）
"""

from __future__ import annotations


# ── drift 模块渲染顺序（唯一数据源）────────────────────────────────────────────

DRIFT_MODULE_ORDER = [
    "rumination", "self_eval", "philosophy", "aesthetic",
    "counterfactual", "positive_memory", "daydream", "future",
    "social_rehearsal", "imagery",
]


# ── moment → 文本 ─────────────────────────────────────────────────────────────

def render_moments(moments: list[dict]) -> str:
    """将 moments 列表渲染为文本行。
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


# ── 全模块输出 → 文本 ────────────────────────────────────────────────────────

def _filter_real_moments(moments: list[dict]) -> list[dict]:
    """过滤掉 _meta 伪 moment（reactive conclusion 等）。"""
    return [m for m in moments if not m.get("_meta")]


def render_all_outputs(module_outputs: dict[str, list[dict]]) -> str:
    """
    渲染所有模块输出为连续文本（写入文件用）。
    reactive 在前，drift 模块以 '……' 分隔追加。
    """
    sections: list[str] = []

    reactive_moments = _filter_real_moments(module_outputs.get("reactive", []))
    if reactive_moments:
        sections.append(render_moments(reactive_moments))

    for name in DRIFT_MODULE_ORDER:
        if name not in module_outputs:
            continue
        moments = _filter_real_moments(module_outputs[name])
        if not moments:
            continue
        rendered = render_moments(moments)
        if rendered.strip():
            sections.append(rendered)

    return "\n\n……\n\n".join(sections)


def render_all_outputs_labeled(module_outputs: dict[str, list[dict]]) -> str:
    """
    渲染所有模块输出为带标签文本（终端评估用）。
    格式：== 模块名 ==\n{内容}
    """
    sections: list[str] = []

    reactive_moments = _filter_real_moments(module_outputs.get("reactive", []))
    if reactive_moments:
        rendered = render_moments(reactive_moments)
        if rendered.strip():
            sections.append(f"== reactive ==\n{rendered}")

    for name in DRIFT_MODULE_ORDER:
        if name not in module_outputs:
            continue
        moments = _filter_real_moments(module_outputs[name])
        if not moments:
            continue
        rendered = render_moments(moments)
        if rendered.strip():
            sections.append(f"== {name} ==\n{rendered}")

    return "\n\n".join(sections)

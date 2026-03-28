"""
core/viz_renderer.py — 可视化层 JSON 渲染器

将单个 tick 的 module_outputs 转换为前端可消费的 viz JSON。

输出格式（per-tick JSON）：
{
  "tick": 1,
  "event": "...",
  "time": "15:00",
  "location": "望京某互联网公司",
  "sleep_state": "AWAKE",
  "emotion": { "dominant": "sadness", "intensity": 0.48, "anger": 0.22, ... },
  "moments": [
    { "id": 0, "type": "body_sensation", "display_text": "...", "source": null, "module": "reactive" },
    ...
  ]
}

类型处理规则：
  voice_intrusion → "name说，「content」"（name 取 source 首个逗号前的部分）
  unsymbolized    → 去掉〔〕包裹，直接返回内容（前端负责斜体+灰色渲染）
  其余            → 原样输出 content
"""

from __future__ import annotations

import json
import os
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.behavior import BehaviorState
    from core.emotion import EmotionState


# 模块输出顺序（reactive 优先，drift 按认知权重排列）
_MODULE_ORDER = [
    "reactive",
    "rumination",
    "self_eval",
    "philosophy",
    "aesthetic",
    "counterfactual",
    "positive_memory",
    "daydream",
    "future",
    "social_rehearsal",
    "imagery",
]


def _transform_moment(m: dict, module_name: str, moment_id: int) -> dict | None:
    """将单个 raw moment 转换为 viz-ready dict。失败返回 None。"""
    mtype = m.get("type", "")
    content = (m.get("content") or "").strip()
    source = (m.get("source") or "").strip()

    if not content:
        return None

    # voice_intrusion：渲染为 "name说，「content」"
    if mtype == "voice_intrusion":
        name = source.split("，")[0].split(",")[0].strip() if source else ""
        # 剥掉 LLM 可能自带的外层「」，避免双层括号
        inner = re.sub(r"^「+|」+$", "", content).strip()
        if name:
            display_text = f"{name}说，「{inner}」"
        else:
            display_text = f"「{inner}」"
    # unsymbolized：去掉〔〕
    elif mtype == "unsymbolized":
        display_text = re.sub(r"^〔|〕$", "", content).strip()
    else:
        display_text = content

    if not display_text:
        return None

    return {
        "id": moment_id,
        "type": mtype or "compressed_speech",
        "display_text": display_text,
        "source": source or None,
        "module": module_name,
    }


def render_for_viz(
    tick: int,
    event: str,
    behavior: "BehaviorState | None",
    emotion: "EmotionState",
    module_outputs: dict[str, list[dict]],
) -> dict:
    """
    将一个 tick 的所有模块输出转换为 viz JSON dict。

    Args:
        tick:           轮次序号（1-based）
        event:          本轮触发的环境事件文本（空字符串 = 无事件）
        behavior:       BehaviorState（含 wall_clock_time / location / sleep_state）
        emotion:        本轮最终 EmotionState
        module_outputs: dict[模块名 → moments列表]（run_cognitive_cycle 的返回值）

    Returns:
        viz-ready dict，可直接序列化为 JSON。
    """
    moments: list[dict] = []
    moment_id = 0

    for module_name in _MODULE_ORDER:
        raw_moments = module_outputs.get(module_name, [])
        for m in raw_moments:
            # 过滤掉内部 _meta 标记
            if m.get("_meta"):
                continue
            transformed = _transform_moment(m, module_name, moment_id)
            if transformed:
                moments.append(transformed)
                moment_id += 1

    emo_dict = emotion.to_dict()
    emotion_data = {
        "dominant": emotion.dominant(),
        "intensity": round(emotion.intensity, 3),
    }
    for k, v in emo_dict.items():
        if k != "intensity":
            emotion_data[k] = round(v, 3)

    return {
        "tick": tick,
        "event": event or "",
        "time": behavior.wall_clock_time if behavior else "",
        "location": behavior.location if behavior else "",
        "sleep_state": behavior.sleep_state if behavior else "AWAKE",
        "emotion": emotion_data,
        "moments": moments,
    }


def write_tick_viz(run_id: str, tick: int, viz_data: dict, output_dir: str = "output") -> str:
    """
    将 viz_data 写入 output/{run_id}_viz/tick_{tick:02d}.json。
    返回写入路径。
    """
    viz_dir = os.path.join(output_dir, f"{run_id}_viz")
    os.makedirs(viz_dir, exist_ok=True)
    path = os.path.join(viz_dir, f"tick_{tick:02d}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(viz_data, f, ensure_ascii=False, indent=2)
    return path

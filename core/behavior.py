"""
core/behavior.py — Layer 0：行为预测层。

每轮 tick 第一步：从 profile.typical_schedule 查表推断当前时间/地点/活动，
再通过 LLM 加入情绪弹性偏离，输出 BehaviorState。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Dict, List

from agents.base_agent import fast_call

if TYPE_CHECKING:
    from core.profile import PersonProfile


_SYS_BEHAVIOR = (
    "你是行为预测器。根据人物的当前时间、地点、活动和情绪状态，"
    "用1-2句话描述此刻的具体行为细节。"
    "要真实、有细节感，体现出情绪对行为的微妙影响（若情绪强烈）。"
    "直接输出行为描述，不加任何前缀。"
)


@dataclass
class BehaviorState:
    location: str        # 当前地点，e.g. "出租屋"
    activity: str        # 当前活动，e.g. "在家休息"
    sleep_state: str     # "AWAKE" | "ASLEEP"
    description: str     # LLM 弹性行为描述（1-2句）
    wall_clock_time: str # 当前时刻，e.g. "15:00"


def _parse_hm(time_str: str) -> int:
    """解析 HH:MM，返回当天分钟数（0~1439）。"""
    h, m = time_str.strip().split(":")
    return int(h) * 60 + int(m)


def _lookup_schedule(schedule: List[Dict[str, Any]], wall_dt: datetime) -> Dict[str, Any]:
    """根据当前时间在作息表中查表，支持跨午夜时段（如 23:00-07:00）。"""
    cur = wall_dt.hour * 60 + wall_dt.minute
    for entry in schedule:
        tr = entry.get("time_range", "")
        if "-" not in tr:
            continue
        start_str, end_str = tr.split("-", 1)
        s, e = _parse_hm(start_str), _parse_hm(end_str)
        if s > e:  # 跨午夜
            if cur >= s or cur < e:
                return entry
        else:
            if s <= cur < e:
                return entry
    return schedule[0] if schedule else {}


def behavior_layer(
    profile: "PersonProfile",
    tick: int,
    emotion_intensity: float,
    emotion_dominant: str,
) -> BehaviorState:
    """
    Layer 0：行为预测。
    1. 从 profile.typical_schedule 查表 → 基础 {location, activity}
    2. LLM 根据情绪生成弹性行为描述
    """
    schedule = getattr(profile, "typical_schedule", [])
    start_str = getattr(profile, "scenario_start_time", "2024-01-01T09:00:00")
    tick_h = getattr(profile, "tick_duration_hours", 2.0)

    # tick=1 对应 start_time，tick=2 对应 start_time+2h，以此类推
    start_dt = datetime.fromisoformat(start_str)
    wall_dt = start_dt + timedelta(hours=tick_h * (tick - 1))
    time_str = wall_dt.strftime("%H:%M")

    entry = _lookup_schedule(schedule, wall_dt) if schedule else {}
    location = entry.get("location", getattr(profile, "home_location", "某处"))
    activity = entry.get("activity", "日常活动")
    sleep_state = "ASLEEP" if "睡眠" in activity else "AWAKE"

    emotion_hint = ""
    if emotion_intensity > 0.35:
        emotion_hint = f"当前主导情绪：{emotion_dominant}（强度{emotion_intensity:.2f}）。"

    prompt = (
        f"人物：{profile.name}\n"
        f"当前时间：{time_str}\n"
        f"所在地点：{location}\n"
        f"正在做：{activity}\n"
        f"{emotion_hint}"
        f"性格：{', '.join(list(getattr(profile, 'personality_traits', []))[:3])}"
    )
    description = fast_call(prompt, system=_SYS_BEHAVIOR, max_tokens=80)

    return BehaviorState(
        location=location,
        activity=activity,
        sleep_state=sleep_state,
        description=description,
        wall_clock_time=time_str,
    )

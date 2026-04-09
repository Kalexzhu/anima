"""
scenarios/kobe_2020/runner.py — 科比坠机前一天旁路场景跑手

旁路框架：直接控制每个 tick 的行为状态（BehaviorState），
跳过 WorldEngine / NarrativeThreadManager / WritebackManager，
保留完整认知引擎（emotion / memory / modules）。

时间线：2020-01-25 07:00 → 2020-01-26 09:47（坠机时刻）
  · Tick 1-8：Jan 25，每 tick 约 2 小时
  · Tick 9：Jan 26 清晨（2.75 小时）
  · Tick 10-15：Jan 26 飞行阶段，每 tick 约 10 分钟

用法：
  cd ~/Projects/mind-reading
  python3 scenarios/kobe_2020/runner.py --profile scenarios/kobe_2020/kobe_profile.json
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

# 把项目根目录加入 sys.path，保证 core/ 可导入
_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

import dataclasses

from core.profile import PersonProfile
from core.emotion import EmotionState
from core.thought import ThoughtState
from core.memory import MemoryManager
from core.behavior import BehaviorState
from core.tick_history import TickHistoryStore
from core.cognitive_engine import run_cognitive_cycle
from core.renderer import render_all_outputs_labeled
from core.viz_renderer import render_for_viz, write_tick_viz

# ── 路径常量 ────────────────────────────────────────────────────────────────────

SCENARIO_DIR = Path(__file__).parent
TIMELINE_PATH = SCENARIO_DIR / "timeline.json"


# ── 工具函数（复用 run.py 模式）────────────────────────────────────────────────

def _load_profile(path: str) -> PersonProfile:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    known = {f.name for f in dataclasses.fields(PersonProfile)}
    filtered = {k: v for k, v in data.items() if k in known}
    return PersonProfile(**filtered)


def _next_output_index(prefix: str) -> int:
    os.makedirs("output", exist_ok=True)
    n = 1
    while os.path.exists(f"output/{prefix}_{n:02d}.txt"):
        n += 1
    return n


def _seed_initial_emotion(profile: PersonProfile, state: ThoughtState) -> ThoughtState:
    """tick 1 前用 current_situation 播种初始情绪，避免从强度 0 开始。"""
    from core.occ import OCC_SYSTEM_PROMPT, parse_occ_response, occ_to_plutchik, apply_personality_modifiers
    from agents.base_agent import fast_call

    prompt = (
        f"人物性格：{', '.join(profile.personality_traits)}\n"
        f"核心价值观：{', '.join(profile.core_values)}\n"
        f"认知偏差：{', '.join(profile.cognitive_biases)}\n"
        f"当前感知：{profile.current_situation}。身体状态：{profile.current_physical_state}\n"
        f'当前情绪基线：{{"anger": 0.0, "fear": 0.0, "joy": 0.0, "sadness": 0.0, '
        f'"surprise": 0.0, "disgust": 0.0, "anticipation": 0.0, "trust": 0.0, "intensity": 0.0}}'
    )
    try:
        raw = fast_call(prompt, system=OCC_SYSTEM_PROMPT)
        appraisal = parse_occ_response(raw)
        if appraisal is None:
            print("[情绪播种] OCC 解析失败，保持初始 0.0")
            return state
        plutchik = occ_to_plutchik(appraisal)
        plutchik = apply_personality_modifiers(plutchik, profile.cognitive_biases)
        seeded = state.emotion.update_from_dict(plutchik)
        print(f"[情绪播种] 初始情绪：{seeded.dominant()}（强度 {seeded.intensity:.2f}）")
        return dataclasses.replace(state, emotion=seeded)
    except Exception as e:
        print(f"[情绪播种] 失败：{e}，保持初始 0.0")
        return state


def _print_divider(
    tick: int,
    date: str,
    wall_clock_time: str,
    location: str,
    event: str,
    intensity: float,
    dominant: str,
    tick_duration_hours: float,
) -> None:
    bar = "█" * int(intensity * 20) + "░" * (20 - int(intensity * 20))
    duration_label = f"{tick_duration_hours*60:.0f}min" if tick_duration_hours < 1 else f"{tick_duration_hours:.1f}h"
    print(f"\n{'─'*68}")
    print(f"  Tick {tick:02d}  |  [{bar}] {intensity:.2f}  |  {dominant}")
    print(f"  ⏰ {date} {wall_clock_time}  📍 {location}  🕐 {duration_label}")
    if event:
        preview = event[:80] + "…" if len(event) > 80 else event
        print(f"  事件：{preview}")
    print(f"{'─'*68}")


# ── 主场景跑手 ──────────────────────────────────────────────────────────────────

def run_scenario(profile_path: str, max_ticks: int | None = None, start_tick: int = 1) -> None:
    profile = _load_profile(profile_path)

    # 运行前备份 profile
    backup_dir = os.path.join("output")
    os.makedirs(backup_dir, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    backup_name = os.path.basename(profile_path).replace(".json", f"_pre_run_{ts}.json")
    shutil.copy2(profile_path, os.path.join(backup_dir, backup_name))

    with open(TIMELINE_PATH, "r", encoding="utf-8") as f:
        timeline: list[dict] = json.load(f)

    # 起始偏移（1-based）
    if start_tick > 1:
        timeline = timeline[start_tick - 1:]
    if max_ticks is not None:
        timeline = timeline[:max_ticks]

    memory = MemoryManager()
    memory.load_from_profile(profile.memories)

    tick_store = TickHistoryStore()
    state = ThoughtState(text="", emotion=EmotionState(), tick=0)
    state = _seed_initial_emotion(profile, state)

    # 输出文件
    n = _next_output_index("kobe_2020")
    run_id = f"kobe_2020_{n:02d}"
    txt_path = f"output/{run_id}.txt"
    json_path = f"output/{run_id}.json"
    os.makedirs("output", exist_ok=True)

    print(f"\n[scenario] 开始运行：{run_id}")
    print(f"[scenario] profile：{profile.name}，{profile.age}岁")
    print(f"[scenario] 时间线：{len(timeline)} ticks\n")

    records: list[dict] = []
    prev_tick_outputs: dict = {}

    with open(txt_path, "w", encoding="utf-8") as out_f:
        out_f.write(f"=== {run_id} ===\n")
        out_f.write(f"角色：{profile.name}，{profile.age}岁\n")
        out_f.write(f"场景：科比坠机前的最后时光（2020-01-25 ~ 2020-01-26）\n\n")

        for tick_data in timeline:
            behavior = BehaviorState(
                location=tick_data["location"],
                activity=tick_data["activity"],
                sleep_state=tick_data.get("sleep_state", "AWAKE"),
                description=tick_data.get("description", ""),
                wall_clock_time=tick_data["wall_clock_time"],
            )
            tick_duration = tick_data.get("tick_duration_hours", 2.0)
            event_text = tick_data.get("event", "")

            state, _, module_outputs = run_cognitive_cycle(
                profile=profile,
                state=state,
                memory_manager=memory,
                event=event_text,
                tick_store=tick_store,
                prev_tick_outputs=prev_tick_outputs,
                narrative_thread=None,
                behavior_override=behavior,
                tick_duration_hours=tick_duration,
            )

            prev_tick_outputs = module_outputs

            _print_divider(
                tick=state.tick,
                date=tick_data["date"],
                wall_clock_time=tick_data["wall_clock_time"],
                location=behavior.location,
                event=event_text,
                intensity=state.emotion.intensity,
                dominant=state.emotion.dominant(),
                tick_duration_hours=tick_duration,
            )

            # 打印带标签的输出供评估
            labeled = render_all_outputs_labeled(module_outputs)
            print(labeled)

            # 写入文本文件
            out_f.write(f"── Tick {state.tick:02d}  {tick_data['date']} {tick_data['wall_clock_time']} ──\n")
            out_f.write(f"地点：{behavior.location}\n")
            out_f.write(f"情绪：{state.emotion.dominant()}（{state.emotion.intensity:.2f}）\n")
            if state.conclusion:
                out_f.write(f"微决定：{state.conclusion}\n")
            out_f.write("\n" + state.text + "\n\n")
            out_f.flush()

            records.append({
                "tick": state.tick,
                "date": tick_data["date"],
                "wall_clock_time": tick_data["wall_clock_time"],
                "location": behavior.location,
                "event": event_text,
                "tick_duration_hours": tick_duration,
                "emotion": {k: v for k, v in state.emotion.to_dict().items() if k != "intensity"},
                "intensity": state.emotion.intensity,
                "dominant": state.emotion.dominant(),
                "conclusion": state.conclusion,
                "text": state.text,
            })

            # 写入 viz JSON（供网页端实时预览）
            viz_data = render_for_viz(
                tick=state.tick,
                event=event_text,
                behavior=behavior,
                emotion=state.emotion,
                module_outputs=module_outputs,
            )
            write_tick_viz(run_id=run_id, tick=state.tick, viz_data=viz_data)

            time.sleep(0.5)

    # 写入 JSON 结构化数据
    with open(json_path, "w", encoding="utf-8") as jf:
        json.dump({
            "run_id": run_id,
            "profile": profile.name,
            "scenario": "kobe_2020",
            "ticks": records,
        }, jf, ensure_ascii=False, indent=2)

    print(f"\n[scenario] 完成。输出：{txt_path} / {json_path}")


# ── CLI 入口 ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Kobe 2020 场景跑手")
    parser.add_argument(
        "--profile",
        default=str(SCENARIO_DIR / "kobe_profile.json"),
        help="profile JSON 路径（默认：scenarios/kobe_2020/kobe_profile.json）",
    )
    parser.add_argument(
        "--max-ticks",
        type=int,
        default=None,
        help="最多运行几个 tick（默认：全部 15 个）",
    )
    parser.add_argument(
        "--start-tick",
        type=int,
        default=1,
        help="从第几个 tick 开始（1-based，默认：1）",
    )
    args = parser.parse_args()

    if not os.path.exists(args.profile):
        print(f"[错误] profile 文件不存在：{args.profile}")
        print("请先创建 kobe_profile.json，参考 examples/demo_profile.json 格式。")
        sys.exit(1)

    run_scenario(args.profile, max_ticks=args.max_ticks, start_tick=args.start_tick)


if __name__ == "__main__":
    main()

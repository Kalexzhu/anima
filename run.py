"""
run.py — ANIMA 主入口（重构版）。
输出：output/run_{name}_{n}.txt（流式文本）
      output/run_{name}_{n}.json（结构化数据）
      output/run_{name}_{n}_viz.txt（可视化报告）
"""

import json
import os
import sys
import time
from datetime import datetime

from core.profile import PersonProfile
from core.emotion import EmotionState
from core.thought import ThoughtState
from core.memory import MemoryManager
from core.cognitive_engine import run_cognitive_cycle, render_all_outputs_labeled
from core.viz_renderer import render_for_viz, write_tick_viz
from core.tick_history import TickHistoryStore
from core.world_engine import WorldEngine
from core.residual_feedback import ResidualFeedback
from core.writeback import WritebackManager
from core.narrative import NarrativeThreadManager
MAX_TICKS          = 20
INTENSITY_THRESHOLD = 0.45
CALM_INTERVAL       = 3

# WorldEngine v2 参数（均可在此调整）
EMOTION_DECAY             = 0.4    # 情绪惯性衰减（0=无惯性，1=不变化）
REL_APPEAR_THRESHOLD      = 0.3    # 关系登场概率线性公式下限
REL_APPEAR_SLOPE          = 0.7    # 关系登场概率线性公式斜率
EVENT_HISTORY_WINDOW      = 10     # 跨轮次事件历史窗口大小
DRAMATIC_COOLDOWN         = 2      # dramatic 事件冷却轮数

EMOTIONS_ZH = {
    "anger": "愤怒", "fear": "恐惧", "joy": "喜悦", "sadness": "悲伤",
    "surprise": "惊讶", "disgust": "厌恶", "anticipation": "期待", "trust": "信任",
}


def load_profile(path: str) -> PersonProfile:
    import dataclasses
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    # 过滤掉 PersonProfile 不认识的字段，保证兼容性
    known = {f.name for f in dataclasses.fields(PersonProfile)}
    filtered = {k: v for k, v in data.items() if k in known}
    return PersonProfile(**filtered)


def _resolve_narrative_state_path(profile_path: str) -> str:
    """
    确定运行时 narrative_state.json 的路径。
    1. 若 output/narrative_state.json 已存在，直接使用（续跑）。
    2. 否则从 examples/*_narrative_state.json 复制初始版本。
    3. 若 examples 版本也不存在，报错退出。
    """
    output_path = "output/narrative_state.json"
    if os.path.exists(output_path):
        return output_path

    # 推断 examples 版本路径：demo_profile.json → demo_narrative_state.json
    profile_dir = os.path.dirname(profile_path) or "."
    profile_basename = os.path.basename(profile_path)
    stem = profile_basename.replace("_profile.json", "").replace(".json", "")
    example_path = os.path.join(profile_dir, f"{stem}_narrative_state.json")

    if not os.path.exists(example_path):
        print(f"[run.py] 错误：找不到叙事线索初始文件 {example_path}")
        print(f"         请创建该文件（参考 examples/demo_narrative_state.json 格式）")
        sys.exit(1)

    import shutil
    os.makedirs("output", exist_ok=True)
    shutil.copy(example_path, output_path)
    print(f"[run.py] 叙事线索初始文件已复制：{example_path} → {output_path}")
    return output_path


def _next_output_index(prefix: str) -> int:
    """找当前 output/ 下最大序号 + 1。"""
    os.makedirs("output", exist_ok=True)
    n = 1
    while os.path.exists(f"output/{prefix}_{n:02d}.txt"):
        n += 1
    return n


def print_divider(tick: int, event: str, intensity: float, dominant: str, mem_mode: str,
                  wall_time: str = "", location: str = "", sleep_state: str = "AWAKE"):
    bar = "█" * int(intensity * 20) + "░" * (20 - int(intensity * 20))
    event_str = f"事件：{event}" if event else "（无新事件）"
    sleep_icon = "💤" if sleep_state == "ASLEEP" else "👁"
    time_loc = f"  ⏰ {wall_time}  📍 {location}  {sleep_icon}" if wall_time else ""
    print(f"\n{'─'*62}")
    print(f"  轮次 {tick:02d}  |  [{bar}] {intensity:.2f}  |  {dominant}  |  mem:{mem_mode}")
    if time_loc:
        print(time_loc)
    print(f"  {event_str}")
    print(f"{'─'*62}")


# ── 可视化生成 ─────────────────────────────────────────────────────────────────

def _bar(value: float, width: int = 20) -> str:
    filled = int(value * width)
    return "█" * filled + "░" * (width - filled)


def _wrap(text: str, width: int = 60, indent: str = "  ") -> str:
    """简单自动换行（不依赖 textwrap，避免破坏中文）。"""
    lines = []
    current = ""
    for char in text:
        current += char
        if char in ("。", "！", "？", "…", "\n") or len(current) >= width:
            lines.append(indent + current.strip())
            current = ""
    if current.strip():
        lines.append(indent + current.strip())
    return "\n".join(lines)


def generate_visualization(
    profile: PersonProfile,
    records: list,
    mem_mode: str,
    run_id: str,
) -> str:
    W = 68
    SEP = "═" * W
    sep = "─" * W

    lines = []

    # ── 标题 ──────────────────────────────────────────────────────────────────
    lines += [
        "",
        SEP,
        f"  ANIMA 可视化报告  |  {run_id}",
        SEP,
        f"  角色：{profile.name}，{profile.age}岁",
        f"  处境：{profile.current_situation}",
        f"  身体：{profile.current_physical_state}",
        f"  性格：{', '.join(profile.personality_traits)}",
        f"  认知偏差：{', '.join(profile.cognitive_biases)}",
        f"  记忆模式：{mem_mode}  |  共 {len(records)} 轮",
        SEP,
    ]

    # ── 情绪弧线（纵轴=情绪维度，横轴=轮次）────────────────────────────────
    lines += ["", "  ── 情绪弧线（全程）──", ""]
    header = "  维度      " + "".join(f" {r['tick']:02d} " for r in records)
    lines.append(header)
    lines.append("  " + "─" * (len(header) - 2))

    for emo_key, emo_zh in EMOTIONS_ZH.items():
        values = [r["emotion"].get(emo_key, 0.0) for r in records]
        max_v = max(values) if max(values) > 0 else 0
        row = f"  {emo_zh}{'　' * (4 - len(emo_zh))}"  # 对齐中文
        for v in values:
            block = "▓" if v > 0.5 else ("░" if v > 0.1 else " ")
            row += f" {block}{v:.1f}"
        lines.append(row)

    lines += [""]
    # 强度行
    intensity_row = "  强度      "
    for r in records:
        intensity_row += f" {r['intensity']:.2f}"
    lines.append(intensity_row)

    # ── 环境时间线 ──────────────────────────────────────────────────────────
    lines += ["", sep, "  ── 环境时间线 ──", ""]
    timeline = "  "
    for r in records:
        marker = f"[{r['tick']:02d}]"
        if r["event"]:
            timeline += f"{marker}★ "
        else:
            timeline += f"{marker}── "
    lines.append(timeline)

    for r in records:
        if r["event"]:
            lines.append(f"  轮次{r['tick']:02d}: 【事件】{r['event']}")

    # ── 逐轮详情 ────────────────────────────────────────────────────────────
    lines += ["", sep, "  ── 逐轮详情 ──"]

    for r in records:
        tick = r["tick"]
        emo = r["emotion"]
        dominant = r["dominant"]
        intensity = r["intensity"]

        lines += [
            "",
            f"  ╔══ 轮次 {tick:02d} {'═' * (W - 10)}",
            f"  ║",
            f"  ║  ⏰ {r.get('wall_clock_time', '??:??')}  📍 {r.get('location', '未知')}  {'💤' if r.get('sleep_state') == 'ASLEEP' else '👁'}",
            f"  ║  环境事件：{'【' + r['event'] + '】' if r['event'] else '（无）'}",
        ]

        if r.get("perceived"):
            lines.append(f"  ║  感知焦点：{r['perceived']}")

        if r.get("memory_fragment") and r["memory_fragment"].strip() not in ("无", ""):
            lines.append(f"  ║  激活记忆：{r['memory_fragment'][:80]}{'…' if len(r['memory_fragment']) > 80 else ''}")

        if r.get("reasoning"):
            lines.append(f"  ║  内心推断：{r['reasoning'][:80]}{'…' if len(r['reasoning']) > 80 else ''}")

        # 情绪快照（只显示 > 0 的维度）
        emo_parts = [
            f"{EMOTIONS_ZH[k]}={v:.2f}"
            for k, v in emo.items()
            if k in EMOTIONS_ZH and v > 0.05
        ]
        emo_str = " | ".join(emo_parts) if emo_parts else "平静（所有维度 ≈ 0）"
        lines += [
            f"  ║  情绪快照：{emo_str}",
            f"  ║  强度：{_bar(intensity, 20)} {intensity:.2f}  主导：{dominant}",
            f"  ║",
            f"  ║  ── 思维流 ──",
        ]

        # 思维流文本，自动换行
        thought = r.get("thought", "")
        for seg in thought.split("\n"):
            seg = seg.strip()
            if seg:
                lines.append(f"  ║  {seg}")
            else:
                lines.append(f"  ║")

        lines.append(f"  ╚{'═' * (W - 2)}")

    # ── 尾部统计 ────────────────────────────────────────────────────────────
    lines += ["", SEP, "  ── 统计摘要 ──", ""]

    events_count = sum(1 for r in records if r["event"])
    peak_tick = max(records, key=lambda r: r["intensity"])
    lines += [
        f"  总轮次：{len(records)}  |  环境事件触发：{events_count} 次",
        f"  情绪峰值：轮次 {peak_tick['tick']:02d}  强度 {peak_tick['intensity']:.2f}（{peak_tick['dominant']}）",
    ]

    if records:
        all_emo = {k: [r["emotion"].get(k, 0) for r in records] for k in EMOTIONS_ZH}
        avg_dominant = max(EMOTIONS_ZH.keys(), key=lambda k: sum(all_emo[k]))
        lines.append(f"  全程主导情绪：{EMOTIONS_ZH[avg_dominant]}（{avg_dominant}）")

    lines += ["", SEP, ""]
    return "\n".join(lines)


# ── 情绪初始播种 ─────────────────────────────────────────────────────────────────

def _seed_initial_emotion(profile, state: "ThoughtState") -> "ThoughtState":
    """
    tick 1 前用 current_physical_state + current_situation 做一次快速 OCC 估算，
    播种初始 EmotionState，避免 tick 1 从强度 0.00 开始。
    """
    import dataclasses
    from core.occ import OCC_SYSTEM_PROMPT, parse_occ_response, occ_to_plutchik, apply_personality_modifiers
    from agents.base_agent import fast_call

    prompt = (
        f"人物性格：{', '.join(profile.personality_traits)}\n"
        f"核心价值观：{', '.join(profile.core_values)}\n"
        f"认知偏差：{', '.join(profile.cognitive_biases)}\n"
        f"当前感知：{profile.current_situation}。身体状态：{profile.current_physical_state}\n"
        f"当前情绪基线：{{\"anger\": 0.0, \"fear\": 0.0, \"joy\": 0.0, \"sadness\": 0.0, \"surprise\": 0.0, \"disgust\": 0.0, \"anticipation\": 0.0, \"trust\": 0.0, \"intensity\": 0.0}}"
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


# ── 主入口 ─────────────────────────────────────────────────────────────────────

def main(profile_path: str, max_ticks_override: int | None = None):
    global MAX_TICKS
    if max_ticks_override is not None:
        MAX_TICKS = max_ticks_override
    profile = load_profile(profile_path)
    # 初始化记忆管理器并加载历史记忆
    memory = MemoryManager()
    memory.load_from_profile(profile.memories)

    # 初始化叙事线索管理器
    narrative_path = _resolve_narrative_state_path(profile_path)
    thread_mgr = NarrativeThreadManager(state_path=narrative_path)

    world = WorldEngine(
        profile,
        threshold=INTENSITY_THRESHOLD,
        calm_interval=CALM_INTERVAL,
        dramatic_cooldown=DRAMATIC_COOLDOWN,
        event_history_window=EVENT_HISTORY_WINDOW,
        rel_appear_threshold=REL_APPEAR_THRESHOLD,
        rel_appear_slope=REL_APPEAR_SLOPE,
        thread_mgr=thread_mgr,
    )
    state = ThoughtState(text="", emotion=EmotionState(), tick=0)
    event = ""
    writeback_mgr = WritebackManager(profile)

    # 输出文件路径
    safe_name = profile.name.replace(" ", "_")
    idx = _next_output_index(f"run_{safe_name}")
    run_id = f"run_{safe_name}_{idx:02d}"
    txt_path  = f"output/{run_id}.txt"
    json_path = f"output/{run_id}.json"
    viz_path  = f"output/{run_id}_viz.txt"
    viz_dir   = f"output/{run_id}_viz"  # 每 tick 一个 JSON 文件

    print(f"\n🧠 ANIMA — {profile.name}")
    print(f"记忆系统模式：{memory.mode}")
    print(f"处境：{profile.current_situation}")
    print(f"身体状态：{profile.current_physical_state}\n")
    print(f"输出文件：{txt_path}\n")

    tick_records = []
    tick_store = TickHistoryStore(profile_name=profile.name)
    prev_tick_outputs: dict = {}  # 跨轮传递，供多模块影响机制使用

    # ── 情绪初始播种（tick 1 前用 current_physical_state 种入初始情绪）──────────
    state = _seed_initial_emotion(profile, state)

    with open(txt_path, "w", encoding="utf-8") as f_txt:
        # 写入 header
        header = (
            f"[MemoryManager] 使用 {'CAMEL LongtermAgentMemory ✓' if memory.mode == 'camel' else 'fallback 简单记忆'}\n\n"
            f"🧠 ANIMA — {profile.name}\n"
            f"记忆系统模式：{memory.mode}\n"
            f"处境：{profile.current_situation}\n"
            f"身体状态：{profile.current_physical_state}\n\n"
        )
        f_txt.write(header)

        for tick in range(1, MAX_TICKS + 1):
            # 线索urgency自动递增（每轮+0.05）
            thread_mgr.tick_urgency()
            top = thread_mgr.get_top_thread(current_tick=tick)
            thread_summary = thread_mgr.summary_line()

            print_divider(tick, event, state.emotion.intensity, state.emotion.dominant(), memory.mode)
            print(f"  线索：{thread_summary}")

            bar = "█" * int(state.emotion.intensity * 20) + "░" * (20 - int(state.emotion.intensity * 20))
            event_str = f"事件：{event}" if event else "（无新事件）"
            f_txt.write(f"\n{'─'*62}\n")
            f_txt.write(f"  轮次 {tick:02d}  |  [{bar}] {state.emotion.intensity:.2f}  |  {state.emotion.dominant()}  |  mem:{memory.mode}\n")
            f_txt.write(f"  线索：{thread_summary}\n")
            f_txt.write(f"  {event_str}\n")
            f_txt.write(f"{'─'*62}\n")

            # 运行认知循环（非流式）
            state, behavior, module_outputs = run_cognitive_cycle(
                profile, state, memory, event, tick_store,
                prev_tick_outputs=prev_tick_outputs,
                narrative_thread=top,
            )
            prev_tick_outputs = module_outputs  # 保存供下轮影响机制使用

            # 显示行为状态
            time_loc = f"  ⏰ {behavior.wall_clock_time}  📍 {behavior.location}  {'💤' if behavior.sleep_state == 'ASLEEP' else '👁'}"
            print(time_loc)
            # 终端：带模块标签（评估用）；文件：连续无标签版本
            if module_outputs:
                print(render_all_outputs_labeled(module_outputs))
            else:
                print(state.text)
            f_txt.write(f"{time_loc}\n")
            f_txt.write(state.text)
            f_txt.flush()

            print()
            emo_dict = state.emotion.to_dict()
            emo_display = {k: round(v, 2) for k, v in emo_dict.items()}
            print(f"\n  [情绪] {json.dumps(emo_display, ensure_ascii=False)}")
            f_txt.write(f"\n\n  [情绪] {json.dumps(emo_display, ensure_ascii=False)}\n")

            # 收集本轮结构化数据
            tick_records.append({
                "tick": tick,
                "event": event,
                "wall_clock_time": behavior.wall_clock_time,
                "location": behavior.location,
                "sleep_state": behavior.sleep_state,
                "perceived": state.perceived,
                "memory_fragment": state.memory_fragment,
                "reasoning": state.reasoning,
                "thought": state.text,
                "emotion": {k: v for k, v in emo_dict.items() if k != "intensity"},
                "intensity": state.emotion.intensity,
                "dominant": state.emotion.dominant(),
                "active_thread": top["description"] if top else None,
            })

            event = world.tick(state, behavior)

            # B2 结论立刻传给线索管理器（关闭/新建线索）
            if state.conclusion:
                thread_mgr.process_action(state.conclusion, current_tick=tick)

            thread_mgr.save()  # 持久化线索状态

            writeback_mgr.add_candidate(tick, state.conclusion)
            writeback_mgr.maybe_flush(tick)

            # ── 写 viz JSON（每 tick 实时落盘，前端可轮询）──────────────────────
            try:
                viz_data = render_for_viz(tick, event, behavior, state.emotion, module_outputs)
                viz_json_path = write_tick_viz(run_id, tick, viz_data)
                print(f"  [viz] tick_{tick:02d}.json → {viz_json_path}")
            except Exception as e:
                print(f"  [viz] 写入失败（tick {tick}）：{e}")

            if tick < MAX_TICKS:
                time.sleep(2)  # 轮次间隔 2s

    # ── 写出 JSON ──────────────────────────────────────────────────────────
    run_meta = {
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
        "profile_name": profile.name,
        "profile_age": profile.age,
        "current_situation": profile.current_situation,
        "current_physical_state": profile.current_physical_state,
        "personality_traits": profile.personality_traits,
        "cognitive_biases": profile.cognitive_biases,
        "memory_mode": memory.mode,
        "max_ticks": MAX_TICKS,
        "ticks": tick_records,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(run_meta, f, ensure_ascii=False, indent=2)
    print(f"\n✅ JSON 数据已写出：{json_path}")

    # ── 写出 VIZ ───────────────────────────────────────────────────────────
    viz_text = generate_visualization(profile, tick_records, memory.mode, run_id)
    with open(viz_path, "w", encoding="utf-8") as f:
        f.write(viz_text)
    print(f"✅ 可视化报告已写出：{viz_path}")

    # 打印 VIZ 到终端
    print(viz_text)

    # ── 认知残差写回 Profile ────────────────────────────────────────────────
    ResidualFeedback(profile_path).analyze_and_update(tick_store._jsonl_path)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="ANIMA — 意识流认知模拟")
    parser.add_argument("profile", nargs="?", default="examples/demo_profile.json",
                        help="profile JSON 路径（默认：examples/demo_profile.json）")
    parser.add_argument("--max-ticks", type=int, default=None,
                        help=f"最多运行几个 tick（默认：{MAX_TICKS}）")
    args = parser.parse_args()
    main(args.profile, max_ticks_override=args.max_ticks)

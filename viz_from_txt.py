"""
viz_from_txt.py — 从已有 run 输出文本重新生成可视化报告。
用法：python viz_from_txt.py output/run_linxiaoyu_01.txt
"""
import re
import sys
import json
import os

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(__file__))

import config
from core.profile import PersonProfile

EMOTIONS_ZH = {
    "anger": "愤怒", "fear": "恐惧", "joy": "喜悦", "sadness": "悲伤",
    "surprise": "惊讶", "disgust": "厌恶", "anticipation": "期待", "trust": "信任",
}

def _bar(value: float, width: int = 20) -> str:
    filled = int(value * width)
    return "█" * filled + "░" * (width - filled)


def parse_txt(path: str) -> tuple[dict, list]:
    """从文本输出解析 profile 摘要和 tick_records。"""
    DIVIDER = chr(0x2500) * 20  # ─{20}

    with open(path, encoding="utf-8") as f:
        content = f.read()

    # 解析 header
    name_m = re.search(r"ANIMA — (.+)", content)
    situation_m = re.search(r"处境：(.+)", content)
    physical_m = re.search(r"身体状态：(.+)", content)
    mem_mode_m = re.search(r"记忆系统模式：(\S+)", content)

    meta = {
        "name": name_m.group(1).strip() if name_m else "未知",
        "situation": situation_m.group(1).strip() if situation_m else "",
        "physical": physical_m.group(1).strip() if physical_m else "",
        "mem_mode": mem_mode_m.group(1).strip() if mem_mode_m else "?",
    }

    # 用 chr(0x2500){20,} 分割
    blocks = re.split(chr(0x2500) + r"{20,}", content)

    records = []
    i = 0
    while i < len(blocks):
        block = blocks[i]
        # 查找轮次头行：格式 "轮次 01  |  [bar] 0.00  |  anger  |  mem:camel"
        tick_m  = re.search(r"轮次\s+(\d+)", block)
        intens_m = re.search(r"\]\s*([\d.]+)", block)
        domin_m = re.search(r"]\s*[\d.]+\s*\|\s*(\w+)", block)
        if tick_m and intens_m and domin_m:
            tick = int(tick_m.group(1))
            intensity = float(intens_m.group(1))
            dominant = domin_m.group(1)

            event_m = re.search(r"事件：(.+)", block)
            event = event_m.group(1).strip() if event_m else ""

            # 思维流在下一块
            thought_block = blocks[i + 1] if i + 1 < len(blocks) else ""

            # 从思维块中抓情绪 JSON
            emotion_m = re.search(r'\[情绪\]\s*(\{.+?\})', thought_block, re.DOTALL)
            emotion = {}
            if emotion_m:
                try:
                    raw = json.loads(emotion_m.group(1))
                    raw.pop("intensity", None)
                    emotion = raw
                    intensity = sum(v**2 for v in emotion.values()) ** 0.5
                except Exception:
                    pass

            # 提取思维文本（去掉情绪行）
            thought = re.sub(r'\s*\[情绪\].+', '', thought_block).strip()

            records.append({
                "tick": tick,
                "event": event,
                "perceived": "",
                "memory_fragment": "",
                "reasoning": "",
                "thought": thought,
                "emotion": emotion,
                "intensity": intensity,
                "dominant": dominant,
            })
            i += 2
        else:
            i += 1

    return meta, records


def generate_visualization(meta: dict, records: list) -> str:
    W = 68
    SEP = "═" * W
    sep = "─" * W
    lines = []

    run_id = os.path.basename(sys.argv[1]).replace(".txt", "")

    lines += [
        "",
        SEP,
        f"  ANIMA 可视化报告  |  {run_id}",
        SEP,
        f"  角色：{meta['name']}",
        f"  处境：{meta['situation']}",
        f"  身体：{meta['physical']}",
        f"  记忆模式：{meta['mem_mode']}  |  共 {len(records)} 轮",
        SEP,
    ]

    # 情绪弧线
    lines += ["", "  ── 情绪弧线（全程）──", ""]
    header = "  维度      " + "".join(f"  {r['tick']:02d} " for r in records)
    lines.append(header)
    lines.append("  " + "─" * (len(header) - 2))

    for emo_key, emo_zh in EMOTIONS_ZH.items():
        values = [r["emotion"].get(emo_key, 0.0) for r in records]
        row = f"  {emo_zh}{'　' * (4 - len(emo_zh))}"
        for v in values:
            block = "▓" if v > 0.5 else ("▒" if v > 0.2 else ("░" if v > 0.05 else "·"))
            row += f"  {block}{v:.2f}"
        lines.append(row)

    lines.append("")
    intensity_row = "  强度      "
    for r in records:
        intensity_row += f"  {r['intensity']:.2f}"
    lines.append(intensity_row)

    # 情绪强度时间轴
    lines += ["", "  ── 情绪强度走势 ──", ""]
    for r in records:
        bar = _bar(r["intensity"], 30)
        lines.append(f"  轮{r['tick']:02d} [{bar}] {r['intensity']:.2f}  {r['dominant']}")

    # 环境时间线
    lines += ["", sep, "  ── 环境时间线 ──", ""]
    timeline = "  "
    for r in records:
        if r["event"]:
            timeline += f"[{r['tick']:02d}★]─"
        else:
            timeline += f"[{r['tick']:02d}]──"
    lines.append(timeline)
    lines.append("")

    for r in records:
        if r["event"]:
            lines.append(f"  轮次 {r['tick']:02d} ★ 【环境事件】{r['event']}")

    # 逐轮详情
    lines += ["", sep, "  ── 逐轮详情 ──"]

    for r in records:
        tick = r["tick"]
        emo = r["emotion"]
        dominant = r["dominant"]
        intensity = r["intensity"]

        lines += [
            "",
            f"  ╔══ 轮次 {tick:02d} {'═' * (W - 11)}",
            f"  ║",
            f"  ║  环境事件：{'【' + r['event'] + '】' if r['event'] else '（无）'}",
        ]

        emo_parts = [
            f"{EMOTIONS_ZH[k]}={v:.2f}"
            for k, v in emo.items()
            if k in EMOTIONS_ZH and v > 0.05
        ]
        emo_str = " | ".join(emo_parts) if emo_parts else "平静（所有维度 ≈ 0）"
        lines += [
            f"  ║  情绪快照：{emo_str}",
            f"  ║  强度走势：[{_bar(intensity, 24)}] {intensity:.2f}  主导：{dominant}",
            f"  ║",
            f"  ║  ── 思维流 ──",
        ]

        thought = r.get("thought", "")
        for seg in thought.split("\n"):
            seg = seg.strip()
            if seg:
                lines.append(f"  ║  {seg}")
            else:
                lines.append(f"  ║")

        lines.append(f"  ╚{'═' * (W - 2)}")

    # 统计
    lines += ["", SEP, "  ── 统计摘要 ──", ""]
    events_count = sum(1 for r in records if r["event"])
    if records:
        peak = max(records, key=lambda r: r["intensity"])
        lines += [
            f"  总轮次：{len(records)}  |  环境事件触发：{events_count} 次",
            f"  情绪峰值：轮次 {peak['tick']:02d}  强度 {peak['intensity']:.2f}（{peak['dominant']}）",
        ]
        all_emo = {k: sum(r["emotion"].get(k, 0) for r in records) for k in EMOTIONS_ZH}
        avg_dominant = max(EMOTIONS_ZH.keys(), key=lambda k: all_emo[k])
        total = sum(all_emo.values())
        if total > 0:
            lines.append(f"  全程主导情绪：{EMOTIONS_ZH[avg_dominant]}（{avg_dominant}）  累计强度 {all_emo[avg_dominant]:.2f}")
        else:
            lines.append("  注：本次运行情绪向量全程为 0（情绪解析 bug，已在代码中修复）")

    lines += ["", SEP, ""]
    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print("用法：python viz_from_txt.py output/run_xxx.txt")
        sys.exit(1)

    txt_path = sys.argv[1]
    meta, records = parse_txt(txt_path)

    print(f"解析完成：{len(records)} 轮记录，角色：{meta['name']}")

    viz = generate_visualization(meta, records)

    out_path = txt_path.replace(".txt", "_viz.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(viz)

    print(f"✅ 可视化报告已写出：{out_path}")
    print(viz)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
ui/viz/scripts/txt_to_viz.py — 历史 txt 文件 → viz JSON 转换器

用法：
  python3 txt_to_viz.py output/run_林晓雨_13.txt
  python3 txt_to_viz.py output/run_林晓雨_13.txt --out output/run_林晓雨_13_viz/

输出：output/{run_id}_viz/tick_01.json, tick_02.json, ...

类型检测（启发式，基于文本特征）：
  - name说，「content」 或 「content」（source）→ voice_intrusion
  - 〔content〕                                → unsymbolized
  - len ≤ 20 字                               → compressed_speech
  - 包含身体部位词                             → body_sensation
  - len ≥ 80 字                               → expanded_speech
  - 其余                                       → visual_fragment
"""

import argparse
import json
import os
import re
import sys

# 身体部位词（用于 body_sensation 检测）
_BODY_WORDS = {
    "手", "脚", "胸", "喉", "眼", "心", "脖", "肩", "腿", "腰",
    "背", "腹", "头", "脸", "颧", "睫", "泪", "鼻", "耳", "指",
    "掌", "臂", "膝", "踝", "臀", "脊", "肘", "腕", "皮肤",
}

_BODY_PATTERN = re.compile("|".join(_BODY_WORDS))


def detect_type(line: str) -> str:
    """启发式判断一行文本的 DES 类型。"""
    stripped = line.strip()

    # voice_intrusion：旧格式 "「...」"（source）或新格式 name说，「...」
    if re.match(r'.+说，「', stripped):
        return "voice_intrusion"
    if re.match(r'[""「]', stripped) and re.search(r'[」""][（(]', stripped):
        return "voice_intrusion"
    # unsymbolized：〔〕包裹
    if stripped.startswith("〔") and stripped.endswith("〕"):
        return "unsymbolized"
    # body_sensation：含身体部位词且句子较短
    if _BODY_PATTERN.search(stripped) and len(stripped) < 80:
        return "body_sensation"
    # compressed_speech：极短片段
    if len(stripped) <= 20:
        return "compressed_speech"
    # expanded_speech：很长的内心独白
    if len(stripped) >= 80:
        return "expanded_speech"
    return "visual_fragment"


def transform_line(line: str, mtype: str) -> tuple[str, str | None]:
    """
    返回 (display_text, source)。
    voice_intrusion 提取 source；unsymbolized 去掉〔〕。
    """
    stripped = line.strip()

    if mtype == "voice_intrusion":
        # 新格式：name说，「content」
        m = re.match(r'^(.+?)说，「(.+?)」', stripped)
        if m:
            return f"{m.group(1)}说，「{m.group(2)}」", m.group(1)
        # 旧格式："「content」"（source）或 "「content」"（source，其他）
        m = re.match(r'[""「](.+?)[」""]\s*[（(](.+?)[）)]', stripped)
        if m:
            content = m.group(1).strip('「」')  # 去掉可能嵌套的「」
            source_full = m.group(2)
            name = source_full.split("，")[0].split(",")[0].strip()
            return f"{name}说，「{content}」" if name else f"「{content}」", name or None
        return stripped, None

    if mtype == "unsymbolized":
        # 去掉〔〕
        display = re.sub(r"^〔|〕$", "", stripped).strip()
        return display, None

    return stripped, None


def parse_tick_block(block_lines: list[str], tick_meta: dict) -> dict:
    """
    将一个 tick 的内容行列表解析为 viz dict。
    """
    moments = []
    moment_id = 0

    # 合并多行内容（以 …… 分隔，空行跳过）
    content_lines = []
    for line in block_lines:
        stripped = line.strip()
        if not stripped or stripped == "……" or stripped.startswith("──────"):
            continue
        if stripped.startswith("[情绪]"):
            continue
        if stripped.startswith("⏰") or stripped.startswith("  ⏰"):
            continue
        content_lines.append(stripped)

    for raw_line in content_lines:
        mtype = detect_type(raw_line)
        display_text, source = transform_line(raw_line, mtype)
        if not display_text:
            continue
        moments.append({
            "id": moment_id,
            "type": mtype,
            "display_text": display_text,
            "source": source,
            "module": "unknown",  # txt 格式不保留模块信息
        })
        moment_id += 1

    return {
        "tick": tick_meta["tick"],
        "event": tick_meta.get("event", ""),
        "time": tick_meta.get("time", ""),
        "location": tick_meta.get("location", ""),
        "sleep_state": tick_meta.get("sleep_state", "AWAKE"),
        "emotion": tick_meta.get("emotion", {"dominant": "unknown", "intensity": 0.0}),
        "moments": moments,
    }


def parse_txt(path: str) -> list[dict]:
    """解析 run_*.txt，返回每个 tick 的 viz dict 列表。"""
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    ticks: list[dict] = []
    current_meta: dict | None = None
    current_lines: list[str] = []
    divider_re = re.compile(r"^[\s─]+$")
    tick_header_re = re.compile(r"轮次\s+(\d+)\s+\|")
    thread_re = re.compile(r"线索：")
    event_re = re.compile(r"事件：(.+)")
    no_event_re = re.compile(r"（无新事件）")
    time_loc_re = re.compile(r"⏰\s+([^\s]+)\s+📍\s+(.+?)\s+[👁💤]")
    emotion_re = re.compile(r"\[情绪\]\s+(\{.*\})")
    sleep_re = re.compile(r"（睡眠中）")

    def flush():
        nonlocal current_meta, current_lines
        if current_meta:
            viz = parse_tick_block(current_lines, current_meta)
            ticks.append(viz)
        current_meta = None
        current_lines = []

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # 检测 tick 标题行
        m = tick_header_re.search(stripped)
        if m:
            flush()
            tick_num = int(m.group(1))
            current_meta = {
                "tick": tick_num,
                "event": "",
                "time": "",
                "location": "",
                "sleep_state": "AWAKE",
                "emotion": {"dominant": "unknown", "intensity": 0.0},
            }
            i += 1
            continue

        if current_meta is None:
            i += 1
            continue

        # 线索行：跳过
        if thread_re.search(stripped):
            i += 1
            continue

        # 事件行
        m_event = event_re.search(stripped)
        if m_event:
            current_meta["event"] = m_event.group(1).strip()
            i += 1
            continue
        if no_event_re.search(stripped):
            current_meta["event"] = ""
            i += 1
            continue

        # 时间/地点行
        m_tl = time_loc_re.search(stripped)
        if m_tl:
            current_meta["time"] = m_tl.group(1).strip()
            current_meta["location"] = m_tl.group(2).strip()
            if "💤" in line:
                current_meta["sleep_state"] = "ASLEEP"
            i += 1
            continue

        # 情绪行
        m_emo = emotion_re.search(stripped)
        if m_emo:
            try:
                emo_raw = json.loads(m_emo.group(1))
                intensity = emo_raw.pop("intensity", 0.0)
                dominant = max(
                    (k for k in emo_raw if k != "intensity"),
                    key=lambda k: emo_raw.get(k, 0.0),
                    default="unknown"
                )
                current_meta["emotion"] = {
                    "dominant": dominant,
                    "intensity": round(intensity, 3),
                    **{k: round(v, 3) for k, v in emo_raw.items()},
                }
            except Exception:
                pass
            i += 1
            continue

        # 分隔线：跳过
        if divider_re.match(stripped) or stripped == "":
            i += 1
            continue

        # 内容行
        current_lines.append(stripped)
        i += 1

    flush()
    return ticks


def main():
    parser = argparse.ArgumentParser(description="Convert run_*.txt to viz JSON files")
    parser.add_argument("txt_path", help="Path to run_*.txt file")
    parser.add_argument("--out", default=None, help="Output directory (default: auto-derived)")
    args = parser.parse_args()

    if not os.path.exists(args.txt_path):
        print(f"Error: {args.txt_path} not found", file=sys.stderr)
        sys.exit(1)

    # 推断 run_id 和输出目录
    basename = os.path.basename(args.txt_path)
    run_id = basename.replace(".txt", "")
    if args.out:
        out_dir = args.out
    else:
        parent = os.path.dirname(args.txt_path) or "output"
        out_dir = os.path.join(parent, f"{run_id}_viz")

    os.makedirs(out_dir, exist_ok=True)

    print(f"解析：{args.txt_path}")
    ticks = parse_txt(args.txt_path)
    print(f"共解析 {len(ticks)} 个 tick")

    for viz in ticks:
        tick_num = viz["tick"]
        out_path = os.path.join(out_dir, f"tick_{tick_num:02d}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(viz, f, ensure_ascii=False, indent=2)
        print(f"  → {out_path}（{len(viz['moments'])} moments）")

    print(f"\n✅ 输出目录：{out_dir}")
    print(f"启动预览：python3 -m http.server 8000 （项目根目录）")
    print(f"然后访问：http://localhost:8000/ui/viz/index.html?run={run_id}")


if __name__ == "__main__":
    main()

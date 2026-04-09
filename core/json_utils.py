"""
core/json_utils.py — LLM 输出 JSON 解析工具。

LLM 经常输出带代码块包裹、格式不标准的 JSON。
这里提供统一的容错解析逻辑，支持 json_repair fallback。
"""

from __future__ import annotations
import json
import re


def parse_json_object(raw: str) -> dict | None:
    """从 LLM 输出中提取单个 JSON 对象，支持 json_repair 容错。"""
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


def parse_json_moments(raw: str) -> list[dict]:
    """从 LLM 输出中提取 moments 列表，支持 json_repair 容错。"""
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

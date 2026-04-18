"""
core/display_utils.py — 终端/文本显示工具函数。
"""


def intensity_bar(value: float, width: int = 20) -> str:
    """情绪强度可视化条：█ 填充 + ░ 空白。"""
    filled = int(value * width)
    return "█" * filled + "░" * (width - filled)

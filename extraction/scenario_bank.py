"""
extraction/scenario_bank.py — 情境题库

设计原则：
  不问"你是什么样的人"，而是呈现具体的两难情境，
  通过强迫选择采集行为指纹，映射到 PersonProfile 字段。

题目维度：
  self_suppression   自我压抑程度（→ core_values / personality_traits）
  approval_need      外部认可需求（→ cognitive_biases）
  conflict_style     冲突处理方式（→ personality_traits）
  intimacy_pattern   亲密关系模式（→ relationships / cognitive_biases）
  failure_response   失败后的认知反应（→ cognitive_biases）
  boundary_setting   边界设定能力（→ core_values / personality_traits）
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class ScenarioOption:
    label: str                        # "A" / "B" / "C"
    text: str                         # 选项文本
    maps_to: Dict[str, Any]           # 映射到 PersonProfile 的哪个字段


@dataclass
class Scenario:
    id: str
    dimension: str                    # 题目所属维度
    scenario: str                     # 情境描述
    options: List[ScenarioOption]
    follow_up: str = ""               # 可选：追问文本（用于 interviewer）


# ── 核心题库（Phase 3 时扩充至 50~100 题）─────────────────────────────────────

SCENARIO_BANK: List[Scenario] = [

    # ── 自我压抑维度 ──────────────────────────────────────────────────────────
    Scenario(
        id="self_suppression_01",
        dimension="self_suppression",
        scenario="你帮一个朋友做了很多事，但他从来没主动问过你好不好。",
        options=[
            ScenarioOption("A", "继续帮，不提",
                           {"core_values": "不能给别人添麻烦", "weight": 0.8}),
            ScenarioOption("B", "委婉说出来",
                           {"personality_traits": "能表达边界", "weight": 0.6}),
            ScenarioOption("C", "慢慢疏远",
                           {"cognitive_biases": "回避冲突", "weight": 0.7}),
        ],
        follow_up="你选择这样做的时候，心里有没有一刻想过另一种做法？",
    ),

    Scenario(
        id="self_suppression_02",
        dimension="self_suppression",
        scenario="你很累，但一个朋友突然发消息说他/她需要倾诉。",
        options=[
            ScenarioOption("A", "放下自己的事，立刻回应",
                           {"core_values": "坚强是一种礼貌", "weight": 0.75}),
            ScenarioOption("B", "说'我现在有点累，稍后可以吗'",
                           {"personality_traits": "能设定边界", "weight": 0.6}),
            ScenarioOption("C", "看了消息，但没有立刻回",
                           {"cognitive_biases": "情感逃避", "weight": 0.5}),
        ],
    ),

    # ── 外部认可需求 ──────────────────────────────────────────────────────────
    Scenario(
        id="approval_need_01",
        dimension="approval_need",
        scenario="你做了一件很好的事，但没有人知道，也不会有人知道。",
        options=[
            ScenarioOption("A", "内心满足，无所谓",
                           {"personality_traits": "内驱型", "weight": 0.7}),
            ScenarioOption("B", "有点空，希望有人发现",
                           {"cognitive_biases": "需要外部认可", "weight": 0.75}),
            ScenarioOption("C", "会想办法让人'顺便'知道",
                           {"cognitive_biases": "需要外部认可", "weight": 0.9}),
        ],
        follow_up="你觉得这种感觉是从什么时候开始有的？",
    ),

    # ── 失败响应维度 ──────────────────────────────────────────────────────────
    Scenario(
        id="failure_response_01",
        dimension="failure_response",
        scenario="你精心准备的东西被当众否定了。",
        options=[
            ScenarioOption("A", "第一反应是：我哪里出了问题",
                           {"cognitive_biases": "过度自责", "weight": 0.85}),
            ScenarioOption("B", "第一反应是：他不懂",
                           {"cognitive_biases": "外部归因", "weight": 0.6}),
            ScenarioOption("C", "第一反应是：想消失",
                           {"cognitive_biases": "灾难化思维", "weight": 0.9}),
        ],
    ),

    Scenario(
        id="failure_response_02",
        dimension="failure_response",
        scenario="事情搞砸了，你一个人待着。脑子里转的第一句话是什么？",
        options=[
            ScenarioOption("A", "'我下次一定要……'",
                           {"core_values": "努力一定有回报", "weight": 0.7}),
            ScenarioOption("B", "'都怪我……'",
                           {"cognitive_biases": "过度自责", "weight": 0.85}),
            ScenarioOption("C", "'算了'",
                           {"personality_traits": "习惯独自承受", "weight": 0.75}),
        ],
        follow_up="这句'算了'之后，你通常会做什么？",
    ),

    # ── 亲密关系模式 ──────────────────────────────────────────────────────────
    Scenario(
        id="intimacy_01",
        dimension="intimacy_pattern",
        scenario="你很难受，但身边有人可以倾诉。你会：",
        options=[
            ScenarioOption("A", "主动说",
                           {"personality_traits": "能寻求支持", "weight": 0.6}),
            ScenarioOption("B", "等对方问",
                           {"cognitive_biases": "需要被主动关心", "weight": 0.7}),
            ScenarioOption("C", "不说，假装没事",
                           {"personality_traits": "习惯独自承受", "weight": 0.85}),
        ],
        follow_up="如果对方没有问，你会有什么感受？",
    ),
]


def get_by_dimension(dimension: str) -> List[Scenario]:
    return [s for s in SCENARIO_BANK if s.dimension == dimension]


def get_all() -> List[Scenario]:
    return SCENARIO_BANK

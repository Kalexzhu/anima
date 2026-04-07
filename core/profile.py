"""
PersonProfile — 人物档案 Schema。
这是系统的全部输入：性格、价值观、过往经历、当前状态、关系图谱。
"""

import random
from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class Relationship:
    """
    重要他人节点。
    valence: -1.0（恐惧/回避）~ +1.0（依恋/渴望）
    power_dynamic: 描述权力关系格局
    unresolved_conflicts: 尚未和解的矛盾，会在高强度情绪时浮现
    typical_phrases: 这个人说过的、会在内心响起的典型话语
    """
    name: str
    role: str                                         # "母亲" / "前男友" / "直属领导"
    valence: float = 0.0
    power_dynamic: str = ""                           # "权威型" / "平等型" / "依赖型"
    unresolved_conflicts: List[str] = field(default_factory=list)
    typical_phrases: List[str] = field(default_factory=list)
    speech_style: str = ""                            # 这个人说话的方式（1句话）

    @classmethod
    def from_dict(cls, d: dict) -> "Relationship":
        return cls(
            name=d.get("name", ""),
            role=d.get("role", d.get("relation", "")),
            valence=float(d.get("valence", 0.0)),
            power_dynamic=d.get("power_dynamic", d.get("dynamic", "")),
            unresolved_conflicts=d.get("unresolved_conflicts", []),
            typical_phrases=d.get("typical_phrases", []),
            speech_style=d.get("speech_style", ""),
        )

    def to_prompt_line(self) -> str:
        sign = "+" if self.valence >= 0 else ""
        line = f"{self.name}（{self.role}，情感倾向{sign}{self.valence:.1f}，{self.power_dynamic}）"
        if self.unresolved_conflicts:
            line += f" | 未解冲突：{self.unresolved_conflicts[0]}"
        if self.speech_style:
            line += f" | 说话方式：{self.speech_style}"
        return line


@dataclass
class PersonProfile:
    # ── 基础身份 ──────────────────────────────────────────
    name: str                          # 人物名称（可以是虚构的）
    age: int = 0
    background: str = ""               # 一段话描述人物背景

    # ── 性格与价值观 ──────────────────────────────────────
    personality_traits: List[str] = field(default_factory=list)
    # 例：["内向", "完美主义", "高度共情", "不善拒绝"]

    core_values: List[str] = field(default_factory=list)
    # 例：["家庭高于一切", "诚实是底线", "不能示弱"]

    cognitive_biases: List[str] = field(default_factory=list)
    # 例：["灾难化思维", "过度自责", "非黑即白"]

    # ── 过往经历（作为记忆图谱的原始素材）───────────────
    memories: List[Dict[str, Any]] = field(default_factory=list)
    # 格式：[{"event": "...", "age": 12, "emotion_tag": "fear", "importance": 0.9}]

    # ── 当前状态 ──────────────────────────────────────────
    current_situation: str = ""
    # 例："刚刚收到裁员通知，正在回家的地铁上"

    current_physical_state: str = ""
    # 例："三天没睡好，胃不舒服"

    # ── 时间轴与作息（v3 新增）────────────────────────────
    home_location: str = ""
    work_location: str = ""
    scenario_start_time: str = ""      # ISO 格式，e.g. "2024-03-15T15:00:00"
    tick_duration_hours: float = 2.0   # 每轮 tick 对应的真实时长（小时）
    typical_schedule: List[Dict[str, Any]] = field(default_factory=list)
    emotion_schedule_correction: Dict[str, Any] = field(default_factory=dict)

    # ── 欲望与兴趣（v3 新增，arbiter Direction B 内容来源）─
    hobbies: List[str] = field(default_factory=list)
    desires: List[str] = field(default_factory=list)

    # ── 关系图谱（重要他人，影响认知的声音来源）──────────
    relationships: List[Dict[str, Any]] = field(default_factory=list)

    # ── 多模块认知架构字段（v5 新增，缺失时优雅降级）─────
    daydream_anchors: List[str] = field(default_factory=list)
    # 例：["有一天能在自己的工作室画画，不受打扰", "一杯好咖啡，阳光从窗户斜进来"]

    philosophy_seeds: List[str] = field(default_factory=list)
    # 例：["努力到底有没有意义", "认可是人真正需要的东西吗"]

    aesthetic_sensitivities: List[str] = field(default_factory=list)
    # 例：["线条的细腻感，墨线很细", "等间距排列产生的节奏感"]

    imagery_seeds: List[str] = field(default_factory=list)
    # 意识边缘自发浮现的感知触发点：日常物件、感官残留、身体记忆等碎片
    # 例：["地铁换乘通道荧光灯打在地面的条纹", "开水烫到手指后的迟钝感"]

    counterfactual_nodes: List[str] = field(default_factory=list)
    # 例：["如果当初没有接这个项目", "如果分手前说了那句话"]

    self_eval_patterns: List[str] = field(default_factory=list)
    # 例：["在权威评价下立刻自我否定", "用完美主义保护自己不被真正失败"]

    social_pending: List[Dict[str, Any]] = field(default_factory=list)
    # 例：[{"person": "张明", "unresolved": "他昨晚的消息还没回"}]

    rumination_anchors: List[str] = field(default_factory=list)
    # 例：["「跟你在一起我喘不过气」", "「这个方案完全跑偏了」"]

    # ── 认知指纹三维度（v6 新增，驱动角色差异化）─────
    inner_voice_style: str = ""
    # 内心语言方式：人称、句式、断句方式
    # 例："内心独白在自我否定时切换为第二人称，情绪激动时句子断在动词上"

    somatic_anchors: str = ""
    # 情绪的身体着陆点
    # 例："胸口（发紧）和手指（发凉、微颤）"

    cognitive_default: str = ""
    # 压力下的认知默认模式
    # 例："反复回放对方最后那句话的语气和表情，或去做一件可控的小事"

    output_language: str = "zh"
    # "zh"（默认）或 "en"：控制 DES moment content 的输出语言

    # self_model 已删除（2026-03-27）：
    #   known_patterns 与 self_eval_patterns 冗余；
    #   open_questions 合并入 philosophy_seeds（保留第一人称内省题）

    def to_cognitive_fingerprint(self) -> str:
        """合并认知指纹三维度为紧凑文本块，注入 drift 模块 prompt。

        当前：全量输出（~80字）。
        未来扩展点：可接收 module_name 参数，按模块筛选相关子集。
        """
        parts = []
        if self.inner_voice_style:
            parts.append(self.inner_voice_style)
        if self.somatic_anchors:
            parts.append(f"身体感知集中在{self.somatic_anchors}")
        if self.cognitive_default:
            parts.append(self.cognitive_default)
        if not parts:
            return ""
        return "认知特征：" + "。".join(parts)

    @property
    def relationship_objects(self) -> List[Relationship]:
        """将 dict 格式关系列表转为 Relationship 对象列表。"""
        return [
            r if isinstance(r, Relationship) else Relationship.from_dict(r)
            for r in self.relationships
        ]

    def to_prompt_context(self, memory_override: list | None = None) -> str:
        """将档案序列化为 LLM 可读的提示词上下文。

        memory_override: 由 run_cognitive_cycle 统一预采样后传入，
                         保证同一 tick 内所有调用看到相同记忆组合。
                         若为 None 则退回本地 5+3 随机采样（兼容测试等独立调用场景）。
        """
        lines = [
            f"人物：{self.name}，{self.age}岁",
            f"背景：{self.background}",
            f"性格特质：{', '.join(self.personality_traits)}",
            f"核心价值观：{', '.join(self.core_values)}",
            f"认知偏差（思维惯性）：{', '.join(self.cognitive_biases)}",
            f"当前处境：{self.current_situation}",
            f"身体状态：{self.current_physical_state}",
        ]
        rel_objs = self.relationship_objects
        if rel_objs:
            lines.append("重要关系网络：")
            for r in rel_objs:
                lines.append(f"  · {r.to_prompt_line()}")
                if r.typical_phrases:
                    phrases = "、".join(f'"{p}"' for p in r.typical_phrases[:3])
                    lines.append(f"    常说：{phrases}")
        if memory_override is not None:
            selected = memory_override
        elif self.memories:
            sorted_mems = sorted(self.memories, key=lambda m: -m.get("importance", 0))
            top_5 = sorted_mems[:5]
            remaining = sorted_mems[5:]
            random_3 = random.sample(remaining, min(3, len(remaining)))
            selected = top_5 + random_3
        else:
            selected = []

        if selected:
            mem_lines = [
                f"  - [{m.get('age','?')}岁] {m['event']}（情绪标签：{m.get('emotion_tag','')}）"
                for m in selected
            ]
            lines.append("关键记忆：\n" + "\n".join(mem_lines))
        fingerprint = self.to_cognitive_fingerprint()
        if fingerprint:
            lines.append(fingerprint)
        return "\n".join(lines)

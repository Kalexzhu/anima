# ANIMA — 系统架构文档

## 项目定位（已更新）

**认知数字分身（Cognitive Digital Twin）**

> 给定足够的关于一个人的信息，构建其认知模型，使其能在任意情境下生成真实的思维过程。

不是"读心术"（捕捉某一刻的状态），而是**构建这个人的认知运行时**——
一个可以在任何情境下被触发、持续运转的数字分身。

---

## 系统全景

```
┌─────────────────────────────────────────────────────────────────┐
│                    LAYER 0 · 数据输入层                          │
│                                                                   │
│  情境选择题（主路径）  │  原始文本  │  聊天记录（可选）           │
│  强迫性两难选择        │  日记/自述  │  微信导出                  │
│  → 行为指纹采集        │  → 语义提取 │  → 行为模式挖掘            │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                 LAYER 1 · Profile 提取引擎                       │
│                    extraction/                                    │
│                                                                   │
│  ScenarioBank          Interviewer         TextExtractor          │
│  情境题库              对话式访谈           文本语义提取            │
│  (强迫选择→字段映射)   (追问→补全空缺)      (模式识别→偏差检测)    │
│                          │                                        │
│                    ProfileBuilder                                 │
│                    合成器：字段置信度评分 + 矛盾标注               │
└────────────────────────────┬────────────────────────────────────┘
                             │ PersonProfile（带置信度）
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                 LAYER 2 · 认知引擎（核心）                       │
│                    core/                                          │
│                                                                   │
│   感知层 Perception      注意力过滤，决定"注意到什么"             │
│        ↓                                                          │
│   情绪层 Emotion         8维Plutchik向量更新                      │
│        ↓                                                          │
│   记忆层 Memory          CAMEL LongtermAgentMemory 语义检索       │
│        ↓                                                          │
│   推理层 Reasoning       认知偏差介入的内心逻辑推演               │
│        ↓                                                          │
│   仲裁层 Arbiter         整合所有层，流式输出意识流               │
│                                                                   │
│   ← ThoughtState 在各层流动，携带：                              │
│     text / emotion(8D) / perceived / memory / reasoning          │
└──────────┬──────────────────────────────────────┬───────────────┘
           │ ThoughtState                          │ ThoughtState
           ▼                                       ▼
┌──────────────────────┐              ┌────────────────────────────┐
│  LAYER 3 · 世界引擎  │              │  LAYER 3 · 分身运行时       │
│  core/world_engine   │              │  twin/                      │
│                      │              │                             │
│  情绪阈值触发机制:    │              │  CognitiveTwin              │
│  intensity > 0.45    │              │  · 持久化 PersonProfile     │
│  → dramatic 事件     │              │  · 跨 session 记忆积累      │
│  平静≥3轮            │              │  · 任意情境模拟接口          │
│  → subtle 事件       │              │  · 多情境并发对比            │
└──────────┬───────────┘              └────────────────────────────┘
           │ event
           └──────────────────────────→ 回注认知引擎（闭环）
```

---

## 三大子系统详细设计

### LAYER 1 · Profile 提取引擎

**核心问题**：人没有能力直接描述自己的认知模式，
但人有能力在具体情境里做选择，这些选择的模式就是认知指纹。

#### 数据流

```
输入源（任选其一或组合）
    ↓
Input Normalizer（格式标准化）
    ↓
多维度提取器（并行）
  ├── FactExtractor：显性事实（年龄/职业/家庭）
  ├── EventExtractor：生命事件 + 情绪标签 + 重要度
  ├── PatternExtractor：语言习惯 + 反应模式
  ├── ValueExtractor：在冲突情境中坚守什么
  └── BiasDetector：如何解读模糊情境
    ↓
ProfileBuilder（合成 + 标注置信度）
    ↓
PersonProfile JSON
  └── 每字段带 _confidence: high/medium/low
  └── 每字段带 _evidence: [来源句子列表]
```

#### 情境题设计原则（ScenarioBank）

不问"你是什么样的人"，呈现具体两难：

```json
{
  "id": "boundary_01",
  "scenario": "你帮一个朋友做了很多事，但他从来没主动问过你好不好。",
  "options": [
    {"label": "A", "text": "继续帮，不提", "maps_to": {"core_values": "不能给别人添麻烦", "weight": 0.8}},
    {"label": "B", "text": "委婉说出来", "maps_to": {"personality_traits": "能表达边界", "weight": 0.6}},
    {"label": "C", "text": "慢慢疏远", "maps_to": {"cognitive_biases": "回避冲突", "weight": 0.7}}
  ],
  "dimension": "self_suppression"
}
```

---

### LAYER 2 · 认知引擎

**现状（v3 已实现）**：六层架构（Layer 0 行为预测 + 原五层）。

#### 六层数据流（v3）

```
event（外部事件，可为空）
    ↓
behavior_layer(profile, tick, emotion)  ← Layer 0（新增）
    → BehaviorState {location, activity, sleep_state, wall_clock_time}
    ↓
[ASLEEP?] → _dream_arbiter → ThoughtState  ← 简化睡眠循环
[AWAKE?] ↓
perception_layer(profile, event, state, behavior)
    → perceived: str（≤60字，注意焦点）
    ↓
emotion_layer(profile, perceived, state)
    → EmotionState（OCC六维评价 → Plutchik 8D → 认知偏差修正 → 情绪惯性平滑）
    ↓
passive_decay × 0.7（无条件，每轮）
    ↓
memory_layer(memory_manager, perceived, emotion)
    → mem_fragment: str（语义检索，top-3）
    ↓
reasoning_layer(profile, perceived, emotion, memory, behavior)
    → reasoning: str（≤80字，认知偏差介入的内心推演）
    ↓
arbiter_layer(...)  ← 非流式，Direction B
    → full_thought（100~200字，事件/记忆/欲望为主，情绪调色）
    ↓
ThoughtState {text, emotion, tick, last_event, perceived, memory_fragment, reasoning}
```

#### Direction B：arbiter 内容规则

- **主要内容** = 脑子里在想的具体事物（某人/某件事/欲望/记忆画面）
- **情绪** = 只影响语气和用词，不是话题本身
- **禁止** = "我好难受""我真的很痛苦"等情绪陈述作为主体

#### 睡眠状态机

```
AWAKE ──睡眠时段──→ ASLEEP
  ↑                     ↓
  └──醒来时段←──────────┘

ASLEEP 时：behavior_layer 判定 → _dream_arbiter → 情绪衰退继续
AWAKE 时：完整六层循环
```

#### 关键参数（v3）

| 参数 | 当前值 | 含义 |
|------|--------|------|
| MAX_TICKS | 40 | 每次运行轮次 |
| tick_duration_hours | 2.0 | 每轮 = 2 小时真实时间 |
| PASSIVE_DECAY | 0.7 | 情绪被动衰退/轮（约3轮减半） |
| INTENSITY_THRESHOLD | 0.45 | 触发 dramatic 事件阈值 |
| CALM_INTERVAL | 3 | 触发 subtle 事件间隔（轮） |
| 轮次间 sleep | 2s | 防限流 |

---

### LAYER 3 · 世界引擎

**触发逻辑**（已实现）：

```python
if intensity > 0.45:        # 情绪激烈 → dramatic 事件
    mode = "dramatic"
elif ticks_since_event >= 3: # 平静太久 → subtle 事件
    mode = "subtle"
else:
    return ""               # 世界沉默
```

**两种事件风格**：
- `dramatic`：突然、有冲击力、直击人物最敏感点
- `subtle`：细小但意味深长，悄悄推动故事

---

### LAYER 3 · 数字分身运行时（待建）

**目标**：让 PersonProfile 成为可持久化、可复用的认知模型

```python
# 设想接口
twin = CognitiveTwin.load("profiles/linxiaoyu.json")

# 在任意情境下运行
result = twin.simulate(
    situation="刚刚收到录取通知",
    physical_state="激动，手有点抖",
    ticks=5
)

# 跨情境对比
twin.compare_scenarios([
    "收到表扬后独自走在路上",
    "被朋友误解后独自走在路上",
])
```

---

## 技术栈

| 层 | 技术 |
|----|------|
| LLM 快速层 | qwen3-max（DashScope OpenAI 兼容接口） |
| LLM 降级层 | Anthropic Claude（Sonnet 4.6，fallback） |
| 记忆系统 | 简单情绪编码检索（CAMEL 暂不依赖） |
| 情绪模型 | Plutchik 情绪轮（8维）+ OCC 六维评价模型 |
| 输出模式 | fast_call 非流式（arbiter 层） |
| 持久化 | JSON（Profile）+ jsonl（tick history / event history） |

---

## 目录结构

```
mind-reading/
├── config.py                 # .env 加载（force override）
├── run.py                    # 认知引擎主入口
├── viz_from_txt.py           # 离线可视化工具
│
├── core/                     # 认知引擎
│   ├── profile.py            # PersonProfile schema
│   ├── emotion.py            # EmotionState（8D Plutchik）
│   ├── thought.py            # ThoughtState（含中间层数据）
│   ├── memory.py             # MemoryManager（CAMEL）
│   ├── cognitive_engine.py   # 五层认知循环
│   └── world_engine.py       # 世界事件生成引擎
│
├── agents/                   # LLM agent 工厂
│   └── base_agent.py         # CAMEL ChatAgent + Anthropic 直连兜底
│
├── extraction/               # Profile 提取引擎【待建】
│   ├── scenario_bank.py      # 情境题库（强迫选择→字段映射）
│   ├── interviewer.py        # 对话式AI访谈
│   ├── text_extractor.py     # 原始文本语义提取
│   └── profile_builder.py    # Profile 合成器（置信度评分）
│
├── twin/                     # 数字分身运行时【待建】
│   ├── twin.py               # CognitiveTwin 主类
│   ├── scenario_runner.py    # 任意情境模拟
│   └── twin_store.py         # 分身持久化
│
├── examples/
│   ├── demo_profile.json     # 林晓雨（手写）
│   └── scenarios/            # 情境题示例【待建】
│
├── output/                   # 所有生成文件
└── docs/
    ├── arch.md               # 本文档
    └── profile-field-rules.md  # Profile 字段收录规则（准入条件 + 字段边界）
```

---

## 开发优先级

```
Phase 1（当前）：打通认知引擎闭环
  ✅ 五层认知架构
  ✅ 世界引擎（情绪阈值触发）
  ✅ 可视化输出（txt + json + viz）
  ⬜ 情绪向量 bug 验证修复
  ⬜ API 调用优化（减少每轮次数，合并 perception+emotion）

Phase 2：数字分身运行时
  ⬜ CognitiveTwin 持久化封装
  ⬜ 任意情境模拟接口
  ⬜ 跨情境对比功能

Phase 3：Profile 提取引擎
  ⬜ 情境题库设计（50~100题）
  ⬜ 对话式访谈（AI 主导问答）
  ⬜ 文本提取（日记/自述）
  ⬜ 可选：聊天记录解析

Phase 4：产品化
  ⬜ Web 界面
  ⬜ 用户隐私边界设计
  ⬜ 历史人物 / 剧本角色内容包
```

---

## 已决策记录

| 决策 | 结论 | 原因 |
|------|------|------|
| 架构定位 | 认知数字分身，不是读心术 | 分身可复用、可迭代，价值更高 |
| 情绪模型 | Plutchik 8维 + L2范数 | 维度独立，intensity 直接可用 |
| 事件触发 | 情绪阈值 + calm_interval | 避免固定节拍，产生自然戏剧性 |
| 艺术 vs 科学 | 偏艺术，不追求科学精确 | 先做震撼体验，参数后调 |
| 输入方式 | 情境题为主路径 | 比表格有温度，比开放问题可答 |
| 数据流向 | 分析用户自身认知，不分析他人 | 隐私边界清晰 |
| **第一版场景** | **艺术/实验装置：喋喋不休的数字角色** | 纯艺术定位，不追求实用性，先跑通体验 |
| 输出载体 | 屏幕头像 + 口型同步视频流 | 情绪结果实时驱动视觉输出 |
| 视频生成策略 | 非实时、无限流，10分钟延迟缓冲 | 认知引擎与视频生成解耦，各自独立运转 |
| CAMEL 记忆 | LongtermAgentMemory（camel mode）| 语义检索质量高 |
| proxy 兼容 | 禁用 CAMEL ChatAgent，走 Anthropic 直连 | yunjintao 不支持 count_tokens |
| 情绪标定精度目标 | Level 2（相对强度排序正确）| 绝对数值精度无科学标准，方向+强度排序可验证 |
| 情绪标定词典 | DUTIR 中文情感词汇本体库（27,466词）| 中文直接匹配，无需翻译层，维度与 Plutchik 高度重合 |
| 标定约束策略 | 软约束：词典提供候选集合，LLM 方向优先 | 词义歧义问题（"背叛+信任"）导致词典不能做硬性方向断言 |
| 统计修正机制 | 同类事件 ≥20 条后统计 prior 覆盖词典约束 | 无人工干预，冷启动期词典兜底，数据积累后自动收敛 |
| 标定数据存储 | output/event_emotion_log.jsonl（append-only）| 轻量，支持离线分析，不依赖数据库 |

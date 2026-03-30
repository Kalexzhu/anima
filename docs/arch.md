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

**当前版本（v5，已实现）**：10 模块并发架构。

#### 数据流（v5）

```
event（外部事件，可为空）+ profile + emotion + prev_tick_outputs
    ↓
behavior_layer(profile, tick, emotion)
    → BehaviorState {location, activity, sleep_state, wall_clock_time}
    ↓
[ASLEEP?] → 静默输出"（睡眠中）"，情绪继续衰减
[AWAKE?]  ↓

ThreadPoolExecutor（max_workers=6）并发运行 10 个认知模块：
  ┌─ ReactiveModule（情绪反应式，B1 锚点选择 + B2 时刻链生成）
  ├─ DriftModule × 9（各自独立 LLM 调用）：
  │   emotion_drift   · 情绪惯性漂移
  │   memory_surface  · 无意识记忆浮现
  │   voice_intrusion · 他人声音侵入
  │   imagery         · 意象碎片（视觉画面）
  │   philosophy      · 哲学沉思
  │   daydream        · 白日梦/另一种可能
  │   counterfactual  · 反事实假设（如果当时…）
  │   rumination      · 反刍思维
  │   self_eval       · 自我评价
  └─ （drift_sampler 按情绪状态采样 2~3 个 DriftModule 运行）
    ↓
cognitive_engine 整合 module_outputs
    → 合并 DES moments（7类：compressed_speech/visual_fragment/
      unsymbolized/body_sensation/intrusion/voice_intrusion/expanded_speech）
    → 提取 reactive._conclusion → WritebackManager
    → 更新 ThoughtState.text（连续意识流）
    ↓
OCC emotion_layer（fast_call，事件+感知→8D Plutchik 向量）
    → EmotionState（惯性衰减 × 0.4/轮）
    ↓
ThoughtState {text, emotion, tick, perceived, memory_fragment, reasoning, conclusion}
```

#### 关键参数（v5）

| 参数 | 当前值 | 含义 |
|------|--------|------|
| MAX_TICKS | 20 | 每次运行轮次 |
| tick_duration_hours | 2.0 | 每轮 = 2 小时真实时间 |
| EMOTION_DECAY | 0.4 | 情绪惯性衰减/轮 |
| INTENSITY_THRESHOLD | 0.45 | 触发 dramatic 事件阈值 |
| CALM_INTERVAL | 3 | 触发 subtle 事件间隔（轮）|
| _MODULE_TIMEOUT_S | 90 | 单模块最长等待（超时跳过）|
| 轮次间 sleep | 2s | 防限流 |

#### 睡眠状态机

```
AWAKE ──睡眠时段──→ ASLEEP
  ↑                     ↓
  └──醒来时段←──────────┘

ASLEEP 时：behavior_layer 判定 → 静默输出 → 情绪衰退继续
AWAKE 时：10 模块并发循环
```

---

### LAYER 3 · 世界引擎 + WorldState 主干情境系统

**WorldState（Phase A，已实现）**：

人物有 2~4 个长期悬而未决的主干情境（Trunk），每个属于一个独立生命域（work / romance / family / identity / friendship / health / finance / home）。Trunk 驱动外部事件和内部漂移认知，是比"叙事线索"更深层的心理基底。

```
WorldState (output/world_state.json)
  ├── Trunk × 2~4（各属不同域，强制正交）
  │     ├── title：一句话情境标题
  │     ├── description：具体未解决的处境
  │     ├── domain：生命域（work/romance/family/identity...）
  │     ├── phase：developing / critical / resolving
  │     └── urgency：0~1（每轮自然衰减 + 叙事时间归一化）
  │
  └── get_trunk_context(emotion, tick)
        → Softmax + Recency Penalty 概率选择
        → 返回 context_str："当前主干情境[domain]：title——description"
```

**Trunk 选择算法**（防 Winner-Take-All 垄断）：

```
base_score = f(phase, urgency, emotion_resonance)
recency_penalty = exp(-ticks_since_activated / 4.0)
adjusted = base_score × (1 - 0.75 × recency_penalty)

→ Softmax(adjusted / 0.25)  # temperature=0.25
→ random.choices(trunks, weights=probs)  # 概率选择，非贪心
```

**Trunk → 认知闭环**（Phase A.5，已实现）：

```
get_trunk_context() → active_trunk_context
    ├── WorldEngine.tick()            外部事件（领域一致性）
    └── ModuleContext.active_trunk_context
          ├── rumination.get_anchor()   [强接入] Trunk 优先
          ├── self_eval.get_anchor()    [强接入] Trunk 优先
          ├── philosophy.get_anchor()   [强接入] Trunk 优先
          └── future.get_anchor()       [中接入] Trunk + desire 组合
```

同一 tick，外部事件与内省漂移共享同一个 Trunk 锚点，产生领域内聚的认知输出。

**WorldEngine 触发逻辑**：

```python
# 睡眠时不推进外部叙事
if behavior.sleep_state == "ASLEEP":
    return ""

if intensity > 0.45:        # 情绪激烈 → dramatic 事件
    mode = "dramatic"
elif ticks_since_event >= 3: # 平静太久 → subtle 事件
    mode = "subtle"
else:
    return ""
```

**两种事件风格**：
- `dramatic`：突然、有冲击力、直击当前 Trunk 最敏感点
- `subtle`：细小但意味深长，悄悄推动 Trunk 内部进展

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
| LLM 核心层 | Anthropic Claude Sonnet 4.6（ReactiveModule/DriftModule/WorldEngine/Writeback）|
| LLM 快速层 | qwen3-max via DashScope OpenAI 兼容接口（OCC 情绪计算/Behavior 行为推断）|
| 记忆系统 | MemoryManager 简单情绪编码检索（CAMEL LongtermAgentMemory 可选，需配置）|
| 情绪模型 | Plutchik 8维向量，intensity = RMS（均方根），OCC 认知评估模型驱动 |
| 并发 | ThreadPoolExecutor（max_workers=6）并发调度 10 个认知模块 |
| 持久化 | JSON（Profile + narrative_state）+ jsonl（tick_history / event_history）|
| 可视化 | p5.js 浏览器端，每 tick 写 viz JSON，支持实时轮询和历史回放 |

---

## 目录结构

```
anima/
├── config.py                 # .env 加载（force override）
├── run.py                    # 主入口（林晓雨等通用 profile）
├── viz_from_txt.py           # 离线 txt → viz JSON 工具
│
├── core/                     # 认知引擎
│   ├── profile.py            # PersonProfile schema（含 output_language 等 v5 字段）
│   ├── emotion.py            # EmotionState（8D Plutchik + RMS intensity）
│   ├── thought.py            # ThoughtState（各层中间数据）
│   ├── memory.py             # MemoryManager（简单检索 + CAMEL 可选）
│   ├── cognitive_engine.py   # 编排层（11模块并发 + 情绪更新 + 输出渲染）
│   ├── world_engine.py       # 世界事件生成（情绪阈值触发 + Trunk 驱动）
│   ├── world_state.py        # WorldState 主干情境系统（Trunk tree）
│   ├── occ.py                # OCC 情绪评估模型
│   ├── narrative.py          # NarrativeThreadManager（叙事线索）
│   ├── viz_renderer.py       # viz JSON 生成（每 tick）
│   ├── residual_feedback.py  # 认知残差自动写回 profile
│   ├── writeback.py          # B2 结论批量写回 memories
│   └── cognitive_modules/    # 11 个并发认知模块
│       ├── base.py           # CognitiveModule 基类 + ModuleContext
│       ├── runner.py         # ModuleRunner（ThreadPoolExecutor）
│       ├── reactive.py       # ReactiveModule（B1锚点 + B2时刻链）
│       └── drift.py          # DriftModule × 10（各类漂移内容）
│
├── agents/                   # LLM 调用工厂
│   └── base_agent.py         # 双层路由（claude_call 主力 / fast_call 快速层）
│                             # + Key 轮转池 + output_language 旁路
│
├── extraction/               # Profile 提取引擎【待建】
│   ├── scenario_bank.py      # 情境题库（强迫选择→字段映射）
│   └── profile_builder.py    # Profile 合成器
│
├── twin/                     # 数字分身运行时【骨架】
│   └── twin.py               # CognitiveTwin 主类（未完成）
│
├── scenarios/                # 特定人物场景
│   └── kobe_2020/            # 科比场景（含 timeline.json + runner.py）
│
├── examples/                 # 示例人物档案
│   ├── demo_profile.json     # 林晓雨
│   └── demo_narrative_state.json
│
├── tests/                    # 单元测试
├── ui/viz/                   # p5.js 浏览器端可视化
├── sample_outputs/           # 开源展示用示例输出
├── output/                   # 运行时生成文件（gitignore）
└── docs/
    ├── arch.md               # 本文档
    └── profile-field-rules.md
```

---

## 开发优先级

```
Phase 1（已完成）：认知引擎闭环 ✅
  ✅ 10 模块并发认知架构（v5）
  ✅ OCC 情绪模型 + Plutchik 8D + 惯性衰减
  ✅ 叙事线索系统（NarrativeThreadManager）
  ✅ 世界引擎（情绪阈值触发 + 关系登场）
  ✅ 可视化输出（txt + json + p5.js viz 实时漂浮）
  ✅ 情绪初始播种（tick 1 前 OCC 种入）
  ✅ 两套示例人物档案（林晓雨 + 科比·布莱恩特）
  ✅ 断点续跑 + 原子写入
  ✅ ModuleRunner 超时保护
  ✅ ResidualFeedback 停用词表（修复关系检测误报）

Phase 2（进行中）：数字生命 · 实时感知 + 具身输出
  构建顺序：A → B → C → D

  Phase A：WorldEngine 迭代（长跑质量）
    ✅ WorldState 主干情境系统（Trunk tree，2~4 个生命域）
    ✅ Softmax + Recency Penalty Trunk 选择算法（防 Winner-Take-All 垄断）
    ✅ Trunk 域正交约束（VALID_DOMAINS 8个域，同域去重）
    ✅ ASLEEP 状态事件抑制（睡眠时 WorldEngine 静默）
    ✅ Trunk → drift 层横向接入（rumination/self_eval/philosophy/future 强/中接入）

    Phase A 精修（设计文档：iterations/2026-03-30-phase-a-polish-design.md）
    优先级：D1 → B1 → A1 → B3 → C1 → A2 → C2 → A3 → B2 → C3

    第一批（单文件微调）：
    ✅ D1  Trunk 写入日志（run.py 1行，txt 可观察性）
    ✅ B1  睡眠衰减率（_SLEEP_DECAY=0.95，睡眠时每小时衰减 5%）
    ✅ A1  事件记忆注入（禁止重复约束 + Trunk 域提示，core/world_engine.py）

    第二批（跨文件但逻辑独立）：
    ✅ B3  清晨情绪特征（ASLEEP→AWAKE 切换时 fear/sadness 轻微上调）
    ✅ C1  Urgency 双向运动（未激活 Trunk 缓慢发酵上涨，resolving 加速衰减）
    ✅ A2  正向事件类型（joy/trust/anticipation 触发，细小喘息型事件）

    第三批（需要新字段/新机制）：
    ✅ C2  认知疲劳强制切换（consecutive_activation 连续计数惩罚）
    ✅ A3  事件因果性链（action_history 注入 WorldEngine，防重复驱动）
    ✅ C3  Trunk 间渗透（secondary_trunk_context 注入 drift anchor）

    第四批（最复杂）：
    ✅ B2  情绪积压-释放机制（suppression_pressure 积累 → release 事件触发）

    Phase A 测试反馈修复（run_05 评估后）：
    ✅ 梦境接入（ASLEEP tick 调用 _dream_arbiter，fast_call 轻量生成梦境碎片）
    ✅ voice_intrusion 跨模块去重（ModuleContext.recent_voice_contents 注入去重约束）
    ✅ C2 强制冷却期（consecutive >= 4 强制跳过该 Trunk，兜底：全部冷却时解除）
    ✅ OCC 自适应惯性（adaptive_decay = 0.4~0.65，随情绪强度线性增大，防单事件扭转高峰情绪）

  Phase B：音频感知输入
    ⬜ audio/stt_listener.py（Whisper 本地流式，Mac M 系列）
    ⬜ audio/salience_filter.py（显著性评分：定向性/情绪触点/新颖性）
    ⬜ audio/event_queue.py（线程安全队列 + drain 接口）

  Phase C：双循环集成
    ⬜ run.py 改造（从 EventQueue drain，WorldEngine 降为 idle generator）
    ⬜ 双模运行支持（--realtime 真实感知 / 默认虚构事件）

  Phase D：具身输出
    ⬜ TTS 接入（内心独白文本 → 语音）
    ⬜ 对口型视频输出

Phase 3（暂缓）：
  ⬜ 问卷系统：通过填写问卷自动生成心理档案
  ⬜ 英文 persona 完整支持
  ⬜ CognitiveTwin 持久化封装（跨情境对比接口）
  ⬜ Profile 提取引擎（情境题库 + 对话访谈 + 文本提取）
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
| **Phase A 方向** | **WorldState 主干情境系统（Trunk tree）** | 以生命域具体处境（非心理元主题）作为认知基底，驱动事件和内省 |
| Trunk 选择算法 | Softmax + Recency Penalty（temperature=0.25，halflife=4，weight=0.75） | 概率选择防垄断；Recency Penalty 强制领域轮转，模拟认知"换气" |
| drift 接入策略 | 分级接入（强/中/不接入），10模块中4个接入 | 内省型模块（philosophy/self_eval/rumination/future）与外部事件共享 Trunk 锚点；享乐/感知型模块不接入 |
| 实时感知延迟 | 单 tick 5 分钟以内可接受 | 不是回复机器人，自有节奏，长延迟是特性 |
| TTS 定位 | 纯视觉化载体，念出内心独白，不模拟行为 | 最简形式创造最强在场感，行为模拟暂不在范围 |
| 双循环架构 | Fast Loop（STT）+ Slow Loop（认知引擎），EventQueue 做桥 | 两个时间尺度（秒 vs 分钟）不兼容，必须解耦；WorldEngine 降为 idle generator |
| Phase A 优先 | 先迭代 WorldEngine 事件质量，再接入真实感知 | 感知输入槽位已存在，先拉高基线；技术风险最高的在前 |
| Phase A 精修 | 10项改动分4批，优先级：可观察性→情绪→事件→Trunk系统→复杂机制 | 改动小+收益大在前，架构复杂在后；设计文档已归档至 iterations/ |
| ASLEEP 梦境 | 每个睡眠 tick 调用 _dream_arbiter（fast_call，qwen3-max）| 连续静默 tick 失去观察价值；梦境碎片化特征与睡眠 DES 学术研究一致 |
| voice_intrusion 去重 | ModuleContext.recent_voice_contents 跨模块注入禁止重复约束 | 同一声音在同一 tick 多模块重复破坏沉浸感；约束在 prompt 层实现，零架构成本 |
| C2 强制冷却 | consecutive >= 4 强制排除候选（兜底：全冷却时解除限制）| 渐进惩罚在绝对强势 Trunk 面前失效；强制冷却保证最多 4 轮后强制领域轮转 |
| OCC 自适应惯性 | adaptive_decay = 0.4 + 0.25 × min(1, intensity/0.5)，上限 0.65 | 高峰情绪（intensity > 0.4）被单一正向事件扭转不符合心理真实；随强度线性增大抵抗 |

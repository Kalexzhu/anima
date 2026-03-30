# Phase A 精修设计文档

## 背景

Phase A（WorldState 主干情境系统）核心机制已完成并通过 10-tick 验证。
本文档记录 10 项精修方向的设计决策，供实现时参考。

---

## 分组总览

```
Group A · 事件系统          Group B · 情绪系统
  A1  事件记忆注入              B1  睡眠衰减率
  A2  正向事件类型              B2  情绪积压-释放
  A3  事件因果性链              B3  清晨情绪特征

Group C · Trunk 系统        Group D · 可观察性
  C1  Urgency 双向运动          D1  Trunk 写入日志
  C2  认知疲劳强制切换
  C3  Trunk 间渗透

优先级：D1 → B1 → A1 → B3 → C1 → A2 → C2 → A3 → B2 → C3
（改动小+收益大在前，架构复杂在后）
```

---

## Group D · 可观察性

### D1 · Trunk 写入日志

**问题**：txt 日志只显示叙事线索（NarrativeThreadManager），无法直接看到每轮激活的是哪个 Trunk，导致人工评估需要事后翻 world_state.json。

**实现**：`run.py` 写入 txt 文件时加一行。

```python
# run.py，在 f_txt.write(thread_summary) 附近
trunk_line = f"  主干：{world_state.summary_line()}\n"
f_txt.write(trunk_line)
```

**影响文件**：`run.py`（1 行）

**测试**：目视检查 txt 输出

---

## Group B · 情绪系统

### B1 · 睡眠衰减率

**问题**：`_PASSIVE_DECAY = 0.7`（per 小时），每轮 2 小时 → `0.7² = 0.49`。
连续 4 tick 睡眠（8 小时）→ `0.7⁸ = 0.057`，几乎归零。
现实中人醒来时往往还带着昨天的情绪底色。

**设计**：

```
AWAKE：decay_factor = _PASSIVE_DECAY ** tick_duration_hours   （现有逻辑，不变）
ASLEEP：decay_factor = _SLEEP_DECAY ** tick_duration_hours    （新增，更缓慢）

_PASSIVE_DECAY = 0.7   # 清醒时每小时衰减 30%
_SLEEP_DECAY   = 0.95  # 睡眠时每小时衰减 5%（8小时后保留 ~66%）
```

**实现**：`core/cognitive_engine.py`，在计算 `_decay_factor` 处读取 behavior.sleep_state。

```python
# 修改 run_cognitive_cycle() 内
is_asleep = behavior and behavior.sleep_state == "ASLEEP"
_decay_base = _SLEEP_DECAY if is_asleep else _PASSIVE_DECAY
_decay_factor = _decay_base ** (tick_duration_hours or 1.0)
```

**影响文件**：`core/cognitive_engine.py`（~5 行），新增常量 `_SLEEP_DECAY`

**副作用**：睡醒后第一 tick 的情绪强度会偏高，更接近现实。需要在验证中确认不导致事件过于密集。

---

### B2 · 情绪积压-释放机制

**问题**：情绪只有衰减，没有积压。现实中长期压抑的情绪会累积，到临界点需要释放（林晓雨档案："厕所里哭完补妆"）。

**设计**：

```
suppression_pressure（0~1）：每轮在情绪高但 behavior 显示压抑时 +delta
                             情绪自然表达时 -delta
                             超过阈值 0.8 → 触发一次 "release" 事件

压抑条件：sadness/fear > 0.4 AND (behavior.activity 包含"压抑"关键词 OR 人物性格包含"情绪抑制")
表达条件：reactive 模块输出包含 expanded_speech
```

```
┌──────────────────────────────────────────────────────┐
│  每 tick                                              │
│  if (情绪高 AND 行为压抑):  pressure += 0.08          │
│  elif (情绪自然表达):       pressure -= 0.15          │
│  else:                      pressure += 0.01（缓慢积累）│
│                                                       │
│  if pressure > 0.8:                                   │
│    → WorldEngine 触发 "release" 类型事件               │
│    → pressure 重置为 0.2                              │
└──────────────────────────────────────────────────────┘
```

**实现**：
- `core/thought.py`：ThoughtState 新增 `suppression_pressure: float = 0.0`
- `core/cognitive_engine.py`：每轮更新 pressure 值
- `core/world_engine.py`：新增 `release` 事件模式

**影响文件**：3 个文件，中等复杂度

**注意**：`release` 事件不一定是哭泣，可以是：独自笑出来、给朋友发了一条很长的消息、突然很饿、睡得很死。由 profile 的 cognitive_biases 和当前 Trunk 决定方向。

---

### B3 · 清晨情绪特征

**问题**：ASLEEP→AWAKE 切换后第一 tick 直接进入正常清醒状态，但现实中清晨醒来往往是焦虑最高点（意识未完全在线，昨天的事情已经压上来）。

**设计**：

```python
# core/cognitive_engine.py，AWAKE 路径开头
def _is_morning_wakeup(behavior, prev_behavior):
    """检测是否为睡眠后第一个清醒 tick"""
    return (behavior.sleep_state == "AWAKE"
            and prev_behavior is not None
            and prev_behavior.sleep_state == "ASLEEP")

if _is_morning_wakeup(behavior, prev_behavior):
    # 在 decayed emotion 基础上轻微上调 fear/sadness
    wakeup_boost = {"fear": 0.08, "sadness": 0.05}
    new_emotion = new_emotion.add_delta(wakeup_boost)
```

**实现**：需要 `run_cognitive_cycle` 接收上一 tick 的 behavior state（或简单地在 run.py 传一个 `prev_sleep_state` 参数）

**影响文件**：`core/cognitive_engine.py` + `run.py`（~10 行）

---

## Group A · 事件系统

### A1 · 事件记忆注入

**问题**：WorldEngine 的事件生成虽然有 `event_history`，但注入 prompt 的只有近 3 条事件文本，没有明确要求"禁止重复已发生的事"。run_04 里陈总出现了 4 次。

**设计**：改进事件历史注入的 prompt 措辞，从"参考以下已发生事件"改为显式去重约束：

```python
# world_engine.py，_build_event_prompt() 内
if self._event_history:
    recent = self._event_history[-5:]
    history_str = "；".join(recent)
    history_section = (
        f"\n\n【已发生事件（禁止重复相同人物、地点、对话内容）】\n{history_str}"
    )
```

同时增加 Trunk 域约束，让事件更贴合当前主干而非随机散射：

```python
# 在 prompt 里加入 Trunk domain 提示
if trunk_context:
    domain_hint = f"\n当前认知主干：{trunk_context}\n事件应与此主干所在域（工作/感情/家庭等）有关联，或形成对比。"
```

**影响文件**：`core/world_engine.py`（~10 行改动）

---

### A2 · 正向事件类型

**问题**：所有事件都是压力源（dramatic = 冲击，subtle = 暗示问题）。真实生活里有正向微小时刻。

**设计**：新增 `positive` 事件模式，由 joy/trust/anticipation 维度触发。

```
触发条件：
  NOT (intensity > threshold)           # 不在情绪激烈时
  AND ticks_since_event >= 3            # 已平静足够久
  AND (joy + trust + anticipation) > 0.2  # 有正向情绪残余

positive 事件风格：
  - 细小、不戏剧化
  - 来自外部环境或非核心关系（路人、天气、物件）
  - 不解决 Trunk 问题，只是短暂的"喘息"
  - 允许触发 daydream / positive_memory 模块
```

```python
# world_engine.py tick() 方法
elif (ticks_since_event >= self.calm_interval
      and pos_score > 0.2):
    return self._generate_event(state, "positive", behavior=behavior)
```

**影响文件**：`core/world_engine.py`（新增 `_generate_positive_event` 方法，~30 行）

---

### A3 · 事件因果性链

**问题**：林晓雨在 tick 4 回复了陈总的邮件，tick 6 的事件生成不知道这件事发生了，可能又生成一个"陈总发邮件"。

**根本原因**：`event_history` 记录的是事件文本，不是"角色做了什么决定"。

**设计**：

```
数据流：
  ThoughtState.conclusion（B2 结论）→ WritebackManager 存入 memories
                                    → 也写入 action_history（新增，轻量）

  WorldEngine 生成事件时注入 action_history 最近 2 条：
  "角色最近的行动：[回复了陈总邮件][拒绝接充电器的电话]"
  → 模型生成事件时自然避免重复驱动
```

**实现**：
- `core/world_engine.py` 接收一个 `recent_actions: list[str]` 参数
- `run.py` 从 `state.conclusion` 提取并传入

**影响文件**：`core/world_engine.py`、`run.py`（~20 行）

---

## Group C · Trunk 系统

### C1 · Urgency 双向运动

**问题**：Trunk urgency 目前只随叙事时间衰减，但真实认知里未解决的事情放着不管会越来越压迫（母亲的电话越拖越烫手）。

**设计**：

```
当前逻辑：urgency -= decay_per_tick（每轮无条件减少）

新逻辑：
  if trunk.phase in ("developing", "critical"):
    if trunk.last_activated_tick < current_tick - 3:
      # 超过 3 轮未被激活：情境在后台发酵，urgency 缓慢上涨
      urgency += 0.03 per tick（上限 1.0）
    else:
      urgency -= narrative_decay（现有逻辑）

  if trunk.phase == "resolving":
      urgency -= narrative_decay × 2   # 解决阶段加速衰减
```

```
Urgency 变化示意：
  developing Trunk（未激活）：  ──→ 缓慢上涨
  developing Trunk（激活中）：  ──→ 正常衰减
  critical Trunk：              ──→ 缓慢上涨（更快发酵）
  resolving Trunk：             ──→ 加速衰减
```

**影响文件**：`core/world_state.py`，`tick_update()` 方法（~15 行）

---

### C2 · 认知疲劳强制切换

**问题**：Recency Penalty 用 `exp(-ticks_since/4)` 抑制刚激活的 Trunk，但如果一个 Trunk urgency 很高，它仍可以连续激活很多轮，不会出现"想换换脑子"的自然切换。

**设计**：在 Recency Penalty 基础上，加"连续激活次数"额外惩罚：

```python
# world_state.py，get_trunk_context() 内

# 新增：consecutive_activation 计数（同一 Trunk 连续被选中的次数）
# 存储在 Situation 的运行时状态中（不持久化）

consecutive = self._consecutive_count.get(trunk_id, 0)
if consecutive >= 3:
    # 连续激活 3 次以上：施加"认知疲劳"惩罚
    fatigue_factor = 1.0 - min(0.6, (consecutive - 2) * 0.15)
    adjusted *= fatigue_factor

# 选出结果后：
if selected.id == self._last_selected_id:
    self._consecutive_count[selected.id] = consecutive + 1
else:
    self._consecutive_count[selected.id] = 1
    self._last_selected_id = selected.id
```

**影响文件**：`core/world_state.py`（新增 2 个运行时字段，~20 行）

**注意**：`_consecutive_count` 和 `_last_selected_id` 是运行时变量，不写入 JSON，重启后重置（合理——重启就是新的一天）。

---

### C3 · Trunk 间渗透

**问题**：工作压力渗透到对感情的解读方式（"陈总否定我" → "李杨也觉得我让人窒息"），但目前各 Trunk 完全独立运作。

**设计**：保持 Trunk 选择算法不变（不增加复杂度），在 **drift 模块 anchor 构建阶段**注入次级 Trunk 作为背景：

```python
# drift.py，FragmentModule.run() 内
# 主锚点：active_trunk_context（当前主 Trunk）
# 次背景：secondary_trunk（第二高分 Trunk 的 title）

secondary = ctx.secondary_trunk_context  # 新增字段，ModuleContext 里
if secondary:
    anchor = anchor + f"\n（背景：{secondary}）"
```

```
ModuleContext 新增字段：
  secondary_trunk_context: str = ""  # 第二高分 Trunk 的 context_str，可为空
```

**实现**：
- `core/world_state.py`：`get_trunk_context()` 同时返回 secondary Trunk context
- `core/cognitive_modules/base.py`：ModuleContext 新增 `secondary_trunk_context`
- `run.py`：接收并传入
- `drift.py`：rumination / self_eval / philosophy 的 anchor 构建时选择性注入

**影响文件**：4 个文件，但每处改动量小（各 ~5 行）

---

## 实现顺序建议

```
第一批（单文件微调，可一次提交）：
  D1 → B1 → A1

第二批（跨文件但逻辑独立）：
  B3 → C1 → A2

第三批（需要新字段/新机制）：
  C2 → A3 → C3

第四批（最复杂，需充分验证）：
  B2
```

---

## 代码健康原则

1. **新常量进 `cognitive_engine.py` 顶部或 `run.py` 顶部**，不散落在函数内
2. **新运行时状态**（如 `_consecutive_count`）放在对应类的 `__init__`，注释清楚"不持久化"
3. **每批改动后跑 `python3 -m pytest tests/ -q`**，36 tests must pass
4. **每次有实质性改动，跑一次 5-tick 快速验证**再进入下一批
5. **不在 prompt 里加可以用代码解决的规则**（CLAUDE.md 核心原则）

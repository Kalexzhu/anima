# 2026-03-30 · Phase A — WorldState 主干情境系统

## 背景

本次迭代完成 Phase A 的核心实现：为 WorldEngine 引入「主干情境」（Trunk）层，
解决长期运行时事件重复、缺乏叙事推进方向的问题。

---

## 核心问题（改之前）

| 问题 | 表现 |
|------|------|
| 事件无叙事方向 | 只有 dramatic/subtle 两种风格，缺乏「这件事在向哪里发展」的意识 |
| urgency 单调递增 | NarrativeThreadManager 每轮 +0.05，无衰退；长期运行后所有线索堆到 critical |
| 事件与人物底层张力脱节 | 生成的事件只对应当前线索，不呼应人物持续数周的心理压力 |

---

## 设计决策

### D-1：Trunk/Branch/Leaf 三层树，Branch 层不动

Trunk 是持续数月的「底层心理张力」（职业困惑、关系张力、身份危机），
来自 PersonProfile，由 LLM 一次性提取，持久化后不再重新生成。

Branch 层（NarrativeThreadManager）保持不变，WorldState 在其上层工作，
只为事件生成提供「主题骨架」和「行动方向」两个信息。

Leaf 层（日常小事，小时级）暂不实现，Phase B 后视需要添加。

### D-2：Tick 频率归一化

所有速率以「per narrative hour」定义，乘以 `tick_duration_hours` 使用，
确保 tick 频率改变时（模拟模式 2h/tick vs 实时模式 5min/tick）行为一致。

### D-3：Phase 双向转移，不单调

```
latent ←→ emerging ←→ developing ←→ critical ←→ confronting
```

urgency 上升时 phase 向前推进，urgency 自然衰退时 phase 可回退。
防止「所有情境永远处于 critical」的长期麻木问题。

### D-4：action_type 由 Branch urgency 派生（代码，不靠 LLM）

```python
urgency < 0.25  → "open"       # 轻轻触碰主题
0.25~0.55       → "complicate" # 增加障碍
0.55~0.80       → "escalate"   # 推到顶点
≥ 0.80          → "confront"   # 正面面对
```

LLM 只负责把「行动方向」翻译成一句事件文字，不再自行决定方向。

### D-5：Trunk 被事件激活时 urgency 小幅上升

每次生成的事件引用了某个 Trunk 的上下文，`mark_trunk_activated()` 被调用：
```python
trunk.urgency = min(1.0, trunk.urgency + 0.04)
```
自然衰退（0.006/h × tick_duration_hours）与激活上升形成平衡，
长期运行时 urgency 稳定在 0.3~0.6 区间，不会趋向 0 也不会堆满。

---

## 实现

### 新文件：`core/world_state.py`（~220 行）

```
Situation        主干情境 dataclass（id/title/description/phase/tags/urgency/...）
WorldState       管理器
  init_trunks()  首次运行：一次 LLM 调用提取 2~4 个 Trunk
  tick_update()  每 tick：衰退 + phase 转移
  get_trunk_context(emotion) → (trunk_id, context_str)
  get_action_directive(thread_urgency) → (action_type, hint)
  mark_trunk_activated(trunk_id, tick)
  save() / _load()
```

Tag 集合（14 个）与情绪共鸣映射表（`_TAG_EMOTION_MAP`）：
情绪共鸣分数用于在多个活跃 Trunk 中选出「当前最相关」的一个。

### 改动：`core/world_engine.py`

- `__init__` 新增 `world_state` 可选参数（无则回退旧逻辑，向后兼容）
- `_generate_thread_event`：注入 trunk_context + action_directive；事件生成后调用 mark_trunk_activated
- `_generate_open_event`：注入 trunk_context

### 改动：`run.py`

- 初始化 `WorldState(state_path="output/world_state.json")`
- 首次运行调用 `world_state.init_trunks(profile)`（续跑直接加载持久化数据）
- 每 tick 末尾：`world_state.tick_update(tick, profile.tick_duration_hours)` + `world_state.save()`
- 终端分隔栏新增「主干」摘要行

---

## 验证计划

跑 10 轮（`python3 run.py examples/demo_profile.json --max-ticks 10`），主观评估：

1. **叙事推进感**：事件是否有「这件事在发展」的方向感，而非随机散点
2. **主题一致性**：连续几轮事件是否围绕相同主干情境展开，而非每轮换话题
3. **情绪驱动**：高情绪强度时 action_type 是否正确变为 escalate/confront

---

## 未决事项

- **Trunk 提取质量**：首轮提取的 Trunk 是否准确反映人物底层张力，需人工审阅
- **Leaf 层**：日常小事（小时级，自动消失）暂未实现
- **Trunk 与 Writeback 的联动**：结论是否触发 Trunk phase 推进，记录待后续讨论

# Drift 层 × Trunk 树横向扩展（Phase A.5 实现）

## 背景

Phase A 完成后，Trunk 树已能驱动 WorldEngine 产生领域一致的外部事件（工作/感情/家庭等）。
但内省型 drift 模块仍使用 profile 静态字段（philosophy_seeds / self_eval_patterns / desires）
作为认知锚点，导致外部事件与内部漂移在同一 tick 可能指向完全不同的主干情境。

**核心问题**：人在想到某个人生主干时，不仅外部世界会响应，内省也会自然聚焦在同一件事上。

---

## 设计决策

### 接入分级

| 模块 | 接入强度 | 理由 |
|------|---------|------|
| `rumination` | 强 | 反刍天然依附于当前最沉重的主干情境（已在上一轮实现） |
| `self_eval` | 强 | 自我评估需要具体事件锚点，Trunk 比抽象 pattern 更真实 |
| `philosophy` | 强 | 哲学探讨"从具体处境出发向上抽象"，Trunk 是最好的具体处境 |
| `future` | 中 | 未来想象需要欲望驱动，但 Trunk 提供方向感；两者组合注入 |
| `daydream` | 不接入 | 享乐性发散，不应被现实主干锁定 |
| `counterfactual` | 不接入 | 有独立的反事实节点，与 Trunk 无直接关联 |
| `positive_memory` | 不接入 | 正向记忆回溯应保持独立，避免被当前压力污染 |
| `social_rehearsal` | 不接入 | 已有 social_pending 专属锚点机制 |
| `aesthetic` | 不接入 | 完全脱离情绪和情境的纯形式感知 |
| `imagery` | 不接入 | 意识边缘意象，锚点来自 perceived（感知层）更合适 |

### 锚点逻辑

```python
# self_eval / philosophy（强接入）：Trunk 优先，静态字段兜底
get_anchor=lambda ctx: (
    ctx.active_trunk_context
    or (random.choice(ctx.profile.self_eval_patterns)
        if ctx.profile.self_eval_patterns
        else "")
)

# future（中接入）：Trunk + desire 组合，两者都有时拼接
get_anchor=lambda ctx: (
    (ctx.active_trunk_context + "\n" + random.choice(ctx.profile.desires))
    if ctx.active_trunk_context and ctx.profile.desires
    else (ctx.active_trunk_context
          or (random.choice(ctx.profile.desires)
              if ctx.profile.desires
              else ctx.profile.current_situation[:30]))
)
```

---

## 实现细节

### 数据流

```
world_state.get_trunk_context(emotion, tick)
    │
    ├── → trunk_context  ──→  WorldEngine.tick()  ──→  外部事件
    │
    └── → ModuleContext.active_trunk_context
              │
              ├── rumination.get_anchor()     [强]
              ├── self_eval.get_anchor()      [强]
              ├── philosophy.get_anchor()     [强]
              └── future.get_anchor()         [中，与 desires 组合]
```

### 关键约束

- `active_trunk_context` 格式：`"当前主干情境[domain]：title——description（phase_hint）"`
- 同一 tick 内，WorldEngine 与所有 drift 模块读取的是**同一个** Trunk 实例（run.py 统一调用一次）
- 强接入模块：`active_trunk_context` 为空时（无激活 Trunk）自动降级到静态字段，不崩溃

### 修改文件

- `core/cognitive_modules/drift.py`：更新 `self_eval`、`philosophy`、`future` 的 `get_anchor`

---

## 预期效果

同一 tick 的认知输出应呈现**领域内聚性**：

**示例（Trunk = 工作领域：方案被否）**：
- 外部事件：主管在微信催进度
- rumination：胸口发紧，脑子里一遍遍复盘那个被否决的提案
- self_eval：她总是在会议室里选择沉默，然后事后懊悔
- philosophy：努力是否只是一种让自己有所依凭的幻觉？
- future：今晚回去，打开电脑，空白文档，然后呢

**对比之前**：四个模块可能分别聚焦在感情/工作/家庭/感情，认知散射。

---

## 测试结果

### 单元测试
- 36/36 通过（`python3 -m pytest tests/ -q`）

### 10-tick 集成验证（run_林晓雨_04）

**Trunk 激活分布**（world_state.json 记录）：

| Trunk | 域 | 激活次数 | 结束 urgency |
|---|---|---|---|
| 方案被否后的去留 | work | 5 | 0.61 |
| 努力还值不值得 | identity | 4 | 0.47 |
| 母亲那边的电话 | family | 5 | 0.36 |
| 分手后的相处模式 | romance | 2 | 0.34 |

4 个域全部参与，无垄断，Softmax + Recency Penalty 机制有效。

**领域内聚性验证**：
- tick 03 philosophy：*"否定的是方案，还是否定了「努力可以换来确认」这件事本身？我是谁这件事，是否根本不能靠积累来回答？"*（identity Trunk 直接触发的哲学追问）
- tick 10 philosophy：同样锚定在"努力/积累/自我认同"主题
- tick 09 social_rehearsal：*"还好吗……他就问了这三个字"*（romance Trunk 当轮激活时的感情相关内容）

**睡眠抑制验证**：tick 05–08（23:00→05:00）全程静默，无内容输出，无外部事件推进。✅

**注意**：txt 日志显示的是叙事线索（NarrativeThreadManager），看起来全程是 [work]，
但实际 Trunk 切换需从 world_state.json 反查。可观察性待改进（建议写入 txt 文件）。

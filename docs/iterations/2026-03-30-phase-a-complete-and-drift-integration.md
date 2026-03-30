# 2026-03-30 · Phase A 收尾 + Trunk 树横向扩展至 drift 层

## Phase A 最终验证（run_林晓雨_03，10 轮）

### 结果

| 维度 | 目标 | 实测 |
|---|---|---|
| Trunk 域正交 | 不同域 | work / identity / romance / family ✓ |
| 多线激活 | ≥ 2 个 Trunk 被激活 | 4/4 全部激活（3/1/1/5）✓ |
| 事件类型多样 | 工作/感情/家庭三类事件 | 均出现 ✓ |
| 睡眠期行为事件 | 无 | 仍有（修复见下）|

### 额外修复：ASLEEP 事件抑制

**问题**：WorldEngine 生成事件时不检查 sleep_state，导致凌晨睡眠期间出现
"打电话给前男友"这样的清醒行为类事件，与认知输出的"（睡眠中）"严重撕裂。

**修复**（`core/world_engine.py`）：
```python
# tick() 方法开头加判断
if behavior is not None and getattr(behavior, "sleep_state", None) == "ASLEEP":
    return ""  # 睡眠中不推进外部事件，让 drift 层自由运转
```

### Phase A 结论

核心机制验证通过：生命域正交提取 + Softmax 多线激活。Phase A 关闭。

---

## 横向扩展：Trunk 树接入 drift 层（Phase A.5）

### 设计决策

**问题**：drift 模块（rumination/daydream/future/philosophy 等）各自独立，
从 profile 中随机抽取锚点（rumination_anchors / daydream_anchors / philosophy_seeds），
与 WorldEngine 使用的 Trunk 树完全解耦。
结果：外部事件在讲工作危机，rumination 可能在反刍一件两年前的事，互不呼应。

**核心洞察**：
Trunk 树的本质是「持续性认知占用」（sustained preoccupation）——
它不只是外部世界的事件驱动器，也应该是内部认知的焦点驱动器。
同一个 tick 内，多个认知进程（事件/反刍/白日梦/哲学思考）应当在
同一条 Trunk 上产生共振，只是入射角度不同。

**方案**：`ModuleContext` 新增 `active_trunk_context: str` 字段，
由 `run_cognitive_cycle()` 接收并传入所有模块。
各模块的 `get_anchor` 优先使用 trunk context，
降级（fallback）回原有 profile 锚点。

### 各模块接入策略

| 模块 | 接入强度 | 逻辑 |
|---|---|---|
| rumination | **强**（替换锚点） | 反刍最压着的那件事，和当前 active Trunk 高度重合 |
| philosophy | **强**（替换锚点） | 哲学思考必须从具体处境出发，Trunk description 正是最好的出发点 |
| self_eval | **强**（替换锚点） | 自我评估绑定当前最紧迫的处境 |
| future | **中**（注入前缀） | 近未来投射沿着当前最迫切的 Trunk 方向展开 |
| daydream | **弱**（软提示） | 白日梦跟随欲望而非焦虑，Trunk 只作背景色，不替换欲望锚点 |
| aesthetic / counterfactual / positive_memory / social_rehearsal | **不接入** | 这些模块的内容源头与 Trunk 正交 |

### 实现

**`core/cognitive_modules/base.py`**：
`ModuleContext` 新增字段：
```python
active_trunk_context: str = ""  # Trunk 层注入：当前最相关主干情境的一行描述
```

**`core/cognitive_engine.py`**：
`run_cognitive_cycle()` 新增参数 `active_trunk_context: str = ""`，
写入 `ModuleContext`。

**`run.py`**：
每 tick 调用 `world_state.get_trunk_context()` 获得 `(trunk_id, context_str)`，
将 `context_str` 传入 `run_cognitive_cycle()` 和 `world.tick()`。

（注意：`get_trunk_context()` 本身已有 Softmax 选择逻辑，
同一 tick 内 WorldEngine 和 drift 模块拿到的可能是不同 Trunk。
Phase A.5 改为：先从 world_state 取一次，复用同一个结果传入两处，
保证当轮事件和 drift 内容指向同一条 Trunk。）

**`core/cognitive_modules/drift.py`**：
rumination / philosophy / self_eval 的 `get_anchor` 改为：
```python
lambda ctx: ctx.active_trunk_context or (
    random.choice(ctx.profile.rumination_anchors)
    if ctx.profile.rumination_anchors else ctx.perceived[:30]
)
```
future 的 `get_anchor` 在 trunk context 存在时注入前缀，保留原有 desires 锚点。
daydream 不改，trunk context 不强制介入欲望方向。

---

## 未决事项

- WorldEngine 和 drift 现在共享同一 tick 的 trunk selection，
  但 WorldEngine 在认知循环之后调用（`event = world.tick(state, behavior)`），
  drift 在循环内。严格来说两者看到的情绪状态不同（before/after cognitive cycle）。
  暂时接受这个近似，后续如有必要可拆成两个不同的 trunk selection 时刻。
- Thread urgency 恒为 1.00 问题仍未处理，action_type 始终 confront，后续迭代解决。

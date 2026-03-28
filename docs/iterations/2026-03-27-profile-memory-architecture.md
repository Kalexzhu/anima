# Profile 架构迭代：记忆采样机制 + 死代码清理

**日期**：2026-03-27
**状态**：已实现，语法验证通过
**涉及文件**：`core/profile.py` / `core/cognitive_engine.py` / `core/cognitive_modules/base.py` / `core/cognitive_modules/reactive.py` / `core/cognitive_modules/drift.py` / `examples/demo_profile.json` / `docs/profile-field-rules.md`

---

## 一、Profile 字段修复

### `desires` 随机选择 bug（drift.py）
- **问题**：`future` 模块和 `daydream` fallback 均使用 `profile.desires[0]`，5条欲望中只有第1条永远被触发
- **修复**：改为 `random.choice(profile.desires)`，所有欲望条目机会均等

### `self_model` 字段删除
- **决策**：`self_model.known_patterns` 与 `self_eval_patterns` 内容几乎逐条重复 → 删除
- **保留价值**：`self_model.open_questions` 的2条第一人称内省题（"我的努力是为了谁"、"我怕的是失败本身还是被看见失败"）在语感上与 `philosophy_seeds` 的抽象三人称题不同，有保留价值
- **处理**：将2条内省题合并入 `philosophy_seeds`，`self_model` 字段从 `PersonProfile` dataclass 和 `demo_profile.json` 中删除

---

## 二、Profile 字段收录规则文档

新建 `docs/profile-field-rules.md`：

- 每个字段的准入条件与"不收录什么"
- 七个漂移锚点字段的横向区分决策树（最易混淆的部分）
- `hobbies` / `desires` / `daydream_anchors` 三字段层次区分
- `social_pending` 严格准入（场景时间点的悬而未决，非长期状态）
- 时间轴字段的场景依赖说明

---

## 三、关键设计决策（讨论过程中确认）

### Profile 数据规模策略
- **同一条资料可进入多个字段**，重点是与各字段功能契合，不需要强制归一
- **两个独立维度**：
  - 广度（条数）：锚点字段 5-10 条为宜，过多降低每条的触发频率
  - 深度（每条的具体程度）：是输出真实感的核心来源，鼓励每条记忆写到段落级别的具体细节（具体时间/地点/人物/感官/原话）
- **成本模型**：Profile 体量增大 → token 成本**线性**增长（不是指数型），可预测

### 记忆注入的 A/B 类字段区分
- **A类（每 tick 完整注入）**：`background`、`personality_traits`、`core_values`、`cognitive_biases`、`current_situation`、`relationships`、`memories`（采样子集）
  - 约束：密度优先，防注意力稀释，`to_prompt_context()` 目标 400-600 token
- **B类（每 tick 随机取一条作锚点）**：7个漂移锚点字段
  - 约束：每条需足够具体，能独立驱动一个 tick 的模块输出

### 记忆数量的有效性条件
- **旧机制**（固定 top-5）：写100条记忆等于写5条，第6条起永不注入
- **新机制**（5 importance + 3 random）：数量才真正产生多样性效果
- **结论**：在新采样机制下，更大的记忆库 = 更多样的思维流历史维度；推荐科比 profile 写 20-30 条详细记忆

---

## 四、记忆采样架构重构

### 问题
1. `to_prompt_context()` 在同一 tick 内被调用3次（perception / B1 / B2），每次各自做随机采样 → 三份不同的记忆组合注入
2. 冷却机制需要跨 tick 的状态追踪，无法在纯函数 `to_prompt_context()` 内实现

### 解决方案：预采样 + 单次传递

```
run_cognitive_cycle()
  ├─ _sample_memories(profile, _cooldown_tracker, tick)  ← 唯一一次采样
  │    → top-5（importance 降序，稳定）
  │    → random-3（排除冷却期内的条目；池枯竭时回退到全部剩余）
  │    → 记录采样 indices 进 tracker
  ├─ ModuleContext.memory_sample = 采样结果（新增字段）
  ├─ perception_layer(..., memory_sample=)
  │    → to_prompt_context(memory_override=memory_sample)
  └─ ReactiveModule.run(ctx)
       → B1: to_prompt_context(memory_override=ctx.memory_sample)
       → B2: to_prompt_context(memory_override=ctx.memory_sample)
```

### MemoryCooldownTracker
- `COOLDOWN_TICKS = 5`：被采样的记忆在5轮内排出随机池
- 冷却**只影响 random-3 的候选范围**，不影响 importance top-5（高重要性记忆仍可每轮出现）
- 池枯竭保护：若全部剩余记忆均在冷却期，自动 fallback 到全部剩余（防死锁）
- 全局实例 `_cooldown_tracker`，session 级别，挂在 `cognitive_engine.py`

### `to_prompt_context()` 签名变更
```python
def to_prompt_context(self, memory_override: list | None = None) -> str:
```
- 传入 override → 直接使用（生产路径）
- 不传 → fallback 到本地 5+3 随机采样（兼容测试 / 独立调用）

---

## 五、死代码清理（cognitive_engine.py）

### 删除内容
| 被删除的符号 | 原因 |
|-------------|------|
| `_SYS_B1`、`_SYS_B2` | v5 架构后 B1/B2 唯一来源是 `reactive.py`，此处是重复定义 |
| `arbiter_layer()` | 完整 B1+B2+B3 逻辑，已被 `ReactiveModule` 替代，`run_cognitive_cycle()` 从未调用 |
| `_SYS_DRIFT` | 只被已删除的 `drift_layer()` 使用 |
| `drift_layer()` | v5 架构后 drift 唯一来源是 `drift.py` 的 DriftModule 实例，此处是遗留实现 |

### 单一数据源确认（删除后）
- B1/B2 prompt 定义：仅 `core/cognitive_modules/reactive.py`
- Drift 模块逻辑：仅 `core/cognitive_modules/drift.py`
- JSON 渲染：`_render_moments()` 仍在 `cognitive_engine.py`（被 `_render_all_outputs` 调用，保留）

---

## 六、Kobe Bryant Profile 启动准备

### 场景锚点
- **人物**：科比·布莱恩特（Kobe Bryant），41岁
- **时间**：2020年1月25日（坠机事故前一天）
- **背景**：当晚 LeBron James 超越科比的历史得分纪录，科比在场边观战
- **场景意义**：退役后身份转型（Granity Studios + Mamba Sports Academy 教练），对basketball的执念与告别并存

### WeChat 解析路线
- **状态**：⏸ 暂缓（见 TODO.md）
- **理由**：主流程（公众人物手工 profile）尚未验证有效，手工路线先行，积累字段设计经验后再启动 System A

### 资料处理工作流
1. 用户粘贴原始资料（任意格式，混合 OK）
2. 按 `docs/profile-field-rules.md` 分类提取进暂存文档
3. 用户校对后生成最终 JSON

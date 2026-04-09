# 代码健康清理实施计划

> 日期：2026-04-09
> 触发：代码审计（health score 6.5/10）
> 原则：每个修复独立验证、独立提交。不改变任何运行时行为（除 bug 修复）。

---

## 已验证的问题清单

### Bug（影响运行时行为）

| # | 问题 | 位置 | 验证结果 |
|---|------|------|---------|
| B1 | 梦境历史去重失效 | cognitive_engine.py:594 | TickHistoryStore 无 `__iter__`，`for ts in tick_store` 抛 TypeError。被 try/except 吞掉，fallback 到无历史梦境。功能从未生效。 |

### 死代码

| # | 问题 | 位置 | 验证结果 |
|---|------|------|---------|
| D1 | 孤立渲染代码块 | cognitive_engine.py:330-357 | 旧 _render_moments 的残留，位于 reasoning_layer return 之后，永远不执行。同名函数在 L456 正式定义。 |
| D2 | `_anthropic_client` 未使用 | base_agent.py:97 | 模块级创建了 client 但 `_get_client()` 每次重新创建，旧 client 从未被引用。 |
| D3 | `_MODEL` 未使用 | world_engine.py:27 | 定义了但文件内无任何引用。 |
| D4 | `ModuleContext.narrative_thread` 未被模块读取 | base.py:40 | 字段存在且被 cognitive_engine.py:682 赋值，但 9 个 drift + 1 个 reactive 模块均未访问 `ctx.narrative_thread`。 |

### 架构违规（超行数限制）

| # | 问题 | 位置 | 现状 |
|---|------|------|------|
| A1 | cognitive_engine.py 717 行 | — | 超 500 行红线 |
| A2 | run_cognitive_cycle 178 行 | cognitive_engine.py:539-717 | 超 50 行限制 |
| A3 | create_drift_modules 234 行 | drift.py:245-479 | 超 50 行限制 |
| A4 | run.py 516 行 | — | 略超 500 行 |

### DRY 违规

| # | 问题 | 位置 |
|---|------|------|
| R1 | history_block + retry 循环 copy-paste 5 次 | world_engine.py 5 个事件生成方法 |
| R2 | `drift_order` 列表重复 2 次 | cognitive_engine.py:490 和 :521 |
| R3 | `_NEGATIVE_DIMS` 重复 | occ.py:28 和 cognitive_engine.py:114 |
| R4 | `_bar()` 函数重复 | run.py:110 和 viz_from_txt.py:21 |
| R5 | `_parse_json()` 重复 | reactive.py:57 和 narrative.py:189 |
| R6 | 情绪维度名散落 5 处 | emotion.py, emotion_descriptor.py×2, run.py, drift_sampler.py |
| R7 | 模块名散落 3 处 | drift.py, cognitive_engine.py:490, drift_sampler.py:20 |

### 代码气味

| # | 问题 | 位置 |
|---|------|------|
| S1 | `import re as _re` 在循环体内 | reactive.py:112（re 已在模块顶层 import） |
| S2 | 多余的 `getattr` 防御 | reactive.py:94-95（字段有 dataclass 默认值，不需要 getattr） |
| S3 | `_cooldown_tracker` 模块级单例 | cognitive_engine.py:66（跨 run 状态泄漏） |
| S4 | `_ZH_TO_EN` 硬编码在函数内 | cognitive_engine.py:648（应与 drift_sampler 统一） |

### 部署缺口

| # | 问题 | 位置 |
|---|------|------|
| P1 | kobe runner.py 无 profile 备份 | scenarios/kobe_2020/runner.py |

---

## 实施计划

### 批次 1：Bug 修复 + 死代码清理（低风险，独立）

每项独立提交，不影响运行时行为（除 B1 修复梦境去重）。

**B1：修复梦境历史去重**

```
文件：core/tick_history.py
改动：TickHistoryStore 新增 __iter__ 方法
实现：
    def __iter__(self):
        return iter(self._snapshots)

文件：core/cognitive_engine.py:594-596
改动：修正字段访问
现状：ts.perceived == "（睡眠中）" and ts.text  ← TickSnapshot 无 text 字段
改为：从 ThoughtState 角度重新设计，或在 TickSnapshot 中保存 text 摘要

注意：TickSnapshot 设计意图是只存 tick/emotion/perceived/reasoning（不存 text，因为太长）。
      梦境去重需要的是 text 内容。两种方案：
      方案 A：TickSnapshot 新增 text_summary 字段（梦境 tick 写入时保存前 60 字）
      方案 B：梦境历史直接用 run.py 层的变量跟踪（不走 TickHistoryStore）
      推荐 B——不改 TickSnapshot 的设计（它应该保持轻量），在 run.py tick 循环中维护 dream_history 列表。

验证：跑带睡眠 tick 的 run，检查梦境 prompt 中是否出现历史去重约束。
```

**D1：删除孤立渲染代码块**

```
文件：core/cognitive_engine.py
改动：删除 L330-357 之间的孤立代码（从 `# ── 梦境生成` 注释到 `return "\n".join(lines)`）
验证：python3 -c "from core.cognitive_engine import run_cognitive_cycle; print('OK')"
```

**D2：删除 `_anthropic_client`**

```
文件：agents/base_agent.py
改动：删除 L97 的 _anthropic_client = ... 行
验证：python3 -c "from agents.base_agent import claude_call, fast_call; print('OK')"
```

**D3：删除 `_MODEL`**

```
文件：core/world_engine.py
改动：删除 L27 的 _MODEL = ... 行
验证：python3 -c "from core.world_engine import WorldEngine; print('OK')"
```

**D4：移除 `narrative_thread` 字段**

```
注意：不能直接删除——cognitive_engine.py:682 在赋值，run.py 在传参。
      需要同时清理三处：base.py 字段定义、cognitive_engine.py 赋值、run.py 传参。
      但 NarrativeThreadManager 本身在 run.py 中是有用的（驱动 urgency 和事件生成）。
      只是它的数据不通过 ModuleContext 传递给模块。
      
改动：
  - base.py: 删除 narrative_thread 字段
  - cognitive_engine.py run_cognitive_cycle(): 删除 narrative_thread 参数和 ModuleContext 赋值
  - run.py: 删除 narrative_thread=top 的传参

验证：python3 run.py examples/demo_profile.json --max-ticks 1
```

**S1 + S2：reactive.py 小修**

```
文件：core/cognitive_modules/reactive.py
改动 1：删除 L112 的 import re as _re，用模块顶层已 import 的 re
改动 2：L94-95 getattr(profile, "desires", []) → profile.desires（dataclass 保证存在）
验证：python3 -c "from core.cognitive_modules.reactive import ReactiveModule; print('OK')"
```

### 批次 2：cognitive_engine.py 拆分（降到 500 行以下）

这是最大的改动，需要谨慎。目标：从 717 行降到 ~450 行。

**拆出 core/renderer.py（~80 行）**

```
移出的函数：
  - _render_moments()（L456-475）
  - _render_all_outputs()（L478-505）
  - render_all_outputs_labeled()（L508-536）

新文件：core/renderer.py
  - 从 cognitive_engine.py 导入的唯一依赖：无（纯文本处理）
  - drift_order 列表提取为模块常量 DRIFT_MODULE_ORDER

cognitive_engine.py 改为：
  from core.renderer import _render_all_outputs, render_all_outputs_labeled

run.py 改为：
  from core.renderer import render_all_outputs_labeled

验证：跑 1 tick，对比输出文本完全一致
```

**拆出 core/memory_sampler.py（~50 行）**

```
移出的函数/类：
  - MemoryCooldownTracker 类（L48-66）
  - _sample_memories()（L69-101）

新文件：core/memory_sampler.py

cognitive_engine.py 改为：
  from core.memory_sampler import MemoryCooldownTracker, _sample_memories

验证：python3 run.py examples/demo_profile.json --max-ticks 1
```

**拆后 cognitive_engine.py 预估**：717 - 80 - 50 - 28（D1 死代码）= ~559 行。

还需额外减 ~60 行。候选：
- `_apply_dutir_calibration()`（L170-211，42 行）→ 移入 core/occ.py（本就是情绪校准逻辑）
- `_get_inner_voices()` + `_build_relationship_context()`（L141-165，25 行）→ 移入 core/profile.py 作为 PersonProfile 方法（它们只依赖 profile 数据）

拆后 cognitive_engine.py 预估：559 - 42 - 25 = ~492 行。低于 500 行红线。

**run_cognitive_cycle 长度**：拆出渲染和记忆采样后，函数本身减少 ~20 行（调用改为 import）。剩余 ~158 行仍超标，但这个函数是整个引擎的编排逻辑，进一步拆分需要引入新的抽象（如 AwakeCycle / AsleepCycle 类），工作量大且风险高。建议标记为已知技术债，不在本次处理。

### 批次 3：DRY 清理

**R2 + R7：drift_order / 模块名统一**

```
文件：core/renderer.py（批次 2 新建后）
改动：DRIFT_MODULE_ORDER 作为唯一数据源

文件：core/cognitive_engine.py
改动：drift_order 引用改为 from core.renderer import DRIFT_MODULE_ORDER

文件：drift_sampler.py
改动：DRIFT_CATEGORIES 改为 from core.renderer import DRIFT_MODULE_ORDER
注意：drift_sampler 目前还有 imagery 不在列表中。确认 imagery 是否参与采样。

验证：grep -rn "drift_order\|DRIFT_CATEGORIES\|DRIFT_MODULE_ORDER" core/
```

**R3：`_NEGATIVE_DIMS` 统一**

```
文件：core/emotion_utils.py（已存在 EMOTION_DIMS）
改动：新增 NEGATIVE_DIMS 和 POSITIVE_DIMS

文件：core/occ.py + cognitive_engine.py
改动：删除各自的 _NEGATIVE_DIMS/_POSITIVE_DIMS，改为 from core.emotion_utils import

验证：python3 -c "from core.occ import occ_to_plutchik; from core.cognitive_engine import run_cognitive_cycle; print('OK')"
```

**R1：world_engine.py history_block + retry 去重**

```
文件：core/world_engine.py
改动：
  - 提取 _build_history_block(self) → str 方法
  - 提取 _llm_generate(prompt, system, max_tokens, label) → str 方法（含 retry 逻辑）
  - 5 个事件生成方法各自调用这两个 helper

预估：从 497 行减至 ~380 行

验证：跑 5 tick，检查事件生成正常（dramatic + subtle 各至少触发一次）
```

**R4：`_bar()` 提取**

```
文件：新建 core/display_utils.py（或直接放 run.py 中不管 viz_from_txt.py）
改动：run.py 和 viz_from_txt.py 共用同一个 _bar()
验证：两个文件 import 正常
```

**R5：`_parse_json()` 提取**

```
文件：core/json_utils.py（或 core/cognitive_modules/ 内共享）
改动：reactive.py 和 narrative.py 共用
验证：python3 -c "from core.cognitive_modules.reactive import ReactiveModule; print('OK')"
```

**R6：情绪维度名统一**

```
现状：emotion.py 的 EmotionState 是 dataclass，8 个维度是字段名。
      其他地方用字符串字面量引用这些维度名。
      
方案：在 core/emotion_utils.py 中定义 EMOTION_DIMS（已存在），
      其他文件的硬编码字典键从 EMOTION_DIMS 派生。
      
注意：emotion_descriptor.py 的 _DESCRIPTORS 和 _ZH_NAMES 是深度嵌套的字典，
      改为从 EMOTION_DIMS 循环构造会降低可读性。标记为低优先级。
```

### 批次 4：部署补全

**P1：kobe runner.py 加 profile 备份**

```
文件：scenarios/kobe_2020/runner.py
改动：main() 开始时加 shutil.copy2 备份（参考 run.py 的实现）
验证：跑 kobe runner，检查 output/ 中出现备份文件
```

**S3：MemoryCooldownTracker 重置**

```
在批次 2 拆出 memory_sampler.py 后，_cooldown_tracker 不再是模块级单例。
在 run.py 的 main() 中每次 run 创建新实例，传入 run_cognitive_cycle。
这需要 run_cognitive_cycle 接收 cooldown_tracker 参数（或在拆分时重新设计）。
标记为与批次 2 合并处理。
```

**S4：`_ZH_TO_EN` 统一到 drift_sampler**

```
drift_sampler.py 已有 _ZH_NAMES（英文→中文映射）。
cognitive_engine.py:648 的 _ZH_TO_EN 是反向映射。

改动：drift_sampler.py 导出 sample_drift_key()（直接返回英文 key 而非中文名）
cognitive_engine.py 删除 _ZH_TO_EN，直接调用 sample_drift_key()

与批次 2 合并处理。
```

---

## 实施顺序与依赖

```
批次 1（独立，可并行）
  B1  梦境去重修复
  D1  删孤立代码块
  D2  删 _anthropic_client
  D3  删 _MODEL
  D4  删 narrative_thread
  S1  reactive import 修复
  S2  reactive getattr 修复
      ↓
批次 2（依赖批次 1 的 D1 完成，认知引擎拆分）
  新建 core/renderer.py
  新建 core/memory_sampler.py
  _apply_dutir_calibration 移入 occ.py
  _build_relationship_context + _get_inner_voices 移入 profile.py
      ↓
批次 3（依赖批次 2 的 renderer.py 存在）
  R2+R7  模块名统一
  R3     NEGATIVE_DIMS 统一
  R1     world_engine DRY
  R4     _bar 提取
  R5     _parse_json 提取
  R6     情绪维度名（低优先级，可延后）
      ↓
批次 4（独立）
  P1  kobe runner 备份
  S3  cooldown tracker 重置（与批次 2 合并）
  S4  _ZH_TO_EN 统一（与批次 2 合并）
```

---

## 验证策略

每批完成后：
1. `python3 -c "from core.cognitive_engine import run_cognitive_cycle"` — import 不报错
2. `python3 run.py examples/demo_profile.json --max-ticks 1` — 单 tick 跑通
3. 对比改动前后同一 tick 的输出格式是否一致（渲染逻辑拆出后尤为重要）
4. `wc -l core/cognitive_engine.py` — 确认低于 500 行（批次 2 后）

---

## 不做的事

| 不做 | 原因 |
|------|------|
| run_cognitive_cycle 进一步拆分至 50 行以下 | 需要引入 AwakeCycle/AsleepCycle 抽象，改动大，风险高，当前函数逻辑线性清晰 |
| emotion_descriptor.py 的 _DESCRIPTORS 改为从 EMOTION_DIMS 派生 | 降低可读性，收益低 |
| drift_sampler.py 的生产模式验证 | _TEST_ALL_MODULES=True 是当前正确的设定（全模块运行用于质量评估），生产模式切换是独立议题 |

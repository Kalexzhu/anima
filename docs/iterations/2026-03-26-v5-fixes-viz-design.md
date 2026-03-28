# v5 修复实施 + 可视化层设计

**日期**：2026-03-26（第二次会话）
**状态**：修复已实施并验证，可视化层设计待开发
**依据**：run_林晓雨_13.txt（5轮，全模块测试）

---

## 本次实施的改动

### 改动 1 — imagery 模块 + ASLEEP 静默

**文件**：`core/cognitive_modules/drift.py`、`core/cognitive_engine.py`

- `create_drift_modules()` 末尾新增第10个模块 `imagery`（FragmentModule）
  - anchor：`ctx.perceived[:30]`（感知触发意象，无预设锚点列表）
  - moment_count：`"1~2"`
  - system prompt：意识边缘浮现的感知画面，允许超现实并置，禁止情绪分析
- ASLEEP 路径删除 `_dream_arbiter` 调用，改为静默输出 `"（睡眠中）"`，仅保留情绪衰退
- `_dream_arbiter` 函数保留代码但不再调用

### 改动 2 — future 模块 prompt 修正

**文件**：`core/cognitive_modules/drift.py`

- 原 step_system 含"包含行动序列（先做什么再做什么）"→ 删除
- 改为：强调「脑中到达那个未来场景」的画面感；要求感官细节（光线/声音/温度）
- 新增明确禁止项："严格禁止：操作步骤、待办项、行动序列"

### 改动 3 — 情绪初始播种

**文件**：`run.py`

新增 `_seed_initial_emotion(profile, state)` 函数：
- tick 1 主循环前调用一次
- 以 `current_physical_state` + `current_situation` 作为感知输入
- 调用同一条 OCC 管线（`fast_call` → `parse_occ_response` → `occ_to_plutchik` → `apply_personality_modifiers`）
- 用 `dataclasses.replace()` 更新初始 `ThoughtState.emotion`
- 失败时静默 fallback，保持 0.0 不报错

### 改动 4 — anger 缺失修复

**文件**：`core/occ.py`

- **OCC_SYSTEM_PROMPT**：`causal_agent` 字段说明补充客观性备注：
  > "按客观事实判断，不受人物主观归因偏差影响。他人的行为（如领导当众否定）即使人物倾向自责，causal_agent 仍应判为 'other'"
- **BIAS_MODIFIERS**：`过度自责` 的 anger 系数从 0.4 改为 0.7
  - 设计原理：过度自责者仍有愤怒，只是压抑了一部分；完全归零在心理上不真实

### 测试模式开关（临时）

**文件**：`cognitive_engine.py`、`run.py`

- `_TEST_ALL_MODULES = True`：每轮运行全部10个漂移模块，绕过 drift_sampler（含 TODO 注释，评估完后改回 False）
- `MAX_TICKS = 5`（含 TODO 注释，评估完后改回 20）
- 终端输出带模块标签（`== 模块名 ==`），txt 文件仍写无标签连续版

---

## run_13 评估结论（5轮，全模块测试）

### ✅ 改动验证

| 改动 | 结论 |
|------|------|
| 情绪初始播种 | 有效：tick 1 intensity=0.48（run_12 为 0.00） |
| anger 修复 | 有效：tick 1 anger=0.22（run_12 全程 0.00） |
| future prompt | 有效：不再有 GTD 清单，改成画面式心理时间旅行 |
| ASLEEP 静默 | 有效：tick 5 正确输出"（睡眠中）" |

### 各模块表现

| 模块 | 评级 | 备注 |
|------|------|------|
| reactive | ✅ | 稳定，DES 类型准确 |
| rumination | ✅ | 显性循环 + 身体感知锚定 |
| self_eval | ✅ 亮点 | 第三人称观察精准，有命名模式能力（"权威定论吸收"） |
| philosophy | ✅ | 从具体到抽象，停在问题不给结论 |
| aesthetic | ✅ 亮点 | 跨轮积累（prev_tick_outputs 机制工作）：tick1铝型材→tick3"和上轮有某种同构" |
| counterfactual | ✅ | 合肥分叉线多轮延续，感官具体 |
| positive_memory | ✅ 亮点 | 22岁公告栏记忆每轮补充新感官细节；tick4触发 joy=0.21，自发情绪调节机制工作 |
| daydream | ✅ | tick4 画室场景感官化极佳 |
| future | ✅ 改善 | 不再是操作步骤，改为场景画面；4步链条连贯成时间流 |
| social_rehearsal | ✅ | 张明/领导排演逻辑清晰，建模准确 |
| imagery | ⚠️ 偏弱 | 产出少（1~2个），内容与 aesthetic 边界模糊，超现实并置特质未体现 |

### 新发现的问题

**anger 衰减过快**（非紧急）
tick1=0.22 → tick2=0.12 → tick3=0.03。后续轮次事件切换后 OCC 不再有 other/humiliation 语境，anger 随被动衰退快速归零。可接受，后续如需调整可降低 anger 的 decay 系数。

**imagery 与 aesthetic 边界模糊**（P2）
两者都产出 visual_fragment，区分应在于：aesthetic 关注形式关系（比例/节奏），imagery 关注超现实并置。目前 imagery 输出更像短版 aesthetic。待下次评估后决定是否调整 prompt。

---

## 提示词规范化 + 渲染器修改

**背景**：为后续可视化层（文字漂浮动画、TTS）做输出格式准备，输出需能从角色视角朗读/显示。

### 问题定位

1. **voice_intrusion 渲染格式**：`"「content」"（主管，男声，普通话，语速偏慢）` → 无法从角色口中说出
2. **代词歧义**：social_rehearsal 和 B2 输出中"他/她/对方"没有指向具体人名
3. **social_rehearsal 虚构人名**：run_13 中出现"陈浩"（profile 中不存在的人物）

### 修复内容

**`_SYS_B2`（cognitive_engine.py）**：
- voice_intrusion source 说明：只填人名，禁止填声调/语速/性别等描述
- 新增约束：出现具体人物时用人名，不用「他/她/对方/那个人」代词

**`_DES_TYPES`（drift.py，被所有 FragmentModule 使用）**：
- 同上，voice_intrusion source 约束 + 人名代替代词约束

**`social_rehearsal step_system`（drift.py）**：
- source 只填人名约束
- 人名代替代词约束
- 新增："对话内容必须来自 profile 中已存在的关系人物，禁止虚构新人名"

**`_render_moments()`（cognitive_engine.py）**：
- voice_intrusion 渲染从：`"「content」"（source）`
- 改为：`"name说，「content」"`（name 取 source 第一个逗号前的部分，防御旧格式）
- source 为空时渲染为 `「content」`

---

## 可视化层设计

### 决策

| 方向 | 状态 |
|------|------|
| 连线图（思维网络） | 封存，暂不开发 |
| TTS 对口型生成 | 暂缓，作为另一独立可视化方向 |
| 文字漂浮动画 | **优先开发** |

### 文字漂浮动画 spec

**时间轴**：单个 tick 的内容在 5 分钟内渐序出现

**出现规则**：
- 每段文字出现方向：正负 45 度之间随机
- 已出现的文字逐渐降低透明度
- 屏幕上逐渐被文字交叠堆满

**背景**：低饱和度颜色渐变，多角度弧光，营造意识朦胧感

**tick 切换**：
1. 当前 tick 全部文字输出完成后，清除所有文字
2. 屏幕中央出现文字展示当前事件内容
3. 进入下一个 tick

### render 层架构决策

当前 `_render_moments()` 是给「心理文本」（txt 文件存档）用的渲染器，不应承担可视化职责。

**方案**：独立的 `render_for_viz(moments)` 函数，消费同一份 JSON moment 数据，按以下规则转换：

| DES 类型 | 可视化处理 |
|----------|-----------|
| `compressed_speech` | 直接显示，短而突出 |
| `visual_fragment` | 直接显示 |
| `body_sensation` | 直接显示 |
| `voice_intrusion` | `"name说，「content」"` |
| `expanded_speech` | 直接显示 |
| `unsymbolized` | 去掉〔〕，改为可读句式，或以斜体/灰色区分 |
| `intrusion` | 直接显示，可用较小字号 |

**注意**：`unsymbolized` 类型在心理文本中用`〔〕`包裹，属于第三方旁白语气，在可视化中需要特殊处理（转为第一人称？斜体？还是跳过？）——待开发时决定。

---

## 文件影响范围

| 文件 | 改动类型 |
|------|----------|
| `core/cognitive_modules/drift.py` | imagery 模块、future prompt、social_rehearsal prompt、_DES_TYPES |
| `core/cognitive_engine.py` | ASLEEP 静默、_SYS_B2、_render_moments、_TEST_ALL_MODULES、render_all_outputs_labeled |
| `run.py` | _seed_initial_emotion、MAX_TICKS=5、终端标签输出 |
| `core/occ.py` | OCC_SYSTEM_PROMPT causal_agent 备注、BIAS_MODIFIERS anger 0.4→0.7 |

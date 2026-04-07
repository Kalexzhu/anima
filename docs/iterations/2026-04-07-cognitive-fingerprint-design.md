# 认知指纹迭代设计（Cognitive Fingerprint）

> 日期：2026-04-07
> 状态：待 eng-review
> 前置文档：2026-04-07-colleague-skill-borrowing.md（调研，本文档基于其结论）

---

## 一、背景与动因

### 外部背景

.skill 文化浪潮期间，对比 colleague-skill 的双层架构（Work Skill + Persona L0-L5），识别出两个值得借鉴的方向：行为规则化（用具体行为描述替代形容词标签）和表达风格建模（不同关系人物有独立的说话方式）。

### 内部问题

**问题 1：角色差异化丢失**

9 个 drift 模块的 user prompt（drift.py:126-135）只含名字、年龄、处境、情绪、锚点。没有任何人格特征信息。林晓雨和科比跑同一个 rumination 模块，输出的语言方式、身体感知、思维走向可能高度相似。

ReactiveModule 不同 — 它通过 `to_prompt_context()` 拿到完整 profile。但 drift 模块没有。drift 模块是意识流的主体来源（9 个模块），差异化在这里丢失。

**问题 2：ResidualFeedback 垃圾写入**

demo_profile.json 中已有 4 个误检的关系条目（"睡眠中""喘不过""声音在""耳边响"）。

---

## 二、迭代目标

1. 不同角色的意识流输出有明显可辨的个体差异（语言方式、身体感知位置、思维走向）
2. 不同关系人物的 voice_intrusion 有可区分的风格
3. 不增加模块 prompt 的规则复杂度（新增的是上下文，不是规则）
4. 数据层结构化，为未来迭代预留扩展通道

---

## 三、设计原则

### 原则 1：上下文，不是规则

fingerprint 描述的是"这个人是什么样的"，不是"你必须遵守什么"。放在 user prompt 的人物信息段，不在 system prompt 里。DES 格式规则在 system prompt（高优先级），fingerprint 在 user prompt（作为上下文）。两者不在同一层级竞争。

### 原则 2：数据层结构化，输出层紧凑

Profile JSON 中用独立字段存储每个维度（方便编辑、未来进化机制更新、按需筛选）。面向 LLM 的输出合并为一个 ~80 字的紧凑文本块。

### 原则 3：为未来解耦预留结构

当前角色信息只有 3 个字段共 ~80 字，全量注入 drift prompt 即可。

未来角色信息膨胀时，`to_cognitive_fingerprint()` 可以扩展为按模块筛选相关子集的机制（类似 memory 检索的 top-5+3 模式），保持每个 prompt 轻量。这个扩展只需修改序列化方法，不需要改动任何模块代码。

当前的数据层结构（独立字段）天然支持这种按字段筛选。

### 原则 4：不伤害已有逻辑

- `personality_traits` → OCC BIAS_MODIFIERS 情绪调制 — 不动
- `cognitive_biases` → 情绪权重修正 — 不动
- `typical_phrases` → voice_intrusion 内容来源 — 不动
- 所有模块 system prompt 常量 — 不动
- drift_sampler 采样逻辑 — 不动
- WorldState Trunk 系统 — 不动

---

## 四、具体设计

### 4.1 Profile 数据层：新增字段

```python
# core/profile.py — PersonProfile 新增

inner_voice_style: str = ""
# 内心语言方式（1-2句话）
# 这个人在脑子里怎么跟自己说话：人称、句式、断句方式
# 例："内心独白在自我否定时切换为第二人称（'你又……'），
#      平时用碎片化短句，情绪激动时句子断在动词上"

somatic_anchors: str = ""
# 情绪的身体着陆点（1句话）
# 不同人的焦虑/压力/悲伤落在不同的身体部位
# 例："胸口（发紧）和手指（发凉、微颤）"

cognitive_default: str = ""
# 压力下的认知默认模式（1-2句话）
# 这个人在压力下自动进入的思维回路
# 例："压力下不面对问题，而是反复回放对方最后那句话的语气和表情，
#      或去做一件可控的小事（整理抽屉、重叠衣服）"
```

```python
# core/profile.py — Relationship 新增

speech_style: str = ""
# 这个人说话的方式（1句话）
# 控制 voice_intrusion 中不同人的声音风格差异
# 例："极短句、命令式、从不解释理由、经常以反问结尾"
```

### 4.2 序列化方法

```python
# core/profile.py — PersonProfile 新增方法

def to_cognitive_fingerprint(self) -> str:
    """合并认知指纹三维度为一个紧凑文本块。
    
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
```

### 4.3 关系序列化增强

```python
# core/profile.py — Relationship.to_prompt_line() 修改

def to_prompt_line(self) -> str:
    sign = "+" if self.valence >= 0 else ""
    line = f"{self.name}（{self.role}，情感倾向{sign}{self.valence:.1f}，{self.power_dynamic}）"
    if self.unresolved_conflicts:
        line += f" | 未解冲突：{self.unresolved_conflicts[0]}"
    if self.speech_style:
        line += f" | 说话方式：{self.speech_style}"
    return line
```

`to_prompt_line()` 是关系信息的唯一输出出口。`_build_relationship_context()`、`to_prompt_context()`、`_get_inner_voices()` 都通过它展示关系。一处改动自动传播到 perception / reasoning / reactive。

`Relationship.from_dict()` 追加 `speech_style=d.get("speech_style", "")`。

### 4.4 注入点（2 处）

**注入点 1：`to_prompt_context()` 追加 fingerprint**

```python
# profile.py — to_prompt_context() 末尾，return 前
fingerprint = self.to_cognitive_fingerprint()
if fingerprint:
    lines.append(fingerprint)
```

传播范围：
- `reactive.py` B1 — L123 调用 `profile.to_prompt_context()` ✓
- `reactive.py` B2 — L138 调用 `profile.to_prompt_context()` ✓
- `cognitive_engine.py` perception_layer — L224 调用 ✓

**注入点 2：drift 模块 user prompt 追加 fingerprint**

`FragmentModule.run()`（drift.py:126-135）`处境` 之后追加：

```python
fingerprint = ctx.profile.to_cognitive_fingerprint()

user = (
    f"人物：{ctx.profile.name}，{ctx.profile.age}岁\n"
    f"处境：{ctx.profile.current_situation}\n"
    + (f"{fingerprint}\n" if fingerprint else "")
    + f"情绪：{emotion_desc}"
    + ...  # 其余不变
)
```

`ChainModule._build_step_prompt()`（drift.py:227-235）同样位置追加：

```python
fingerprint = ctx.profile.to_cognitive_fingerprint()

return (
    f"人物：{ctx.profile.name}，{ctx.profile.age}岁\n"
    f"处境：{ctx.profile.current_situation}\n"
    + (f"{fingerprint}\n" if fingerprint else "")
    + location_ctx
    + ...  # 其余不变
)
```

传播范围：全部 9 个 drift 模块 ✓

**不改动的地方**：
- 所有模块 system prompt 常量 — 不动
- `_get_inner_voices()` — 不动（speech_style 通过 `to_prompt_line()` 自动传播）
- `reasoning_layer` — 不动
- OCC 情绪管线 — 不动
- `cognitive_engine.py` — 不动（fingerprint 通过 `to_prompt_context()` 自动传播到 perception/reactive）

### 4.5 数据示例

**林晓雨 profile 补充**：

```json
{
  "inner_voice_style": "内心独白在自我否定时切换为第二人称（「你又……」「你以为你是谁」），平时用碎片化短句，情绪激动时句子断在动词上",
  "somatic_anchors": "胸口（发紧、像被什么压住）和手指（发凉、微颤）",
  "cognitive_default": "压力下不面对问题，而是反复回放对方最后那句话的语气和表情，或去做一件可控的小事（整理抽屉、重叠衣服）",
  
  "relationships": [
    {
      "name": "陈总",
      "speech_style": "极短句、命令式、从不解释理由、经常以反问结尾（「有没有想清楚？」）",
      "...": "其余字段不变"
    },
    {
      "name": "母亲",
      "speech_style": "絮叨、以关心包裹否定（「我是为你好」）、常用「你这孩子」开头、句尾带叹息",
      "...": "其余字段不变"
    },
    {
      "name": "前男友李杨",
      "speech_style": "平静但疏远、像在陈述事实而非吵架、用「你太……了」句式",
      "...": "其余字段不变"
    },
    {
      "name": "张明",
      "speech_style": "轻松、口语化、常用「没事的」开头、善用具体小事转移注意力",
      "...": "其余字段不变"
    }
  ]
}
```

**科比 profile 补充**：

```json
{
  "inner_voice_style": "内心语言是命令式极短句（「Again」「Not enough」「Mamba mentality」），不用疑问句，自我称呼为 Mamba",
  "somatic_anchors": "肩膀（力量蓄积感）和膝盖（旧伤隐痛，作为身体记忆的常驻背景）",
  "cognitive_default": "面对失败不停留在情绪上，立刻在脑中拆解原因和下一步动作；独处时思维高度聚焦，不发散"
}
```

### 4.6 drift prompt 改动前后对比

**改动前**：
```
人物：林晓雨，28岁
处境：刚刚在会议上被领导当众否定了她做了两周的方案，正独自坐在公司楼道里的窗边
情绪：sadness=0.61 fear=0.34 anger=0.12 ...
锚点：「这个方案完全跑偏了」
```

**改动后**：
```
人物：林晓雨，28岁
处境：刚刚在会议上被领导当众否定了她做了两周的方案，正独自坐在公司楼道里的窗边
认知特征：内心独白在自我否定时切换为第二人称（「你又……」），平时用碎片化短句，情绪激动时句子断在动词上。身体感知集中在胸口（发紧）和手指（发凉、微颤）。压力下不面对问题，而是反复回放对方最后那句话的语气和表情，或去做一件可控的小事
情绪：sadness=0.61 fear=0.34 anger=0.12 ...
锚点：「这个方案完全跑偏了」
```

新增 ~80 字上下文。不是规则指令，是人物描述。

### 4.7 预期输出对比

**改动前 — rumination 模块（林晓雨 vs 科比可能相似）**：

```json
// 林晓雨
{"type": "compressed_speech", "content": "方案——"}
{"type": "body_sensation", "content": "心里有些沉"}
{"type": "compressed_speech", "content": "为什么——"}

// 科比
{"type": "compressed_speech", "content": "比赛——"}
{"type": "body_sensation", "content": "心里有些沉"}
{"type": "compressed_speech", "content": "为什么——"}
```

body_sensation 雷同（"心里"），compressed_speech 句式雷同，仅锚点不同。

**改动后 — 有 fingerprint 的输出**：

```json
// 林晓雨（第二人称、胸口手指、回放表情）
{"type": "body_sensation", "content": "胸口发紧，像被什么压住，呼吸变浅了"}
{"type": "compressed_speech", "content": "你又——"}
{"type": "visual_fragment", "content": "陈总说完那句话时的表情，嘴角那个弧度"}
{"type": "compressed_speech", "content": "你以为你能——"}

// 科比（命令式、肩膀膝盖、拆解分析）
{"type": "body_sensation", "content": "右肩沉下来，像扛了一整场比赛"}
{"type": "compressed_speech", "content": "Again."}
{"type": "compressed_speech", "content": "第三节——防守换位慢了半拍"}
{"type": "expanded_speech", "content": "Not enough."}
```

差异来源：同一个 ~80 字的 fingerprint 上下文，LLM 自行推导出不同的语言人称、身体部位、思维方式。

---

## 五、附加改动：ResidualFeedback 修复

与认知指纹独立，同批实施。

### 5.1 问题

demo_profile.json 中已有 4 个 ResidualFeedback 误检的垃圾关系条目（"睡眠中""喘不过""声音在""耳边响"）。`role: "(自动检测)"`, `valence: 0.0`，空 `typical_phrases`。这些骨架条目注入 prompt 后是噪音。

### 5.2 改动

1. **数据清理**：删除 demo_profile.json 中 4 个垃圾条目
2. **staging 区写入**：`residual_feedback.py` 中 relationship 检测结果不直接写入 profile，而是写入 `output/{name}_detected_entities.json`，等待审阅后手动纳入
3. **run 前备份**：`run.py` main() 开始时 `shutil.copy2(profile_path, ...)`

---

## 六、实施计划

### 第一步：Profile 字段 + 数据

1. `core/profile.py` — PersonProfile 新增 `inner_voice_style` / `somatic_anchors` / `cognitive_default`
2. `core/profile.py` — Relationship 新增 `speech_style`，`from_dict()` 追加解析
3. `core/profile.py` — 新增 `to_cognitive_fingerprint()` 方法
4. `core/profile.py` — `to_prompt_context()` 末尾追加 fingerprint
5. `core/profile.py` — `Relationship.to_prompt_line()` 追加 speech_style
6. 更新 `examples/demo_profile.json` — 补充新字段 + 清理 4 个垃圾关系
7. 更新 `scenarios/kobe_2020/kobe_profile.json` — 补充新字段

### 第二步：drift 模块注入

8. `core/cognitive_modules/drift.py` — `FragmentModule.run()` user prompt 追加 fingerprint（~3 行）
9. `core/cognitive_modules/drift.py` — `ChainModule._build_step_prompt()` 追加 fingerprint（~3 行）

### 第三步：ResidualFeedback 修复

10. `core/residual_feedback.py` — relationship 写入改为 staging 区
11. `run.py` — main() 开始时备份 profile

### 验证

- 跑 5 轮林晓雨 + 5 轮科比，对比 drift 模块输出差异度
- 重点：compressed_speech 句式差异、body_sensation 部位差异、voice_intrusion 风格差异
- DES 结构回归：type 分布和 moment 数量不应因 fingerprint 显著偏移
- OCC 回归：情绪向量不受影响
- Trunk 回归：WorldState 行为不变

---

## 七、改动范围汇总

| 文件 | 改动类型 | 改动量 |
|------|---------|--------|
| `core/profile.py` | 新增 3 字段 + 1 字段(Relationship) + 1 方法 + 3 处小改 | ~35 行 |
| `core/cognitive_modules/drift.py` | 2 处追加 fingerprint 到 user prompt | ~6 行 |
| `core/residual_feedback.py` | relationship 写入改 staging | ~20 行 |
| `run.py` | 新增 profile 备份 | ~3 行 |
| `examples/demo_profile.json` | 补充新字段 + 清理垃圾 | 数据变更 |
| `scenarios/kobe_2020/kobe_profile.json` | 补充新字段 | 数据变更 |

**不改动的文件**：
- `core/cognitive_engine.py` — 不改（fingerprint 通过 `to_prompt_context()` 自动传播）
- `core/cognitive_modules/reactive.py` — 不改（同上）
- `core/cognitive_modules/base.py` — 不改
- `core/occ.py` — 不改
- `core/world_engine.py` — 不改
- `core/world_state.py` — 不改
- `agents/base_agent.py` — 不改

---

## 八、长期演化路径

### 当前（本次迭代）

```
Profile: 3 个 fingerprint 字段 + speech_style → 全量序列化 ~80 字 → 注入所有 drift 模块
```

### 未来（当角色信息膨胀时）

```
Profile: N 个角色特征字段（inner_voice_style / somatic_anchors / cognitive_default / 
         subject_patterns / cultural_background / ...）
    ↓
to_cognitive_fingerprint(module_name=...) → 按模块筛选相关子集 → 每个模块仍只看 ~80 字
    例：rumination → somatic_anchors + inner_voice_style
    例：social_rehearsal → 对应人物的 subject_patterns + speech_style
    例：daydream → cognitive_default
```

筛选逻辑是确定性代码（if/else），不需要额外 LLM 调用。数据层可以无限扩展，prompt 层保持恒定体积。

### 更远的未来（如果需要表达层解耦）

如果某个维度的表达转换确实需要独立处理（如语种切换），可以在渲染前加一个轻量的后处理步骤。但这是在生成阶段已经输出了高质量、角色化内容的前提下做的**微调**，不是从稀薄输入创造细节。

---

## 九、已否决的方案

| 方案 | 否决原因 |
|------|---------|
| 5 字段 × 11 注入点（旧方案 A-H） | 每个模块单独改 prompt，冗余且易冲突 |
| 翻译层（voice_translator.py） | 翻译不能凭空创造信息；drift 模块生成的稀薄输出无法被"翻译"成丰富的角色化内容 |
| 翻译层 + 内容/表达分离 | 内容与表达在意识流中不可干净分离（"你又——"既是内容也是表达），强行分离导致架构过度复杂 |

最终方案：fingerprint 作为上下文（非规则）注入 drift prompt，信息在生成时一次给足。数据层结构化为未来按需筛选预留通道。

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR (PLAN) | 3 issues, 1 critical gap |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |
| Outside Voice | Claude subagent | Independent plan challenge | 1 | ISSUES | speech_style propagation gap, system prompt conflict |

**ENG REVIEW FINDINGS:** Architecture: full fingerprint injection (accepted), speech_style drift gap (accepted as known limitation). Code quality: keep inline (no premature abstraction). Tests: expanded to 13 cases including mock LLM tests. Performance: 0 issues. Critical gap: ResidualFeedback staging write needs os.makedirs.
**OUTSIDE VOICE:** speech_style doesn't reach drift modules (accepted, main-character differentiation is primary goal). System prompt body examples may conflict with somatic_anchors (verify during validation runs).
**VERDICT:** ENG CLEARED — ready to implement with noted limitations.

# 多模块认知架构设计

**日期**：2026-03-26
**状态**：设计已确认，待实现
**触发原因**：v4 运行评估发现思维流缺乏发展性，情绪反应式架构无法产生自发联想链条

---

## 问题诊断

现有架构的根本缺陷：**整条管线是纯"反应式"的**。

```
外部事件 → 感知 → 情绪 → B1锚点 → B2思维链
```

每一步都在"响应"。B1 几乎永远选择"最让角色焦虑的事"，B2 从那里展开，
结果是陷在同一个情绪坑里转圈。缺失的是**自发生成式思维**——不由事件触发、
不受情绪驱动、自然漫游的认知链条。

**示例对比：**
- 现有输出：`"你太累了"（李杨）→ 是我 → 方案跑偏了 → 还是我 → …`（循环）
- 目标输出：`想喝咖啡 → 喝什么 → 那家店 → 今天去不去 → 几点下班`（链条）

---

## 核心设计：多模块并发 + 链条型模块

### 架构概览

```
每轮认知循环：
  ┌─────────────────────────────────────────────────────┐
  │  ModuleRunner（并发）                                │
  │                                                     │
  │  片段型模块（各自独立输出 DES moments）              │
  │  ├── rumination     （反刍）                        │
  │  ├── self_eval      （自我评估）                    │
  │  ├── philosophy     （哲学探讨）                    │
  │  ├── aesthetic      （审美联想）                    │
  │  ├── counterfactual （反事实思考）                  │
  │  ├── positive_memory（正向记忆）                    │
  │  └── reactive       （情绪反应，原 B1+B2）          │
  │                                                     │
  │  链条型模块（step N 以 step N-1 为输入，顺序展开）   │
  │  ├── daydream       （欲望联想链）                  │
  │  ├── future         （规划链）                      │
  │  └── social_rehearsal（对话排演链）                 │
  └─────────────────────────────────────────────────────┘
         ↓ 所有模块输出的 DES moments 合并保存
  dict[module_name → list[DES moments]]
         ↓
  下轮所有模块读取上轮完整输出作为 prev_tick_outputs（影响机制）
```

### 两种模块类型

| 类型 | 输出结构 | 认知依据 |
|------|----------|----------|
| **片段型** | 独立 DES moments，彼此不依存 | 多系统并发激活（DMN、情绪系统、记忆提取） |
| **链条型** | step N 以 step N-1 为输入，顺序推进 | 扩散激活链（Collins & Loftus, 1975） |

**链条型的关键规则**：prompt 中显式传入上一步内容，LLM 必须从上一步自然延伸。这使"咖啡链条"成为可能：
```
锚点（daydream_anchors 中的"咖啡"）
  → 想喝咖啡
    → 喝什么（感官触发类别搜索）
      → 以前那家（记忆提取）
        → 今天去不去（决策）
          → 几点下班（行动规划）
```
以上全部由 **daydream 模块独自完成**，不需要跨模块协作。

---

## 各模块学术定义与规则

### 片段型模块（7个）

#### 1. reactive（情绪反应式，原 B1+B2）
**定位**：唯一感知并直接响应当前事件的模块。无 reactive，思维流与触发事件脱钩。
- 读取 event + emotion + cognitive_biases
- 输出：compressed_speech、voice_intrusion、body_sensation 为主
- 高情绪时输出量多，低情绪时可输出极少甚至为空

#### 2. rumination（反刍）
**学术依据**：Nolen-Hoeksema (1991)，重复性负面思维。
- 同一内容在序列中必须出现 **2 次以上**（显性循环）
- 每次重复允许微变形，核心情感不变
- **禁止**出现解决方向或行动意图
- 身体感知优先（胸口、手、喉咙）——反刍在身体里有根
- 读取 profile 的 `rumination_anchors`（精确引文）

#### 3. self_eval（自我评估）
**学术依据**：自我参照加工，medial PFC 激活，自我概念更新。
- 以**第三人称视角**观察自己的行为模式（"她总是……"）
- 每个时刻必须绑定**具体证据**（记忆或事件）
- **禁止**情绪评判，只允许观察性陈述
- 读取 profile 的 `self_eval_patterns`
- 可以命名模式（"过度用力""退缩保护"）

#### 4. philosophy（哲学/存在性探讨）
**学术依据**：Smallwood - 深度加工形式的心智游荡，叙事认同建构。
- 从具体处境出发，每步向上**一个抽象层级**
- 结尾必须停在**无答案的问题**上，禁止给结论
- 语调冷静，带追问而非受苦
- 读取 profile 的 `philosophy_seeds`
- 序列形如：陈总否定方案 → 努力有没有用 → 认可是人真正需要的吗 → 认可是什么

#### 5. aesthetic（创意/审美联想）
**学术依据**：创意孵化期的松散联想，Dijksterhuis & Meurs (2006)。
- **完全不含情绪内容**
- 关注形式：比例、节奏、颜色、排列、密度
- 联想可以跨领域（地铁灯带间距 → 某画面的构图）
- 允许 unsymbolized 感知（「有什么东西是对的」）
- 读取 profile 的 `aesthetic_sensitivities`

#### 6. counterfactual（反事实思考）
**学术依据**：Roese (1997)，上行/下行反事实，明确分叉点。
- 必须有清晰的「如果当时……」**分叉点**
- 从分叉点展开另一条时间线，不停留在情感
- 上行（更好的另一种结果）或下行（幸好没有）均可
- 读取 profile 的 `counterfactual_nodes`

#### 7. positive_memory（正向记忆回溯）
**学术依据**：DMN 中自传体记忆激活，正向情感放大效应。
- 必须绑定**具体时间/地点**
- 感官细节优先（颜色、声音、气味）
- **不分析**记忆，只呈现记忆本身
- **禁止**将记忆与当下处境比较（比较是 rumination 的领域）

---

### 链条型模块（3个）

#### 8. daydream（白日梦/欲望联想链）
**学术依据**：DMN 默认激活方向，享乐性内容，感官丰富（Killingsworth & Gilbert, 2010）。
- 从 `daydream_anchors` 中取一个具体欲望/意象作为锚点
- 每步通过**一步联想**发展到下一步（感官→类别→记忆→决定→计划）
- 高度感官化：气味、光线、触感
- **完全禁止**情绪分析和自我评判
- step N 的内容显式传入 step N+1 的 prompt（链条机制）

#### 9. future（未来规划/预期想象链）
**学术依据**：Atance & O'Neill (2001)，情境性未来思维，心理时间旅行。
- 内容必须有**具体时间/地点**（明天、下班后、到了那里）
- 包含行动**序列**（先做什么再做什么）
- 可以包含对他人反应的预期（建模对方）
- step N 推进到 step N+1（越来越具体的计划）

#### 10. social_rehearsal（假设社交场景排演链）
**学术依据**：Lieberman (2007)，心智化网络，建模他人心理状态。
- 必须有**具体对话对象**（从 `social_pending` 取）
- 包含想象中的对话内容（voice_intrusion 类型为主）
- 链条：我说什么 → Ta的反应 → 我再说什么 → 结果
- 读取 profile 的 `social_pending`

---

## Profile 分类扩展方案

### 设计原则

同一条内容可以重复出现在多个字段——这不是冗余，而是**同一现实的不同模块切面**。

**示例：「李杨分手的那句话」**
```
memories[]             → [26岁·sadness] 分手事件（供 emotion 层使用）
rumination_anchors[]   → 「跟你在一起我喘不过气」（精确引文）
social_rehearsal anchors → "如果现在见到李杨，她会说什么"
self_eval_patterns[]   → "与亲密关系中总是给对方压力感"
philosophy_seeds[]     → "亲密关系里的「累」是什么"
```

**示例：「画画」**
```
hobbies[]                  → 画画，用细墨线（通用）
daydream_anchors[]         → 有一天在自己工作室里画，不被打扰
aesthetic_sensitivities[]  → 线条细腻感，构图比例
```

### 新增 Profile 字段（加在现有字段之外）

```json
{
  "daydream_anchors": [
    "有一天能在自己的工作室画画，不受打扰",
    "一杯好咖啡，阳光从窗户斜进来",
    "坐在某个安静的地方，没有人需要她做任何事"
  ],
  "philosophy_seeds": [
    "努力到底有没有意义",
    "认可是人真正需要的东西吗",
    "亲密关系里的「累」是谁造成的"
  ],
  "aesthetic_sensitivities": [
    "线条的细腻感，墨线很细",
    "等间距排列产生的节奏感",
    "某种颜色配比是对的，不知道为什么"
  ],
  "counterfactual_nodes": [
    "如果当初没有接这个项目",
    "如果分手前说了那句话",
    "如果没有来北京"
  ],
  "self_eval_patterns": [
    "在权威评价下立刻自我否定",
    "用完美主义保护自己不被真正失败",
    "总是独自承受，让别人以为她还好"
  ],
  "social_pending": [
    {"person": "张明", "unresolved": "他昨晚的消息还没回，他不知道她现在的状态"},
    {"person": "妈妈", "unresolved": "电话一直没打，知道接了会被问婚事"},
    {"person": "陈总", "unresolved": "方案需要修改，但她不知道从哪里开口"}
  ],
  "rumination_anchors": [
    "「跟你在一起我喘不过气」",
    "「这个方案完全跑偏了」",
    "13岁，读错字站在讲台上的那个画面"
  ],
  "self_model": {
    "known_patterns": [
      "在权威评价下会立刻自我否定",
      "用完美主义保护自己不被真正失败",
      "习惯独自承受，让外界以为她还好"
    ],
    "open_questions": [
      "我的努力是为了谁",
      "我怕的是失败本身还是被看见失败"
    ]
  }
}
```

---

## 代码架构

### 目录结构

```
core/
  cognitive_modules/
    __init__.py
    base.py          ← CognitiveModule ABC + ModuleContext 统一数据结构
    runner.py        ← ModuleRunner（ThreadPoolExecutor 并发调度）
    reactive.py      ← ReactiveModule（唯一读取 event 的模块，原 B1+B2）
    drift.py         ← DriftModule（9 个实例，构造时传入分类参数和 prompt）
```

### 模块接口

```python
class ModuleContext:
    profile: PersonProfile
    state: ThoughtState          # 含情绪、上轮思维文本
    event: str                   # 当前事件
    behavior: BehaviorState
    narrative_thread: dict | None
    prev_tick_outputs: dict[str, list[dict]]  # 上轮所有模块输出（影响机制）

class CognitiveModule(ABC):
    name: str
    module_type: str  # "fragment" | "chain"

    @abstractmethod
    def run(self, ctx: ModuleContext) -> list[dict]:
        """返回 DES moment JSON 列表"""
        pass

class ModuleRunner:
    def run_all(self, ctx: ModuleContext) -> dict[str, list[dict]]:
        # ThreadPoolExecutor 并发，全部模块每轮运行
        # 返回 {module_name: [moments]}
```

### 链条型模块的特殊机制

```python
class ChainModule(CognitiveModule):
    """step N 的 content 作为 step N+1 的 context 显式传入"""
    module_type = "chain"

    def run(self, ctx: ModuleContext) -> list[dict]:
        anchor = self._get_anchor(ctx)
        moments = []
        prev_step = anchor
        for _ in range(self.chain_length):  # 默认 5 步
            moment = self._generate_step(ctx, prev_step)
            moments.append(moment)
            prev_step = moment["content"]
        return moments
```

---

## 影响机制（当前版本）

**跨轮次影响**：每轮结束后，所有模块输出合并存入 `prev_tick_outputs`，下轮每个模块都能读到。

效果示例：
- 若上轮 rumination 输出了「又是这个——」，下轮 philosophy 模块会感知到并提升抽象层级
- 若上轮 daydream 生成了咖啡链条，下轮 future 模块可能接续生成"去那家店的具体计划"

**待实现的精细影响机制**（Deferred）：
- 模块间能量压制（reactive 输出越多 → daydream 权重越低）
- 同轮内顺序影响（先运行 reactive，其输出作为其他模块的 context 补充）

---

## TODO（Deferred）

- [ ] **选择/合成机制**：目前全部模块输出都保留，后续需要"摘果实"机制决定哪些进入最终展示流
- [ ] **触发条件调优**：目前所有模块每轮全跑，后续可为每个模块设定触发阈值（情绪范围、叙事线索状态等）
- [ ] **视觉化层**：各模块输出实时展示为漂浮字体词云，从中摘取组合为可读思维流（装置展示层）
- [ ] **模块间同轮内影响**：reactive 先跑后，输出追加进其他模块的 context
- [ ] **self_model 动态更新**：self_eval 和 write-back 的结论写入 `self_model.json`，跨轮持久化

---

## 与现有系统的关系

| 现有组件 | 在新架构中的命运 |
|---------|----------------|
| B1（锚点选择） | 被 reactive 模块内化，每个模块有自己的锚点逻辑 |
| B2（DES链生成） | 成为 reactive 模块的内部实现 |
| drift_layer | 拆解为 9 个独立模块，不再是单一 drift |
| drift_sampler | 权重矩阵逻辑可迁移到 ModuleRunner 的触发条件 |
| NarrativeThreadManager | 保持不变，narrative_thread 作为 ModuleContext 的一个字段传入所有模块 |

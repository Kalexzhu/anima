# 借鉴 colleague-skill 架构的改进设计

> 日期：2026-04-07
> 背景：.skill 文化浪潮（同事.skill 5天8000 star）。对比 colleague-skill（titanwings/colleague-skill）的双层架构与 ANIMA 引擎，识别可借鉴的改进方向。
> 原则：colleague-skill 是职场场景，ANIMA 是个人认知/意识流。只借鉴架构思路，不照搬职场内容。

---

## 改进总览

| 编号 | 改进项 | 影响层 | 优先级 |
|------|--------|--------|--------|
| A | behavioral_rules：认知行为规则化 | profile.py → reactive/drift prompts | P0 |
| B | inner_voice_style：主角内心语言风格 | profile.py → DES moment prompts | P0 |
| G | 行为规则化翻译表：personality_traits → behavioral_rules 系统转化 | 新建 trait_to_rules.py | P0 |
| H | 表达风格建模：关系人物语言差异化 | profile.py Relationship → voice_intrusion/social_rehearsal | P0 |
| C | subject_patterns：关系中的主角行为模式 | profile.py Relationship → social_rehearsal/reactive | P1 |
| D | ResidualFeedback 修复：骨架条目 + 版本管理 | residual_feedback.py / writeback.py | P1 |
| E | 自我强化回路抑制 | residual_feedback.py | P2 |
| F | 用户修正机制 | 新建 correction 流程 | P3（记录，暂缓） |

---

## A. behavioral_rules — 认知行为规则化

### 问题

`personality_traits` 是描述性标签（"内向"、"完美主义"），在两处被使用：
1. OCC `BIAS_MODIFIERS` — 子串匹配触发情绪权重（"灾难化" → fear×1.4）
2. 各层 prompt 中作为文本注入（"性格特质：内向, 完美主义, ..."）

标签太抽象，LLM 对同一个"完美主义"可以产生截然不同的行为表现。colleague-skill 的 L0 层用**具体行为规则**替代形容词标签，这个思路值得借鉴。

### 设计

**ANIMA 的 behavioral_rules 不是职场行为逻辑，是认知/情绪/身体层面的行为模式。**

与 colleague-skill L0 的区别：

| colleague-skill L0 | ANIMA behavioral_rules |
|---|---|
| "被质疑时反问'你的判断依据是什么'" | "被否定后不会当场反驳，回去在心里反复排练'如果我当时说了…'" |
| "开会前先说'先把context对齐一下'" | "压力大时第一反应是清理房间，而不是面对问题本身" |
| "评价方案先问impact" | "独处时遇到未解决的冲突，不试图分析，而是反复回放对方最后那句话的语气" |

**规则编写格式**：`在[情境/触发条件]下，[具体认知或行为反应]`

林晓雨示例：
```json
"behavioral_rules": [
  "被当众否定后，不会当场反驳，而是在心里反复排练'如果我当时说了……'",
  "独处安静下来时，最近一次被伤害的场景会自动回放，每次回放都从对方的表情开始",
  "压力积累到一定程度时，会突然想做一件无关的小事（整理抽屉、重新叠衣服），不是逃避，是身体需要一个可以控制的东西",
  "接到母亲电话前会深呼吸，准备好'一切都好'的语气",
  "被夸奖时第一反应不是开心，而是怀疑对方是不是在客气",
  "哭之前会先确认周围没有人"
]
```

### 代码改动

**1. `core/profile.py`** — PersonProfile 新增字段

```python
behavioral_rules: List[str] = field(default_factory=list)
# 格式: "在[情境]下，[具体认知/情绪/身体反应]"
# 与 personality_traits 的区别：
#   personality_traits → OCC BIAS_MODIFIERS 情绪调制（保留）
#   behavioral_rules → 认知模块 prompt 注入（新增）
```

**2. `core/profile.py`** — `to_prompt_context()` 新增输出段

在 `lines` 列表中，`认知偏差` 之后追加：

```python
if self.behavioral_rules:
    lines.append("行为模式（最高优先级，生成内容必须与以下规则一致）：")
    for rule in self.behavioral_rules:
        lines.append(f"  · {rule}")
```

**3. `core/cognitive_modules/reactive.py`** — B2 system prompt 追加约束

在 `_SYS_B2` 末尾追加一段（仅当 profile 有 behavioral_rules 时动态拼接）：

```python
# reactive.py run() 中，b2_system 构建时
rules = ctx.profile.behavioral_rules
if rules:
    rules_text = "\n".join(f"  · {r}" for r in rules)
    b2_system += (
        f"\n\n行为模式约束（生成时刻链时必须遵守，优先级高于其他所有规则）：\n"
        f"{rules_text}"
    )
```

**注意**：不修改 `_SYS_B2` 常量本身，而是在 `run()` 方法中动态拼接到 `b2_system`。这样无 behavioral_rules 的 profile 不受影响。

**4. `core/cognitive_modules/drift.py`** — FragmentModule.run() 追加注入

在 `user` prompt 构建中（约 L126-136），personality 信息后追加：

```python
rules_ctx = ""
rules = ctx.profile.behavioral_rules
if rules:
    rules_ctx = "\n行为模式约束：" + "；".join(rules[:3])
```

注入到 `user` 字符串中。只取前 3 条，避免 prompt 过长。

**5. 不改动的地方**：
- `personality_traits` 保持不变，继续驱动 OCC BIAS_MODIFIERS
- `cognitive_biases` 保持不变，继续驱动情绪调制
- OCC 管线不注入 behavioral_rules（OCC 是情绪计算，不是行为模拟）

---

## B. inner_voice_style — 主角内心语言风格

### 问题

ANIMA 的 DES moments 中，`compressed_speech` 和 `expanded_speech` 是主角的内心语言。但当前 prompt 没有指定**这个人的内心语言听起来是什么样的**。

不同人的内心独白差异很大：
- 有人用第一人称自我对话（"我得…"）
- 有人用第二人称自我审判（"你又搞砸了"）
- 有人极度碎片化（半句话就断）
- 有人习惯性反问（"为什么每次都是我？"）
- 有人内心语言偏书面/偏口语

colleague-skill 的 L2 表达风格层虽然是对话场景的，但**内心语言也需要风格区分**这个思路是对的。

### 设计

```python
# profile.py 新增
inner_voice_style: str = ""
# 描述主角内心语言的特征，不超过 2 句话
# 例："内心独白使用第二人称自我审判（'你又……'），句子经常说到一半就断掉"
# 例："内心语言极度简洁，不超过五个字，像电报"
# 例："习惯用反问句式思考（'凭什么？''不是说好的吗？'），从不给自己答案"
```

林晓雨示例：
```json
"inner_voice_style": "内心独白在自我否定时切换为第二人称（'你又……''你以为你是谁'），平时用碎片化短句，情绪激动时句子会突然断在动词上"
```

科比示例：
```json
"inner_voice_style": "内心语言是命令式的，像教练在喊（'再来''不够'），极少用疑问句，自我对话时称自己为Mamba"
```

### 代码改动

**1. `core/profile.py`** — 新增字段（同 A 节）

**2. `core/cognitive_modules/reactive.py`** — B2 prompt 注入

在 `b2_system` 动态拼接中，behavioral_rules 之后：

```python
if ctx.profile.inner_voice_style:
    b2_system += (
        f"\n\n内心语言风格（compressed_speech 和 expanded_speech 必须体现）：\n"
        f"  {ctx.profile.inner_voice_style}"
    )
```

**3. `core/cognitive_modules/drift.py`** — FragmentModule 和 ChainModule

对所有生成 compressed_speech / expanded_speech 的模块注入。

在 `FragmentModule.run()` 的 `user` prompt 中追加：

```python
voice_style_ctx = ""
if ctx.profile.inner_voice_style:
    voice_style_ctx = f"\n主角内心语言风格：{ctx.profile.inner_voice_style}"
```

对 `ChainModule._build_step_prompt()` 同理追加。

**4. `core/cognitive_engine.py`** — reasoning_layer prompt 注入

`reasoning_layer()` 生成第一人称内心独白（≤80字），也需要遵循 inner_voice_style：

```python
if profile.inner_voice_style:
    prompt += f"\n\n内心语言风格：{profile.inner_voice_style}"
```

**5. 不改动的地方**：
- perception_layer 不改（输出是第三人称感知描述，不是内心语言）
- OCC / emotion_layer 不改（数值计算，不涉及文本风格）
- voice_intrusion 不改（那是别人的声音，不是主角的）

---

## C. subject_patterns — 关系中的主角行为模式

### 问题

当前 Relationship 描述的是**对方是什么样的**（典型话语、权力动态），不描述**主角在对方面前是什么样的**。

demo_profile.json 的关系数据能告诉引擎"陈总会说'这个方案完全跑偏了'"，但不能告诉引擎"林晓雨在陈总面前会不自觉压低声音"。

colleague-skill 的 L4 按角色类别（对上/对下/对平级）分层，但 ANIMA 的 per-person 建模更精准。改进方向是**在 per-person 的基础上增加主角侧的行为模式**。

### 设计

```python
# profile.py Relationship dataclass 新增字段
subject_patterns: List[str] = field(default_factory=list)
# 主角面对此人时的认知/情绪/行为模式
# 格式: "主角在[情境]下会[反应]"
```

林晓雨-陈总示例：
```json
{
    "name": "陈总",
    "role": "直属领导",
    "valence": -0.6,
    "power_dynamic": "权威型，评价即判决",
    "unresolved_conflicts": ["从不在私下给反馈，永远在公开场合否定"],
    "typical_phrases": ["这个方案完全跑偏了"],
    "subject_patterns": [
        "在陈总面前说话会不自觉压低音量，话到嘴边吞回去一半",
        "被陈总否定后不当场反驳，但回去后连续三天在脑中排练应该怎么回应",
        "准备给陈总看方案前会反复检查到无法停下来"
    ]
}
```

林晓雨-母亲示例：
```json
"subject_patterns": [
    "接妈妈电话前深呼吸三次，准备好'一切都好'的语气",
    "被问到婚事时会沉默五秒，然后转移话题，挂电话后会哭",
    "想主动打电话但每次拿起手机又放下"
]
```

### 代码改动

**1. `core/profile.py`** — Relationship dataclass 新增字段

```python
subject_patterns: List[str] = field(default_factory=list)
```

`from_dict()` 追加：
```python
subject_patterns=d.get("subject_patterns", []),
```

`to_prompt_line()` 追加（仅当有 subject_patterns 时）：
```python
if self.subject_patterns:
    line += f" | 主角面对此人时：{self.subject_patterns[0]}"
```

**2. `core/profile.py`** — `to_prompt_context()` 关系输出增强

在关系网络输出段（L148-153），对有 subject_patterns 的关系追加一行：

```python
if r.subject_patterns:
    lines.append(f"    主角面对{r.name}时：{'；'.join(r.subject_patterns[:2])}")
```

**3. `core/cognitive_modules/drift.py`** — social_rehearsal anchor 增强

`_get_social_pending_anchor()` 返回值增加 subject_patterns 信息：

```python
def _get_social_pending_anchor(ctx: ModuleContext) -> str:
    pending = ctx.profile.social_pending
    if pending:
        item = random.choice(pending)
        person = item.get("person", "")
        unresolved = item.get("unresolved", "")
        # 查找对应关系的 subject_patterns
        patterns_hint = ""
        for r in ctx.profile.relationship_objects:
            if r.name == person and r.subject_patterns:
                patterns_hint = f"\n主角面对{person}时的模式：{'；'.join(r.subject_patterns[:2])}"
                break
        return f"{person}（{unresolved}）{patterns_hint}"
    # ... fallback 逻辑不变
```

**4. `core/cognitive_engine.py`** — `_get_inner_voices()` 增强

当情绪触发某人的 voice_intrusion 时，同时注入主角面对此人的 subject_patterns：

```python
def _get_inner_voices(profile: PersonProfile, emotion_intensity: float) -> str:
    if emotion_intensity < 0.2:
        return ""
    voices = []
    for r in profile.relationship_objects:
        if r.valence < -0.1 and r.typical_phrases:
            phrases = "、".join(f'"{p}"' for p in r.typical_phrases[:2])
            voices.append(f"{r.name}的声音：{phrases}")
            # 新增：注入主角面对此人时的反应模式
            if r.subject_patterns:
                voices.append(f"  （听到这个声音时，主角会：{r.subject_patterns[0]}）")
        elif r.valence > 0.5 and r.typical_phrases and emotion_intensity > 0.4:
            voices.append(f"（渴望）{r.name}会怎么看我……")
    return "\n".join(voices)
```

---

## D. ResidualFeedback 修复

### 问题 1：骨架条目污染（已发生）

demo_profile.json 中已存在 4 个垃圾条目：
- `"睡眠中"` `"喘不过"` `"声音在"` `"耳边响"` — 全部 `role: "(自动检测)"`, `valence: 0.0`, 空 `typical_phrases`

虽然 2026-03-28 已加入停用词表 `_NAME_STOP_WORDS`，但停用词是手工维护的脆弱机制，无法覆盖所有误判。

### 解决方案：staging 区 + 准入门槛

**不直接写入 profile，而是写入 staging 文件。**

```python
# residual_feedback.py 改动

# 原逻辑：直接 append 到 profile_data["relationships"]
# 新逻辑：写入 output/{name}_detected_entities.json（staging 文件）

def _stage_new_entities(self, new_rels: list[str], profile_data: dict) -> None:
    """将检测到的新实体写入 staging 文件，不直接修改 profile。"""
    staging_path = os.path.join(
        os.path.dirname(self.profile_path),
        "..", "output",
        f"{profile_data['name']}_detected_entities.json"
    )
    existing = []
    if os.path.exists(staging_path):
        with open(staging_path) as f:
            existing = json.load(f)
    
    for name in new_rels:
        if not any(e["name"] == name for e in existing):
            existing.append({
                "name": name,
                "detected_at_tick": "post_run",
                "frequency": "pending_review",
                "status": "unreviewed"
            })
    
    with open(staging_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    
    print(f"[ResidualFeedback] {len(new_rels)} 个新实体写入 staging：{staging_path}")
```

cognitive_biases 和 memories 的写回逻辑保持不变（这两个字段的误判风险低得多——高频关键词和重复事件的置信度天然高于"人名检测"）。

### 问题 2：无版本回滚

ResidualFeedback 和 WritebackManager 都直接修改 profile，不保留历史。

### 解决方案：写入前自动备份

```python
# residual_feedback.py — _atomic_write() 前增加备份
import shutil

def _backup_before_write(self) -> str:
    """备份当前 profile 到 output/ 目录。"""
    backup_dir = os.path.join(os.path.dirname(self.profile_path), "..", "output")
    os.makedirs(backup_dir, exist_ok=True)
    import time
    ts = time.strftime("%Y%m%d_%H%M%S")
    name = os.path.basename(self.profile_path).replace(".json", "")
    backup_path = os.path.join(backup_dir, f"{name}_backup_{ts}.json")
    shutil.copy2(self.profile_path, backup_path)
    return backup_path
```

在 `analyze_and_update()` 的 `if updates:` 分支中，`_atomic_write()` 前调用。

WritebackManager 同理：在 `_flush()` 写入 `profile.memories` 后，调用 profile 的序列化保存前做备份（需要 WritebackManager 持有 profile_path，当前只持有 profile 对象——改为额外传入 path，或在 run.py 层统一管理备份）。

**推荐做法**：在 `run.py` 层统一管理，每次 run 开始时备份一次 profile，而不是在每次微写回时都备份。更简洁。

```python
# run.py — main() 开始处
shutil.copy2(profile_path, profile_path.replace(".json", f"_pre_run_{run_id}.json"))
```

### 问题 3：清理现有垃圾数据

demo_profile.json 中的 4 个垃圾关系条目需要手动清理：

```json
// 删除以下 4 个条目（role 为 "（自动检测）" 的全部删除）
{"name": "睡眠中", ...},
{"name": "喘不过", ...},
{"name": "声音在", ...},
{"name": "耳边响", ...}
```

---

## E. 自我强化回路抑制

### 问题

feedback loop：`profile → 引擎生成 tick → tick_history → ResidualFeedback 检测模式 → 写回 profile → 更强化的 tick → ...`

profile 中的"灾难化思维"偏差会驱动引擎在 tick_history 中频繁生成灾难化推理，ResidualFeedback 检测到这个"高频模式"后可能将其固化为新的 cognitive_biases 条目，进一步加剧。

### 解决方案：区分"确认"与"新发现"

修改 `_top_items()` 的逻辑：

```python
def _top_items(
    all_items: List[str],
    existing: List[str],
    total_ticks: int,
) -> List[str]:
    counter = Counter(all_items)
    results = []
    for item, count in counter.most_common():
        freq = count / total_ticks
        if freq < MIN_FREQUENCY:
            break
        # 已有：子串匹配 → 跳过（不重复确认）
        if any(item in e or e in item for e in existing):
            continue
        # 新增：检查是否与已有条目语义过近
        # 简单实现：如果新 item 中包含已有条目的任何关键词（≥3字），也跳过
        if any(
            any(kw in item for kw in _extract_nouns(e, min_len=3))
            for e in existing
        ):
            continue
        results.append(item)
        if len(results) >= MAX_NEW_PER_FIELD:
            break
    return results
```

这确保只写入**真正新发现**的模式，不强化已有模式。

### 进阶方案（Phase 3 候选）

给自动写入的条目打 `source` 标记：

```json
{
    "event": "某某事件",
    "importance": 0.5,
    "source": "auto_writeback",
    "created_tick": 15
}
```

在 prompt 注入时，`source: "auto_writeback"` 的条目权重低于手工编写的条目。防止自动检测的"低置信度"条目与作者精心设计的"高置信度"条目平权竞争。

---

## F. 用户修正机制（记录，暂缓实施）

colleague-skill 的 correction_handler 允许用户说"他不会这样"，自动转为规则追加到 Correction 层，优先级最高。

ANIMA 不是 chatbot，没有对话交互界面。但可以设计一个离线修正流程：

```bash
# 用户观察意识流输出后，在 profile 中追加 corrections 字段
"corrections": [
    {"rule": "她不会在外人面前哭，即使独处也会先确认没有人", "added": "2026-04-07"},
    {"rule": "她的反刍不会超过三天，第四天会用工作把自己填满", "added": "2026-04-07"}
]
```

corrections 在所有模块 prompt 中作为最高优先级约束注入（类似 behavioral_rules，但来源是用户修正，优先级更高）。

**暂缓原因**：当前优先级是引擎质量和视觉化 demo，不是用户交互。但 `corrections` 字段可以先在 PersonProfile 中预留。

---

## 与现有架构的层次对照

```
用户意图层  run.py
     ↓
编排层      core/cognitive_engine.py
            ├── perception_layer:  注入 behavioral_rules（via to_prompt_context）+ speech_style（via _build_relationship_context）  [改动 A, H]
            ├── reasoning_layer:   注入 inner_voice_style + inner_voices with subject_patterns + speech_style  [改动 B, C, H]
            └── emotion_layer:     不改（OCC 继续用 personality_traits + cognitive_biases）
     ↓
处理层      core/cognitive_modules/
            ├── reactive.py:       B2 system prompt 动态追加 behavioral_rules + inner_voice_style + voice_intrusion speech_style  [改动 A, B, H]
            └── drift.py:          FragmentModule/ChainModule prompt 追加 behavioral_rules + inner_voice_style  [改动 A, B]
                                   social_rehearsal anchor 增强 subject_patterns + speech_style  [改动 C, H]
     ↓
Profile层   core/profile.py:       新增 behavioral_rules / inner_voice_style / Relationship.subject_patterns / Relationship.speech_style  [改动 A, B, C, H]
            core/trait_to_rules.py: personality_traits → behavioral_rules 翻译表  [改动 G]
            core/residual_feedback.py:  staging 区 + 备份 + 去强化  [改动 D, E]
     ↓
基础层      agents/base_agent.py   不改
```

---

## G. 行为规则化 — personality_traits → behavioral_rules 系统性转化

### 问题

A 节定义了 `behavioral_rules` 字段，但只说了"手工编写"。如果每个 profile 都需要人工从零写行为规则，门槛太高。

colleague-skill 用一张**标签翻译表**解决这个问题："甩锅高手" → 自动展开为 3-5 条行为规则。ANIMA 需要等价的**认知域翻译机制**，把现有的 `personality_traits` 标签系统性转化为 `behavioral_rules`。

### 设计：认知特质翻译表

```python
# 新建 core/trait_to_rules.py

TRAIT_RULE_MAP: dict[str, list[str]] = {
    # ── 认知/情绪特质 ──
    "完美主义": [
        "开始做一件事之前，会在脑中反复推演所有可能出错的环节，直到确认万无一失才动手",
        "完成一件事后不会感到满足，而是立刻注意到还可以改进的地方",
        "别人说'差不多就行了'时，身体会产生一种抵触感，即使嘴上不说",
    ],
    "内向": [
        "社交场合中能量持续消耗，独处时缓慢恢复",
        "想说的话会在脑中排练多次，实际开口时只说出三分之一",
        "被突然问到观点时，第一反应是沉默，不是因为没想法，是需要时间组织",
    ],
    "高度共情": [
        "看到别人尴尬或痛苦时，自己身体会产生相似的不适感（胸闷、手心出汗）",
        "与人交谈时会不自觉地模拟对方此刻的内心状态",
        "很难对别人说'不'，因为能清晰地预见对方被拒绝后的失落",
    ],
    "不善拒绝": [
        "接受了不想做的事后，不会当场表达，而是在独处时对自己生闷气",
        "拒绝的话在嘴边，但看到对方的表情就自动吞回去",
    ],
    "习惯独自承受": [
        "遇到困难时第一反应是'不要让别人知道'",
        "别人问'你还好吗'时，会条件反射地说'还好'，即使不好",
        "哭之前会先确认周围没有人",
    ],
    "习惯性自我否定": [
        "被夸奖时第一反应是怀疑对方是不是在客气",
        "做对了一件事会归因于运气，做错了一件事会归因于自己能力不足",
    ],

    # ── 认知偏差（对应 cognitive_biases，但展开为行为层）──
    "灾难化思维": [
        "一件小事出错后，脑中会自动推演最坏的结果链条（这件事没做好→领导不满→被边缘化→失业）",
        "晚上躺在床上时，白天的负面事件会在脑中放大三倍",
    ],
    "过度自责": [
        "别人的不开心会被归因于'是不是我哪里做错了'",
        "出了集体问题时，第一反应是在自己身上找原因",
    ],
    "回避冲突": [
        "发现对方明显做错了，也不会当面说，而是找一个间接的方式暗示",
        "争吵即将发生时，身体先于思维行动——离开现场、低头、沉默",
    ],

    # ── 竞争/外向型特质（科比等角色）──
    "极度竞争性": [
        "看到别人的成就时，第一反应不是欣赏，而是在心里衡量自己和对方的差距",
        "失败后不会沮丧太久，而是立刻在脑中拆解失败的原因，规划下一次怎么赢",
    ],
    "自我隔离": [
        "情绪激动时选择独处而非倾诉，认为独处是力量的来源",
        "与人在一起时保持一层薄薄的距离，不是因为不在乎，是因为习惯了不被完全理解",
    ],
}
```

### 使用方式

**方式 1：Profile 创建时自动展开（推荐）**

在 `profile_builder`（未来）或手工创建 profile 时，调用翻译函数：

```python
def expand_traits_to_rules(
    personality_traits: list[str],
    cognitive_biases: list[str],
) -> list[str]:
    """将特质标签展开为行为规则。未匹配的标签跳过。"""
    rules = []
    for trait in personality_traits + cognitive_biases:
        for key, key_rules in TRAIT_RULE_MAP.items():
            if key in trait:  # 子串匹配，兼容"灾难化思维倾向"等变体
                rules.extend(key_rules)
                break
    return rules
```

**方式 2：Profile 加载时动态合并（备选）**

不修改 profile JSON，在 `PersonProfile` 初始化后动态合并：

```python
# profile.py — PersonProfile.__post_init__() 或加载逻辑中
if not self.behavioral_rules:
    from core.trait_to_rules import expand_traits_to_rules
    self.behavioral_rules = expand_traits_to_rules(
        self.personality_traits, self.cognitive_biases
    )
```

**推荐方式 1**：显式写入 profile JSON，因为：
- 用户可以审阅和修改自动生成的规则
- 避免运行时依赖翻译表（翻译表未来可能更新，导致同一 profile 不同 run 的行为不一致）
- behavioral_rules 一旦确定就应该是 profile 的稳定组成部分

### 与 personality_traits 的关系（精确分工）

```
personality_traits（保留，不动）
    ↓ 驱动
    OCC BIAS_MODIFIERS → 情绪向量调制
    to_prompt_context() → 各层 prompt 的"性格特质"段

behavioral_rules（新增）
    ↓ 来源
    personality_traits + cognitive_biases 经翻译表展开
    + 用户手工补充的人物特有规则（翻译表覆盖不到的）
    ↓ 驱动
    reactive B2 / drift 模块 / reasoning_layer → 意识流内容约束
```

personality_traits 管**情绪怎么变**，behavioral_rules 管**行为怎么表现**。两者不冲突。

### 翻译表的扩展原则

- 每个特质展开为 2-3 条行为规则，不超过 5 条
- 规则格式统一为"在[情境]下，[具体反应]"
- 反应必须包含认知/身体/行为三层中至少一层的具体表现
- 禁止使用形容词描述（"变得焦虑"），必须是可观察的动作（"开始反复检查手机"）
- 翻译表是**起点**，每个具体 profile 都应该有用户手工补充的个人化规则（翻译表给出的是通用模式，不是全部）

---

## H. 表达风格建模 — 关系人物的语言差异化

### 问题

当前关系人物只有 `typical_phrases`（说了什么），没有 `speech_style`（怎么说）。

在 voice_intrusion 中，陈总的声音和母亲的声音应该听起来截然不同：
- 陈总：简短、命令式、不解释原因、带质问
- 母亲：长句、情感包裹、以关心的形式施压、带叹气

但当前 prompt 只给了原话内容，LLM 在生成 voice_intrusion 的 content 时没有风格指导，可能让所有人的声音听起来都像"AI 在说话"。

### 设计

**Relationship dataclass 新增字段**：

```python
speech_style: str = ""
# 这个人说话的方式（1 句话描述）
# 例："简短、命令式、不解释原因、总以反问结尾"
# 例："絮叨、以关心包裹否定、常用'你这孩子'开头、句尾带叹气"
# 例："温和、不评判、总留余地、用'要不要'而不是'你应该'"
```

林晓雨各关系示例：

```json
{
    "name": "陈总",
    "speech_style": "极短句、命令式、从不解释理由、经常以反问结尾（'有没有想清楚？'）"
},
{
    "name": "母亲",
    "speech_style": "长句、以关心包裹否定（'我是为你好'）、常用'你这孩子'开头、句尾语气带叹息"
},
{
    "name": "前男友李杨",
    "speech_style": "平静但疏远、像在陈述事实而非吵架、用'你太……了'句式"
},
{
    "name": "张明",
    "speech_style": "轻松、口语化、常用'没事的'开头、善用具体小事转移注意力（'要不要买杯奶茶'）"
}
```

### 代码改动

**1. `core/profile.py`** — Relationship dataclass 新增

```python
speech_style: str = ""
```

`from_dict()` 追加：
```python
speech_style=d.get("speech_style", ""),
```

`to_prompt_line()` 追加：
```python
if self.speech_style:
    line += f" | 说话方式：{self.speech_style}"
```

**2. `core/cognitive_engine.py`** — `_build_relationship_context()` 增强

L141-152，对每个关系的输出增加 speech_style：

```python
def _build_relationship_context(profile: PersonProfile, emotion_intensity: float) -> str:
    rel_objs = profile.relationship_objects
    if not rel_objs:
        return ""
    lines = ["重要关系网络（这些人此刻可能浮现在脑海中）："]
    for r in rel_objs:
        line = f"  · {r.to_prompt_line()}"
        if emotion_intensity > 0.3 and r.typical_phrases:
            phrases = "、".join(f'"{p}"' for p in r.typical_phrases[:2])
            line += f"\n    Ta的声音：{phrases}"
            # 新增：声音的风格约束
            if r.speech_style:
                line += f"\n    说话方式：{r.speech_style}"
        lines.append(line)
    return "\n".join(lines)
```

**3. `core/cognitive_engine.py`** — `_get_inner_voices()` 增强

L155-165，voice_intrusion 触发时注入 speech_style：

```python
def _get_inner_voices(profile: PersonProfile, emotion_intensity: float) -> str:
    if emotion_intensity < 0.2:
        return ""
    voices = []
    for r in profile.relationship_objects:
        if r.valence < -0.1 and r.typical_phrases:
            phrases = "、".join(f'"{p}"' for p in r.typical_phrases[:2])
            style_hint = f"（{r.speech_style}）" if r.speech_style else ""
            voices.append(f"{r.name}的声音{style_hint}：{phrases}")
            if r.subject_patterns:
                voices.append(f"  （听到这个声音时，主角会：{r.subject_patterns[0]}）")
        elif r.valence > 0.5 and r.typical_phrases and emotion_intensity > 0.4:
            voices.append(f"（渴望）{r.name}会怎么看我……")
    return "\n".join(voices)
```

**4. `core/cognitive_modules/drift.py`** — social_rehearsal chain prompt 增强

social_rehearsal 是模拟对话链（我说→Ta反应→我再说→结果），对方的反应需要遵循 speech_style。

`_get_social_pending_anchor()` 返回值追加 speech_style：

```python
def _get_social_pending_anchor(ctx: ModuleContext) -> str:
    pending = ctx.profile.social_pending
    if pending:
        item = random.choice(pending)
        person = item.get("person", "")
        unresolved = item.get("unresolved", "")
        # 查找对应关系的 subject_patterns 和 speech_style
        extra = ""
        for r in ctx.profile.relationship_objects:
            if r.name == person:
                if r.subject_patterns:
                    extra += f"\n主角面对{person}时的模式：{'；'.join(r.subject_patterns[:2])}"
                if r.speech_style:
                    extra += f"\n{person}的说话方式：{r.speech_style}"
                break
        return f"{person}（{unresolved}）{extra}"
    rels = ctx.profile.relationship_objects
    if rels:
        r = rels[0]
        style = f"，说话方式：{r.speech_style}" if r.speech_style else ""
        return f"{r.name}（{r.role}{style}）"
    return ""
```

**5. `core/cognitive_modules/reactive.py`** — B2 voice_intrusion 约束增强

B2 生成 voice_intrusion 时，需要知道 source 人物的说话方式。在 `b2_system` 动态拼接中追加关系语音风格信息：

```python
# reactive.py run() 中，构建 b2_system 后
rel_styles = []
for r in ctx.profile.relationship_objects:
    if r.speech_style:
        rel_styles.append(f"  · {r.name}：{r.speech_style}")
if rel_styles:
    b2_system += (
        "\n\nvoice_intrusion 风格约束（生成某人声音时必须遵守其说话方式）：\n"
        + "\n".join(rel_styles)
    )
```

### 与 inner_voice_style（B节）的关系

```
inner_voice_style（主角的内心语言风格）
    ↓ 控制
    compressed_speech / expanded_speech 的语言风格
    reasoning_layer 内心独白的风格

speech_style（每个关系人物的说话方式）
    ↓ 控制
    voice_intrusion 的语言风格
    social_rehearsal 中对方回应的语言风格
```

两者分别控制意识流中**两类不同的声音**：主角自己的内心语言 vs 他人声音的侵入。结合使用时，同一段意识流中可以清晰区分"这是主角在想" vs "这是陈总的声音在回响" vs "这是母亲的声音在责备"。

---

## 不做的事

| 不做 | 原因 |
|------|------|
| colleague-skill Work Skill（技术能力层）| ANIMA 模拟内心世界，不是工作能力 |
| 企业文化标签（"字节范""阿里味"）| 职场行为模式，不是认知模式 |
| L4 按角色类别分层（对上/对下/对平级）| ANIMA 的 per-person 建模更精准 |
| 数据采集管线（飞书/钉钉 API）| 当前优先级是引擎 + 视觉化，用户端全部暂缓 |
| 认知风格标签系统 | 降低用户门槛的设计，属于用户端，暂缓 |
| colleague-skill 的对话式调用（/{slug}）| ANIMA 不是 chatbot |

---

## 实施顺序建议

**第一批（Profile 字段 + 数据清理 + 翻译表）**：
1. `core/profile.py` 新增 `behavioral_rules` / `inner_voice_style` / `Relationship.subject_patterns` / `Relationship.speech_style` / `corrections`（预留）
2. 新建 `core/trait_to_rules.py` — 认知特质翻译表
3. 清理 demo_profile.json 中 4 个垃圾关系条目
4. 为林晓雨补充新字段：behavioral_rules（翻译表展开 + 手工补充）、inner_voice_style、各关系的 subject_patterns 和 speech_style
5. 为科比补充新字段（同上）

**第二批（Prompt 注入 — 行为规则 + 表达风格）**：
6. `reactive.py` B2 动态拼接 behavioral_rules + inner_voice_style + voice_intrusion speech_style
7. `drift.py` FragmentModule / ChainModule prompt 注入 behavioral_rules + inner_voice_style
8. `drift.py` social_rehearsal anchor 增强 subject_patterns + speech_style
9. `cognitive_engine.py` reasoning_layer 注入 inner_voice_style
10. `cognitive_engine.py` `_build_relationship_context()` 增强 speech_style
11. `cognitive_engine.py` `_get_inner_voices()` 增强 subject_patterns + speech_style

**第三批（进化机制修复）**：
12. ResidualFeedback 改 staging 区写入（relationships）
13. run.py 增加 run 前 profile 备份
14. ResidualFeedback `_top_items()` 增加去强化逻辑

**验证**：每批改完跑 5 轮 run，对比改动前后意识流输出的差异。重点关注：
- behavioral_rules 是否让同一人物的不同 run 产生更一致的行为模式
- inner_voice_style 是否让 compressed_speech 有明显的个人特征
- speech_style 是否让不同人的 voice_intrusion 听起来有明显风格差异
- subject_patterns 是否让 social_rehearsal 更贴合人物关系

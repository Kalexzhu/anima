# 2026-03-28 科比场景接入 + 输出质量迭代

## 概要

本次迭代做了两件事：
1. 新建 `scenarios/kobe_2020/` 场景，完整接入 viz 可视化管线
2. 根据首次运行（kobe_2020_02，9 ticks）的质量分析，对认知模块做了系统性修复

---

## 一、科比场景（kobe_2020）

### 文件结构

```
scenarios/kobe_2020/
├── kobe_profile.json     ← 完整 Profile（22条记忆，6段关系）
├── timeline.json         ← 15 tick 时间线（2020-01-25 07:00 → 2020-01-26 09:47）
└── runner.py             ← 旁路场景跑手（绕过 WorldEngine，直接注入 BehaviorState）
```

### 时间线设计

- Tick 1-8：2020-01-25，每 tick 约 2 小时（清晨独醒 → 后院训练 → 午餐 → 教练会议 → 查看ESPN → 看比赛 → 目击LeBron破纪录 → 书房整理）
- Tick 9：2020-01-26 清晨，与 Gianna 共进早餐（2.75 小时）
- Tick 10-15：飞行阶段，每 tick 约 10 分钟（起飞 → 穿越盆地 → 进入山谷走廊 → 零能见度爬升 → 坠机前最后时刻）

### Profile 构建原则

严格遵循 `docs/profile-field-rules.md`：
- 所有记忆（22条）必须同时满足：具体时间/地点锚定、有情绪留痕、有文献记录/引用
- 每条记忆带 `source` 字段（Dear Basketball / Kobe Facebook帖子 / Shaq Uncut / ESPN档案等）
- `typical_phrases` 只使用有文献记录的原话，不做推断
- A 类字段（全量注入）严格控制条数在规格范围内

### viz 接入

`runner.py` 在每个 tick 结束后调用：
```python
viz_data = render_for_viz(tick, event, behavior, emotion, module_outputs)
write_tick_viz(run_id=run_id, tick=state.tick, viz_data=viz_data)
```
与 `run.py` 的集成方式完全一致，浏览器可实时预览进行中的场景。

---

## 二、输出质量问题诊断（基于 kobe_2020_02）

### 问题一：代词错误 "科比说，「...」"

**根源**：`social_rehearsal` 模块用 `voice_intrusion` 类型模拟"我说什么"那一步，LLM 填了 `source="科比"`，渲染函数输出 `"科比说，「...」"`。

**修复**（`drift.py`）：
```
主角自己说的话：用 compressed_speech / expanded_speech，不加姓名标注
对方说的话：用 voice_intrusion，source = 对方名字
```

### 问题二：漂浮文字重复（同一场景反复出现）

**根源**：
- `daydream`（chain_length=5）和 `future`（chain_length=4）都是链条型模块，每步延续前一步
- 若锚点是"Mamba Academy + Gianna 训练"，5 步全会停在同一场景
- 两个模块合计产生 9 个几乎相同的视觉片段

**修复**（`drift.py`）：
- `daydream` chain_length：5 → 4
- `future` chain_length：4 → 3
- 两个模块均加入约束："每步必须切换感官维度或时间节点，禁止在同一场景连续停留"
- `FragmentModule` prev_ctx 指令：从"可延续，也可另起"改为"必须引入新视角，禁止重复"

### 问题三：Tick 间缺乏发展（情节驱动失效）

**根源**：B1（锚点选择步骤）的 user message 中 profile 在最前，当前事件在后面，LLM 注意力偏向前段，导致无论 timeline 事件是教练会议还是 LeBron 破纪录，B1 总选"Gianna 脚踝"作为当轮锚点。

表现：Tick 4（教练会议）/ Tick 7（LeBron 破纪录）/ Tick 8（确认直升机天气）的输出几乎都是"Gianna 训练场"内容，看不出 timeline 发展。

**修复**（`reactive.py`）：

1. B1 system prompt 加优先级规则：
   > "当前事件不为空时，锚点必须与当前事件直接相关；只有当前事件为空或极度日常时，才从 profile 长期偏好中选取锚点"

2. B1 user message 重排：当前事件置顶，profile 下移：
   ```
   前：人物档案 → 当前事件 → ...
   后：【当前事件（优先参考）】 → 感知焦点/情绪 → 人物档案 → ...
   ```

---

## 三、锚点多样性扩展（kobe_profile.json）

**问题**：`daydream_anchors` 中第 4 条（"陪Gianna练球时她接球的声音"）是所有 Mamba Academy 场景的主要来源，单一锚点权重过高。

**扩展**（5 → 8 条，新增非篮球场景）：
- Granity Studios 书房，写稿凌晨，台灯一圈黄
- Newport Beach 后院，Capri 刚学走路，脚踩草皮那一下
- 奥斯卡台上，聚光灯正上方打下来，奖杯金属底座是凉的

**`rumination_anchors`**（6 → 8 条，新增）：
- "Mamba out——那三个字说出去的那一秒之后的安静"
- "跟腱断裂的声音，像被棒球棒打到腿上那一下"

---

## 四、social_rehearsal 锚点轮换

**问题**：`_get_social_pending_anchor` 固定取 `pending[0]`，9 个 tick 都在排演同一个社交情境（LeBron 私信）。

**修复**：改为 `random.choice(pending)`，让三条社交待定事项（LeBron / Mamba Academy 教练聘任 / Granity Studios 编辑进度）都有机会出现。

---

## 五、runner 新增 `--max-ticks`

```bash
python3 scenarios/kobe_2020/runner.py --max-ticks 5
```

用于快速测试前 N 个 tick，不必跑完全部 15 tick。

---

## 文件改动清单

| 文件 | 改动类型 |
|------|---------|
| `core/cognitive_modules/drift.py` | 修复 social_rehearsal 代词；daydream/future 链条缩短+多样性约束；FragmentModule prev_ctx 指令加强；social_rehearsal 锚点随机化 |
| `core/cognitive_modules/reactive.py` | B1 event 优先级规则；B1 user message 重排 |
| `scenarios/kobe_2020/kobe_profile.json` | daydream_anchors +3；rumination_anchors +2 |
| `scenarios/kobe_2020/runner.py` | viz 接入；`--max-ticks` 参数 |
| `scenarios/kobe_2020/timeline.json` | 新建（15 ticks） |

---

## 待验证

下次运行 `--max-ticks 5` 后，重点检查：
1. Tick 4（教练会议）的 reactive 锚点是否切换到"标准不能稀释"相关内容
2. social_rehearsal 是否不再出现"科比说，「...」"
3. daydream/future 是否在 5 步内出现了多个不同场景
4. 跨 tick 的情绪/内容发展曲线是否可读

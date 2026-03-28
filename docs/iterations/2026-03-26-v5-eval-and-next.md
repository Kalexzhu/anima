# v5 首轮评估 + 下一步计划

**日期**：2026-03-26
**状态**：评估完成，待实现
**依据**：run_林晓雨_12.txt（10轮）

---

## 评估结论

### ✅ 运转良好

| 模块 | 表现 | 代表轮次 |
|------|------|----------|
| reactive | DES 类型准确（body_sensation / compressed_speech / voice_intrusion），格式心理真实 | tick 1、3、9 |
| counterfactual | 具体感官化分叉点（成都格子间、天府大道路灯），符合上行反事实定义 | tick 4、9 |
| rumination | "两周。两周。放在那里了。两周。" + 身体感知锚定，显性循环成立 | tick 9 |

### ❌ 需要修的问题

**P0 — future 模块输出是行动计划，不是思维流**

> "备忘录新建一条，标题就写'逻辑'，不写日期不写名字，先列他说的三条..."

system prompt 没有阻止它写操作步骤。应改为「情境性未来思维」——有时间地点、身体感知、对他人反应的想象，而非 GTD 清单。

**P0 — 情绪初始强度为 0.00**

Profile `current_physical_state = "心跳很快，手有点抖，强忍着没有哭"`，但 tick 1 情绪强度是 0.00。`ThoughtState` 初始化为空时，emotion_layer 拿不到身体状态信息。需要在 `run.py` 里用 profile 的 `current_physical_state` 播种初始 EmotionState，或在 tick 1 的 perception 里注入物理状态。

**P1 — 梦境修辞过重（ASLEEP tick 5~8）**

> "碎冰如纸片般簌簌剥落"、"萤火虫拼出母亲晾衣绳上滴水的蓝布衫"

`_SYS_DREAM` 是纯诗意写作 prompt，无心理模拟约束。用户决策：**删除梦境内容生成，ASLEEP 轮次改为静默**。

**P2 — anger 全程为 0**

被当众公开否定，anger 应该存在但持续缺席。OCC 评估可能把羞辱情境映射到 fear/disgust 而跳过 anger。待排查 OCC 到 Plutchik 的映射规则。

**P3 — daydream 链条未出现**

9 轮里没有出现"咖啡链条"式感官漂移。原因：情绪强度偏高，drift_sampler 将 rumination/counterfactual 权重排在 daydream 之前。属正常机制行为，需要角色情绪平静后才能观察到。

---

## 下一步实现计划

### 改动 1：新增 `imagery` 模块（替代梦境）

**动机**：输出中偶发的诗意画面感觉对，但不应绑定在睡眠时段。改为常驻片段型模块，随时浮现。

**规格**：
- 类型：`FragmentModule`（与 rumination 等同级）
- 名称：`imagery`
- 输出：1~2 个 `visual_fragment` DES moment，格式统一
- System prompt 基于 `_SYS_DREAM` 改写：
  - 去掉"梦中"框架 → 改为「意识边缘浮现的感知画面」
  - 去掉"60~120字散文" → 改为 DES moment JSON
  - 保留：非线性、混合残留记忆与欲望、感官丰富、不要标注来源

**ASLEEP 路径**：删除 `_dream_arbiter` 调用，改为静默输出 `"（睡眠中）"`，仅保留情绪衰退。

### 改动 2：future 模块 system prompt 修正

当前问题：生成操作性计划步骤。
修改方向：
- 强调「脑中闪现的画面/感知」，不是计划清单
- 加"禁止写操作步骤、待办项、行动序列"约束
- 加"必须有感官细节（光线、声音、温度）"约束
- 参考 Atance & O'Neill (2001)：是「心理时间旅行」，脑中「到达」那个未来场景，而非规划如何到达

### 改动 3 — 情绪初始播种

在 `run.py` 主循环前，根据 profile 的 `current_physical_state` 和 `current_situation` 做一次快速情绪估算，播种初始 `EmotionState`，不让 tick 1 从强度 0.00 开始。

### 改动 4 — anger 缺失排查（OCC/DUTIR 映射）

羞辱情境（被当众否定）下 anger 全程为 0，只有 fear/disgust/sadness。
排查路径：
1. 检查 `occ.py` 的 `occ_to_plutchik()` 映射：`SelfAccountability` + `Reproach` 事件是否有 anger 输出路径
2. 检查 `_apply_dutir_calibration()`：DUTIR 是否把 anger 方向判定为负向后主动压低
3. 若确认映射缺失，在 `occ_to_plutchik()` 补充"当众羞辱/权威否定"情境的 anger 激活规则

---

## 文件影响范围

| 文件 | 改动 |
|------|------|
| `core/cognitive_modules/drift.py` | 新增 `imagery` 模块（`create_drift_modules()` 末尾追加） |
| `core/cognitive_engine.py` | ASLEEP 路径删除 `_dream_arbiter`；future prompt 约束；`imagery` 加入采样池 |
| `run.py` | 初始情绪播种 |
| `core/occ.py` | anger 映射规则排查与补充 |

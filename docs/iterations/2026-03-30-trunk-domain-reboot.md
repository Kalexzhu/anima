# 2026-03-30 · Trunk 本体论重构 + 选择算法升级

## 背景

Phase A 首轮评估（run_林晓雨_02，10 轮）暴露两个根本性问题：

1. **Trunk 本体论错误**：提取出的 4 个 Trunk 全部指向同一个心理元主题（自我价值感），
   只是同一维度的 4 个切面，互相不独立。
   结果：无论算法如何选择，生成的内容都是同一篇文章。

2. **Winner-Take-All 垄断**：贪心选最高分 Trunk，一旦某 Trunk 首先得分最高，
   激活正反馈（urgency +0.04）使它继续领先，最终 trunk_01 独占 10/10 轮。

---

## 核心决策

### D-6：Trunk 是生命域，不是心理模式

**错误认知**（改之前）：Trunk = 长期心理张力（底层心理矛盾）

**正确认知**（改之后）：Trunk = 一个人当前正在经历的某个生命领域里的具体未竟之事

| 好的 Trunk（生命域 + 具体处境） | 坏的 Trunk（心理元主题） |
|---|---|
| 做了两周的方案被当众否定，她不知道留下来还是离开 | 努力换不来认可，使她对自身价值产生根本性怀疑 |
| 前男友说"跟你在一起喘不过气"，分手两个月了还没有内化完 | 我的存在是负担 |
| 在北京攒了 3 年钱，不知道继续留还是回成都 | 完美壳下的自我消耗 |

生命域正交保证：work / romance / family / identity / friendship / health / finance / home
同一 domain 只保留 urgency 最高的一个（去重）。

**为什么这样更好**：
- 生命域正交 → 不同 Trunk 能独立生成完全不同类型的外部事件
- 心理元主题收敛 → 换哪个都是同一篇文章

### D-7：Softmax 概率选择 + Recency Penalty（换气机制）

**问题**：贪心选最高分 → 正反馈锁死 → 多 Trunk 等于 1 Trunk

**解法**：Softmax 概率加权 + Recency Penalty

```python
# Recency Penalty：距上次激活越近，得分折扣越大
recency_penalty = exp(-ticks_since / 4.0)   # 半衰期 4 tick
adjusted = base * (1.0 - 0.75 * recency_penalty)  # 最大75%折扣

# Softmax（temperature=0.25）：有偏好但不锁死
exps = [exp((s - max_s) / 0.25) for s in scores]
best = random.choices(active, weights=probs, k=1)[0]
```

心理学含义：刚在某个生命域上停留过后，注意力自然漂向另一个域
（"换气"），不是因为问题解决了，而是认知需要切换焦点。

**参数选择理由**：
- `RECENCY_HALFLIFE = 4.0`：4 tick 内同一 Trunk 被反复选中的概率大幅降低
- `RECENCY_WEIGHT = 0.75`：刚激活后立刻选中它的有效概率 ≈ 25%（不是 0，但很低）
- `TEMPERATURE = 0.25`：保留 urgency 优先级，但最高urgency Trunk不锁死

---

## 实现

### 改动：`core/world_state.py`

- 新增 `VALID_DOMAINS` frozenset（8 个生命域）
- `Situation` dataclass 新增 `domain: str` 字段
- `get_trunk_context(emotion, current_tick=0)`：接受 `current_tick` 参数，
  改 Softmax 选择，加 Recency Penalty
- `_extract_trunks()`：
  - Prompt 完全重写：要求按生命域提取，描述"具体未竟之事"而非心理模式
  - 新增 domain 字段；同域去重（保留 urgency 最高）；domain 透明注入 context_str
  - system prompt 明确：禁止写心理元主题
  - `max_tokens` 800 → 1000（为更丰富的描述留空间）

### 改动：`core/world_engine.py`

- `_generate_thread_event`：`get_trunk_context(state.emotion, state.tick)`
- `_generate_open_event`：同上

---

## 验证计划

跑 10 轮（`python3 run.py examples/demo_profile.json --max-ticks 10`）：

1. **Trunk 提取质量**：3 个 Trunk 是否属于不同生命域（work / romance / identity 等）
2. **多线交替**：10 轮中被激活的 Trunk 是否有至少 2 个，而非 1 个垄断
3. **事件类型多样**：工作域事件 vs 感情域事件 vs 自我方向事件，是否能明显区分

---

## 未决事项

- Recency Penalty 参数（halflife / weight / temperature）待根据实测结果调整
- domain 字段目前不参与情绪共鸣计算（`_emotion_resonance` 只用 tags）；
  未来可考虑 domain-level 情绪映射补充 tag 系统
- Thread urgency 恒为 1.00 问题（NarrativeThreadManager 单调递增）未处理，
  导致 action_type 始终为 confront；可在后续迭代中为 Branch 加自然衰退

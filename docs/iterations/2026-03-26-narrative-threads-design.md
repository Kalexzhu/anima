# 叙事线索系统 — 架构设计

**日期**：2026-03-26
**问题**：系统无状态，重复输出，情绪/事态不发展
**根本原因**：WorldEngine 用情绪值决定事件类型，情绪稳定后输入退化
**治本方案**：引入持久化叙事线索，WorldEngine 由"响应情绪"改为"推进故事"

---

## 核心思路

```
旧：情绪值 → [随机事件类型] → 事件
新：最高urgency线索 → [推进该线索的事件] → 事件 + 线索状态更新
```

角色的行动结论（write-back）可以关闭线索或开启新线索，形成真正的叙事闭环：
```
事件 → 角色反应 → 行动决定 → 世界变化 → 新事件
```

---

## 数据结构

### narrative_state.json（运行时文件，与 profile 分离）

```json
{
  "threads": [
    {
      "id": "t001",
      "description": "陈总今天当众否定了她做了两周的方案",
      "category": "work",
      "urgency": 0.8,
      "status": "open",
      "tick_opened": 0,
      "tick_resolved": null,
      "resolution": null
    },
    {
      "id": "t002",
      "description": "李杨分手留下的话——「跟你在一起我喘不过气」",
      "category": "relationship",
      "urgency": 0.5,
      "status": "open",
      "tick_opened": 0,
      "tick_resolved": null,
      "resolution": null
    },
    {
      "id": "t003",
      "description": "妈妈的电话一直没回，知道打过去会被问婚事",
      "category": "family",
      "urgency": 0.35,
      "status": "open",
      "tick_opened": 0,
      "tick_resolved": null,
      "resolution": null
    },
    {
      "id": "t004",
      "description": "想换工作但怕找不到更好的，这个念头一直悬着",
      "category": "self",
      "urgency": 0.3,
      "status": "open",
      "tick_opened": 0,
      "tick_resolved": null,
      "resolution": null
    }
  ]
}
```

**字段说明：**
- `category`：work / relationship / family / self / desire（影响事件生成的上下文风格）
- `urgency`：0.0~1.0，每轮自动 +0.05（capped 1.0），角色处理后降低或关闭
- `status`：open / resolved（只有 open 的线索参与选择）

---

## 新组件：NarrativeThreadManager（`core/narrative.py`）

```python
class NarrativeThreadManager:
    def __init__(self, state_path: str)

    def get_active_threads(self) -> list[dict]
    # 返回所有 status=open 的线索，按 urgency 降序

    def get_top_thread(self) -> dict | None
    # 返回最高urgency的open线索

    def tick_urgency(self) -> None
    # 每轮自动递增所有open线索的urgency

    def process_action(self, conclusion: str, current_tick: int) -> None
    # 角色行动结论 → LLM判断 → 关闭/新建/修改线索
    # 立刻执行，不等5轮write-back批次

    def add_thread(self, description: str, category: str, urgency: float, tick: int) -> None
    # WorldEngine或process_action中新建线索

    def save(self) -> None
    # 原子写入 narrative_state.json
```

**process_action 的 LLM 判断 prompt：**
```
当前活跃线索列表（id + description）
角色刚做出的行动决定：{conclusion}

判断：
1. 这个行动是否关闭了某条线索？（要求：直接处理了该线索的核心矛盾）
2. 这个行动是否产生了新的待处理情况？（要求：真实世界会有后果的行动）

输出JSON：
{
  "close": ["t001"],       // 要关闭的线索id，可为空
  "open": [                // 新开的线索，可为空
    {"description": "...", "category": "work", "urgency": 0.5}
  ]
}
```

---

## WorldEngine 变更

**旧事件决策逻辑（删除）：**
```python
if intensity > 0.45 → dramatic
elif ticks_since_event >= 3 → subtle
```

**新事件决策逻辑：**
```python
def _decide_event(state, behavior):
    thread = self.thread_mgr.get_top_thread()

    if thread:
        # 情绪影响事件的紧迫感，但不影响选哪条线索
        tone = "pressing" if intensity > 0.5 else "quiet"
        return self._generate_thread_event(thread, state, behavior, tone)
    else:
        # 所有线索都已关闭时，生成开放性事件（新发现/机会）
        return self._generate_open_event(state, behavior)
```

**_generate_thread_event 的 prompt 结构：**
```
人物：{profile.name}
当前时间/地点：{behavior}
正在进行的故事线索：{thread.description}（urgency={thread.urgency:.2f}）
人物当前情绪：{emotion_desc}
近期思维片段：{state.text[-100:]}
近期已发生的事（避免重复）：{event_history[-3:]}

生成一件与这条线索直接相关的事：
- 1~2句话，纯事实陈述，不加感受描写
- 可以是：线索的直接发展、相关人物出现、环境触发对线索的联想
- 不要完全重复上次的事件
```

---

## run.py 变更

```python
# 初始化
thread_mgr = NarrativeThreadManager(state_path="output/narrative_state.json")
# 从 profile 目录的初始线索文件加载，或从 profile 的某个字段加载
world = WorldEngine(profile, thread_mgr=thread_mgr, ...)

# 主循环每轮：
thread_mgr.tick_urgency()          # 线索自动升级
event = world.tick(state, behavior) # WorldEngine 推进最高urgency线索

state, behavior = run_cognitive_cycle(...)

# B2结论立刻传给线索管理器
if state.conclusion:
    thread_mgr.process_action(state.conclusion, current_tick=tick)

thread_mgr.save()  # 持久化

# write-back 批次（每5轮）照旧
writeback_mgr.add_candidate(tick, state.conclusion)
writeback_mgr.maybe_flush(tick)
```

---

## 初始化方式

**profile.json 不变**，初始叙事线索写在一个**配套文件**里：

```
examples/
  demo_profile.json          ← 人物档案（不变）
  demo_narrative_state.json  ← 初始叙事线索（手写）
```

`run.py` 启动时查找同名 `*_narrative_state.json`，没有则报错提示用户创建。

运行时线索变化写入 `output/` 目录（不修改 examples/ 原始文件）。

---

## 数据流全景（更新后）

```
narrative_state.json（线索持久化）
       ↓ get_top_thread()
WorldEngine → 推进该线索的事件
       ↓
CognitiveEngine（感知→情绪→记忆→推理→arbiter→drift）
       ↓
ThoughtState { text, conclusion }
       ↓                        ↓
   write-back              process_action()
  (5轮批次，                  （立刻执行）
  写入memories)          → 关闭/新建线索
                         → narrative_state.json
```

---

## 预期效果

| 问题 | 修前 | 修后 |
|------|------|------|
| 重复内容 | 情绪不变 → 同样的事件 | 不同线索 → 不同事件 |
| 事态不发展 | WorldEngine 生成孤立事件 | 每轮推进一条线索 |
| 角色没主动性 | write-back 结论无处去 | 结论关闭线索，可产生下一轮事件 |
| 情绪无恢复 | 无正向刺激 | 张明/欲望类线索可自然触发正向事件 |

---

## 不在本次范围

- current_situation 字段的动态更新（之后可以从已关闭线索自动生成）
- 线索之间的依赖关系（A 关闭后才能开 B）
- 多角色线索交互

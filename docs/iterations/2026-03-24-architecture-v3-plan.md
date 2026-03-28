# 迭代记录：架构 v3 规划（2026-03-24）

## 本次迭代做了什么

本次为**规划迭代**，未写代码。通过 20 轮 Q&A 完成了下一阶段所有架构决策。

### 发现的问题（来自 run_林晓雨_03.txt 37 轮输出审查）

1. **情绪不衰退**：情绪始终维持 sadness/fear 0.3~0.5，无时间流逝感。drift 模式从未触发
2. **世界引擎事件质量低**：上下文太少，事件倾向 generic（"收到一条消息"、"有人走过来"），缺乏个性化；戏剧性过强，过于矫情
3. **内心独白矫情**：持续念叨童年创伤/职场委屈，正常人随时间推进会走出来
4. **空间连续性缺失**：系统不知道角色在哪里，15:00楼道坐到40轮结束
5. **方向 A 问题**：以情绪为主线的内心独白导致内容重复，真实的人类意识是围绕具体事物展开的
6. **Anthropic 代理 key 耗尽**：yunjintao.com 所有 key 失效，arbiter 层不可用
7. **ResidualFeedback bug**："你太累了"被当成人名写入 relationships

---

## 架构决策（全部经用户确认）

### 1. 全 LLM 迁移 qwen3-max（DashScope）
- 快速层已完成（Perception/OCC/WorldEngine/Reasoning）
- arbiter 层：从 Anthropic streaming 改为 `fast_call()` 非流式（整段输出）
- Anthropic 保留作 fallback

### 2. 情绪被动衰退
- 每轮无条件 × 0.7（2h/tick 尺度）
- 约 3 轮强度减半，一觉醒来（4 ticks）基本平复
- 不同时间尺度（1天/1月）预留扩展入口，逻辑分层处理
- 月尺度情绪不可预测，情绪仅作语气调色幂，不影响实质内容

### 3. 方向 B：事件/记忆/欲望为主，情绪调色
- **旧方式（方向 A）**：情绪驱动内心独白 → 矫情、重复
- **新方式（方向 B）**：主内容 = 脑子里在想什么具体的事（食物/欲望/某人/一个问题）；情绪 = 影响语气/词汇，不是话题
- 变更范围：arbiter 系统提示词重写，感知/推理层小幅调整，代码架构不变

### 4. Layer 0：行为预测层（新增）
- 每轮 tick 第一步先推断"角色现在在哪里/在做什么"
- 规则查表（profile.typical_schedule）+ LLM 弹性偏离（情绪影响今日作息）
- 输出 BehaviorState {location, activity, sleep_state, description}
- 全链路注入 BehaviorState，解决空间一致性问题

### 5. 时间轴（tick = 2h，从 15:00 开始）
- scenario_start_time 存入 profile，tick_duration_hours = 2.0
- WorldEngine 维护 wall_clock_time，所有事件时间感知

### 6. 睡眠状态机（两态）
- AWAKE：正常认知循环（5层）
- ASLEEP：简化循环（WorldEngine 生成梦境事件 → Arbiter 直出梦境文本）
- 梦 = 睡眠状态下的事件类型
- 入睡时间按作息表 + 情绪偏移计算

### 7. 地点显式编码
- profile 新增 typical_schedule（时间段 + 地点 + 活动 + 情绪修正参数）
- WorldEngine 从 BehaviorState 读取当前地点，生成对应事件
- 解决"21:00还在办公室楼道"的穿帮

### 8. profile 全量重写
- 虚构林晓雨 + 真实感细节（不是真实人物，字段结构为未来真实数据替换预留）
- 充实维度：居住环境、兴趣爱好、内心欲望、日常作息、典型关系细节
- 修复 cognitive_biases 字段（"陈总说跑偏"是关系短语不是认知偏差）
- 删除 "你太累了" 关系条目

### 9. ResidualFeedback 过滤修复
- 过滤含中文虚词（你/我/了/的/是）的短语作为人名
- 过滤超过 5 字的词组
- 继续开启，不禁用

### 10. 世界引擎事件质量
- 注入：当前时间/地点/主导情绪/最近 reasoning 内容（150字）
- 事件改为 2-3 句：触发事实 + 感受暗示
- dramatic/subtle 模式也可指向具体记忆/关系

### 11. drift 模式内省内容
- 混合：日常欲望/兴趣/想见的人（轻盈）+ 当前处境深化反思
- 情绪衰退后 drift 会更自然触发

---

## 变更清单

| 文件 | 类型 | 核心变更 |
|------|------|----------|
| `core/behavior.py` | **新增** | BehaviorState dataclass + behavior_layer() |
| `core/cognitive_engine.py` | 更新 | Layer 0 调用、passive decay 0.7、arbiter 改 fast_call、方向 B prompt |
| `core/world_engine.py` | 更新 | BehaviorState 注入、rich context、事件 2-3 句、睡眠事件 |
| `agents/base_agent.py` | 更新 | 移除 streaming、保留 Anthropic fallback |
| `core/residual_feedback.py` | 更新 | 实体名过滤 |
| `run.py` | 更新 | 移除流式循环、睡眠分支、WorldEngine 新参数 |
| `examples/demo_profile.json` | 重写 | 完整林晓雨：作息表+情绪修正+居住/兴趣/欲望/记忆 |

---

## 新 profile 字段设计

```json
{
  "typical_schedule": [
    {"time_range": "07:00-08:30", "location": "出租屋→地铁", "activity": "上班通勤"},
    {"time_range": "08:30-18:30", "location": "望京某互联网公司", "activity": "上班"},
    {"time_range": "18:30-19:45", "location": "地铁", "activity": "下班通勤"},
    {"time_range": "19:45-23:00", "location": "出租屋", "activity": "在家"},
    {"time_range": "23:00-07:00", "location": "出租屋卧室", "activity": "睡眠"}
  ],
  "emotion_schedule_correction": {
    "high_negative_intensity": {"shift_home_minutes": 45, "sleep_delay_minutes": 60}
  },
  "home_location": "北京通州区某老小区一居室出租屋",
  "work_location": "望京某互联网公司",
  "scenario_start_time": "2024-03-15T15:00:00",
  "tick_duration_hours": 2.0,
  "hobbies": ["..."],
  "desires": ["..."]
}
```

---

## 架构层次图（新）

```
用户意图层   run.py
      ↓
编排层       cognitive_engine.run_cognitive_cycle()
      ↓
处理层       behavior_layer / perception_layer / emotion_layer
             memory_layer / reasoning_layer / arbiter_layer
             WorldEngine
      ↓
基础层       agents/base_agent.fast_call() / LLM client
```

---

## 下次验证点

1. Layer 0 输出的 BehaviorState 是否使后续层事件/思维在空间上一致
2. 情绪 × 0.7/轮 衰退后，40 轮内 drift 是否至少触发 2-3 次
3. 方向 B 输出是否不再以"我好难受"开头，内容是否更多元
4. 睡眠状态切换：tick 进入 ASLEEP 后梦境输出是否自然
5. ResidualFeedback 过滤后是否还出现非人名条目

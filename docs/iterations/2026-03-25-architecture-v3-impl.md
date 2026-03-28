# 迭代记录：架构 v3 实现（2026-03-25）

## 本次迭代做了什么

将 2026-03-24 规划的架构 v3 全部落地实现。

### 变更文件

| 文件 | 类型 | 核心变更 |
|------|------|----------|
| `core/behavior.py` | **新增** | BehaviorState dataclass + behavior_layer()（Layer 0） |
| `core/cognitive_engine.py` | 重写 | Layer 0 调用、passive decay × 0.7、arbiter 改 fast_call 非流式、Direction B prompt、sleep state machine |
| `core/world_engine.py` | 更新 | BehaviorState 注入、rich context（时间/地点/情绪/推理）、事件 2-3 句、max_tokens 80→150 |
| `core/profile.py` | 更新 | 新增字段：typical_schedule、emotion_schedule_correction、home/work_location、scenario_start_time、tick_duration_hours、hobbies、desires |
| `core/residual_feedback.py` | 更新 | 实体名过滤（_is_valid_person_name）、max_len=3 精确提取、_FUNCTION_CHARS 虚词集 |
| `run.py` | 更新 | 去流式化、BehaviorState 显示、sleep_state 显示、wall_clock_time 记录、轮次间隔 3s→2s |
| `examples/demo_profile.json` | 重写 | 完整林晓雨档案：typical_schedule、emotion_schedule_correction、hobbies、desires、修复 cognitive_biases、删除"你太累了"关系条目 |
| `docs/arch.md` | 更新 | 六层数据流、Direction B 规则、睡眠状态机 ASCII 图、参数表更新、技术栈更新 |
| `tests/test_world_engine_v2.py` | 更新 | mock 断言加 behavior=None（接口变更适配） |

### 38/38 测试全绿

---

## 架构决策（本次落地）

### Layer 0 行为预测（behavior_layer）
- 从 `profile.typical_schedule` 查表（支持跨午夜时段）
- tick=1 对应 scenario_start_time，每 tick 推进 tick_duration_hours
- LLM 生成弹性行为描述（情绪 > 0.35 时注入情绪线索）
- 输出 BehaviorState：注入 perception / reasoning / arbiter

### 情绪被动衰退
- `_apply_decay(emotion, factor=0.7)`，在 AWAKE OCC 结果之后、ASLEEP 循环中各调用一次
- 约 3 轮强度减半，有助于 drift 模式自然触发

### 睡眠状态机
- `behavior.sleep_state` 决定走哪条分支
- ASLEEP：`_dream_arbiter` 直出梦境文本，跳过感知/OCC/记忆/推理
- AWAKE：完整六层循环

### Direction B（arbiter 重写）
- `_SYS_ARBITER`：明确"主内容=具体事物，情绪=调色"
- user prompt 注入：location/time（BehaviorState）+ 欲望/兴趣（profile）+ drift instruction
- 非流式：`fast_call(user, system=system, max_tokens=512)`

### ResidualFeedback 过滤修复
- `max_len=3`：关系实体提取只取 2-3 字片段（典型中文人名）
- `_FUNCTION_CHARS`：含虚词（你/我/了/的/是等）的片段视为非人名过滤
- "你太累了"类型的误写入问题已修复

---

## 下次验证点

1. 40 轮运行中，drift 模式是否至少触发 2-3 次（情绪衰退后）
2. 夜间 tick 是否正确切入 ASLEEP，梦境文本是否自然
3. 方向 B 输出是否不再以"我好难受"开头，内容是否更多元
4. BehaviorState 在感知/推理/arbiter 中是否一致体现时间地点
5. WorldEngine 的 2-3 句事件质量是否有显著提升

# 2026-03-30 · 方向三：实时感知 + 认知层 + TTS 数字生命

## 背景

Phase 1（认知引擎闭环）已完成并开源。本次会话确定了 Phase 2 的核心方向：
不是做一个聊天机器人，而是做一个**持续存在于真实空间的数字生命**。

---

## 核心愿景

三个能力组合在一起，产生质变：

```
真实世界（麦克风）
      ↓ 感知
认知引擎（持续运转，有情绪史、有记忆、有反刍）
      ↓ 生成内心独白文本
TTS + 对口型视频（念出来，让人看到它活着）
```

这个组合是目前不存在的东西：一个有内心、有身体、会被真实世界影响、但不打算和任何人交流的实体。

---

## 关键决策

### D-1：延迟接受度
- **结论**：单 tick 延迟 5 分钟以内完全可接受
- **理由**：这不是实时回复的机器人。它有自己的节奏，外部事件是它感知到的刺激，不是它等待回答的问题。长延迟是特性，不是缺陷。

### D-2：TTS + 视频的定位
- **结论**：纯粹的视觉化载体。把认知引擎生成的内心独白文本念出来。
- **不做**：行为模拟、肢体动作、情绪驱动的表情变化（当前阶段）
- **理由**：最简单的形式创造最强的"在场感"；技术路径已打通，是时间问题。

### D-3：实时感知 + 认知引擎的同步架构
- **结论**：Producer-Consumer 双循环，EventQueue 做桥
- **原则**：两个循环互不阻塞

```
FAST LOOP（独立线程，每 3~5s）
  Whisper STT → 显著性评分 → EventQueue（线程安全）
                                    │
                                    ▼ 每 tick 开始时 drain
SLOW LOOP（认知引擎，每 tick 可达 5 分钟）
  取队列最高显著性 event 作为主感知
  其余事件 → 一句话摘要 → 注入 context
  正常跑 10 模块并发
```

- **理由**：Whisper 推理和 LLM 推理时间尺度完全不同，必须解耦。
- **WorldEngine 的新角色**：EventQueue 为空超过 N 秒 → WorldEngine 生成虚构事件填充（退化为 idle generator，不再是主事件源）

### D-4：构建顺序
```
Phase A：WorldEngine 迭代（事件生成质量）
Phase B：音频输入模块（Whisper STT + 显著性过滤 + EventQueue）
Phase C：两者集成（run.py 改造，双模运行）
Phase D：接 TTS + 视频输出
```

- **理由**：感知输入的接口槽位（`run_cognitive_cycle(event=...)`）已存在。先把这个槽位的质量基线拉高，再往里填真实感知内容。技术风险最高的在前，依赖最多的在后。

---

## WorldEngine 现有问题（Phase A 的目标）

当前 WorldEngine 为"20 轮短跑"设计，放到"持续运转"场景有三个问题：

| 问题 | 表现 | 影响 |
|------|------|------|
| 事件词汇太窄 | 只有 dramatic / subtle 两种风格 | 跑几百轮后句式重复，失去真实感 |
| 情绪无自然节律 | 每 tick 线性衰减，趋向平衡点后角色"麻木" | 长期运转缺乏情绪起伏的自然感 |
| 叙事线索无淡出 | 线索关闭即硬切断，相关情绪/记忆消失 | 叙事弧线不连贯 |

**Phase A 第一步**：事件记忆注入——生成下一个事件前，把最近 N 个事件摘要注入 prompt，让 LLM 自动规避重复。改动范围小（只动 `world_engine.py` prompt 构建部分），可测试（跑 50 轮看多样性）。

---

## 方向三与现有代码的对应关系

```
已有（不用重建）：
  run_cognitive_cycle(event=...)   ← 感知输入槽位已存在
  perception_layer()               ← 显著性过滤的语义部分已有
  WorldEngine                      ← 降级为 idle generator，复用
  NarrativeThreadManager           ← 复用

需要新建：
  audio/stt_listener.py            ← Whisper 本地流式
  audio/salience_filter.py         ← 显著性评分
  audio/event_queue.py             ← 线程安全队列 + drain 接口
  run.py 改造                      ← 双模运行（实时感知 / 虚构事件）
  （TTS 接入层，Phase D）
```

---

## 未决问题（Phase B 实现时确认）

- [ ] Whisper.cpp vs faster-whisper：Mac M 系列哪个更稳定？
- [ ] 实时流式 vs VAD 触发：持续监听 + 5s 截帧，还是 Voice Activity Detection 触发？
- [ ] 显著性打分逻辑：纯基于 STT 置信度 + 长度，还是加一层 LLM 语义判断？
- [ ] EventQueue drain 策略：只取最高分 1 条，还是合并 top-K 条？

---

## 下一次验证点

Phase A 完成后跑 50 轮，验证：
- 事件句式多样性是否提升（主观评估）
- 情绪弧线是否在长期运转中仍有起伏（看 intensity 曲线）
- 叙事线索关闭前后的过渡是否自然

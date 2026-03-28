# 方向二 — 麦克风/键盘实时输入模块

> 记录时间：2026-03-24（plan-eng-review 会话）
> 状态：设计冻结，待方向一（B+C）完成后实现

---

## 定位

方向一（WorldEngine v2）的事件全部来自 LLM 虚构生成。
方向二将输入通道替换为**真实世界感知**：麦克风拾取环境音 + 键盘补充输入，
让数字分身从"自言自语的内心戏"升级为"能感知真实世界的认知运行时"。

---

## 架构

```
麦克风（主） ──→ Whisper STT（本地，Mac）
                     │
                     ▼
              显著性过滤（感知层前置）
              · 距离远/识别置信度低 → 丢弃
              · 短片段（< 1s）→ 丢弃
              · 噪音/无意义音节 → 丢弃
                     │
键盘输入（次） ──→ 合并通道
                     │
                     ▼
              event: str  （传入 WorldEngine / cognitive_engine）
```

---

## 用户需求（逐条确认）

### 1. STT 引擎
- **选型**：Whisper 本地（Mac），推荐 `whisper.cpp` 或 `faster-whisper`
- **语言**：中文优先，可配置
- **模型大小**：可配置（small / medium / large），默认 small（速度优先）

### 2. 麦克风输入
- 主通道，持续监听
- 拾取环境音：对话片段、背景声、用户发言
- **显著性过滤由感知层（perception_layer）负责**，而非 STT 层
  - 理由：麦克风物理特性已做了第一层过滤（远处声音本身识别不清）
  - 感知层再做第二层：置信度阈值、片段长度、语义相关性

### 3. 键盘输入
- 次要通道，用于：
  - 调试时手动注入事件
  - 装置场景中引导员的隐蔽输入
- 格式：单行文本回车提交
- 优先级：与麦克风合并，键盘输入立即触发（不等待静音检测）

### 4. 参数可调
| 参数 | 含义 | 默认值 |
|------|------|--------|
| `stt_confidence_threshold` | STT 置信度下限，低于此值丢弃 | 0.6 |
| `min_segment_duration` | 最短有效音频片段（秒） | 1.0 |
| `listening_language` | Whisper 识别语言 | `"zh"` |
| `whisper_model_size` | 模型大小 | `"small"` |
| `keyboard_enabled` | 是否启用键盘备用通道 | `True` |

### 5. 时间尺度
- 可配置：感知窗口（多少秒内的语音合并为一个 event）
- 默认：每 5 秒检查一次，有内容则触发

---

## 与现有架构的接口约定

```python
# perception_layer 已有接口：
def perception_layer(profile, event: str, state: ThoughtState) -> str:
    ...

# 方向二只需将麦克风/键盘内容转为 event: str 传入，无需修改认知引擎内部
```

WorldEngine v2 的事件生成在方向二中**降为备用**：
- 有麦克风输入 → 使用真实输入作为 event
- 无输入超过 N 秒 → WorldEngine 生成虚构事件填充（保持思维流连续）

---

## 实现顺序（建议）

1. `audio/stt_listener.py` — Whisper 本地推理 + 麦克风流
2. `audio/salience_filter.py` — 显著性过滤（置信度 + 时长 + 语义）
3. `audio/keyboard_listener.py` — 键盘备用通道
4. `audio/input_router.py` — 合并两路输入，输出 `event: str`
5. `run.py` 修改 — 在 tick 循环中从 `InputRouter` 拉取 event，而非 WorldEngine 专有

---

## 未决问题（实现时需确认）

- [ ] Whisper.cpp vs faster-whisper：哪个在 Mac M系列上更稳定？
- [ ] 实时流式 vs 定时批处理：麦克风每 5s 截取一段 vs VAD（Voice Activity Detection）触发？
- [ ] 装置展示时麦克风是否需要降噪预处理？（嘈杂展览环境）
- [ ] 键盘输入在装置中如何隐藏（引导员使用无线键盘？）

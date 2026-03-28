# 架构 v4 实现记录

日期：2026-03-25
触发原因：20 轮 v3 测试发现 4 个质量问题

---

## 问题诊断

| # | 问题 | 根因 |
|---|------|------|
| 1 | 思维流诗意感强 | LLM 把"意识流"理解为文学体裁；arbiter 没有结构约束 |
| 2 | ticks 17-19 思维流完全重复 | drift 靠稳定性检测触发，v3 检测逻辑失效；emotion 衰退后无新刺激 |
| 3 | 输出字数不足（<100字） | `max_tokens=600` 不足以容纳 JSON 结构 + 内容；时刻数 3~5 偏少 |
| 4 | 情绪长期卡在 sadness/fear | write-back 不断写入负面"自我认识"；drift 路径打架（B2注入drift但B1仍选负面锚点） |

---

## v4 架构变更

### 1. Arbiter 拆为 B1 + B2 + B3
- **B1**（锚点选择）：`claude_call`，输出 JSON `{anchor, anchor_type, trigger}`
- **B2**（DES 时刻链）：`claude_call`，输出 JSON `{moments[], conclusion, write_back}`
- **B3**（代码渲染）：确定性函数 `_render_moments()`，无 LLM 调用

**DES 时刻类型（7种）：**
- `compressed_speech`：1-5字碎片，末尾自动补——
- `visual_fragment`：闪过的视觉画面
- `unsymbolized`：有认知但无语言/图像，用〔〕括号
- `body_sensation`：先于语言的身体感知
- `intrusion`：随机闯入的不相关念头
- `voice_intrusion`：他人声音侵入，引用原话
- `expanded_speech`：完整内语句，**每轮最多1次，≤15字，禁连接词**

### 2. 常驻 drift_layer（原 WorldEngine [DRIFT] 事件）
- 移入 `run_cognitive_cycle`，每轮在主思维流之后执行
- 触发条件：`max(所有情绪维度) < 0.7`
- 长短：`< 0.3` → 3~4 个时刻；`0.3~0.7` → 1~2 个时刻
- 输出以 `\n\n……\n\n` 与主思维流分隔
- 方向由 `drift_sampler` 根据情绪加权采样（9 类）

### 3. Write-back 准入标准收紧
- **旧标准（三选一）：** 微决定 / 解开循环问题 / 对自我/关系的新认识
- **新标准（必须满足）：** 具体行动类微决定（去哪/做什么/不做什么），明确排除情绪评估和自我否定结论

### 4. WorldEngine 事件平白记者体
- System prompt：从"叙事引擎"改为"事件记录员"
- 指令：只写事实（人/物/事），不写感受暗示，不写情绪涟漪
- 删除 `introspective` 事件类型（drift 移入认知引擎后冗余）
- 删除 `_drift_probability()` 方法

### 5. 其他修复
- `max_tokens` 全面放宽：B2→2048，WorldEngine→512，Reasoning→512
- `json_repair` 作为 `_parse_json_from_llm` 的 fallback 解析器
- 情绪向量显示精度从全精度改为 round(2)
- 修复 `base_agent.py` 中 `fast_call` 函数定义头丢失的 bug

---

## 改动文件清单

| 文件 | 改动类型 |
|------|---------|
| `core/cognitive_engine.py` | 重写 arbiter_layer（B1/B2/B3）；新增 drift_layer()；移除 drift_mode 参数 |
| `core/writeback.py` | 更新 `_SYS_REVIEW` 准入标准 |
| `core/world_engine.py` | 删除 drift 分支；改记者体 instruction；删 introspective 模式 |
| `core/drift_sampler.py` | 新文件：9 类 drift，情绪加权采样 |
| `core/emotion_descriptor.py` | 新文件：8维×10区间=80条文字描述 |
| `core/writeback.py` | 新文件：5轮批量 write-back，LLM 审查 |
| `agents/base_agent.py` | 新增 `claude_call()`；修复 `fast_call` 缺 def 的 bug |
| `core/thought.py` | 新增 `conclusion` 字段 |
| `run.py` | 接入 WritebackManager；移除 drift 参数；情绪 round(2) |
| `requirements.txt` | 新增 `json-repair` |

---

## 下次验证点

1. 每轮情绪 max_dim < 0.7 时应出现 `……` 分隔的 drift 段
2. 思维流 + drift 合计字数应稳定在 200 字以上
3. WorldEngine 事件无感受描写、无修辞
4. write-back 5 轮后仅写入行动类结论（如有）
5. 情绪是否出现正向恢复（欲望/审美/白日梦类 drift 是否能拉动情绪）

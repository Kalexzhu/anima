# 迭代记录：OCC 情绪模型 + WorldEngine v2 + 认知残差 B+C

**日期**：2026-03-24
**会话类型**：/plan-eng-review → 实现

---

## 本次做了什么

### 新建文件
- `core/occ.py`：OCC 认知评价模型（OCCAppraisal + occ_to_plutchik + apply_personality_modifiers + blend_with_prev_state + parse_occ_response）
- `core/world_engine.py`：v2 全量重写（4种事件类型、事件历史持久化、关系登场线性概率、drift 检测、dramatic cooldown）
- `core/residual_feedback.py`：认知残差自动写回 Profile（perceived 高频实体 → relationships；原子写入）
- `docs/direction2.md`：方向二（麦克风/键盘实时输入）详细需求记录
- `tests/test_occ.py` / `tests/test_world_engine_v2.py` / `tests/test_residual_feedback.py`：31 个测试全绿

### 修改文件
- `core/cognitive_engine.py`：emotion_layer 接入 OCC 四步流程；[DRIFT] 前缀检测；arbiter 新增 drift_mode；DUTIR 降为审计日志
- `run.py`：新常量块（7个可调参数）；WorldEngine v2 初始化；ResidualFeedback 触发；MAX_TICKS=40

---

## 关键决策（来自 plan-eng-review）

| # | 决策 | 选项 | 理由 |
|---|------|------|------|
| 1 | Drift 信号 | `[DRIFT]` 事件前缀 | 零耦合，感知层/arbiter 均可独立处理 |
| 2 | DUTIR 角色 | 降为审计日志，不修正输出 | OCC 公式已处理方向逻辑，双重修正冲突 |
| 3 | 事件历史 | 持久化到 jsonl，跨 run 连续 | 叙事连续性，避免重复事件 |
| 4 | decay 参数位置 | run.py 常量块 | 用户调参无需进 core/ |
| 5 | 关系登场概率 | 线性公式 `max(0, (I-0.3)/0.7)` | 简单可预测，参数可调 |
| 6 | OCC 解析失败 | fallback 保留前一轮情绪 + 警告日志 | 静默降级，不中断运行 |
| 7 | 事件历史窗口 | N=10，可配置 | 避免 prompt 过长，保持叙事相关性 |

## Scope 决策
- **System A（WeChat 解析 + ProfileBuilder）**：defer 到 Phase 3，单独计划

---

## 发现的问题 / 待改进

### 世界引擎事件生成质量不足
**现象**：生成事件倾向于通用描述，缺乏个性化。
**根因**：上下文过少（仅 name + current_situation + 150字思维）；一句话无铺垫。
**改进方向**：
1. 注入当前主导情绪、最近 reasoning 到事件生成 prompt
2. 允许 2~3 句描述：触发事实 + 感受暗示
3. dramatic/subtle 也可锚定到具体关系或记忆节点

**状态**：待积累更多真实运行数据后统一改动。

---

## 遗留问题 / 下次验证点

1. OCC LLM 解析失败率——真实运行中 `[OCC] 解析失败` 打印频率
2. drift 触发频率是否合理（40 ticks 内应出现 1~3 次）
3. 残差写回是否检测到有意义的模式（还是全是噪音）
4. 情绪向量是否全程非零（OCC 路径验证）

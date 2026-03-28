# ANIMA · 认知数字分身

> 给定足够的关于一个人的信息，构建其认知模型，
> 使其能在任意情境下生成真实的思维过程。

## 项目定位

**认知数字分身（Cognitive Digital Twin）**，不是读心术。
分身是持久化的认知运行时，可在任意情境下反复触发。

## 技术栈

- LLM：qwen3-max（DashScope，快速层）+ Anthropic Claude（fallback）
- 记忆：简单情绪编码检索（CAMEL 暂不依赖）
- 情绪：Plutchik 8维向量，intensity = RMS（均方根）
- 输出：fast_call 非流式（arbiter 层）

## 目录结构

```
core/          认知引擎（五层）
agents/        LLM agent 工厂
extraction/    Profile 提取引擎【Phase 3】
twin/          数字分身运行时【Phase 2】
examples/      人物档案示例
output/        所有生成文件
docs/arch.md   架构决策（完整）
```

## 关键约定

- 所有 LLM 调用走 Anthropic 直连（CAMEL ChatAgent 因 proxy 不兼容已禁用）
- 输出文件统一写入 `output/`，命名格式：`run_{name}_{n:02d}.{txt|json}`
- 情绪向量全程独立流动，不在文本里隐式传递
- 每轮 API 调用：perception(1) + emotion(1) + reasoning(1) + arbiter(1) + world_event(0~1) = 4~5次

## 当前阶段

**Phase 1：打通认知引擎闭环**
- [x] 五层认知架构
- [x] 世界引擎（情绪阈值触发）
- [x] 可视化输出（txt + json + viz）
- [ ] 情绪向量 bug 验证
- [ ] API 调用优化（合并层，减少 quota 消耗）

## 文档管理规范

### docs/ 目录结构
```
docs/
├── arch.md           ← 当前架构（唯一允许修改的文档，始终反映最新状态）
├── direction2.md     ← 方向二需求（只增不改）
├── iteration-log.md  ← 迭代索引（只增，每次迭代追加一行）
└── iterations/       ← 每次迭代的完整记录（只增，永不删改）
    └── YYYY-MM-DD-{topic}.md
```

### 规则（强制）
- `iterations/` 下的文件**只增不改不删**，每次迭代新建一个
- `iteration-log.md` 每次追加一行索引，不删除历史行
- `arch.md` 是唯一可修改的文档
- 每次迭代结束时，在 `iterations/` 新建记录文件，在 `iteration-log.md` 加一行摘要
- 记录内容：做了什么、关键决策及理由、发现的问题、下次验证点

## 工作节奏（强制）

**开始实现前，必须先问清楚所有不明确的问题，不做任何假设。**
只有在用户对所有关键决策点都给出明确答复后，才开始写代码。

## 架构红线（强制）

**加功能前先对照层次图定位，只动对应层的文件：**

```
用户意图层  run.py / CLI entry
     ↓
编排层      cognitive_engine.py（循环协调，不含业务逻辑）
     ↓
处理层      core/ 各单一职责模块（behavior / occ / world_engine 等）
     ↓
基础层      agents/base_agent.py（LLM client）/ models.py
```

- 单文件超过 500 行：必须先拆分，再加功能
- 单函数超过 50 行：提取为命名函数
- 同一文件出现 3 个以上不同关注点：拆文件
- 新功能先写成旁路（独立函数/模块），验证后再接入主流程

## 文档索引

- 完整架构见 [docs/arch.md](docs/arch.md)
- 迭代历史见 [docs/iteration-log.md](docs/iteration-log.md)

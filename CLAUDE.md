# ANIMA · 认知数字分身

> 给定足够的关于一个人的信息，构建其认知模型，
> 使其能在任意情境下生成真实的思维过程。

## 项目定位

**认知数字分身（Cognitive Digital Twin）**，不是读心术。
分身是持久化的认知运行时，可在任意情境下反复触发。

## 技术栈

- LLM：Anthropic Claude（主力，核心整合/arbiter 层）+ qwen3-max via DashScope（快速层，情绪计算/事件感知/world_engine）
- 情绪：Plutchik 8维向量，intensity = RMS（均方根），OCC 认知评估模型驱动
- 输出：arbiter 层非流式整合，每 tick 生成连续意识流文本 + viz JSON

## 目录结构

```
core/
├── cognitive_modules/   10个并发认知模块（base/runner/reactive/drift）
├── cognitive_engine.py  编排层（tick 循环协调）
├── occ_engine.py        OCC 情绪评估
├── world_engine.py      世界事件生成
└── viz_renderer.py      可视化数据输出
agents/        LLM agent 工厂（base_agent，双层路由）
examples/      人物档案（demo_profile.json 等）
scenarios/     特定人物场景（kobe_2020/）
output/        所有生成文件（run_*.txt / *_viz/）
ui/viz/        p5.js 浏览器端可视化
docs/arch.md   架构决策（完整）
```

## 关键约定

- 所有 LLM 调用走 Anthropic 直连（CAMEL ChatAgent 已移除）
- 输出文件统一写入 `output/`，命名格式：`run_{name}_{n:02d}.{txt|json}`
- 情绪向量全程独立流动，不在文本里隐式传递
- 每轮 API 调用：10个模块并发（ReactiveModule × 1 + DriftModule × 9）+ arbiter(1) + world_engine(0~1) = 11~12次/tick

## 当前阶段

**Phase 1：认知引擎闭环 ✅ 已完成（v5 架构）**
- [x] 10模块并发认知架构（ReactiveModule + 9个DriftModule）
- [x] OCC 情绪模型 + Plutchik 向量 + 惯性衰减
- [x] 世界引擎（tick 驱动事件生成）
- [x] 可视化输出（txt + json + p5.js viz）
- [x] 情绪初始播种（tick 1 前 OCC 管线种入）
- [x] 两套示例人物档案（林晓雨 + 科比·布莱恩特）

**Phase 2：待做**
- [ ] 问卷系统：用户填写问卷自动生成心理档案
- [ ] TTS + 对口型视频输出
- [ ] 英文 persona 支持

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
用户意图层  run.py / scenarios/*/runner.py（CLI entry）
     ↓
编排层      core/cognitive_engine.py（tick 循环协调，不含业务逻辑）
     ↓
处理层      core/cognitive_modules/（reactive + 9个drift模块）
            core/occ_engine.py / core/world_engine.py
     ↓
基础层      agents/base_agent.py（双层 LLM 路由）/ models.py
```

- 单文件超过 500 行：必须先拆分，再加功能
- 单函数超过 50 行：提取为命名函数
- 同一文件出现 3 个以上不同关注点：拆文件
- 新功能先写成旁路（独立函数/模块），验证后再接入主流程

## Git 提交规范（强制）

每次改动完成后必须提交，不得积压。

**commit 粒度**：一个 commit = 一件事

**commit 格式**：
```
feat: 新增问卷系统生成心理档案
fix: 修复 fragment 模块输出为空的问题
docs: 更新 README 快速开始说明
refactor: 拆分 cognitive_engine 过长函数
```

**完成一个改动后的固定动作**：
```bash
git add <改动的文件>
git commit -m "类型: 一句话说明做了什么"
git push origin main
```

- 禁止用"update"、"fix bugs"、"各种修改"等模糊描述
- 禁止攒多个改动合并成一个大 commit
- 每次 push 后仓库立即更新，无需额外操作



- 完整架构见 [docs/arch.md](docs/arch.md)
- 迭代历史见 [docs/iteration-log.md](docs/iteration-log.md)

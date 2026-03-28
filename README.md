<div align="center">

<img src="docs/assets/logo.png" width="200" alt="anima logo"/>

# 🧠 anima

**A Concurrent Cognitive Engine for Simulating the Human Inner World.**

**多模块并发认知引擎，实时仿真人的意识流。**

[![GitHub Stars](https://img.shields.io/github/stars/Kalexzhu/anima?style=flat-square&color=DAA520)](https://github.com/Kalexzhu/anima/stargazers)
[![GitHub Forks](https://img.shields.io/github/forks/Kalexzhu/anima?style=flat-square&color=DAA520)](https://github.com/Kalexzhu/anima/network)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12-blue?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Claude API](https://img.shields.io/badge/Powered%20by-Claude%20API-8A2BE2?style=flat-square)](https://anthropic.com)

</div>

---

## ⚡ 项目概述

> **这不是聊天机器人，不是情感分析，是认知过程本身在运转。**
>
> 输入一份人物心理档案 → AI 用 10 个并发认知模块实时仿真其内心世界 → 输出连续的意识流文本与可视化

人类的意识流从不是单线程的。同一时刻，你的大脑里可能同时有：情绪还没散、旧记忆突然浮现、某个人的声音响起、情绪在缓慢漂移……

现有的 AI 人物仿真要么只有对话层，要么只有情绪标签。**anima 做的是第三件事：仿真认知过程本身，不等待提问，内心世界持续自主运转。**

---

## 🎬 演示

**科比·布莱恩特（2020 年 1 月 25 日深夜）**

<div align="center">
<img src="docs/assets/Kobe_zh.gif" width="75%" alt="科比心理仿真演示"/>
</div>

**林晓雨（方案被否后独坐楼道）**

<div align="center">
<img src="docs/assets/lin_zh.gif" width="75%" alt="林晓雨心理仿真演示"/>
</div>

---

## 🔬 工作原理

### 10 个并发认知模块

每个 tick（时间单位），以下模块**同时运行**，各自调用 LLM 处理对应的认知层：

| 模块 | 类型 | 负责内容 |
|------|------|---------|
| ReactiveModule | 反应层 | 对外部事件的即时响应 |
| 情绪惯性漂移 | DriftModule | 情绪的惯性延续与缓慢变化 |
| 记忆浮现 | DriftModule | 无意识地想起某段记忆 |
| 他人声音入侵 | DriftModule | 脑海中响起某个人说过的话 |
| 意象碎片 | DriftModule | 模糊的视觉画面、感官碎片 |
| 哲学沉思 | DriftModule | 关于某个命题的反复思考 |
| 白日梦 | DriftModule | 对另一种可能的幻想 |
| 反事实假设 | DriftModule | "如果当时……" |
| 反刍思维 | DriftModule | 对某件事反复回想 |
| 自我评价 | DriftModule | 对自己当下状态的内在评判 |

### 情绪系统：OCC 模型

情绪不是随机的标签。项目基于认知科学的 **OCC 理论**（Ortony-Clore-Collins 认知情绪评估模型），通过事件-目标关联性、责任归因等因素计算情绪状态，并有跨 tick 的**惯性衰减**——上一时刻的情绪会影响下一时刻。

### Tick 时间轴机制

```
Tick 1 ──→ Tick 2 ──→ Tick 3 ──→ ...
  ↓            ↓           ↓
情绪状态      情绪漂移     持续演化
落盘          落盘         落盘
```

每个 tick 完成后立即持久化，支持从任意断点续跑，无需从头开始。

---

## 🚀 快速开始

### 前置要求

| 工具 | 版本要求 | 说明 |
|------|---------|------|
| Python | 3.12+ | 主运行环境 |
| Anthropic API Key | — | 必填，驱动核心整合层 |
| DashScope API Key | — | 可选，配置后快速层改用 qwen3-max，显著降低成本 |
| 浏览器 | 任意现代浏览器 | 查看可视化层 |

### 安装与运行

**第一步：克隆项目**

```bash
git clone https://github.com/Kalexzhu/anima.git
cd anima
```

**第二步：安装依赖**

```bash
pip3 install -r requirements.txt
```

**第三步：配置环境变量**

```bash
cp .env.example .env
```

编辑 `.env`，按需选择配置方式：

**方式一：仅 Claude（最简配置，开箱即用）**

```dotenv
ANTHROPIC_API_KEY=sk-ant-xxxxxxxx
CLAUDE_MODEL=claude-sonnet-4-6
```

所有模块均由 Claude 驱动，无需其他账号。

**方式二：Claude + Qwen 混合（推荐，显著降低 API 成本）**

```dotenv
ANTHROPIC_API_KEY=sk-ant-xxxxxxxx
CLAUDE_MODEL=claude-sonnet-4-6

FAST_LLM_API_KEY=sk-xxxxxxxx
FAST_LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
FAST_LLM_MODEL=qwen3-max
```

短任务（情绪计算、事件感知、世界引擎）走 qwen3-max，核心整合层保留 Claude。
DashScope API Key 在 [阿里云百炼平台](https://bailian.console.aliyun.com/) 申请。

**第四步：运行仿真**

```bash
python3 run.py examples/demo_profile.json
```

输出文件自动保存在 `output/` 目录。

**第五步：查看可视化（可选）**

```bash
python3 -m http.server 8000
```

浏览器打开 `http://localhost:8000/ui/viz/`，加载刚才生成的 run 文件即可。

---

## 👤 人物档案

项目内置两套示例档案，可直接运行体验：

### 林晓雨
```
28 岁 · 产品设计师 · 北京
性格：内向、完美主义、高度共情
当前处境：刚在会议上被领导当众否定方案，独自坐在公司楼道窗边
```

```bash
python3 run.py examples/demo_profile.json
```

### 科比·布莱恩特
```
41 岁 · 退役球员、创作者、父亲
当前截面：2020 年 1 月 25 日深夜
勒布朗刚超越他成为 NBA 历史第三得分王
明早将带 Gigi 去打训练赛
```

```bash
python3 scenarios/kobe_2020/runner.py
```

### 使用自定义档案

参考 `examples/demo_profile.json` 的字段结构，创建属于你的人物档案。
档案支持字段：`personality_traits`、`memories`、`relationships`、`desires`、`rumination_anchors` 等。

---

## 🎨 可视化层

- **深蓝底色**，意识碎片以文字形式漂浮飘动
- **逐字淡入**，模拟思维浮现的节奏感
- 不同类型的认知内容有差异化的视觉呈现
- 支持历史 run 文件回放：`?run=run_XXX`
- 支持 demo 模式快速预览：`?demo=1&speed=10`

---

## 🗺️ Roadmap

- [x] 10 模块并发认知架构
- [x] OCC 情绪模型 + 惯性衰减
- [x] Tick 时间轴 + 断点续跑
- [x] p5.js 浏览器端可视化
- [x] 林晓雨示例档案
- [x] 科比·布莱恩特档案
- [ ] 问卷系统：通过填写问卷自动生成心理档案
- [ ] TTS + 对口型视频输出
- [ ] 英文 persona 支持

---


## 📄 License

MIT © [Kalexzhu](https://github.com/Kalexzhu)

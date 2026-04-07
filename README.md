<div align="center">

<img src="docs/assets/logo.png" width="180" alt="anima logo"/>

# anima

**多模块并发认知引擎——仿真人类内心世界的连续运转**

[![GitHub Stars](https://img.shields.io/github/stars/Kalexzhu/anima?style=flat-square&color=DAA520)](https://github.com/Kalexzhu/anima/stargazers)
[![GitHub Forks](https://img.shields.io/github/forks/Kalexzhu/anima?style=flat-square&color=DAA520)](https://github.com/Kalexzhu/anima/network)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12-blue?style=flat-square&logo=python)](https://python.org)
[![Claude API](https://img.shields.io/badge/Powered%20by-Claude%20API-8A2BE2?style=flat-square)](https://anthropic.com)

🌐 **Language**: 中文 | [English](README_EN.md)

</div>

---

## 这是什么

**anima** 不是聊天机器人，不做情绪识别，也不生成对话剧本。

它模拟的是：**人在一个人独处时，内心世界到底在运转什么。**

给定一份心理档案，引擎用 11 个并发认知模块持续生成意识流——不等待提问，不需要对话，像一台自主运转的内心机器：

```
前男友李杨说，「你太累了，跟你在一起我喘不过气」
手背上有一层什么，压着，不是痛
会议室的白板，红色马克笔写着「逻辑跑偏」，字迹是陈总的
都是我——
〔知道自己在想13岁那件事，但没有画面，没有字，只是那个地方还在〕
母亲说，「你这孩子就是太要强，累死自己有什么用」
再撑一下，不能在这哭

……

合肥老家供销社那份offer的纸质通知单，压在抽屉里没拆开，月薪4800，
步行十分钟到家，当时直接扔进了废纸篓。现在那个抽屉是另一个人在用。
那边不用坐在走廊里。
〔一条线：望京、两周、这间走廊、窗玻璃上贴着的消防疏散图。
  另一条线：没有这条线里的任何一样东西。
  两条线同时存在，没有好坏的判断，只是数量上的差异。〕
```

*以上是林晓雨的一个 tick 输出：28 岁产品设计师，刚在会议上被领导当众否定方案，独自坐在公司楼道窗边。*

---

## 可视化演示

**科比·布莱恩特 · 2020 年 1 月 25 日深夜**

<div align="center">
<img src="docs/assets/Kobe_zh.gif" width="75%" alt="科比心理仿真演示"/>
</div>

**林晓雨 · 方案被否后独坐楼道**

<div align="center">
<img src="docs/assets/lin_zh.gif" width="75%" alt="林晓雨心理仿真演示"/>
</div>

---

## 核心设计

### 为什么是 11 个并发模块

人的意识不是单线程的。心理学家 Killingsworth & Gilbert（2010）发现，人在清醒时有 **47%** 的时间思维处于漫游状态（mind-wandering），而这种漫游本身是多通道同时激活的——情绪残余、记忆浮现、声音闯入、逻辑推断，它们不排队，同时发生。

anima 用 `ThreadPoolExecutor` 并发运行 11 个认知模块，每个模块独立调用 LLM，模拟这种并行结构：

| 模块 | 学术依据 | 负责内容 |
|------|---------|---------|
| ReactiveModule | OCC 认知评估理论 | 对当前事件/处境的即时反应 |
| rumination（反刍） | Nolen-Hoeksema, 1991 | 对同一事件的循环重演，在身体里有根 |
| self_eval（自我评估） | 内侧前额叶皮层自我参照加工 | 第三视角审视自己的行为模式 |
| philosophy（哲学追问） | Smallwood，叙事认同建构 | 从具体处境出发，向上追问，不给结论 |
| aesthetic（审美联想） | Dijksterhuis & Meurs, 2006 | 跨领域形式感知，比例/节奏/色彩，不含情绪 |
| counterfactual（反事实） | Roese, 1997 | "如果当时……"的分叉时间线 |
| positive_memory（正向记忆） | DMN 自传体记忆激活 | 带感官细节的正向记忆画面，不分析 |
| daydream（白日梦） | Killingsworth & Gilbert, 2010 | 感官链条式的享乐性发散联想 |
| future（未来想象） | Atance & O'Neill，心理时间旅行 | 脑中到达未来场景，24小时内 |
| social_rehearsal（社交排演） | Lieberman, 2007，心智化网络 | 假设对话链：我说→对方反应→结果 |
| imagery（意象碎片） | — | 意识边缘浮现的感知画面，允许超现实并置 |

### 主干情境系统（WorldState）

人的注意力不是随机漫游的，而是受若干**长期悬而未决的生命域议题**牵引——工作上的去留、感情上的亏欠、家人那边的期待……这些议题形成认知的深层"主干"（Trunk），随情绪和时间在不同域之间自然轮转。

anima 从 profile 中提取 2~4 个 Trunk，用 **Softmax + Recency Penalty** 算法在每个 tick 选出最突显的主干，同时驱动：
- **外部世界**：WorldEngine 生成与该域一致的事件
- **内心漂移**：反刍、哲学、自我评价、未来想象模块以该主干为认知锚点

```
同一 tick 示例（Trunk = 工作域：方案被否后的去留）：
  外部事件：主管路过时停下，说"方案的问题我发你邮件了"
  rumination：胸口发紧，脑子里一遍遍复盘那个被否决的提案
  philosophy：努力这件事，到底是在建构什么，还是在反复推迟一个没有答案的问题？
  future：今晚打开电脑，空白文档，然后呢
```

### 认知指纹（Cognitive Fingerprint）

不同角色的意识流不只是"想不同的事"，更是"用不同的方式想"。认知指纹用三个维度刻画人物的认知个体性：

| 维度 | 作用 | 林晓雨 | 科比 |
|------|------|--------|------|
| **inner_voice_style** | 内心语言怎么说 | 第二人称自我审判："你又——" | 命令式极短句："Again." "Not enough." |
| **somatic_anchors** | 情绪落在哪里 | 胸口发紧，手指发凉 | 肩膀蓄力，膝盖旧伤隐痛 |
| **cognitive_default** | 压力下自动进入什么思维 | 反复回放对方表情，或做一件可控的小事 | 立刻拆解原因，规划下一步动作 |

同一个 rumination 模块，不同角色产出截然不同的意识流——不是因为模块不同，而是认知指纹让 LLM 自行推导出属于这个人的语言、身体和思维方式。

关系人物也有独立的 **speech_style** 字段，让 voice_intrusion 中陈总的声音（命令式、反问结尾）和母亲的声音（絮叨、以关心包裹否定）可清晰区分。

### 情绪模型

基于 OCC 认知情绪评估理论，输出 **8 维 Plutchik 向量**（愤怒 / 恐惧 / 喜悦 / 悲伤 / 惊讶 / 厌恶 / 期待 / 信任）。情绪有跨 tick 的**惯性衰减**（decay=0.4/轮），不在每轮重置——上一刻的积累会影响下一刻的反应。

---

## 快速开始

### 环境要求

| 工具 | 版本 | 说明 |
|------|------|------|
| Python | 3.12+ | — |
| Anthropic API Key | — | 必填，驱动核心模块 |
| DashScope API Key | — | 可选，快速层改用 qwen3-max 可显著降低成本 |

### 安装

```bash
git clone https://github.com/Kalexzhu/anima.git
cd anima
pip3 install -r requirements.txt
cp .env.example .env
```

编辑 `.env`：

**最简配置（仅 Claude）**

```dotenv
ANTHROPIC_API_KEY=sk-ant-xxxxxxxx
CLAUDE_MODEL=claude-sonnet-4-6
```

**推荐配置（Claude + Qwen，降低成本）**

```dotenv
ANTHROPIC_API_KEY=sk-ant-xxxxxxxx
CLAUDE_MODEL=claude-sonnet-4-6

# 快速层（情绪计算、感知层、世界引擎）走 qwen3-max
FAST_LLM_API_KEY=sk-xxxxxxxx
FAST_LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
FAST_LLM_MODEL=qwen3-max
```

DashScope API Key 在[阿里云百炼平台](https://bailian.console.aliyun.com/)申请。

### 运行

```bash
# 运行内置示例（林晓雨）
python3 run.py examples/demo_profile.json

# 指定运行轮次
python3 run.py examples/demo_profile.json --max-ticks 10
```

输出自动保存在 `output/` 目录（txt + json + viz JSON）。

### 查看可视化

```bash
python3 -m http.server 8000
```

浏览器打开 `http://localhost:8000/ui/viz/`，选择 run 文件即可。

---

## 示例人物档案

项目内置两套完整档案，可直接运行：

### 林晓雨

```
28 岁 · 产品设计师 · 北京望京
性格：内向、完美主义、高度共情、情绪自我压抑
当前处境：刚在会议上被领导当众否定方案，独自坐在公司楼道窗边
身体状态：心跳很快，手有点抖，强忍着没有哭
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

> **声明**：此档案为艺术创作与技术演示，不代表科比·布莱恩特本人的真实想法。
> 所有内容均由 AI 根据公开资料虚构生成。谨以此向他和 Gianna 致敬。

```bash
python3 scenarios/kobe_2020/runner.py
```

---

## 创建自定义档案

参考 `examples/demo_profile.json`。核心字段：

```json
{
  "name": "人物姓名",
  "age": 28,
  "current_situation": "当前所处情境（越具体越好）",
  "current_physical_state": "当前身体感受",
  "personality_traits": ["内向", "完美主义"],
  "cognitive_biases": ["过度自责", "灾难化思维"],

  "inner_voice_style": "内心独白用第二人称自我审判（'你又……'），句子常断在动词上",
  "somatic_anchors": "胸口（发紧）和手指（发凉、微颤）",
  "cognitive_default": "压力下反复回放对方最后那句话的表情，或去做一件可控的小事",

  "memories": [
    {"age": 13, "event": "...", "emotion_tag": "shame", "importance": 0.9}
  ],
  "relationships": [
    {
      "name": "陈总", "role": "直属领导", "valence": -0.6,
      "power_dynamic": "权威型",
      "typical_phrases": ["这个方案完全跑偏了"],
      "speech_style": "极短句、命令式、从不解释理由"
    }
  ],
  "rumination_anchors": ["被否定的两周方案", "分手前的最后一次争吵"],
  "philosophy_seeds": ["努力是否只是让自己有所依凭的幻觉"],
  "desires": ["消失一段时间", "做出一件真正属于自己的东西"],
  "daydream_anchors": ["一个不被人打扰的房间", "独自坐在海边"],
  "social_pending": [
    {"person": "陈总", "unresolved": "要不要主动去找他谈方案"}
  ]
}
```

`inner_voice_style` / `somatic_anchors` / `cognitive_default` 是认知指纹三维度，不填也能跑，但填了后角色差异化会显著提升。`speech_style` 让关系人物的声音各有辨识度。

---

## 输出格式

每个 tick 输出基于 **描述性体验取样（DES，Descriptive Experience Sampling）** 方法论，将内心体验分为 6 种时刻类型：

| 类型 | 示例 |
|------|------|
| `compressed_speech`（极短内语） | `都是我——` |
| `visual_fragment`（视觉画面） | `会议室的白板，红色马克笔写着「逻辑跑偏」` |
| `body_sensation`（身体感知） | `手背上有一层什么，压着，不是痛` |
| `unsymbolized`（无语言认知） | `〔知道自己在想那件事，但没有词〕` |
| `voice_intrusion`（他人声音） | `前男友李杨说，「你太累了，跟你在一起我喘不过气」` |
| `expanded_speech`（完整内语） | `努力是否只是一种让自己有所依凭的幻觉？……` |

---

## 可视化层

- **深蓝底色**，意识碎片以文字形式漂浮飘动
- 不同认知类型的文字有差异化色相和透明度
- **逐字淡入**，模拟思维浮现的节奏感
- 情绪状态驱动背景光晕色调实时变化
- 支持历史 run 回放：`?run=run_XXX`
- 支持 demo 预览：`?demo=1&speed=10`

---

## Roadmap

**已完成**
- [x] 11 模块并发认知架构（ReactiveModule + 10 DriftModule）
- [x] OCC 情绪模型 + Plutchik 8 维向量 + 惯性衰减
- [x] WorldState 主干情境系统（Trunk tree + Softmax 多域轮转）
- [x] Tick 时间轴 + 原子写入 + 断点续跑
- [x] p5.js 浏览器端漂浮动画可视化
- [x] 林晓雨 & 科比·布莱恩特示例档案
- [x] 多 API Key 轮转 + 超时保护
- [x] 认知指纹（Cognitive Fingerprint）— 角色差异化三维度 + 关系人物 speech_style
- [x] ResidualFeedback 只读保护 — 原始 Profile 不再被自动检测修改

**进行中（Phase B → D）**
- [ ] 实时音频感知输入（Whisper 流式 STT）
- [ ] 双循环架构（STT Fast Loop + 认知引擎 Slow Loop）
- [ ] TTS 输出（内心独白 → 语音）

**计划中**
- [ ] 问卷系统：通过填写问卷自动生成心理档案
- [ ] 英文 persona 完整支持
- [ ] CognitiveTwin 持久化封装（跨情境对比接口）
- [ ] Web 界面

---

## License

MIT © [Kalexzhu](https://github.com/Kalexzhu)

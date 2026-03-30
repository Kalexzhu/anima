# ANIMA — 迭代索引

每次迭代新增一行，不删除。详细记录见 `iterations/` 目录。

| 日期 | 文件 | 内容摘要 |
|------|------|----------|
| 2026-03-25 | [2026-03-25-architecture-v4-impl.md](iterations/2026-03-25-architecture-v4-impl.md) | 架构 v4：B1/B2/B3 拆分、DES 7类时刻、常驻 drift_layer、write-back 仅行动类、WorldEngine 平白记者体、json_repair 容错、max_tokens 全面放宽 |
| 2026-03-26 | [2026-03-26-narrative-threads-design.md](iterations/2026-03-26-narrative-threads-design.md) | 叙事线索系统：NarrativeThreadManager、urgency 自动递增、WorldEngine 改为线索驱动、process_action 关闭/新建线索 |
| 2026-03-26 | [2026-03-26-multi-module-cognitive-architecture.md](iterations/2026-03-26-multi-module-cognitive-architecture.md) | 多模块认知架构设计：10模块并发（7片段型+3链条型）、Profile 分类扩展、链条型模块机制（daydream/future/social_rehearsal）、跨轮影响机制 |
| 2026-03-26 | — | 架构 v5 实现：cognitive_modules 包（base/runner/reactive/drift）、ReactiveModule 封装 B1+B2+B3、9个DriftModule实例、ModuleRunner ThreadPoolExecutor 并发、prev_tick_outputs 跨轮传递、narrative_thread 传入 ModuleContext、profile 新增 8 个字段 |
| 2026-03-26 | [2026-03-26-v5-eval-and-next.md](iterations/2026-03-26-v5-eval-and-next.md) | v5 首轮评估（run_12，10轮）：reactive/counterfactual/rumination 运转良好；待修4项：future 输出是行动计划非思维流、情绪初始强度0.00、梦境修辞过重（决策：删梦境+加imagery模块）、anger全程缺失（排查OCC映射） |
| 2026-03-26 | [2026-03-26-v5-fixes-viz-design.md](iterations/2026-03-26-v5-fixes-viz-design.md) | v5 修复实施（imagery+ASLEEP静默/future心理时间旅行/情绪播种/anger修复）+ run_13验证（全模块5轮）+ 提示词规范化（voice_intrusion人名/禁代词）+ render层修改 + 文字漂浮动画可视化spec |
| 2026-03-26 | [2026-03-26-viz-floating-text-impl.md](iterations/2026-03-26-viz-floating-text-impl.md) | 文字漂浮动画实现：viz_renderer.py/txt_to_viz.py/p5.js sketch、逐字淡入淡出、半透明拖影背景、Aurora 径向渐变、离线回放+实时轮询架构 |
| 2026-03-27 | [2026-03-27-viz-visual-iteration.md](iterations/2026-03-27-viz-visual-iteration.md) | sketch.js v2→v3：DES类型色相区分、情绪背景调色（EMOTION_BG_RGB+lerp）、Y轴偏好、微振动、60s/tick、全局alpha渐退（replacing hold+逐字消隐）、跨tick叠压残留 |
| 2026-03-28 | [2026-03-28-kobe-scenario-and-output-quality.md](iterations/2026-03-28-kobe-scenario-and-output-quality.md) | 科比场景接入 viz 管线（runner.py/timeline.json/kobe_profile.json）+ 三项输出质量修复：social_rehearsal 代词/B1 事件权重/daydream 链条重复；daydream+rumination 锚点扩展；--max-ticks 参数 |
| 2026-03-28 | — | 稳定性修复：ModuleRunner 增加 _MODULE_TIMEOUT_S=90 超时机制（防 LLM 挂死导致进程卡住）；Anthropic client 加 timeout=90s；voice_intrusion 双括号修复（viz_renderer/cognitive_engine 均加 re.sub 去重）；voice_intrusion 跨轮去重（B1 注入上轮禁止列表）；ResidualFeedback 关系污染问题已知未修 |
| 2026-03-28 | — | 英文旁路：profile 增加 output_language 字段（默认 zh）；claude_call 检测到 en 时注入 _EN_INJECTION 系统提示；fast_call/OCC 管线不受影响；kobe_profile.json 加 output_language=en 做英文演示（现已重置为 zh）；--start-tick 参数支持分段跑 kobe 场景 |
| 2026-03-28 | — | viz 视觉迭代：停留时长 1.5→1.0 tick；入场随机初始倾角（±0.06rad）；左上角 tick 事件信息图标（点击展开/收起面板）；sketch.js drawMoment 改用 translate+rotate 坐标系 |
| 2026-03-28 | — | demo_profile.json（林晓雨）扩充：daydream_anchors/rumination_anchors 各扩展至 8 条；新增 2 条 memories（23岁初到北京/28岁厕所里哭完补妆）；移除3条自动检测关系垃圾条目 |
| 2026-03-30 | — | 开源准备：项目改名 ANIMA（全量替换展示层字符串，viz_from_txt.py regex 同步）；新增 .env.example；_TEST_ALL_MODULES 改 False（省 ~10x API 开销）；修正 README kobe 路径；.gitignore 补充；sample_outputs/ 归档两套示例输出 |

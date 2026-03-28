# Mind Reading — 迭代索引

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

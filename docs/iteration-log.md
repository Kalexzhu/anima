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
| 2026-03-30 | — | 技术债修复：_key_index 加 threading.Lock（10 并发模块竞争条件）；ResidualFeedback 加停用词表（过滤"睡眠中"等假阳性关系）；删除废弃测试 T-WE-3/T-WE-4（drift_stability 特性从未实现）；base_agent.py 注释更新；requirements.txt 版本精确锁定 |
| 2026-03-30 | [2026-03-30-realtime-cognitive-direction.md](iterations/2026-03-30-realtime-cognitive-direction.md) | 方向三决策记录：实时感知 + 认知引擎 + TTS 数字生命；Producer-Consumer 双循环架构；延迟 5 分钟可接受；构建顺序 WorldEngine迭代→音频输入→集成→TTS；WorldEngine 三个长跑问题识别 |
| 2026-03-30 | [2026-03-30-world-state-phase-a.md](iterations/2026-03-30-world-state-phase-a.md) | Phase A 实现：WorldState 主干情境系统（core/world_state.py 新增）；Trunk 从 profile 一次 LLM 提取；urgency 叙事时间归一化衰退；Phase 双向转移（不单调）；action_type 由 Branch urgency 代码派生；事件 prompt 注入 trunk_context + action_directive；36/36 测试通过 |
| 2026-03-30 | [2026-03-30-trunk-domain-reboot.md](iterations/2026-03-30-trunk-domain-reboot.md) | Trunk 本体论重构：改从心理元主题→生命域具体处境；VALID_DOMAINS 8个域强制正交同域去重；Softmax + Recency Penalty 选择算法（temperature=0.25，halflife=4，weight=0.75）取代 Winner-Take-All；world_engine.py 传 current_tick；36/36 测试通过 |
| 2026-03-30 | [2026-03-30-phase-a-complete-and-drift-integration.md](iterations/2026-03-30-phase-a-complete-and-drift-integration.md) | Phase A 收尾（run_03 验证：4域正交+4线激活）；ASLEEP 事件抑制修复；Phase A.5 设计：Trunk 树接入 drift 层（ModuleContext 新增 active_trunk_context；rumination/philosophy/self_eval 强接入；future 中接入；daydream 不接入） |
| 2026-03-30 | [2026-03-30-drift-trunk-integration.md](iterations/2026-03-30-drift-trunk-integration.md) | Phase A.5 实现：drift.py 更新 self_eval/philosophy/future 的 get_anchor；强接入=Trunk优先静态字段兜底；future中接入=trunk_context+desire组合注入；接入分级设计（10模块中4个接入）；36/36测试通过 |

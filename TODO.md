# ANIMA — TODO

## 下次最重要的 3 件事（2026-04-09 认知指纹迭代完成后更新）

1. **跑完整 20 轮验证（林晓雨 + 科比各一次）**
   - `python3 run.py examples/demo_profile.json --max-ticks 20`
   - `python3 run.py scenarios/kobe_2020/kobe_profile.json --max-ticks 20`
   - 验证重点：fingerprint 效果在长跑中是否持续稳定、drift_sampler 采样模式下差异化是否保持、情绪弧线合理性
   - 对比旧 run（run_07/kobe_2020_04）和新 run 的差异

2. **Phase B 启动准备：音频感知输入**
   - 评估 Whisper 本地流式 STT 在 Mac M 系列的可行性
   - 设计 audio/stt_listener.py + salience_filter.py 接口
   - 见 arch.md Phase B 章节

3. **Phase D 调研：TTS + 对口型视频**
   - 调研 TTS 方案（内心独白 → 语音）
   - 调研对口型视频生成（情绪驱动视觉输出）
   - 这是视觉化 demo 的最终形态

---

## 下次最重要的 3 件事（2026-03-30 方向三规划后更新）

1. - [x] **Phase A 第一步：WorldEngine 事件记忆注入**（已完成）
2. - [x] **初始化 git**（已完成）
3. - [x] **Phase A 其余三项**（已完成：事件风格扩展、积压-释放机制、Trunk 间渗透）

---

## 下次最重要的 3 件事（2026-03-27 视觉迭代后更新）

1. **恢复生产模式，跑 run_14（完整 20 轮）**：
   - `cognitive_engine.py` L56：`_TEST_ALL_MODULES = True` → `False`
   - `run.py` L24：`MAX_TICKS = 5` → `20`
   - 然后：`python3 run.py examples/林晓雨_profile.json`
   - 验证重点：drift_sampler 采样是否正常、20 轮情绪弧线是否合理

2. **run_14 完成后回放验证可视化**：
   - `python3 ui/viz/scripts/txt_to_viz.py output/run_林晓雨_14.txt`
   - `http://localhost:8001/ui/viz/index.html?run=run_林晓雨_14&speed=10`
   - 验证真实数据下颜色区分、情绪背景调色、堆积感是否达预期

3. **run_14 评估后决定 imagery 模块**（P2）：
   - 当前 imagery 输出与 aesthetic 边界模糊，超现实并置特质未体现
   - 评估后决定是否调整 prompt，或合并两模块

---

## 下次最重要的 3 件事（2026-03-26 可视化层实现后更新）

1. **验证可视化效果**：启动本地服务后先跑 demo，再跑 run_13 回放
   ```bash
   cd ~/Projects/mind-reading
   python3 -m http.server 8001
   # http://localhost:8001/ui/viz/index.html?demo=1&speed=10
   # http://localhost:8001/ui/viz/index.html?run=run_林晓雨_13&speed=10
   ```

2. **恢复生产模式，跑 run_14（完整 20 轮）**：
   - `cognitive_engine.py` L56：`_TEST_ALL_MODULES = True` → `False`
   - `run.py` L24：`MAX_TICKS = 5` → `20`
   - 然后：`python3 run.py examples/林晓雨_profile.json`
   - 验证重点：drift_sampler 采样是否正常、20 轮情绪弧线是否合理

3. **run_14 评估后决定 imagery 模块**（P2）：
   - 当前 imagery 输出与 aesthetic 边界模糊，超现实并置特质未体现
   - 评估后决定是否调整 prompt，或合并两模块

---

## 下次最重要的 3 件事（2026-03-25 架构 v4 实现后更新）

1. **跑一次完整 20 轮测试**（`cd ~/Projects/mind-reading && python3 run.py examples/demo_profile.json`），重点验证：drift 块是否出现（每轮情绪低时应有 `……` 分隔段）、思维流是否达到 200 字、世界事件是否消除矫情感、write-back 是否只写行动类结论
2. **根据测试结果评估情绪恢复问题**：若情绪仍长期低落，需检查 profile 中正向刺激来源（`desires`/`hobbies` 字段内容是否足够具体），以及 OCC 是否对 subtle 事件产生过度负面评估
3. **写入 docs/arch.md v4 架构更新**：补充 drift_layer 常驻层、write-back 准入标准变更、WorldEngine 简化（去掉 introspective 类型）

完整变更清单见 [docs/iterations/2026-03-25-architecture-v4-impl.md](docs/iterations/2026-03-25-architecture-v4-impl.md)


## 项目状态
- [x] 项目立项，完成可行性分析
- [x] 初始化目录结构
- [x] 五层认知架构（Perception / Emotion / Memory / Reasoning / Arbiter）
- [x] 世界引擎（情绪阈值触发）
- [x] 可视化输出（txt + json + viz）
- [x] emotion bug 修复（LLM 输出含代码块 JSON，regex 提取逻辑已修复，数值可正确更新）
- [x] /plan-ceo-review 完成认知残差 A+B 架构评审（2026-03-18）
- [x] 情绪标定系统（DUTIR 词典 + EmotionConstraint + 统计修正，2026-03-24）
- [x] 认知残差 A+B 改造（TickHistoryStore + LayerContext + T1-T7 测试全绿，2026-03-24）
- [x] 架构 v4 实现（B1/B2/B3 拆分、DES 类型时刻、常驻 drift_layer、write-back 行动准入、WorldEngine 平白记者体、json_repair 容错，2026-03-25）
- [x] Phase A 全部完成：WorldState Trunk 系统 + 10 项精修（2026-03-30）
- [x] 认知指纹 Cognitive Fingerprint：inner_voice_style / somatic_anchors / cognitive_default + speech_style（2026-04-07）
- [x] ResidualFeedback 只读保护：原始 profile 不再被自动检测修改，全部写入 staging（2026-04-07）
- [x] 持久化文件角色隔离：world_state / narrative_state 按角色名区分（2026-04-07）

## 已完成但仍开放的旧议题
- [ ] 确定第一版场景：历史人物复现 / 剧本角色 / 心理咨询训练？（影响产品路径，暂未决策）
- [ ] 研究 OASIS 框架：了解 MiroFish 底层引擎，评估改造成本
- [ ] 设计人物档案格式：定义"状态 + 经历 + 环境"的输入 schema

## Deferred TODOs（plan-eng-review 2026-03-24 决策）

### System A — Profile 提取系统（Phase 3，暂缓）
- **状态**：⏸ 暂放，待主流程成熟后再启动
- **What：** WeChat SQLite 解析 → MessageFilter → WeChatParser → ChatAnalyzer（OCEAN）→ ProfileBuilder.build()
- **Context：** `extraction/profile_builder.py` 已有接口骨架，`build()` raises `NotImplementedError`
- **Depends on：** 主流程（公众人物手工 profile）验证有效后再启动

### 方向二 — 麦克风/键盘实时输入（Phase 2，见 docs/direction2.md）
- **What：** 本地 Whisper STT（Mac）+ 环境音显著性过滤 + 键盘备用通道 + 参数可调
- **Why：** 装置艺术第二形态核心能力，将系统从虚构事件升级为感知真实世界
- **Depends on：** 方向一（B+C）完成后可独立启动

### Phase 4 — Web UI（参数滑块 + 思维流可视化）
- **What：** 浏览器端界面，参数实时调节 + 情绪弧线图表 + 思维流展示
- **Why：** 装置艺术展示需要面向观众的界面；`tick_records` JSON 已为此预留接口
- **Depends on：** 方向一 + 方向二完成，数据结构稳定后

### Profile 时间演化
- **What：** 单次运行超过阈值时自动标记/更新 `current_situation`
- **Why：** 长期装置展示时处境字段会过时
- **Note：** 与已定决策"时间在事件里体现，不更新 Profile"存在张力，待长期运行数据积累后再决策

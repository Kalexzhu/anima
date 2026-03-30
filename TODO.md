# ANIMA — TODO

## 下次最重要的 3 件事（2026-03-30 方向三规划后更新）

1. **Phase A 第一步：WorldEngine 事件记忆注入**
   - 目标：生成事件前，把最近 N 个事件摘要注入 prompt，让 LLM 自动规避重复
   - 改动范围：仅 `core/world_engine.py` 的 prompt 构建部分，不影响其他模块
   - 验证方式：跑 50 轮，主观评估事件句式多样性是否提升
   - 详细设计见 `docs/iterations/2026-03-30-realtime-cognitive-direction.md`

2. **先初始化 git，再动代码**
   - `cd ~/Projects/mind-reading && git init && git add . && git commit -m "feat: 初始化 ANIMA — v5 认知引擎开源版本"`
   - 之后每次改动一件事就 commit 一次，格式参考 CLAUDE.md
   - 原因：接下来改动较多，没有 git 等于没有安全网

3. **Phase A 其余三项（事件记忆注入验证通过后）**
   - 事件风格扩展（超越 dramatic/subtle）
   - 情绪自然节律（积压-释放机制）
   - 叙事线索淡出（关闭后渐退，不硬切断）

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

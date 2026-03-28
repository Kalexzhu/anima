# 文字漂浮动画可视化层实现

**日期**：2026-03-26（第三次会话）
**状态**：已实现，待浏览器端验证
**依据**：上次 spec（2026-03-26-v5-fixes-viz-design.md）

---

## 新增文件

| 文件 | 说明 |
|------|------|
| `core/viz_renderer.py` | `render_for_viz()` + `write_tick_viz()`：将 module_outputs 转为 viz JSON |
| `ui/viz/index.html` | p5.js 页面容器 |
| `ui/viz/sketch.js` | 动画主体（p5.js） |
| `ui/viz/scripts/txt_to_viz.py` | 历史 run_*.txt → viz JSON 批量转换工具 |

## 修改文件

| 文件 | 改动 |
|------|------|
| `run.py` | 每 tick 完成后调用 `render_for_viz()` + `write_tick_viz()`，写入 `output/{run_id}_viz/tick_NN.json` |

---

## 架构

```
Python simulation
  每 tick 完成
    → render_for_viz(tick, event, behavior, emotion, module_outputs)
    → write_tick_viz(run_id, tick, viz_data)
    → output/{run_id}_viz/tick_01.json
                         tick_02.json ...

python3 -m http.server 8000（项目根目录）
  ↓ 静态文件服务

p5.js 前端（ui/viz/index.html?run={run_id}）
  → fetch tick_NN.json（轮询，每 5 秒重试）
  → 播放 5 分钟动画
  → 完成后 fetch 下一 tick
```

**tick 错开节奏**：simulation 每 tick 约 2-3 分钟（LLM 并发），动画播放 5 分钟。
播放 tick N 时，tick N+1 已在后台生成；动画结束时文件大概率已就绪，实现不间断播放。

---

## viz JSON 格式（per-tick）

```json
{
  "tick": 1,
  "event": "会议室的门从里面打开...",
  "time": "15:00",
  "location": "望京某互联网公司",
  "sleep_state": "AWAKE",
  "emotion": { "dominant": "sadness", "intensity": 0.48, "anger": 0.22, ... },
  "moments": [
    { "id": 0, "type": "body_sensation", "display_text": "手抖还没停，指甲压着掌心", "source": null, "module": "reactive" },
    ...
  ]
}
```

---

## render_for_viz 类型处理规则

| DES 类型 | 处理 |
|----------|------|
| `voice_intrusion` | `"name说，「content」"`（name 取 source 首个逗号前） |
| `unsymbolized` | 去掉〔〕，内容原样输出（前端负责斜体+灰色渲染） |
| 其余 | content 原样 |

---

## 动画设计参数

| 参数 | 值 | 说明 |
|------|----|------|
| `TICK_DURATION_S` | 300（5 分钟） | 每 tick 动画时长 |
| `SPAWN_FRACTION` | 0.62 | 全部 moments 在前 62% 时间内出现 |
| `REVEAL_SPEED_CPS` | 8 | 每秒解锁字符数 |
| `CHAR_FADEIN_S` | 0.40 | 单字符淡入时长（秒） |
| `HOLD_DURATION_S` | 16 | 完全显示后保持时长 |
| `HIDE_SPEED_CPS` | 6 | 每秒消隐字符数 |
| ASLEEP tick | 30 秒 | 睡眠 tick 用短时长 |

---

## 视觉设计决策

**背景**
- 半透明叠加（`fill(8, 14, 22, 0.14)`）：极深蓝底，保留 86% 前帧（拖影效果）
- Aurora 弧光：`drawingContext.createRadialGradient()` 真正平滑渐变（4 段色标，无分层）
- Aurora 颜色：HSB 亮度 46-60，饱和度 52-72（比初版亮约 3x）

**文字**
- 字号：22-27px（compressed_speech 22 / visual_fragment 24 / voice_intrusion 27）
- unsymbolized：Noto Serif SC，灰色（RGB 155,155,155），alpha 0.58
- 浮动范围：3% 边距，接近全屏
- **不换行**：computeLayout 单行布局，长文本横向延伸出屏幕
- **逐字淡入**：`charAlphas[]` 数组，每字独立 alpha，reveal 后以 `baseAlpha/0.4s` 速率淡入
- **逐字消隐**：停止绘制已消隐字符，依赖拖影背景自然退场（无跳变）

---

## 使用方式

```bash
# 1. 历史 txt 转换（run_13 已转好）
python3 ui/viz/scripts/txt_to_viz.py output/run_林晓雨_13.txt

# 2. 启动本地服务
cd ~/Projects/mind-reading
python3 -m http.server 8000

# 3. 浏览器访问
# Demo 模式（20条内置数据）：
http://localhost:8000/ui/viz/index.html?demo=1

# 历史回放：
http://localhost:8000/ui/viz/index.html?run=run_林晓雨_13

# 调试加速（10x，每 tick 30 秒）：
http://localhost:8000/ui/viz/index.html?run=run_林晓雨_13&speed=10

# 新 run 实时跑（run.py 自动写 viz JSON，前端轮询）：
python3 run.py examples/林晓雨_profile.json
```

---

## 待处理问题

- [ ] 浏览器端验证（demo 模式 + run_13 回放）
- [ ] `_TEST_ALL_MODULES = True` 和 `MAX_TICKS = 5` 需改回生产值（见 run.py L24 / cognitive_engine.py L56）
- [ ] imagery 模块与 aesthetic 边界模糊（P2，run_14 评估后决定是否调整 prompt）

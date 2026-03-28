# 可视化视觉迭代（sketch.js v2 → v3）

**日期**：2026-03-27
**状态**：已实现，demo 截图验证通过
**文件**：`ui/viz/sketch.js`（唯一修改文件）

---

## 本轮变更概览

### v2 改动（视觉增强）

| 项目 | 旧值 | 新值 | 说明 |
|------|------|------|------|
| `REVEAL_SPEED_CPS` | 8 | 3 | 字符浮现减慢，意识浮出感 |
| `HOLD_DURATION_S` | 16 | 90 | 大幅延长停留，产生屏幕堆叠感 |
| `HIDE_SPEED_CPS` | 6 | 2 | 消隐减慢 |
| `CHAR_FADEIN_S` | 0.40 | 0.60 | 单字淡入略慢 |
| `DRIFT_ANGLE_HALF` | ±45° | ±70° | 更大倾斜范围 |
| dy 系数 | 0.30 | 0.50 | 垂直漂移增强 |

**新增功能**：
- **DES 类型色相区分**：所有类型改为亮色低饱和（HSB 饱和度 15-32，亮度 88-98），色相区分：
  - visual_fragment → 冷蓝白（H210）
  - body_sensation → 暖橙（H20）
  - voice_intrusion → 暖黄（H50）
  - compressed_speech → 淡紫（H270）
  - expanded_speech → 淡青（H180）
  - intrusion → 淡粉（H0）
  - unsymbolized → 灰色保留原样（serif）
- **情绪背景调色**：`EMOTION_BG_RGB` 映射，`currentBgRgb` 每帧 lerp 过渡（~5秒）
  - sadness=靛蓝 / anger=暗红 / joy=琥珀 / fear=深紫 / disgust=墨绿 / surprise=深青
- **情绪环境光晕**：`drawEmotionAmbient()` 在 Aurora 底层叠加情绪色大光晕，强度随 intensity 变化（0.05–0.13）
- **Y 轴软偏好**：voice_intrusion 偏上（0-42%），body_sensation 偏下（55-93%），其余全屏
- **微振动**：每 moment 独立 `wobblePhase`，sin/cos 轻微摆动（±0.12px/帧）
- **出场密度**：高情绪强度收窄 `currentSpawnFraction`（0.40–0.62）
- **Demo 情绪轮换**：每 tick 切换情绪（sadness/anger/joy/fear/surprise），方便验证背景调色

### v3 改动（生命周期重构）

**核心变化**：废弃"hold + 逐字消隐"机制，改为"全局 alpha 渐退"。

| 项目 | 旧值 | 新值 |
|------|------|------|
| `TICK_DURATION_S` | 300s（speed=10 → 30s/tick） | 600s（speed=10 → 60s/tick） |
| `HOLD_DURATION_S` | 90 | 已移除 |
| `HIDE_SPEED_CPS` | 2 | 已移除 |
| `FADE_DURATION_S` | — | `TICK_DURATION_S × 1.5`（=90s at speed=10） |

**moment 生命周期**（新）：
```
revealing → fading → done
```
- `revealing`：chars 逐字淡入（charAlphas，原有机制）
- `fading`：所有 chars 已出现，`globalAlpha` 以 `speedMultiplier / FADE_DURATION_S` 速率线性下降
- `done`：`globalAlpha <= 0`，从数组移除

**跨 tick 残留**：
- tick 过渡时不再执行 `moments = []`
- 旧 tick 文字继续在新 tick 背景上自然渐退叠压
- tick 1 最早出现的字在 ~90s 后（tick 2 中段）消失；最晚出现的字（t≈37s）在 ~127s（tick 2 末尾）消失

**渲染**：`drawMoment` 中每字 alpha = `charAlphas[i] * globalAlpha`（两层乘积）

---

## 架构讨论：是否拆模块

结论：**暂不拆分**。

- 文件 536 行，注释段落边界清晰，无实质性冗余
- p5.js global mode + 共享状态（moments/frameNow/tickData）跨"模块"强耦合，拆分需改 instance mode，代价中等
- 唯一值得做的轻量操作：提取 `config.js`（常量 + 数据表）+ 合并 `drawLoading/Waiting/Error` → `drawStatus()`，但目前不紧迫

---

## 视觉效果截图

- 6s 时：8 条 moment，背景蓝紫（anger），颜色区分清晰，Y 偏好生效
- 16s 时：18 条 moment 同屏叠压，早期字开始渐退，堆积感达到预期

---

## 待处理

- [ ] 回放 run_13 验证（真实数据 vs demo 数据效果差异）
- [ ] 恢复生产模式跑 run_14（`_TEST_ALL_MODULES=False` / `MAX_TICKS=20`）
- [ ] run_14 评估后决定 imagery 模块（与 aesthetic 边界模糊，P2）

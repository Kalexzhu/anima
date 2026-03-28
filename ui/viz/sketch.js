/**
 * sketch.js — ANIMA 意识流文字漂浮动画
 * v3: 60s/tick / 全局 alpha 渐退 / 跨 tick 叠压残留
 *
 * URL 参数：
 *   ?run=run_林晓雨_13   → 加载 output/run_林晓雨_13_viz/tick_01.json ...
 *   ?speed=1.0           → 时间倍速（调试：speed=10 → 每 tick 60 秒）
 *   ?demo=1              → 内置演示数据，无需后端
 */

// ── 配置 ──────────────────────────────────────────────────────────────────────

const TICK_DURATION_S   = 10 * 60;  // 每 tick 10 分钟（speed=10 → 60s）
const EVENT_DISPLAY_S   = 6;
const POLL_INTERVAL_MS  = 5000;

const SPAWN_FRACTION    = 0.62;     // 全部 moments 在前 62% 时间内出现
const REVEAL_SPEED_CPS  = 3;        // 每秒解锁字符数
const CHAR_FADEIN_S     = 0.60;     // 单字符淡入时长（秒）
// 全局渐退：字符全部出现后开始，持续 1.0 tick → tick1 文字在 tick2 中段消失
const FADE_DURATION_S   = TICK_DURATION_S * 1.0;

const DRIFT_SPEED_MIN   = 0.10;
const DRIFT_SPEED_MAX   = 0.35;
const DRIFT_ANGLE_HALF  = 70 * Math.PI / 180;  // ±70° 漂浮角度范围

// 各 DES 类型视觉样式（亮色低饱和，色相区分）
const TYPE_STYLES = {
  visual_fragment:   { size: 24, baseAlpha: 0.88, color: hsbToRgb(210, 22, 92), serif: false },
  body_sensation:    { size: 24, baseAlpha: 0.83, color: hsbToRgb( 20, 32, 96), serif: false },
  voice_intrusion:   { size: 27, baseAlpha: 0.94, color: hsbToRgb( 50, 28, 98), serif: false },
  compressed_speech: { size: 22, baseAlpha: 0.86, color: hsbToRgb(270, 22, 92), serif: false },
  expanded_speech:   { size: 22, baseAlpha: 0.86, color: hsbToRgb(180, 20, 92), serif: false },
  unsymbolized:      { size: 20, baseAlpha: 0.58, color: [155, 155, 155],        serif: true  },
  intrusion:         { size: 20, baseAlpha: 0.72, color: hsbToRgb(  0, 26, 90), serif: false },
  unknown:           { size: 22, baseAlpha: 0.78, color: hsbToRgb(240, 15, 88), serif: false },
};

// 情绪 → 背景叠加色
const EMOTION_BG_RGB = {
  sadness:  [ 7, 10, 30],
  anger:    [30,  6,  6],
  joy:      [26, 22,  6],
  fear:     [18,  5, 30],
  disgust:  [ 5, 22,  8],
  surprise: [ 5, 22, 22],
  unknown:  [ 8, 14, 22],
};

// 情绪 → 环境光晕色相
const EMOTION_AURORA_H = {
  sadness: 220, anger: 5, joy: 45, fear: 280, disgust: 120, surprise: 175, unknown: 210,
};

// Aurora 装饰弧光
const AURORA_DEFS = [
  { h: 210, s: 68, b: 60 },
  { h: 265, s: 58, b: 52 },
  { h: 183, s: 65, b: 56 },
  { h: 240, s: 52, b: 46 },
  { h: 194, s: 72, b: 58 },
];

// ── 全局状态 ──────────────────────────────────────────────────────────────────

let runId, speedMultiplier, useDemo;
let phase = 'loading';
let currentTick = 1;
let tickData = null;
let moments = [];
let nextMomentIdx = 0;
let tickStartTime = 0;
let phaseStartTime = 0;
let pollTimer = 0;
let lastFrameMs = 0;
let frameNow = 0;
let auroraArcs = [];
let infoEl;

let currentBgRgb         = [8, 14, 22];
let targetBgRgb          = [8, 14, 22];
let currentSpawnFraction = SPAWN_FRACTION;
let showEventPanel       = false;

// ── setup / draw ──────────────────────────────────────────────────────────────

function setup() {
  createCanvas(windowWidth, windowHeight);
  colorMode(RGB, 255, 255, 255, 1.0);
  textAlign(LEFT, TOP);
  noStroke();

  infoEl = document.getElementById('info');
  lastFrameMs = millis();

  const p = new URLSearchParams(window.location.search);
  runId           = p.get('run') || null;
  speedMultiplier = parseFloat(p.get('speed') || '1.0');
  useDemo         = p.get('demo') === '1';

  for (let i = 0; i < AURORA_DEFS.length; i++) {
    const def = AURORA_DEFS[i];
    const rgb = hsbToRgb(def.h, def.s, def.b);
    auroraArcs.push({
      x:      random(width  * 0.1, width  * 0.9),
      y:      random(height * 0.1, height * 0.9),
      r:      random(max(width, height) * 0.42, max(width, height) * 0.85),
      speedX: random(0.18, 0.35) * (random() > 0.5 ? 1 : -1),
      speedY: random(0.10, 0.22) * (random() > 0.5 ? 1 : -1),
      rgb,
    });
  }

  if (useDemo) {
    tickData = buildDemoTick();
    startTick();
  } else if (!runId) {
    phase = 'error';
  } else {
    loadTick(currentTick);
  }
}

function draw() {
  frameNow = millis();
  const dt = (frameNow - lastFrameMs) / 1000;
  lastFrameMs = frameNow;

  // 背景叠加（拖影 + 情绪色调，逐帧 lerp）
  const lr = 0.012;
  currentBgRgb[0] += (targetBgRgb[0] - currentBgRgb[0]) * lr;
  currentBgRgb[1] += (targetBgRgb[1] - currentBgRgb[1]) * lr;
  currentBgRgb[2] += (targetBgRgb[2] - currentBgRgb[2]) * lr;
  fill(currentBgRgb[0], currentBgRgb[1], currentBgRgb[2], 0.14);
  rect(0, 0, width, height);

  drawAurora();

  const tickMs  = TICK_DURATION_S * 1000 / speedMultiplier;
  const eventMs = EVENT_DISPLAY_S * 1000 / speedMultiplier;

  if (phase === 'loading') {
    drawLoading();
    updateAndDraw(dt);  // 旧 tick 的 moments 继续渐退

  } else if (phase === 'animating') {
    const elapsed  = frameNow - tickStartTime;
    const progress = constrain(elapsed / tickMs, 0, 1);
    const total    = tickData ? tickData.moments.length : 0;

    if (total > 0 && nextMomentIdx < total) {
      const threshold = (nextMomentIdx / total) * currentSpawnFraction;
      if (progress >= threshold) {
        spawnMoment(tickData.moments[nextMomentIdx++]);
      }
    }

    updateAndDraw(dt);

    if (elapsed >= tickMs) {
      phase = 'event_display';
      phaseStartTime = frameNow;
    }

  } else if (phase === 'event_display') {
    updateAndDraw(dt);
    const e    = frameNow - phaseStartTime;
    const fin  = constrain(e / 900, 0, 1);
    const fout = constrain((e - (eventMs - 900)) / 900, 0, 1);
    drawEventOverlay(fin * (1 - fout));
    if (e >= eventMs) {
      // 不清除 moments — 旧 tick 文字继续自然渐退
      currentTick++;
      phase = 'loading';
      if (useDemo) { tickData = buildDemoTick(); startTick(); }
      else loadTick(currentTick);
    }

  } else if (phase === 'waiting') {
    updateAndDraw(dt);
    drawWaiting();
    if (frameNow - pollTimer > POLL_INTERVAL_MS) {
      pollTimer = frameNow;
      loadTick(currentTick);
    }

  } else if (phase === 'error' || phase === 'error_no_data') {
    drawError();
  }

  drawEventIcon();
  updateInfo();
}

function windowResized() {
  resizeCanvas(windowWidth, windowHeight);
}

// ── tick 管理 ─────────────────────────────────────────────────────────────────

function loadTick(n) {
  const url = `../../output/${runId}_viz/tick_${String(n).padStart(2, '0')}.json`;
  fetch(url)
    .then(r => { if (!r.ok) throw n; return r.json(); })
    .then(data => { tickData = data; startTick(); })
    .catch(() => {
      phase = n === 1 ? 'error_no_data' : 'waiting';
      pollTimer = millis();
    });
}

function startTick() {
  nextMomentIdx = 0;
  tickStartTime = millis();
  phase = 'animating';
  // moments 数组不清除——旧 tick 文字继续渐退

  if (tickData && tickData.emotion) {
    const dom       = tickData.emotion.dominant || 'unknown';
    const intensity = tickData.emotion.intensity || 0.3;
    targetBgRgb          = (EMOTION_BG_RGB[dom] || EMOTION_BG_RGB.unknown).slice();
    currentSpawnFraction = Math.max(0.40, SPAWN_FRACTION - intensity * 0.15);
  } else {
    targetBgRgb          = EMOTION_BG_RGB.unknown.slice();
    currentSpawnFraction = SPAWN_FRACTION;
  }
}

// ── moment 生命周期 ───────────────────────────────────────────────────────────

function spawnMoment(data) {
  const style = TYPE_STYLES[data.type] || TYPE_STYLES.unknown;
  const text  = data.display_text;

  // Y 轴偏好
  let yMin, yMax;
  if (data.type === 'voice_intrusion') {
    yMin = height * 0.04;  yMax = height * 0.42;
  } else if (data.type === 'body_sensation') {
    yMin = height * 0.55;  yMax = height * 0.93;
  } else {
    yMin = height * 0.04;  yMax = height * 0.93;
  }

  const x = random(width * 0.03, width * 0.95);
  const y = random(yMin, yMax);

  const base  = random() > 0.5 ? 0 : Math.PI;
  const angle = base + random(-DRIFT_ANGLE_HALF, DRIFT_ANGLE_HALF);
  const spd   = random(DRIFT_SPEED_MIN, DRIFT_SPEED_MAX);

  const charAlphas = new Float32Array(text.length).fill(0);

  moments.push({
    text,
    type:           data.type,
    style,
    x, y,
    dx:             Math.cos(angle) * spd,
    dy:             Math.sin(angle) * spd * 0.50,
    wobblePhase:    random(0, Math.PI * 2),
    rotation:       random(-0.06, 0.06),  // 初始倾斜角度（弧度，约±3.4°）
    charAlphas,
    revealProgress: 0,
    globalAlpha:    1.0,   // 字符全部出现后，此值随时间线性下降至 0
    phase:          'revealing',
    chars:          null,
  });
}

function updateAndDraw(dt) {
  const revSpd   = REVEAL_SPEED_CPS * dt * speedMultiplier;
  // 全局渐退速率：使 globalAlpha 在 FADE_DURATION_S 内从 1 降到 0
  const fadeRate = speedMultiplier / FADE_DURATION_S;

  for (let i = moments.length - 1; i >= 0; i--) {
    const m = moments[i];
    if (m.phase === 'done') { moments.splice(i, 1); continue; }

    const len = m.text.length;

    if (m.phase === 'revealing') {
      m.revealProgress = Math.min(len, m.revealProgress + revSpd);
      if (m.revealProgress >= len) m.phase = 'fading';

    } else if (m.phase === 'fading') {
      m.globalAlpha = Math.max(0, m.globalAlpha - fadeRate * dt);
      if (m.globalAlpha <= 0) { m.phase = 'done'; continue; }
    }

    // 各字符淡入（reveal 阶段）
    const revealedCount = Math.floor(m.revealProgress);
    const alphaRate     = m.style.baseAlpha / CHAR_FADEIN_S * dt;
    for (let ci = 0; ci < len; ci++) {
      if (ci < revealedCount) {
        m.charAlphas[ci] = Math.min(m.style.baseAlpha, m.charAlphas[ci] + alphaRate);
      }
    }

    // 漂浮 + 微振动
    m.x += m.dx + Math.sin(frameNow * 0.0009 + m.wobblePhase) * 0.12;
    m.y += m.dy + Math.cos(frameNow * 0.0007 + m.wobblePhase * 0.8) * 0.08;

    drawMoment(m);
  }
}

// ── 字符渲染 ──────────────────────────────────────────────────────────────────

function drawMoment(m) {
  const s = m.style;
  if (!m.chars) m.chars = computeLayout(m.text, s);

  const [cr, cg, cb] = s.color;
  const ga = m.globalAlpha;   // 全局渐退乘数

  push();
  noStroke();
  textSize(s.size);
  textFont(s.serif ? 'Noto Serif SC' : 'Noto Sans SC');
  textAlign(LEFT, TOP);
  translate(m.x, m.y);
  rotate(m.rotation || 0);

  for (let i = 0; i < m.text.length; i++) {
    const a = m.charAlphas[i] * ga;
    if (a < 0.005) continue;

    const ch = m.chars[i];
    if (!ch) continue;

    fill(0, 0, 0, a * 0.40);
    text(ch.char, ch.x + 1, ch.y + 1);

    fill(cr, cg, cb, a);
    text(ch.char, ch.x, ch.y);
  }

  pop();
}

function computeLayout(text, style) {
  push();
  textSize(style.size);
  textFont(style.serif ? 'Noto Serif SC' : 'Noto Sans SC');
  textAlign(LEFT, TOP);

  let cx = 0;
  const result = [];
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    result.push({ char: ch, x: cx, y: 0 });
    cx += textWidth(ch);
  }
  pop();
  return result;
}

// ── 背景弧光 ──────────────────────────────────────────────────────────────────

function drawAurora() {
  const ctx = drawingContext;
  drawEmotionAmbient(ctx);

  for (const arc of auroraArcs) {
    arc.x += arc.speedX;
    arc.y += arc.speedY;

    if (arc.x < -arc.r || arc.x > width  + arc.r) arc.speedX *= -1;
    if (arc.y < -arc.r || arc.y > height + arc.r) arc.speedY *= -1;

    const [r, g, b] = arc.rgb;
    const grad = ctx.createRadialGradient(arc.x, arc.y, 0, arc.x, arc.y, arc.r);
    grad.addColorStop(0.00, `rgba(${r}, ${g}, ${b}, 0.22)`);
    grad.addColorStop(0.35, `rgba(${r}, ${g}, ${b}, 0.10)`);
    grad.addColorStop(0.65, `rgba(${r}, ${g}, ${b}, 0.03)`);
    grad.addColorStop(1.00, `rgba(${r}, ${g}, ${b}, 0.00)`);

    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.ellipse(arc.x, arc.y, arc.r, arc.r * 0.65, 0, 0, Math.PI * 2);
    ctx.fill();
  }
}

function drawEmotionAmbient(ctx) {
  if (!tickData || !tickData.emotion) return;
  const dom       = tickData.emotion.dominant || 'unknown';
  const intensity = tickData.emotion.intensity || 0.3;
  const h         = EMOTION_AURORA_H[dom] || EMOTION_AURORA_H.unknown;
  const [r, g, b] = hsbToRgb(h, 38 + intensity * 28, 44 + intensity * 18);
  const maxAlpha  = 0.05 + intensity * 0.08;

  const cx = width * 0.5, cy = height * 0.5;
  const radius = Math.max(width, height) * 1.05;

  const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius);
  grad.addColorStop(0.0, `rgba(${r}, ${g}, ${b}, ${maxAlpha.toFixed(3)})`);
  grad.addColorStop(0.5, `rgba(${r}, ${g}, ${b}, ${(maxAlpha * 0.35).toFixed(3)})`);
  grad.addColorStop(1.0, `rgba(${r}, ${g}, ${b}, 0)`);

  ctx.fillStyle = grad;
  ctx.beginPath();
  ctx.ellipse(cx, cy, radius, radius * 0.72, 0, 0, Math.PI * 2);
  ctx.fill();
}

// ── 工具函数 ──────────────────────────────────────────────────────────────────

function hsbToRgb(h, s, b) {
  s /= 100; b /= 100;
  const k = n => (n + h / 60) % 6;
  const f = n => b * (1 - s * Math.max(0, Math.min(k(n), 4 - k(n), 1)));
  return [Math.round(f(5) * 255), Math.round(f(3) * 255), Math.round(f(1) * 255)];
}

// ── UI 绘制 ───────────────────────────────────────────────────────────────────

function drawEventOverlay(alpha) {
  if (!tickData || alpha <= 0) return;

  const cx = width / 2, cy = height / 2;
  const eventStr = tickData.event || '（无新事件）';
  const metaStr  = [
    tickData.time     ? `⏰ ${tickData.time}`     : '',
    tickData.location ? `📍 ${tickData.location}` : '',
  ].filter(Boolean).join('  ');

  push();
  textAlign(CENTER, CENTER);
  noStroke();

  fill(8, 14, 22, alpha * 0.70);
  rectMode(CENTER);
  rect(cx, cy, min(width * 0.78, 640), 165, 12);

  textFont('Noto Sans SC');

  textSize(19);
  fill(255, 255, 255, alpha * 0.95);
  text(eventStr, cx, cy - 16, 580, 80);

  if (metaStr) {
    textSize(13);
    fill(170, 170, 170, alpha * 0.75);
    text(metaStr, cx, cy + 22);
  }

  textSize(11);
  fill(110, 110, 110, alpha * 0.55);
  text(`TICK ${String(tickData.tick).padStart(2, '0')}`, cx, cy + 44);
  pop();
}

function drawLoading() {
  push();
  textAlign(CENTER, CENTER);
  textFont('Noto Sans SC');
  textSize(14);
  const p = 0.35 + 0.35 * Math.sin(frameNow * 0.003);
  fill(190, 190, 190, p);
  text('载入中…', width / 2, height / 2);
  pop();
}

function drawWaiting() {
  push();
  textAlign(RIGHT, BOTTOM);
  textFont('Noto Sans SC');
  textSize(11);
  const p = 0.28 + 0.28 * Math.sin(frameNow * 0.002);
  fill(110, 110, 110, p);
  text(`等待轮次 ${String(currentTick).padStart(2, '0')}…`, width - 20, height - 16);
  pop();
}

function drawError() {
  push();
  textAlign(CENTER, CENTER);
  textFont('Noto Serif SC');
  textSize(14);
  fill(210, 90, 90, 0.75);
  const msg = phase === 'error_no_data'
    ? '找不到 viz JSON 文件\n\n请先运行：\npython3 run.py  或  python3 ui/viz/scripts/txt_to_viz.py output/run_*.txt'
    : '请在 URL 中指定 ?run=run_XX 参数\n或使用 ?demo=1 查看演示';
  text(msg, width / 2, height / 2, 520, 240);
  pop();
}

function updateInfo() {
  if (!infoEl) return;
  const elapsed = tickData ? ((frameNow - tickStartTime) / 1000).toFixed(0) : '—';
  const total   = (TICK_DURATION_S / speedMultiplier).toFixed(0);
  const dom     = tickData?.emotion?.dominant || '—';
  const ity     = tickData?.emotion?.intensity != null
    ? tickData.emotion.intensity.toFixed(2) : '—';
  infoEl.textContent =
    `tick ${currentTick} | ${elapsed}s/${total}s | ${moments.length} active | ${dom}(${ity}) | ${runId || 'demo'}`;
}

// ── 左上角事件 Icon ───────────────────────────────────────────────────────────

const _ICON_X = 24, _ICON_Y = 24, _ICON_R = 12;

function drawEventIcon() {
  const hover = dist(mouseX, mouseY, _ICON_X, _ICON_Y) <= _ICON_R + 4;

  push();
  noStroke();

  // 圆形背景
  fill(255, 255, 255, showEventPanel ? 0.22 : (hover ? 0.15 : 0.09));
  ellipse(_ICON_X, _ICON_Y, _ICON_R * 2, _ICON_R * 2);

  // "i" 字
  textAlign(CENTER, CENTER);
  textFont('Noto Sans SC');
  textSize(13);
  fill(180, 180, 180, showEventPanel ? 0.95 : 0.70);
  text('i', _ICON_X, _ICON_Y + 1);

  // 事件面板
  if (showEventPanel && tickData) {
    const px = 8, py = _ICON_Y + _ICON_R + 8;
    const pw = min(width * 0.50, 460);

    const tickLabel = `TICK ${String(tickData.tick || currentTick).padStart(2, '0')}`;
    const eventStr  = tickData.event || '（无事件）';
    const metaStr   = [
      tickData.time     ? `⏰ ${tickData.time}`     : '',
      tickData.location ? `📍 ${tickData.location}` : '',
    ].filter(Boolean).join('  ');

    const panelH = metaStr ? 96 : 74;

    fill(8, 14, 22, 0.80);
    rect(px, py, pw, panelH, 7);

    textAlign(LEFT, TOP);
    textFont('Noto Sans SC');

    textSize(10);
    fill(100, 100, 100, 0.70);
    text(tickLabel, px + 12, py + 10);

    textSize(14);
    fill(215, 215, 215, 0.90);
    text(eventStr, px + 12, py + 26, pw - 24, 36);

    if (metaStr) {
      textSize(11);
      fill(130, 130, 130, 0.65);
      text(metaStr, px + 12, py + 76);
    }
  }

  pop();
}

function mouseClicked() {
  if (dist(mouseX, mouseY, _ICON_X, _ICON_Y) <= _ICON_R + 4) {
    showEventPanel = !showEventPanel;
  }
}

// ── Demo 数据 ─────────────────────────────────────────────────────────────────

function buildDemoTick() {
  const emotions  = ['sadness', 'anger', 'joy', 'fear', 'surprise'];
  const dom       = emotions[currentTick % emotions.length];
  const intensity = 0.3 + (currentTick % 5) * 0.12;
  return {
    tick: currentTick,
    event: '会议室的门从里面打开，陈总和另外两个人走出来边走边说话',
    time: '15:00',
    location: '望京某互联网公司',
    sleep_state: 'AWAKE',
    emotion: { dominant: dom, intensity },
    moments: [
      { id:  0, type: 'body_sensation',   display_text: '手抖还没停，指甲压着掌心' },
      { id:  1, type: 'voice_intrusion',  display_text: '李杨说，「你太累了」' },
      { id:  2, type: 'visual_fragment',  display_text: '会议室里陈总转过来看她的那一秒，其他人低着头' },
      { id:  3, type: 'unsymbolized',     display_text: '知道自己在想那件事和这件事是不是同一件事，但没有词' },
      { id:  4, type: 'compressed_speech',display_text: '一直都是——' },
      { id:  5, type: 'voice_intrusion',  display_text: '陈总说，「这点基本逻辑都不懂？」' },
      { id:  6, type: 'visual_fragment',  display_text: '窗外那棵树上有个塑料袋挂着' },
      { id:  7, type: 'body_sensation',   display_text: '胸口有一块东西，不疼，压着，手放在膝盖上没有温度' },
      { id:  8, type: 'compressed_speech',display_text: '两周。跑偏了。两周。' },
      { id:  9, type: 'visual_fragment',  display_text: '走廊窗玻璃上有一条细长反光带，约3毫米宽，颜色接近冷白偏青' },
      { id: 10, type: 'unsymbolized',     display_text: '某个配比是对的，不是「好看」，是「准确」' },
      { id: 11, type: 'visual_fragment',  display_text: '合肥，某国企办公室，下午三点，窗外是熟悉的老街道' },
      { id: 12, type: 'body_sensation',   display_text: '脸颊有一阵热，从耳根往下走，到脖子停住' },
      { id: 13, type: 'voice_intrusion',  display_text: '22岁时的主管说，「这个思路很清晰，值得给大家看看。」' },
      { id: 14, type: 'visual_fragment',  display_text: '今晚十一点，坐在出租屋卫生间地板上，瓷砖是冷的，贴着脊背' },
      { id: 15, type: 'body_sensation',   display_text: '眼眶里有点热，鼻梁有点酸，喉咙那里卡着什么' },
      { id: 16, type: 'unsymbolized',     display_text: '「两周」这件事还在某处没有结束，像一个文件夹没有关掉' },
      { id: 17, type: 'compressed_speech',display_text: '那个蓝调了四十分钟' },
      { id: 18, type: 'visual_fragment',  display_text: '地铁车厢顶部灯带，等间距排列，每段约1.2米，接缝处有暗区' },
      { id: 19, type: 'voice_intrusion',  display_text: '张明说，「你怎么不回我消息」' },
    ],
  };
}

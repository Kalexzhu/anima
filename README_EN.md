<div align="center">

<img src="docs/assets/logo.png" width="180" alt="anima logo"/>

# anima

**A Concurrent Cognitive Engine for Simulating the Human Inner World**

[![GitHub Stars](https://img.shields.io/github/stars/Kalexzhu/anima?style=flat-square&color=DAA520)](https://github.com/Kalexzhu/anima/stargazers)
[![GitHub Forks](https://img.shields.io/github/forks/Kalexzhu/anima?style=flat-square&color=DAA520)](https://github.com/Kalexzhu/anima/network)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12-blue?style=flat-square&logo=python)](https://python.org)
[![Claude API](https://img.shields.io/badge/Powered%20by-Claude%20API-8A2BE2?style=flat-square)](https://anthropic.com)

🌐 **Language**: [中文](README.md) | English

</div>

---

## What is this

**anima** is not a chatbot, not sentiment analysis, and not dialogue generation.

It simulates what happens inside a person's mind when they're alone — continuously, without waiting to be asked.

Given a psychological profile, anima runs 11 concurrent cognitive modules to generate an unbroken stream of consciousness. Here's what one tick looks like for Lin Xiaoyu — a 28-year-old product designer who just had her two-week project publicly rejected in a meeting, sitting alone by a corridor window:

```
Her ex Li Yang's voice: "You're exhausting. Being with you, I can't breathe."
Something on the back of her hand, pressing — not pain exactly.
The whiteboard in the conference room. Red marker. "Logic completely off." Chen's handwriting.
It's me, it's always—
〔Knows she's thinking about something from age 13. No image, no words. Just that place, still there.〕
Her mother: "You've always been too hard on yourself. What's the point of running yourself into the ground?"
Hold it together. Can't cry here.

……

The paper offer from a government supply cooperative back in Hefei — monthly salary 4,800 yuan,
ten minutes' walk from home. She threw it straight in the trash.
Someone else uses that desk drawer now.
They don't sit in corridors there.
〔One timeline: Wangjing, two weeks, this corridor, the fire evacuation map taped to the window.
  Another timeline: none of what's in this one.
  Both exist simultaneously. No judgment of better or worse. Just a difference in number.〕
```

---

## Demo

**Kobe Bryant · Late night, January 25, 2020**

<div align="center">
<img src="docs/assets/Kobe_zh.gif" width="75%" alt="Kobe cognitive simulation"/>
</div>

**Lin Xiaoyu · After her project was rejected**

<div align="center">
<img src="docs/assets/lin_zh.gif" width="75%" alt="Lin Xiaoyu cognitive simulation"/>
</div>

---

## How it Works

### Why 11 concurrent modules

Killingsworth & Gilbert (2010) found that humans spend **47% of waking hours in mind-wandering** — and that wandering is not sequential. Emotional residue, memory surfacing, intrusive voices, logical inference: they don't queue up, they happen simultaneously.

anima uses `ThreadPoolExecutor` to run 11 cognitive modules in parallel, each making its own LLM call:

| Module | Research Basis | What it does |
|--------|---------------|--------------|
| ReactiveModule | OCC cognitive appraisal theory | Immediate response to current events |
| rumination | Nolen-Hoeksema, 1991 | Looping replay of the same event; body-grounded |
| self_eval | Medial PFC self-referential processing | Third-person observation of own behavior patterns |
| philosophy | Smallwood, narrative identity | Concrete situation → abstract inquiry; no conclusions |
| aesthetic | Dijksterhuis & Meurs, 2006 | Cross-domain form perception — proportion, rhythm, color |
| counterfactual | Roese, 1997 | "What if I had..." timeline forks |
| positive_memory | DMN autobiographical memory activation | Sensory-rich positive memory scenes; no analysis |
| daydream | Killingsworth & Gilbert, 2010 | Hedonic sensory chain — smell → light → touch → temperature |
| future | Atance & O'Neill, mental time travel | Arriving in a future scene; constrained to within 24 hours |
| social_rehearsal | Lieberman, 2007, mentalizing network | Hypothetical dialogue: I say → they react → outcome |
| imagery | — | Non-linear perceptual fragments at the edge of consciousness |

### The Trunk System (WorldState)

Attention doesn't wander randomly — it orbits unresolved life-domain issues. Career uncertainty. A relationship that ended badly. A parent waiting for a call back. These form deep cognitive "trunks" that attention keeps returning to across time.

anima extracts 2–4 Trunks from a profile, each belonging to a different life domain (work / romance / family / identity / friendship…). Each tick, a **Softmax + Recency Penalty** algorithm selects the most salient Trunk, which simultaneously drives:

- **External world**: WorldEngine generates domain-consistent events
- **Internal drift**: rumination, philosophy, self_eval, future modules use the Trunk as their cognitive anchor

```
Example tick — Trunk: work domain ("stay or leave after the rejection")
  External event: Manager stops in the corridor — "I sent the notes on your project. Come find me."
  rumination:    Chest tight. Replaying the rejected proposal over and over.
  philosophy:    Is effort building something, or is it just indefinitely deferring a question with no answer?
  future:        Tonight, open the laptop. Blank document. Then what.
```

### Cognitive Fingerprint

Different characters don't just think about different things — they think *differently*. The cognitive fingerprint captures individuality across three dimensions:

| Dimension | Purpose | Lin Xiaoyu | Kobe |
|-----------|---------|------------|------|
| **inner_voice_style** | How they talk to themselves | Second-person self-judgment: "You again—" | Command-style fragments: "Again." "Not enough." |
| **somatic_anchors** | Where emotions land in the body | Chest tightness, cold fingers | Shoulder tension, knee ache |
| **cognitive_default** | Default stress response | Replays others' facial expressions | Immediately dissects failure mechanics |

Same rumination module, radically different output — driven by ~80 characters of cognitive context, not per-module customization.

Each relationship also has a **speech_style** field, making voice intrusions from different people distinctly recognizable.

### Emotion Model

Based on OCC cognitive appraisal theory, producing an **8-dimensional Plutchik vector** (anger / fear / joy / sadness / surprise / disgust / anticipation / trust). Emotions have **inertial decay** across ticks (decay=0.4/tick) — the accumulated state from one moment shapes the next.

---

## Quick Start

### Requirements

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.12+ | — |
| Anthropic API Key | — | Required — drives core modules |
| DashScope API Key | — | Optional — switches fast layer to qwen3-max, significantly reduces cost |

### Install

```bash
git clone https://github.com/Kalexzhu/anima.git
cd anima
pip3 install -r requirements.txt
cp .env.example .env
```

Edit `.env`:

**Minimal (Claude only)**

```dotenv
ANTHROPIC_API_KEY=sk-ant-xxxxxxxx
CLAUDE_MODEL=claude-sonnet-4-6
```

**Recommended (Claude + Qwen, lower cost)**

```dotenv
ANTHROPIC_API_KEY=sk-ant-xxxxxxxx
CLAUDE_MODEL=claude-sonnet-4-6

# Fast layer (emotion calculation, perception, world engine) → qwen3-max
FAST_LLM_API_KEY=sk-xxxxxxxx
FAST_LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
FAST_LLM_MODEL=qwen3-max
```

Get a DashScope API Key at [Alibaba Cloud Bailian](https://bailian.console.aliyun.com/).

### Run

```bash
# Run with the built-in example (Lin Xiaoyu)
python3 run.py examples/demo_profile.json

# Specify number of ticks
python3 run.py examples/demo_profile.json --max-ticks 10
```

Output is saved to `output/` (txt + json + viz JSON per tick).

### View Visualization

```bash
python3 -m http.server 8000
```

Open `http://localhost:8000/ui/viz/` in any browser, then select a run file.

---

## Example Profiles

Two complete profiles are included and ready to run:

### Lin Xiaoyu

```
28 years old · Product designer · Beijing
Traits: introverted, perfectionist, high empathy, emotional suppression
Situation: Just had her two-week project publicly rejected in a meeting;
           sitting alone by the corridor window
Physical state: heart racing, hands slightly trembling, holding back tears
```

```bash
python3 run.py examples/demo_profile.json
```

### Kobe Bryant

```
41 years old · Retired athlete, creator, father
Snapshot: Late night, January 25, 2020
LeBron just surpassed him as the NBA's 3rd all-time scorer
Flying with Gigi to a training session in the morning
```

> **Disclaimer**: This profile is an artistic and technical demonstration. It does not represent Kobe Bryant's actual thoughts or inner world. All content is AI-generated from public information. Dedicated to him and Gianna.

```bash
python3 scenarios/kobe_2020/runner.py
```

---

## Building a Custom Profile

Reference `examples/demo_profile.json`. Key fields:

```json
{
  "name": "Character name",
  "age": 28,
  "current_situation": "Current context (the more specific the better)",
  "current_physical_state": "Body awareness right now",
  "personality_traits": ["introverted", "perfectionist"],
  "cognitive_biases": ["self-blame", "catastrophizing"],
  "memories": [
    {"age": 13, "event": "...", "emotion_tag": "shame", "importance": 0.9}
  ],
  "rumination_anchors": ["the rejected two-week project", "the last argument before the breakup"],
  "philosophy_seeds": ["Is effort just a way of avoiding a question with no answer?"],
  "desires": ["to disappear for a while", "to make one thing that's genuinely mine"],
  "daydream_anchors": ["a room where no one can find me", "sitting alone by the sea"],
  "social_pending": [
    {"person": "Manager Chen", "unresolved": "whether to bring up the project notes"}
  ]
}
```

The richer the fields, the more specific the cognitive anchors, and the more individual depth in the output.

---

## Output Format

Each tick output is based on **Descriptive Experience Sampling (DES)** methodology — classifying inner experience into moment types:

| Type | Example |
|------|---------|
| `compressed_speech` | `It's me, it's always—` |
| `visual_fragment` | `The whiteboard. Red marker. "Logic completely off."` |
| `body_sensation` | `Something pressing on the back of her hand — not pain exactly` |
| `unsymbolized` | `〔Knows she's thinking about it. No words for it.〕` |
| `voice_intrusion` | `Li Yang: "Being with you, I can't breathe."` |
| `expanded_speech` | `Is effort building something, or just indefinitely deferring...` |

---

## Visualization

- Deep navy background; consciousness fragments drift as floating text
- Different cognitive types have distinct hue and opacity
- **Character-by-character fade-in** — pacing that matches how thoughts surface
- Emotion state drives real-time background hue shifts
- Historical run playback: `?run=run_XXX`
- Demo preview mode: `?demo=1&speed=10`

---

## Roadmap

**Done**
- [x] 11-module concurrent architecture (ReactiveModule + 10 DriftModule)
- [x] OCC emotion model + Plutchik 8D vector + inertial decay
- [x] WorldState Trunk system (multi-domain rotation with Softmax)
- [x] Tick timeline + atomic writes + resume from any breakpoint
- [x] p5.js browser-side floating text visualization
- [x] Lin Xiaoyu & Kobe Bryant example profiles
- [x] Multi-API key rotation + timeout protection
- [x] Cognitive Fingerprint — character differentiation via 3 dimensions + relationship speech_style
- [x] ResidualFeedback read-only protection — original profiles no longer modified by auto-detection

**In Progress (Phase B → D)**
- [ ] Real-time audio input (Whisper streaming STT)
- [ ] Dual-loop architecture (STT Fast Loop + Cognitive Engine Slow Loop)
- [ ] TTS output (inner monologue → voice)

**Planned**
- [ ] Questionnaire system: generate profiles from structured questions
- [ ] Full English persona support
- [ ] CognitiveTwin persistent wrapper (cross-scenario comparison interface)
- [ ] Web UI

---

## License

MIT © [Kalexzhu](https://github.com/Kalexzhu)

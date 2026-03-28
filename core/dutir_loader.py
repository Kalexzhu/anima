"""
core/dutir_loader.py — DUTIR 情感词汇本体库加载与查询。

词典来源：大连理工大学信息检索研究室，27,466 词，7大类情感。
文件路径：data/dutir/emotion_lexicon.csv

主要功能：
  - 加载词典（启动时一次性，LRU 缓存）
  - jieba 分词 + 词典查表
  - 返回文本的情感得分向量（Plutchik 8 维）

DUTIR 分类码 → Plutchik 8 维映射：
  正面（P开头）:
    PA 快乐      → joy
    PB 安心      → trust
    PC 尊敬      → trust（偏权威信任）
    PD 赞扬      → joy + trust
    PE 相信      → trust
    PF 喜爱      → joy + trust
    PG 祝愿      → anticipation + joy
    PH 希望/期待 → anticipation
    PK 感激      → trust + joy

  负面（N开头）:
    NA 愤怒      → anger
    NB 悲伤      → sadness
    NC 恐惧      → fear
    ND 失望      → sadness + anticipation（负向）
    NE 疚        → disgust（自我厌恶/羞愧）
    NF 思        → sadness（思念）
    NG 慌        → fear + surprise
    NH 羞        → disgust + sadness
    NI 烦闷      → disgust + sadness
    NJ 憎恶      → disgust + anger
    NK 贬责      → disgust
    NL 妒忌      → anger + disgust
    NN 中性偏负  → disgust（轻度）

  强度归一化：DUTIR 1-9 → 0.1-0.9（÷10）
  极性：0=正向 1=中性 2=负向 3=兼有
"""

from __future__ import annotations

import csv
import os
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Tuple

import jieba

# Plutchik 8 维
PLUTCHIK_DIMS = ["anger", "fear", "joy", "sadness", "surprise", "disgust", "anticipation", "trust"]

# DUTIR 分类码 → Plutchik 维度权重
_CAT_TO_PLUTCHIK: Dict[str, Dict[str, float]] = {
    # 正面
    "PA": {"joy": 1.0},
    "PB": {"trust": 0.8, "joy": 0.2},
    "PC": {"trust": 1.0},
    "PD": {"joy": 0.6, "trust": 0.4},
    "PE": {"trust": 1.0},
    "PF": {"joy": 0.5, "trust": 0.5},
    "PG": {"anticipation": 0.6, "joy": 0.4},
    "PH": {"anticipation": 1.0},
    "PH ": {"anticipation": 1.0},  # 词典里有个带空格的脏数据
    "PK": {"trust": 0.6, "joy": 0.4},
    # 负面
    "NA": {"anger": 1.0},
    "NB": {"sadness": 1.0},
    "NC": {"fear": 1.0},
    "ND": {"sadness": 0.7, "anticipation": 0.3},  # 失望=预期落空
    "NE": {"disgust": 0.6, "sadness": 0.4},       # 内疚/羞愧
    "NF": {"sadness": 1.0},                        # 思念
    "NG": {"fear": 0.6, "surprise": 0.4},          # 慌张
    "NH": {"disgust": 0.5, "sadness": 0.5},        # 羞耻
    "NI": {"disgust": 0.5, "sadness": 0.5},        # 烦闷
    "NJ": {"disgust": 0.6, "anger": 0.4},          # 憎恶
    "NK": {"disgust": 1.0},                         # 贬责
    "NL": {"anger": 0.5, "disgust": 0.5},          # 妒忌
    "NN": {"disgust": 0.4},                         # 中性偏负（权重较低）
    # 忽略：NA 已处理，5/已经不被使用 跳过
}

_LEXICON_PATH = Path(__file__).parent.parent / "data" / "dutir" / "emotion_lexicon.csv"


@lru_cache(maxsize=1)
def _load_lexicon() -> Dict[str, Tuple[str, int, int]]:
    """
    加载词典，返回：{词: (emotion_cat, intensity, polarity)}
    同一个词有多个义项时，取强度最高的那条。
    启动时调用一次，之后从缓存读取。
    """
    lexicon: Dict[str, Tuple[str, int, int]] = {}
    with open(_LEXICON_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            word = row["word"].strip()
            cat = row["emotion_cat"].strip()
            if cat not in _CAT_TO_PLUTCHIK:
                continue
            try:
                intensity = int(row["intensity"]) if row["intensity"] else 0
                polarity = int(row["polarity"]) if row["polarity"] else 1
            except ValueError:
                continue
            # 同词多义项：取强度最高的
            if word not in lexicon or intensity > lexicon[word][1]:
                lexicon[word] = (cat, intensity, polarity)
    return lexicon


def score_text(text: str) -> Dict[str, float]:
    """
    对中文文本做情感分析，返回 Plutchik 8 维得分向量。

    得分含义：各维度的加权平均激活强度，范围 0.0~1.0。
    未命中任何词典词时返回全零向量。

    Args:
        text: 中文文本（事件描述、感知输出等）

    Returns:
        {"anger": 0.0, "fear": 0.3, "joy": 0.0, ...}
    """
    lexicon = _load_lexicon()
    words = jieba.lcut(text, cut_all=False)

    scores: Dict[str, float] = {dim: 0.0 for dim in PLUTCHIK_DIMS}
    hit_count = 0

    for word in words:
        if word not in lexicon:
            continue
        cat, intensity, polarity = lexicon[word]
        if cat not in _CAT_TO_PLUTCHIK:
            continue

        normalized_intensity = intensity / 10.0  # 1-9 → 0.1-0.9

        # 极性修正：polarity=2 表示负极性（贬义用法）
        # 当词典标注为负向时，若该词映射到正面情绪维度，降权处理
        # 避免"背叛+信任"中"信任"把情绪方向拉成正面
        is_negative_cat = cat.startswith("N")
        if polarity == 2 and not is_negative_cat:
            # 负极性正面词（如"朋友"在"背叛朋友"语境中是被伤害的对象）
            # 降权到 20%，保留语境感知但不主导方向
            normalized_intensity *= 0.2

        weights = _CAT_TO_PLUTCHIK[cat]

        for dim, weight in weights.items():
            scores[dim] += normalized_intensity * weight

        hit_count += 1

    # 归一化：除以命中词数，避免长文本虚高
    if hit_count > 0:
        for dim in scores:
            scores[dim] = min(1.0, scores[dim] / hit_count)

    return scores


def get_dominant_emotions(text: str, top_n: int = 2) -> List[str]:
    """
    返回文本中强度最高的 top_n 个情绪维度名。
    用于 EmotionConstraint 的 dominant_emotions 字段。
    """
    scores = score_text(text)
    # 过滤掉得分为 0 的维度，再取 top_n
    nonzero = {k: v for k, v in scores.items() if v > 0.01}
    if not nonzero:
        return []
    return sorted(nonzero, key=nonzero.get, reverse=True)[:top_n]


def get_hit_words(text: str) -> List[Tuple[str, str, float]]:
    """
    返回文本中命中词典的词及其分析结果，用于调试和日志。

    Returns:
        [(词, emotion_cat, normalized_intensity), ...]
    """
    lexicon = _load_lexicon()
    words = jieba.lcut(text, cut_all=False)
    hits = []
    for word in words:
        if word in lexicon:
            cat, intensity, _ = lexicon[word]
            if cat in _CAT_TO_PLUTCHIK:
                hits.append((word, cat, intensity / 10.0))
    return hits

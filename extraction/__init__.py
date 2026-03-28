"""
extraction/ — Profile 提取引擎（Phase 3）

将用户的原始输入（情境题答案、文本、聊天记录）
转化为结构化的 PersonProfile JSON。

子模块：
  scenario_bank.py   情境题库（强迫选择 → 字段映射）
  interviewer.py     对话式AI访谈（追问补全空缺字段）
  text_extractor.py  原始文本语义提取
  profile_builder.py Profile 合成器（置信度评分 + 矛盾标注）
"""

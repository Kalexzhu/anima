#!/bin/bash
# Tick 6-15：Jan 26 清晨早餐 → 飞行 → 坠机
# 测试修复后的三项修复 + 新增禁止重复 voice_intrusion 功能
cd ~/Projects/mind-reading
python3 scenarios/kobe_2020/runner.py --start-tick 6 --max-ticks 10

#!/bin/bash
# 林晓雨 — WorldEngine 完整流程
# 用法：bash run_linxiaoyu.sh [ticks数，默认20]
cd ~/Projects/mind-reading
python3 run.py examples/demo_profile.json --max-ticks ${1:-20}

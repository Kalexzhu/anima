"""
config.py — 加载环境变量。
从 .env 文件读取配置，在任何模块 import 之前调用。
"""

import os
from pathlib import Path


def load_env():
    """从项目根目录的 .env 文件加载环境变量。"""
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                os.environ[key.strip()] = value.strip()  # 强制覆盖系统环境变量


# 模块被 import 时自动执行
load_env()

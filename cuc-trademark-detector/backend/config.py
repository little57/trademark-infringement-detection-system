# -*- coding: utf-8 -*-
"""
配置文件 - DeepSeek API 及其他设置
"""
import os
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

# ========== DeepSeek API 配置 ==========
# 方式1：从环境变量读取（推荐，避免Key泄露）
# 设置方式：set DEEPSEEK_API_KEY=sk-你的key
# 方式2：直接填写下方（不填不影响基础检测功能）
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "sk-your-api-key-here")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"


# AI增强模式开关
# True  = 规则判定边界模糊时自动调AI增强（混合模式）
# False = 仅使用规则判定（原有逻辑）
AI_ENHANCED_MODE = True

# AI验证的置信度阈值
# 当规则判定置信度为"低"或"中"时，触发AI验证
AI_TRIGGER_CONFIDENCE = ["低", "中"]

# API调用配置
API_TIMEOUT = 30  # 单次API调用超时（秒）
API_MAX_RETRIES = 2  # 失败重试次数
API_CONCURRENT_LIMIT = 3  # 并发限制（避免限流）

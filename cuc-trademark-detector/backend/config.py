# -*- coding: utf-8 -*-
"""
配置文件 - DeepSeek API 及其他设置
"""
import os
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

# ========== DeepSeek API 配置 ==========
# 优先级：环境变量 > 配置文件默认值
#
# 推荐用环境变量（不写入代码，不会被 Git 收录）：
#     set DEEPSEEK_API_KEY=sk-你的key            (当前会话)
#     setx DEEPSEEK_API_KEY sk-你的key           (永久，需重开终端)
#
# 也可直接改下面的 _DEFAULT_API_KEY，但**改完不要把真实 Key 提交到 Git**
# （本文件虽已加入 .gitignore，仍建议优先用环境变量）。
_DEFAULT_API_KEY = ""  # 留空表示只从环境变量读取

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", _DEFAULT_API_KEY)
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

# ========== AI 辅助确认价格 ==========
# True  = 当规则提取的价格不确定（提取失败 / 疑似混入销量数字 / 价格异常）时，调AI复核
# False = 完全依赖本地规则提取（不产生额外API开销）
AI_PRICE_VERIFY = True

# 触发AI价格复核的条件（满足任一即触发）：
#   1) 规则未能提取到价格（空）
#   2) 价格缺失小数位，但价格区原始文本中含小数（疑似被截断，如 5.32 → 5）
#   3) 价格区原始文本中存在"销量类"数字，可能造成混淆
AI_PRICE_TRIGGER_ON_EMPTY = True        # 条件1
AI_PRICE_TRIGGER_ON_DECIMAL_LOSS = True # 条件2
AI_PRICE_TRIGGER_ON_NOISE = True        # 条件3


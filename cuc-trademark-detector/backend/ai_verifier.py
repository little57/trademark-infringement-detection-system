# -*- coding: utf-8 -*-
"""
AI侵权验证模块 - 调用DeepSeek API对商品进行深度侵权分析

混合模式：
1. 规则判定为"不侵权"但边界模糊 → 调AI再审（兜底增强）
2. 规则判定为"侵权"但置信度低 → 调AI确认（减少误判）
3. 用户手动触发批量AI验证 → 对全部结果进行AI分析
"""
import json
import time
import requests
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from backend.config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_API_URL,
    DEEPSEEK_MODEL,
    API_TIMEOUT,
    API_MAX_RETRIES,
    API_CONCURRENT_LIMIT,
)

# ========== Prompt模板 ==========

VERIFICATION_PROMPT = """你是一个极其严格的商标侵权检测专家。请分析以下淘宝商品是否侵犯"中国传媒大学"的商标权，给出精确到每一分的评分。

## 商品信息
- **标题**：{title}
- **价格**：{price}元
- **卖家所在地**：{location}
- **卖家昵称**：{seller}

## ⚠️ 核心铁律（必须遵守）
**只要不是正规出版的书籍/教材，标题含"中国传媒大学"或"中传"或"CUC"的，一律判定为侵权，总分应在80分以上。**
（不再要求标题必须命中"服装/文具/饰品"等类别词 —— 非作品类、非服务类、非书籍，就判侵权）

**只有以下情况一律判定为【不侵权】（is_infringement: false）**：
- **作品/成果类**：实践作品、实习作品、实训作品、毕业作品、原创作品、作品集、文字报告、社会实践报告、调研报告、实习报告、课程作业、毕业论文、报告、作业等**交付内容成果的项目**
- **虚拟服务类商品**：作品代做、报告代写、论文辅导、开题报告、查重降重、PPT代做、设计约稿、插画绘制、源码代写、编程代做、文案润色、排版翻译等**不提供实物**的服务型商品
- **电子资源类**：电子版资料、模板素材、课件、字体包、网盘资源等**虚拟商品**
- **书籍/教材**：正规出版的书籍、教材、教辅

**⚠️ 特别注意——"作品/报告类优先"规则（必须遵守）**：
只要标题中出现**任何**作品/报告类词（"实践作品""文字报告""作品集""实践报告""调研报告""报告""作业""论文"等）或服务类词（"代做""代写""设计""排版"等），就**一律判定为不侵权**。

**不要**根据标题里同时出现的"笔记本""明信片""徽章""挂件"等词去推断"卖家实际卖的是实物"——那是**擅自推断**，禁止这样做。

- `中国传媒大学 实践报告 封面 笔记本` → **不侵权**（含"实践报告"）
- `中传 文字报告 明信片` → **不侵权**（含"文字报告"）
- `中国传媒大学 实践作品 手环 文创` → **不侵权**（含"实践作品"）

**只有标题中完全不含任何作品/报告/服务类词、且不是书籍**时，才判侵权 —— 此时**不需要**标题再含"徽章/笔记本"等类别词：
- `中国传媒大学 徽章 周边 纪念品` → 侵权（按下方评分标准判定）
- `中传 CUC 钥匙扣 定制` → 侵权
- `中国传媒大学 校徽 摆件` → 侵权
- `中国传媒大学 纪念品` → 侵权（即使没有具体类别词，也判侵权）

## 精细化评分标准（满分100分，精确到每一分）

### 1. 商标使用情况（满分30分，精确打分）
- 标题含完整校名"中国传媒大学" → **30分**
- 标题含"中传" → **28分**
- 标题含"CUC"（不区分大小写） → **26分**
- 标题含"广院" → **22分**
- 标题含"传媒"且明显指向学校 → **18分**
- 标题含校徽相关词 → **20分**
- 无任何校名/缩写/校徽相关词 → **0分**

### 2. 商品类别风险（满分25分，精确打分）
- **非书籍、非作品、非服务的实体商品 → 保底20分起**
- 服装类（T恤/卫衣/外套/帽子等） → **25分**
- 箱包类（帆布包/手提袋/包等） → **23分**
- 饰品/挂件类（钥匙扣/挂件/珐琅等） → **22分**
- 文具类（笔记本/书签/明信片等） → **20分**
- 纪念品类（纪念品/礼品/礼盒等） → **20分**
- 手机壳/数码配件 → **18分**
- 杯子/水杯/马克杯 → **18分**
- 家居类（抱枕/靠垫/坐垫等） → **16分**
- 口罩/日用类 → **14分**
- **其他周边/文创类，或标题未出现任何具体类别词** → **20分**
  （★ 默认判侵权：非作品类、非服务类、非书籍即视为侵权商品，不必命中类别词）
- 仅当标题明确显示是**书籍/教材/作品/服务/虚拟商品** → **0分**

### 3. 暗示官方关联程度（满分20分，精确打分）
- 标题含"官方"+"正版"或"官方"+"授权"等多个强暗示词 → **20分**
- 标题含"官方"或"正版"或"授权"单个词 → **18分**
- 标题含"纪念"或"纪念品"或"纪念款" → **16分**
- 标题含"周边"或"文创" → **14分**
- 标题含"定制"或"定制款" → **12分**
- 标题含"同款"或"同款周边" → **10分**
- 标题含"限量"或"限定" → **8分**
- 无任何暗示词 → **0分**

### 4. 价格异常程度（满分15分，精确打分）
- 价格低于20元 → **15分**
- 价格20-39元 → **13分**
- 价格40-59元 → **10分**
- 价格60-79元 → **7分**
- 价格80-99元 → **4分**
- 价格100-150元 → **2分**
- 价格150元以上 → **0分**

### 5. 卖家非官方程度（满分10分，精确打分）
- 非北京商家 → **10分**
- 北京商家但非学校官方店铺 → **6分**
- 无法判断卖家身份 → **8分**
- 明确为中国传媒大学官方店铺 → **0分**

## 最终判定规则
- **总分 = 上述5项得分之和（满分100分）**
- **≥80分**：明确侵权 → is_infringement: true
- **60-79分**：高度疑似侵权 → is_infringement: true（从严判定）
- **40-59分**：疑似侵权 → is_infringement: true（从严判定）
- **<40分**：边界模糊 → is_infringement: false

## 输出格式
请严格按以下JSON格式输出，不要包含其他内容：
```json
{{
    "is_infringement": true/false,
    "confidence_score": 0-100之间的整数分数（精确到每一分，不要笼统给35分）,
    "reason": "简要分析理由（30字以内）",
    "detail": "逐项打分说明，格式如：商标使用28分+商品类别25分+官方关联16分+价格异常13分+卖家非官方10分=92分",
    "suggestion": "确认侵权/酌情复核/建议复核"
}}
```"""



def _call_deepseek_api(prompt, timeout=API_TIMEOUT):
    """
    调用DeepSeek API
    返回: API响应的JSON对象，或None（失败时）
    """
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": "你是一个专业的商标侵权检测专家。请严格按要求的JSON格式输出。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 500,
    }

    for attempt in range(API_MAX_RETRIES + 1):
        try:
            resp = requests.post(
                DEEPSEEK_API_URL,
                headers=headers,
                json=payload,
                timeout=timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                return content
            elif resp.status_code == 429:
                # 限流，等待后重试
                wait = 2 ** (attempt + 1)
                time.sleep(wait)
                continue
            else:
                # 其他错误
                if attempt < API_MAX_RETRIES:
                    time.sleep(1)
                    continue
                return None
        except requests.Timeout:
            if attempt < API_MAX_RETRIES:
                time.sleep(1)
                continue
            return None
        except Exception:
            if attempt < API_MAX_RETRIES:
                time.sleep(1)
                continue
            return None
    return None


def _parse_ai_response(content):
    """
    解析AI返回的JSON内容
    返回: 结构化结果字典
    """
    if not content:
        return {
            "is_infringement": None,
            "confidence_score": 0,
            "reason": "API调用失败",
            "detail": "",
            "suggestion": "建议复核",
        }

    # 尝试从返回内容中提取JSON
    try:
        # 先尝试直接解析
        result = json.loads(content)
    except json.JSONDecodeError:
        # 尝试从markdown代码块中提取
        import re
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
        if json_match:
            try:
                result = json.loads(json_match.group(1))
            except json.JSONDecodeError:
                return {
                    "is_infringement": None,
                    "confidence_score": 0,
                    "reason": "AI返回格式异常",
                    "detail": content[:200],
                    "suggestion": "建议复核",
                }
        else:
            return {
                "is_infringement": None,
                "confidence_score": 0,
                "reason": "AI返回格式异常",
                "detail": content[:200],
                "suggestion": "建议复核",
            }

    # 标准化输出 - 优先使用confidence_score，兼容旧版confidence字段
    conf_score = result.get("confidence_score")
    if conf_score is None:
        # 兼容旧版"高/中/低"
        old_conf = result.get("confidence", "低")
        conf_map = {"高": 85, "中": 60, "低": 35}
        conf_score = conf_map.get(old_conf, 35)
    else:
        try:
            conf_score = int(conf_score)
            conf_score = max(0, min(100, conf_score))  # 限制在0-100
        except (ValueError, TypeError):
            conf_score = 35

    return {
        "is_infringement": result.get("is_infringement", None),
        "confidence_score": conf_score,
        "reason": result.get("reason", ""),
        "detail": result.get("detail", ""),
        "suggestion": result.get("suggestion", "建议复核"),
    }




# ========== 价格提取辅助确认 Prompt ==========

PRICE_PROMPT = """你是电商页面数据提取专家。下面是淘宝/天猫商品卡片中"价格区域"的原始文本，其中**混有价格和销量/人气等干扰信息**。

## 原始文本
```
{raw}
```

## 任务
请从中提取出**商品单价**（人民币元），忽略所有销量/人气/评价/收藏等数字。

## 关键区分规则
- 价格：通常带 "¥"、有小数点（如 5.00 / 19.90），或在"￥/价格/现价"等词附近
- **不是价格**：已售592件、月销1.02万+、102人付款、365条评价、889人收藏，这些都是销量/人气
- 若原文是 "¥19.90 月销1.02万+"，价格是 **19.9**（不是 1.02 万，也不是 102）
- 若只有价格没有销量，直接返回价格
- 若完全没有价格信息，返回空字符串

## 输出格式（严格遵守，不要任何解释）
```json
{{
    "price": "19.9",
    "confidence": 0-100的整数,
    "reason": "20字以内的判断依据"
}}
```
若无法确定价格，price 填 ""。"""


def verify_price_by_ai(raw_text, progress_cb=None):
    """
    用AI辅助确认从"价格区域文本"中提取的价格。
    用于本地规则提取不确定（或提取到空）时的兜底校验。

    参数:
        raw_text: 价格区域的原始文本（如 "¥19.90 月销1.02万+"）
        progress_cb: 进度回调

    返回:
        dict: {
            "price": str,   # 提取到的价格，失败为空串
            "confidence": int,
            "reason": str,
            "ai_used": bool,
        }
    """
    empty = {"price": "", "confidence": 0, "reason": "", "ai_used": False}
    if not raw_text or not str(raw_text).strip():
        return empty

    # 优先环境变量，其次配置默认值
    if not DEEPSEEK_API_KEY:
        return empty

    prompt = PRICE_PROMPT.format(raw=str(raw_text)[:300])
    if progress_cb:
        progress_cb(f"🤖 AI辅助确认价格: {str(raw_text)[:40]}...")

    content = _call_deepseek_api(prompt, timeout=API_TIMEOUT)
    if not content:
        return empty

    # 解析
    import re
    price_val, conf, reason = "", 0, ""
    try:
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
            data = json.loads(m.group(1)) if m else {}
        price_val = str(data.get("price", "") or "").strip()
        try:
            conf = int(data.get("confidence", 0) or 0)
        except (ValueError, TypeError):
            conf = 0
        reason = str(data.get("reason", "") or "")
    except Exception:
        return empty

    # 校验 AI 返回值是否为合法价格（防AI幻觉）
    if price_val:
        m = re.fullmatch(r'\d{1,6}(?:\.\d{1,2})?', price_val)
        if not m:
            # 从返回文本里再抓一次数字
            m2 = re.search(r'(\d{1,6}(?:\.\d{1,2})?)', price_val)
            price_val = m2.group(1) if m2 else ""
        if price_val:
            try:
                v = float(price_val)
                if not (0 < v <= 999999):
                    price_val = ""
                else:
                    # 规范化：去掉无意义的尾随零（128.0 -> 128, 19.90 -> 19.9）
                    price_val = ('%f' % v).rstrip('0').rstrip('.')
            except ValueError:
                price_val = ""

    if progress_cb:
        if price_val:
            progress_cb(f"   AI确认价格: {price_val}元 (置信度{conf}) - {reason}")
        else:
            progress_cb(f"   AI未能确认价格 - {reason}")

    return {"price": price_val, "confidence": conf, "reason": reason, "ai_used": True}


def verify_single_product(title, price="", seller="", location="", progress_cb=None):
    """
    对单个商品进行AI侵权验证
    
    参数:
        title: 商品标题
        price: 价格
        seller: 卖家昵称
        location: 所在地
        progress_cb: 进度回调函数
    
    返回:
        dict: {
            "is_infringement": True/False/None,
            "confidence": "高/中/低/未知",
            "reason": "简要理由",
            "detail": "详细分析",
            "suggestion": "建议操作"
        }
    """
    prompt = VERIFICATION_PROMPT.format(
        title=title[:200],  # 限制标题长度
        price=price or "未知",
        location=location or "未知",
        seller=seller or "未知",
    )

    if progress_cb:
        progress_cb(f"🤖 AI分析: {title[:40]}...")

    content = _call_deepseek_api(prompt)
    result = _parse_ai_response(content)

    if progress_cb:
        status = "✅ 侵权" if result["is_infringement"] else ("❌ 非侵权" if result["is_infringement"] is False else "⚠️ 未知")
        progress_cb(f"   AI结果: {status} (置信度:{result['confidence_score']}分) - {result['reason']}")

    return result



def batch_verify(products, progress_cb=None, max_workers=API_CONCURRENT_LIMIT):
    """
    批量AI验证商品列表
    
    参数:
        products: list[dict] - 商品列表，每项包含 title, price, seller, location
        progress_cb: 进度回调
        max_workers: 并发数
    
    返回:
        list[dict] - 每条商品追加 ai_result 字段
    """
    if not products:
        return products

    total = len(products)
    completed = [0]  # 用列表包装以便在闭包中修改
    lock = threading.Lock()
    results = list(products)  # 复制一份

    def _verify_and_update(idx, product):
        """验证单个商品并更新结果"""
        try:
            ai_result = verify_single_product(
                title=product.get("商品名称", product.get("title", "")),
                price=product.get("价格", product.get("price", "")),
                seller=product.get("卖家", product.get("seller", "")),
                location=product.get("所在地", product.get("location", "")),
                progress_cb=None,  # 内部不回调，由外层统一处理
            )
            results[idx]["ai_result"] = ai_result
        except Exception as e:
            results[idx]["ai_result"] = {
                "is_infringement": None,
                "confidence_score": 0,
                "reason": f"验证异常: {str(e)[:50]}",
                "detail": "",
                "suggestion": "建议复核",
            }



        with lock:
            completed[0] += 1
            if progress_cb:
                progress_cb(f"🤖 AI批量验证: {completed[0]}/{total}")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_verify_and_update, i, p): i for i, p in enumerate(products)}
        for future in as_completed(futures):
            pass  # 异常已在 _verify_and_update 内部处理

    return results


def ai_enhanced_judgment(title, price, location, rule_result, rule_reason, progress_cb=None):
    """
    混合模式核心函数：规则判定后，由AI做增强判断
    
    参数:
        title: 商品标题
        price: 价格
        location: 所在地
        rule_result: 规则判定的结果 (True/False)
        rule_reason: 规则判定的理由字符串
        progress_cb: 进度回调
    
    返回:
        (final_result, final_reason, ai_used)
        - final_result: 最终是否侵权 (True/False)
        - final_reason: 最终理由
        - ai_used: 是否使用了AI (True/False)
    """
    from backend.config import AI_ENHANCED_MODE, AI_TRIGGER_CONFIDENCE

    # 如果AI增强模式关闭，直接返回规则结果
    if not AI_ENHANCED_MODE:
        return rule_result, rule_reason, False

    # 解析规则理由中的置信度
    confidence = "中"  # 默认
    for part in rule_reason.split("; "):
        if "置信度:" in part:
            confidence = part.replace("置信度:", "").strip()
            break

    # 判断是否需要触发AI
    need_ai = False

    # 【重要】以下"终局性否定理由"不允许 AI 推翻为侵权：
    #   规则已确认该商品属于**作品/成果类或服务类**（作品类一律不判侵权、不截图），
    #   或是书籍（不在检测范围），这是硬性边界，
    #   AI 不应基于标题里的"笔记本/明信片"等词把它"救活"成侵权。
    FINAL_NEGATIVE = [
        "非实物产品",              # 实际理由前缀：作品类/服务类，如"非实物产品（作品类，命中"实践作品"）"
        "作品商品",                # 兼容旧格式
        "服务商品",                # 兼容旧格式
        "书籍",                    # 书籍/教材，不在检测范围
        "标题不含校名校徽关键词",     # 与校名无关
    ]
    if not rule_result and any(k in rule_reason for k in FINAL_NEGATIVE):
        return rule_result, rule_reason, False

    if rule_result:
        # 规则判定为侵权，但置信度低 → AI确认（减少误判）
        if confidence in AI_TRIGGER_CONFIDENCE:
            need_ai = True
    else:
        # 规则判定为不侵权（非终局性理由）→ 边界模糊，让AI再审
        need_ai = True

    if not need_ai:
        return rule_result, rule_reason, False

    # 调用AI验证
    seller = ""  # 规则判定阶段没有seller信息，留空
    ai_result = verify_single_product(
        title=title,
        price=price,
        seller=seller,
        location=location,
        progress_cb=progress_cb,
    )

    # 综合规则和AI的结果
    if ai_result["is_infringement"] is True:
        # AI判定侵权 → 采纳
        return True, f"AI判定侵权(置信度:{ai_result['confidence_score']}分): {ai_result['reason']}", True

    elif ai_result["is_infringement"] is False:
        if rule_result:
            # 规则判侵权但AI判不侵权 → 降低优先级，但仍保留（保守策略）
            return True, f"{rule_reason} | AI建议排除({ai_result['reason']})", True
        else:
            # 规则和AI都判不侵权 → 不侵权
            return False, f"AI确认不侵权: {ai_result['reason']}", True
    else:
        # AI调用失败 → 回退到规则结果
        return rule_result, f"{rule_reason} (AI验证失败，使用规则判定)", True

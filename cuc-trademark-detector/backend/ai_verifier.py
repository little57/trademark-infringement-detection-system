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
**只要不是正规出版的书籍/教材，标题含"中国传媒大学"或"中传"或"CUC"且商品属于服装/文具/饰品/纪念品/手机壳等周边类别的，一律判定为侵权，总分应在80分以上。**

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
- 服装类（T恤/卫衣/外套/帽子等） → **25分**
- 箱包类（帆布包/手提袋/包等） → **23分**
- 饰品/挂件类（钥匙扣/挂件/珐琅等） → **22分**
- 文具类（笔记本/书签/明信片等） → **20分**
- 纪念品类（纪念品/礼品/礼盒等） → **20分**
- 手机壳/数码配件 → **18分**
- 杯子/水杯/马克杯 → **18分**
- 家居类（抱枕/靠垫/坐垫等） → **16分**
- 口罩/日用类 → **14分**
- 其他周边/文创类 → **12分**
- 非周边类商品（如食品、电器等） → **0分**

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

    if rule_result:
        # 规则判定为侵权，但置信度低 → AI确认（减少误判）
        if confidence in AI_TRIGGER_CONFIDENCE:
            need_ai = True
    else:
        # 规则判定为不侵权，但原因是"标题不含校名校徽关键词"以外的原因
        # 说明可能边界模糊，让AI再审
        if "标题不含校名校徽关键词" not in rule_reason:
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

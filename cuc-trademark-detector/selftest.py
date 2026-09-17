# -*- coding: utf-8 -*-
"""
侵权判定规则自测（回归测试）

用法：
    set PLAYWRIGHT_BROWSERS_PATH=%CD%\\.playwright-browsers
    F:\\anaconda\\envs\\pyExcel\\python.exe -X utf8 selftest.py

全部通过退出码 0；有失败用例退出码 1 并列出失败项。

覆盖 5 组规则：
  [1] 作品/报告类      → 不侵权、不截图（含实物词也一样）
  [2] 书籍/教材        → 不侵权、不截图
  [3] 其余一律判侵权    ★ 关键新规则（默认判侵权，不要求类别词）
  [4] 书籍误吞检查      → 实物商品不得被 is_book 误判为书籍
  [5] AI 终局性否定     → 规则层已否定的理由，不得再调 AI 翻案
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.detector import (
    is_suspected_infringement, is_service_product, is_book, has_infringement_category
)
import backend.ai_verifier as av

P, L = "99", "北京"
fail = []


def chk(label, cond):
    if not cond:
        fail.append(label)
    return cond


def section(title):
    print()
    print("=" * 104)
    print(title)
    print("=" * 104)


# ============ [1] 作品/报告类 ============
section("[1] 作品/报告类 —— 期望：不侵权、不截图（含实物词也一样）")
WORKS = [
    "中国传媒大学 实践作品", "中国传媒大学 文字报告", "中国传媒大学 实践报告",
    "中国传媒大学 实践作品 笔记本", "中国传媒大学 文字报告 明信片",
    "中国传媒大学 实践报告 封面 笔记本", "中传 文字报告 明信片 套装",
    "中国传媒大学 实践作品 手环 文创", "中国传媒大学 报告 挂件 周边",
    "中传 实践作品 挂件", "中国传媒大学 社会实践 书签", "中国传媒大学 作品集 抱枕",
    "中传 文字作品 马克杯", "中国传媒大学 毕业论文 辅导 查重",
    "中国传媒大学 作品集 制作 设计",
]
w_pass = 0
for t in WORKS:
    inf, reason, _ = is_suspected_infringement(t, P, L)
    svc, kw, kind = is_service_product(t)
    ok = (not inf) and svc
    w_pass += ok
    chk(f"[作品]{t}", ok)
    print(f"  {'PASS' if ok else 'FAIL'} {t:44s} 不侵权={not inf}  不截图={svc}  [{kind}:{kw}]")
print(f"  通过 {w_pass} / {len(WORKS)}")

# ============ [2] 书籍 ============
section("[2] 书籍 —— 期望：不侵权、不截图")
BOOKS = ["中国传媒大学 教材 图书", "中国传媒大学 出版 书籍",
         "中国传媒大学 教辅 用书", "中传 参考书 ISBN"]
b_pass = 0
for t in BOOKS:
    inf, reason, _ = is_suspected_infringement(t, P, L)
    ok = (not inf) and is_book(t)
    b_pass += ok
    chk(f"[书籍]{t}", ok)
    print(f"  {'PASS' if ok else 'FAIL'} {t:44s} 不侵权={not inf}  是书籍={is_book(t)}")
print(f"  通过 {b_pass} / {len(BOOKS)}")

# ============ [3] 默认判侵权 ============
section("[3] 其余一律判侵权 —— 期望：侵权、会截图（★ 关键新规则）")
INFRINGE = [
    "中国传媒大学 徽章 周边 纪念品", "中传 CUC 钥匙扣 定制",
    "中国传媒大学 笔记本 校徽 文具", "中国传媒大学 帆布包 T恤 文化衫",
    "中国传媒大学 纪念品", "中国传媒大学 校徽 摆件", "中国传媒大学 文创",
    "中国传媒大学 定制", "中传 周边", "中国传媒大学", "中传 CUC",
    "中国传媒大学 限量发售",
]
i_pass = 0
for t in INFRINGE:
    inf, reason, _ = is_suspected_infringement(t, P, L)
    svc, _, _ = is_service_product(t)
    ok = inf and (not svc)
    i_pass += ok
    chk(f"[默认侵权]{t}", ok)
    tag = "有类别词" if has_infringement_category(t) else "★ 无类别词"
    print(f"  {'PASS' if ok else 'FAIL'} {t:44s} 侵权={inf}  会截图={not svc}  [{tag}]")
print(f"  通过 {i_pass} / {len(INFRINGE)}")

# ============ [4] 书籍误吞检查 ============
section("[4] 书籍误吞检查 —— 以下实物商品不得被 is_book 判为书籍")
NOT_BOOKS = ["中国传媒大学 笔记本 校徽 文具", "中传 文具 套装", "中国传媒大学 签字笔",
             "中国传媒大学 书签 校徽", "中国传媒大学 书包", "中传 资料袋 帆布包",
             "中国传媒大学 笔记本", "中国传媒大学 纪念册"]
n_pass = 0
for t in NOT_BOOKS:
    ok = not is_book(t)
    n_pass += ok
    chk(f"[非书籍]{t}", ok)
    print(f"  {'PASS' if ok else 'FAIL'} {t:44s} 是书籍={is_book(t)}  (应为 False)")
print(f"  通过 {n_pass} / {len(NOT_BOOKS)}")

# ============ [5] AI 终局性否定 ============
section("[5] ai_enhanced_judgment 终局性否定（不应调用 AI）")
CASES = [
    "作品商品（命中\"实践作品\"），不判侵权",
    "非实物产品（作品类，命中\"文字报告\"）",
    "书籍/教材（不在检测范围）",
    "标题不含校名校徽关键词",
]
a_pass = 0
for reason in CASES:
    called = []

    def fake(*a, **k):
        called.append(1)
        # _call_deepseek_api 返回"原始文本"，_parse_ai_response 再 json.loads
        return ('{"is_infringement": true, "confidence_score": 95, "reason": "x", '
                '"detail": "", "suggestion": "确认侵权", "price": ""}')

    orig = av._call_deepseek_api
    av._call_deepseek_api = fake
    try:
        r, rr, used = av.ai_enhanced_judgment(
            title="中国传媒大学 实践作品", price=P, location=L,
            rule_result=False, rule_reason=reason,
        )
    finally:
        av._call_deepseek_api = orig
    ok = (not r) and (not called)
    a_pass += ok
    chk(f"[AI终局]{reason}", ok)
    print(f"  {'PASS' if ok else 'FAIL'} 理由={reason[:34]:36s} AI调用={bool(called)} 不侵权={not r}")
print(f"  通过 {a_pass} / {len(CASES)}")

# ============ 汇总 ============
total = len(WORKS) + len(BOOKS) + len(INFRINGE) + len(NOT_BOOKS) + len(CASES)
passed = w_pass + b_pass + i_pass + n_pass + a_pass
section(f"汇总: 作品类 {w_pass}/{len(WORKS)} | 书籍 {b_pass}/{len(BOOKS)} | "
        f"默认侵权 {i_pass}/{len(INFRINGE)} | 非书籍 {n_pass}/{len(NOT_BOOKS)} | "
        f"AI终局性 {a_pass}/{len(CASES)}  ==>  {passed}/{total}")
if fail:
    print("\n失败用例:")
    for f_ in fail:
        print("  - " + f_)
    sys.exit(1)
print("\n全部通过 ✅")

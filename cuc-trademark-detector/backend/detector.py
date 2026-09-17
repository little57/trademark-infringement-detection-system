# -*- coding: utf-8 -*-
"""
中国传媒大学 淘宝侵权商品检测 - 完整版
支持：翻页、防爬、书籍过滤、侵权识别、截图、Excel报告
"""
import sys, os, re, json, time, datetime, urllib.parse, pathlib, subprocess, glob, random, threading, logging

# 日志配置
LOG_DIR = pathlib.Path(__file__).resolve().parent.parent / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "detector.log"
logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8",
)
logger = logging.getLogger("detector")

BASE = pathlib.Path(__file__).resolve().parent.parent
SCREENSHOTS = BASE / "data" / "screenshots"
REPORTS_DIR = BASE / "data" / "reports"

# ========== Playwright 浏览器路径 ==========
# 优先使用项目自带的浏览器目录（.playwright-browsers），
# 这样无需依赖全局 ms-playwright 缓存，换机器/换环境也能直接跑。
# 若用户已设置 PLAYWRIGHT_BROWSERS_PATH 环境变量，则尊重用户设置。
_LOCAL_BROWSERS = BASE / ".playwright-browsers"
if _LOCAL_BROWSERS.exists() and not os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_LOCAL_BROWSERS)

# AI增强验证模块（可选导入，不影响原有功能）
try:
    from backend.ai_verifier import ai_enhanced_judgment, batch_verify
    AI_VERIFIER_AVAILABLE = True
except ImportError:
    AI_VERIFIER_AVAILABLE = False
except Exception:
    AI_VERIFIER_AVAILABLE = False

SCREENSHOTS.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
KEYWORD = "中国传媒大学"
# 书籍/教材关键词：**仅保留明确指向出版书籍的词**
# ⚠️ 历史教训：曾包含 "书" "笔" "文具" "笔记" "本子" "资料" "辅导" "考研" 等过宽词，
#    导致真实实物商品被误判为书籍而跳过，例如：
#      "笔记本"  命中 "笔"/"笔记"  → 被当书籍跳过 ❌
#      "文具 套装" 命中 "文具"      → 被当书籍跳过 ❌（"文具"本身是侵权类别词）
#      "签字笔"   命中 "笔"        → 被当书籍跳过 ❌
#      "书签"/"书包" 命中 "书"      → 被当书籍跳过 ❌
#      "资料袋"   命中 "资料"       → 被当书籍跳过 ❌
#    现已全部移除，只保留下面这些"一望即知是出版书籍"的词。
BOOK_KWS = ["书籍","教材","课本","图书","教辅",
            "出版社","当当","新华书店","图书专营","书店",
            "ISBN","正版书","出版物","专著","年鉴","期刊","杂志",
            "习题集","教科书","参考书","工具书"]
# 商标侵权关键词：校名、校徽、缩写等
# 注意：只包含明确指向学校的标识性关键词，不含通用商品描述词
TRADEMARK_KWS = ["中国传媒大学","中传","CUC","校徽","校名"]
# 侵权商品类别关键词
INFRINGEMENT_CATEGORY_KWS = ["T恤","卫衣","衣服","服装","外套","夹克","冲锋衣","帽子","鸭舌帽","棒球帽","帆布包","手提袋","包",
                              "笔记本","记事本","珐琅","钥匙扣","挂件","冰箱贴","磁贴","纪念品","风景卡片"
                              "手机壳","马克杯","水杯","杯子","抱枕","靠垫","坐垫","口罩","书签","明信片",
                              "定制","批发","批量","礼品","礼物","礼盒","礼袋","礼品袋","礼品盒","礼品套装",
                              "徽章","胸针","贴纸","胶带","扇子","手环","徽标","LOGO","纪念章","校徽",
                              "周边","文创","纪念品","纪念","收藏","摆件","装饰","挂饰","饰品",
                              "手提袋","购物袋","环保袋","布袋","纸袋","塑料袋","徽章","胸针","纪念章",
                              "卡套","卡贴","卡包","证件套","工牌套","胸针","徽标贴","标志贴","商标贴","发夹"
                              "鼠标垫","桌垫","杯垫","餐垫",
                              "雨伞","伞","遮阳伞","书签"
                              "毛巾","浴巾","手帕",
                              "拖鞋","凉拖","棉拖",
                              "睡衣","家居服","内裤","袜子",
                              "书包","双肩包","单肩包","斜挎包","钱包",
                              "手链","项链","戒指","耳环","手镯",
                              "公仔","玩偶","娃娃","毛绒",
                              "徽标贴","标志贴","商标贴",
                              "毕业","毕业季","毕业纪念",
                              "录取","通知书","录取通知书",]
# ========== 虚拟服务类商品排除（作品代做/报告代写等，不属于实物侵权） ==========
# 判定原则：本项目只针对「实物产品」的商标侵权，
#           纯服务/虚拟商品（代写、代做、代画、设计、论文辅导等）不计入侵权
SERVICE_KWS = [
    # 代做/代写类
    "代做", "代写", "代画", "代加工", "代印", "代购", "代发", "代算", "代课", "代考",
    # 设计/创作类
    "设计", "定制设计", "logo设计", "LOGO设计", "平面设计", "海报设计", "封面设计",
    "插画", "绘画", "画图", "制图", "原创设计", "约稿", "画师", "手绘", "绘稿", "修图", "抠图",
    # 文档/报告类
    "论文", "毕业论文", "开题报告", "报告", "文献", "综述", "降重", "查重", "查重率",
    "排版", "代运营", "咨询", "辅导", "指导", "答疑", "培训", "课程", "网课", "教程",
    "翻译", "润色", "修改", "校对", "写作", "撰写", "文案", "策划书", "商业计划书",
    # 软件/电子资源类
    "源代码", "源码", "程序代做", "编程", "代码", "脚本", "建模", "渲染", "算法", "调参",
    "电子版", "电子档", "素材", "模板", "字体包", "课件", "PPT", "psd", "AI绘画",
    "网盘", "虚拟", "激活码", "会员", "教程视频", "电子文件", "数字资源",
    # 其他服务
    "服务", "接单", "外包", "兼职", "跑腿", "劳务",
    # 咨询/指导类
    "咨询", "答疑", "陪练", "辅导", "指导", "讲解",
]

# ========== 作品/成果类（虚拟交付物，不属于实物侵权） ==========
# 用户明确要求：实践作品、文字报告之类的**不算侵权**
# 这类是"交付内容/成果"，而非具备商标载体的实体商品
WORK_KWS = [
    # 作品类
    "实践作品", "实习作品", "实训作品", "毕业作品", "原创作品", "个人作品", "参赛作品",
    "优秀作品", "作品集", "作品册", "作品展", "作品评", "阶段性作品", "课程作品",
    "实验作品", "创作作品", "设计作品", "拍摄作品", "摄影作品", "视频作品",
    "作品提交", "作品代做", "作品定制", "作品集制作", "作品集排版", "作品集排版",
    # 报告/文档类
    "实践报告", "实习报告", "实训报告", "调研报告", "调研", "调查报告", "实验报告",
    "社会实践", "社会实践报告", "文字报告", "文字作品", "文字稿", "文字材料",
    "总结报告", "分析报告", "研究报告", "课题报告", "结题报告", "日志报告",
    "毕业论文", "课程论文", "文献综述", "开题报告", "中期报告", "毕业设计",
    "报告书", "报告册", "实习总结", "实践总结", "工作总结",
    # 作业/课业类
    "作业", "课业", "实践作业", "课后作业", "作文", "课程设计", "大作业", "实操作业",
    # 论文/学术交付类
    "学位论文", "小论文", "期刊论文", "发表论文", "论文写作", "论文指导", "论文查重",
]

# ========== 【严禁重新引入"实物载体词表"】（历史教训） ==========
# ⚠️⚠️ 本项目曾**两次**引入名为 PHYSICAL_KWS 的"实物载体词表"，并置于最高优先级，
#      想据此反推"卖家真实意图"——把 `实践报告 封面 笔记本` 认定为"卖笔记本"→ 判侵权。
#
#      这是**擅自推断**，违背需求：
#        需求是「标题含作品/报告类词或服务类词 → 直接判不侵权、不截图」，
#        不允许再根据标题里的"笔记本/明信片/徽章"等词去猜卖家实际卖什么。
#
#      该表两次引入、两次被要求回退，是**反复出问题的根源**。
#      **禁止再次添加任何形式的"实物载体词表"**（无论叫 PHYSICAL_KWS、
#      还是拆成"强实物/普通实物"两档，都不要再加）。
#
# 判定顺序（唯一正确版本）：
#   1) 命中 WORK_KWS（作品/成果类）  → 不侵权、不截图
#   2) 命中 SERVICE_KWS（服务类）    → 不侵权、不截图
#   3) is_book() 为真（书籍/教材）   → 不侵权、不截图
#   4) 以上都不命中                  → **直接判侵权**（默认判侵权，不再要求类别词）

# 低价阈值：低于此价格认为可能是侵权商品
LOW_PRICE_THRESHOLD = 100
STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => false });
Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
window.chrome = { runtime: {} };
const origQuery = window.navigator.permissions.query.bind(window.navigator.permissions);
window.navigator.permissions.query = (params) => {
    if (params.name === 'notifications') return Promise.resolve({state: 'denied'});
    return origQuery(params);
};
"""
IS_LOGGED_IN_JS = """
() => {
    // 方式1：检测Cookie中是否有登录标记（最可靠）
    const cookies = document.cookie.split(';').map(c => c.trim().split('=')[0]);
    const loginCookies = ['_tb_token_', 'cookie2', 'l', 'uc1', 'uc3', 'tracknick', 'dnk', 'thw', 'unb'];
    for (const lc of loginCookies) {
        if (cookies.includes(lc)) return true;
    }
    
    // 方式2：检测用户昵称元素（淘宝新版）
    const nickSelectors = [
        '.site-nav-user .site-nav-login-info-nick',
        '.J_MemberNick', '.member-nick', '.tb-member-nick',
        '.site-nav-user .user-nick', '.user-nick',
        '.site-nav-user .nick', '.nick',
        '.site-nav-user a[class*="nick"]',
        '.site-nav-user span[class*="nick"]',
        '#J_UserInfo .nick', '#J_UserInfo a[class*="nick"]',
        '.site-nav-bd .user', '.site-nav-bd a[class*="user"]',
        '.site-nav-user .username', '.username',
        '.site-nav-user .login-info .name',
        '.header-user .name', '.header-user .nick',
        '.top-nav-user .name',
        '.site-nav-user [class*="user"] a',
        '.site-nav-user [class*="member"]',
        '.site-nav-user [class*="login"] span',
    ];
    for (const sel of nickSelectors) {
        const el = document.querySelector(sel);
        if (el && el.textContent && el.textContent.trim() && el.textContent.trim().length > 0 && el.textContent.trim().length < 30) {
            return true;
        }
    }
    
    // 方式3：检测头像元素
    const avatarSelectors = [
        '.site-nav-user .avatar', '.J_Avatar', '.user-avatar',
        '.site-nav-user img[class*="avatar"]', '.site-nav-user img[class*="head"]',
        '.site-nav-user .user-photo', '.user-photo',
        '.header-user .avatar', '.header-user img[class*="avatar"]',
    ];
    for (const sel of avatarSelectors) {
        const el = document.querySelector(sel);
        if (el && el.offsetParent !== null) return true;
    }
    
    // 方式4：检测登录按钮（如果登录按钮可见，说明未登录）
    const loginBtnSelectors = [
        '.site-nav-login-info a[href*="login"]', '.J_Login', '.btn-login',
        '.site-nav-user a[href*="login"]', '.site-nav a[href*="login"]',
        '.top-nav a[href*="login"]', '.header a[href*="login"]',
        'a[href*="login.taobao.com"]',
    ];
    for (const sel of loginBtnSelectors) {
        const el = document.querySelector(sel);
        if (el && el.offsetParent !== null) return false;
    }
    
    // 方式5：检测页面文字
    const bodyText = document.body && document.body.innerText ? document.body.innerText : '';
    if (bodyText.includes('请登录') || bodyText.includes('登录淘宝')) return false;
    if (bodyText.includes('我的淘宝') || bodyText.includes('我的订单') || bodyText.includes('已买到的宝贝')) return true;
    
    return null;
}
"""


CAPTCHA_CHECK_JS = """
() => {
    const captchaModal = document.querySelector('.nc-container, .nc_modal, #nc_1_nc-container, .sm-pop, .sms-popup');
    const captchaSlider = document.querySelector('.nc_iconfont, .btn_slide, .nc-slider, .slider-icon');
    const hasCaptchaIframe = document.querySelector('iframe[src*="captcha"], iframe[src*="nc"], iframe[src*="verify"]');
    const textMatch = document.body.innerText && (
        document.body.innerText.includes('请拖动下方滑块完成验证') ||
        document.body.innerText.includes('请按住滑块，拖动到最右边') ||
        document.body.innerText.includes('滑动验证') ||
        document.body.innerText.includes('安全验证')
    );
    return !!(captchaModal || captchaSlider || hasCaptchaIframe || textMatch);
}
"""
DISMISS_CAPTCHA_JS = """
() => {
    const closeBtns = document.querySelectorAll('.nc_close, .sm-close, .sms-close, .close-btn, .nc-icon-close, [class*="close"][class*="nc"], .smt-close, .btn-close');
    for (const btn of closeBtns) { if (btn.offsetParent !== null) { btn.click(); return true; } }
    const masks = document.querySelectorAll('.nc_mask, .sm-mask, .sms-mask');
    for (const mask of masks) { if (mask.offsetParent !== null) { mask.click(); return true; } }
    document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', code: 'Escape', keyCode: 27, which: 27}));
    return false;
}
"""
LOGIN_CHECK_JS = """
() => {
    const loginModal = document.querySelector('.login-pop, .login-dialog, #login, .J_LoginDialog, .tb-login');
    const loginIframe = document.querySelector('iframe[src*="login.taobao.com"], iframe[src*="login.alipay"]');
    const loginBox = document.getElementById('J_LoginBox');
    const isLoginUrl = window.location.href.includes('login.taobao.com') || window.location.href.includes('login.alipay.com');
    return !!(loginModal || loginIframe || loginBox || isLoginUrl);
}
"""
DISMISS_LOGIN_JS = """
() => {
    const closeBtns = document.querySelectorAll('.login-close, .close-btn, .J_Close, .pop-close, .dialog-close, [class*="close"][class*="login"], .icon-close, .smt-close, .tb-btn-close');
    for (const btn of closeBtns) { if (btn.offsetParent !== null) { btn.click(); return true; } }
    document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', code: 'Escape', keyCode: 27, which: 27}));
    return false;
}
"""
# 翻页JS：点击页码按钮翻页
CLICK_PAGE_JS = """
(targetPage) => {
    // 方式1：点击页码链接
    const pageLinks = document.querySelectorAll('.pagination a, .page-item a, a[class*="page"], a[class*="Page"], .J_Page a, .J_Ajax a');
    for (const link of pageLinks) {
        const text = (link.textContent || '').trim();
        if (text === String(targetPage)) {
            link.click();
            return true;
        }
    }
    // 方式2：点击页码按钮
    const pageBtns = document.querySelectorAll('.pagination button, .page-item button, button[class*="page"], button[class*="Page"]');
    for (const btn of pageBtns) {
        const text = (btn.textContent || '').trim();
        if (text === String(targetPage)) {
            btn.click();
            return true;
        }
    }
    // 方式3：从所有页码元素中找
    const allPageEls = document.querySelectorAll('[class*="page"] a, [class*="Page"] a, [class*="pagination"] span, [class*="Pagination"] span');
    for (const el of allPageEls) {
        const text = (el.textContent || '').trim();
        if (text === String(targetPage) && el.offsetParent !== null) {
            el.click();
            return true;
        }
    }
    return false;
}
"""
GET_PAGE_INFO_JS = """
() => {
    // 获取当前页码和总页数
    const pageLinks = document.querySelectorAll('.pagination a, .page-item a, a[class*="page"], a[class*="Page"], .J_Page a, .J_Ajax a');
    const pages = [];
    let currentPage = 1;
    for (const link of pageLinks) {
        const text = (link.textContent || '').trim();
        const num = parseInt(text);
        if (!isNaN(num) && num > 0 && num < 100) {
            pages.push(num);
        }
        if (link.classList.contains('active') || link.classList.contains('current') || link.parentElement.classList.contains('active')) {
            currentPage = num;
        }
    }
    // 也检查span
    const pageSpans = document.querySelectorAll('.pagination span, .page-item span, .active, .current');
    for (const span of pageSpans) {
        const text = (span.textContent || '').trim();
        const num = parseInt(text);
        if (!isNaN(num) && num > 0 && num < 100) {
            if (span.classList.contains('active') || span.classList.contains('current') || span.parentElement.classList.contains('active')) {
                currentPage = num;
            }
        }
    }
    const maxPage = pages.length > 0 ? Math.max(...pages) : 1;
    return { currentPage, maxPage, availablePages: [...new Set(pages)].sort((a,b) => a-b) };
}
"""
EXTRACT_ITEMS_JS = """
() => {
    // 辅助函数：从文本中提取价格
    // 【重要】必须先剔除“销量/人气/评价”等干扰数字，否则会把
    //        “已售592件”“102人付款”误当成价格（历史Bug）
    function extractPrice(text) {
        if (!text) return '';
        let s = String(text);

        // 1) 先剔除“销量/人气”片段（必须在去空格之前做！
        //    否则 "¥ 5.00 592人付款" 去掉空格会变成 "5.00592人的"，数字被粘连）
        const NOISE = /(?:已售|月销|销量|成交|付款|已买|人收货|评价|收藏|浏览|加购|想要|人已购|件已售)[^0-9]{0,3}[0-9.]+(?:万\+?)?[^0-9]{0,3}(?:件|人|笔|次)?/g;
        s = s.replace(NOISE, ' ');
        //    数字在前的情况：592人付款 / 1.02万+人付款
        s = s.replace(/[0-9.]+(?:万\+?)?[^0-9]{0,2}(?:人付款|人已买|人收货|人已购|件已售|人想要|条评价|个评价|人收藏)/g, ' ');
        //    “已售”“月销”等词+数字
        s = s.replace(/(?:已售|月销|销量|成交|收藏|评价|浏览)[^0-9]{0,3}[0-9.]+万?\+?/g, ' ');

        // 2) 去掉货币符号、千分位逗号、空白
        s = s.replace(/[¥￥$€,，\s]/g, '');

        // 3) 取第一个形如 价格 的数字（支持 ¥5.00 / 5 / 5.5 / 1234.56）
        //    价格小数位最多2位，整数最多5位
        const m = s.match(/(\d{1,5}(?:\.\d{1,2})?)/);
        if (!m) return '';
        let p = m[1];
        // 去掉前导0
        if (p.indexOf('.') === -1) {
            p = String(parseInt(p, 10));
            if (p === '0') return '';
        } else {
            const v = parseFloat(p);
            if (!(v > 0)) return '';
            p = String(v);
        }
        // 价格合理性上限
        if (parseFloat(p) > 999999) return '';
        return p;
    }

    // 辅助函数：判断一个元素的文本是否像“销量/人气”而非价格
    function looksLikeSales(text) {
        if (!text) return true;
        return /(已售|月销|销量|成交|人付款|人已买|人收货|人想要|评价|收藏|浏览|加购)/.test(text);
    }

    // 辅助函数：判断一个类名是否是“容器”（里面还套着价格子元素）
    function isWrapperClass(cls) {
        return /wrap|Wrap|container|Container|box|Box|root|item|Item|main|Main|info|Info|area|Area/.test(cls);
    }

    // 辅助函数：判断一个类名是否是“销量/人气”元素
    function isSalesClass(cls) {
        return /sales|Sales|sold|Sold|deal|Deal|count|Count|num|Num|total|Total|track|Track|origin|Origin|through|del|Del|market|Market|month|Month/.test(cls);
    }

    // 辅助函数：找到商品卡片内真正的“价格区容器”
    // 【重要】不能用 querySelector('[class*="price"]')！它会直接命中 <span class="priceInt">4</span>
    //        这种最内层叶子节点，导致小数位 .70 丢失（历史Bug）
    // 策略：① 找到所有价格元素；② 逐个"向上爬到最低公共祖先"作为价格容器；
    //       ③ 若公共祖先仍是叶子（如 priceInt/priceDec 直接挂在 card 下），
    //          则回退到它们的父节点，最差返回 scope 本身
    function findPriceRoot(scope) {
        if (!scope) return null;

        // 候选：类名含 price/Price/g_price 的元素，排除销量元素
        let cands = [];
        scope.querySelectorAll('[class*="Price"], [class*="price"], [class*="g_price"]').forEach(e => {
            if (!isSalesClass(String(e.className || ''))) cands.push(e);
        });
        if (!cands.length) return null;

        // 只有一个候选（如 <div class="priceBox">¥88.50</div>）：
        // 它本身就是价格元素，直接返回即可（extractPriceFromContainer 的
        // ①/② 会因 querySelectorAll 不含自身而查不到，最终由 ③ 整体文本兜底，
        // 而它自己的文本就是价格，安全）。
        if (cands.length === 1) return cands[0];

        // 若已有"内含 priceInt/priceDec 的最外层元素"，优先用它（最贴近价格区）
        const withSub = cands.filter(e => e.querySelector('[class*="priceInt"], [class*="priceDec"], [class*="price-int"], [class*="price-dec"]'));
        if (withSub.length) {
            // 取最深（最小）的那个：它是最靠近叶子的公共容器
            let best = withSub[0];
            for (const e of withSub) if (best.contains(e)) best = e;
            return best;
        }

        // 计算所有候选的"最低公共祖先"（注意 ancestorsOf 包含元素自身，
        // 这样 priceInt 与 priceDec 是兄弟时，公共祖先=它们的共同父节点）
        const selfAncestorsOf = (el) => { const a = []; let p = el; while (p && p !== scope) { a.push(p); p = p.parentElement; } return a; };
        let common = selfAncestorsOf(cands[0]);
        for (let i = 1; i < cands.length; i++) {
            const a = selfAncestorsOf(cands[i]);
            common = common.filter(x => a.indexOf(x) !== -1);
            if (!common.length) break;
        }
        if (common.length) {
            // common 从近到远排列，取最远（最外层）的那个
            let root = common[common.length - 1];
            // 【关键】若 root 就是候选叶子自身（说明它没有 price 类子元素），
            //        必须上溯到父节点，否则 extractPriceFromContainer 里的
            //        querySelectorAll('[class*="priceDec"]') 查不到小数位元素，
            //        小数会被静默丢弃（5.32 → 5）。
            if (root === cands[0] && root.parentElement) return root.parentElement;
            return root;
        }

        // 兜底：priceInt/priceDec 直接挂在 scope 下（无共同父容器），
        //        此时没有可用的"价格子容器"，只能返回 scope，
        //        但必须打标记 __priceScoped=true，让 extractPriceFromContainer
        //        知道"这是卡片级别"从而**禁用整体文本兜底**，
        //        否则会把标题里的数字（如"T恤7"）拼进价格（88.5 → 788.5）。
        // 【重要】绝不能返回 cands[0]（最内层 priceInt 叶子），否则小数位丢失。
        try { scope.__priceScoped = true; } catch (e) {}
        return scope;
    }

    // 辅助函数：取价格区的原始文本（供AI复核/日志排查用）
    function getPriceRawText(scope) {
        const root = findPriceRoot(scope);
        if (!root) return '';
        return (root.innerText || root.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 200);
    }

    // 辅助函数：从「价格区容器」中智能取价格
    // 淘宝结构常见：<div class="Price--priceWrap"><span class="priceInt">19</span>
    //                <span class="priceDec">.90</span><span class="price-sales">月销1.02万+</span></div>
    // 策略：① priceInt+priceDec 精确拼接 ② 逐个非容器/非销量元素取"带小数"的完整价格
    //       ③ 容器整体文本兜底
    // 【重要】不能只取 priceInt 就返回整数，否则 5.32 会退化成 5（历史Bug）
    function extractPriceFromContainer(root) {
        if (!root) return '';

        // ① 优先：priceInt + priceDec 拼接（最精确）
        //    注意用 :scope 限定只找直接/后代中"真正的最内层"元素，避免命中外层容器
        const intEls = root.querySelectorAll('[class*="priceInt"], [class*="price-int"], [class*="priceInteger"]');
        const decEls = root.querySelectorAll('[class*="priceDec"], [class*="price-dec"], [class*="priceDecimal"]');
        //    选出类名不是容器的那个（最内层）
        const pickLeaf = (els) => {
            let best = null;
            for (const e of els) {
                const cls = String(e.className || '');
                if (isWrapperClass(cls)) continue;
                if (e.querySelector('[class*="priceInt"], [class*="priceDec"]')) continue;
                if (!best) best = e;
            }
            return best || null;
        };
        const intEl = pickLeaf(intEls);
        const decEl = pickLeaf(decEls);
        if (intEl) {
            const it = (intEl.innerText || intEl.textContent || '').trim();
            // 整数部分本身可能已含小数（如 "5.32" 全放在 priceInt 里）
            if (/[.．]\d/.test(it)) {
                const whole = extractPrice(it);
                if (whole) return whole;
            }
            const im = it.replace(/[^\d]/g, '').match(/\d{1,5}/);
            if (im) {
                let dp = '';
                //    小数元素查找：① 标准 priceDec ② 兜底用 priceInt 的下一个兄弟节点
                //    （淘宝个别页面小数位类名不含 price，如 <span class="dec--b">.70</span>）
                let decNode = decEl;
                if (!decNode) {
                    let sib = intEl.nextElementSibling;
                    while (sib && !isWrapperClass(String(sib.className || '')) && sib.children.length === 0) {
                        const st = (sib.innerText || sib.textContent || '').trim();
                        if (/^[.．]?\d{1,2}$/.test(st)) { decNode = sib; break; }
                        sib = sib.nextElementSibling;
                    }
                }
                if (decNode) {
                    const dt = (decNode.innerText || decNode.textContent || '').trim();
                    // 兼容 ".70" / "70" / "．70" 三种写法
                    const dm = dt.replace(/[．]/g, '.').match(/^[.]?(\d{1,2})$/);
                    if (dm) dp = dm[1];
                }
                // 拼接后统一用 extractPrice 归一化（去前导0等）
                const merged = dp ? (im[0] + '.' + dp) : im[0];
                const v = parseFloat(merged);
                if (v > 0) return String(v);
            }
        }

        // ② 其次：逐个精确价格元素，跳过容器/销量元素
        //    优先返回"带小数位"的候选，避免整数元素抢先返回导致小数丢失
        const cands = root.querySelectorAll(
            '[class*="price-now"], [class*="priceNow"], [class*="price-current"], [class*="priceCurrent"], .price, [class*="price"], [class*="Price"]'
        );
        let intFallback = '';
        for (const pe of cands) {
            const cls = String(pe.className || '');
            if (isSalesClass(cls)) continue;
            if (isWrapperClass(cls)) continue;                                  // 容器跳过
            if (pe.querySelector('[class*="priceInt"], [class*="priceDec"], [class*="price"]')) continue;
            const raw = (pe.innerText || pe.textContent || '').trim();
            if (!raw || looksLikeSales(raw)) continue;
            const got = extractPrice(raw);
            if (!got) continue;
            if (got.indexOf('.') !== -1) return got;   // 带小数的更可信，直接返回
            if (!intFallback) intFallback = got;       // 纯整数先记下，继续找带小数的
        }

        // ③ 兜底：用容器整体文本（extractPrice 内部已剔除销量片段）
        // 【重要】若 root 是"卡片级别"（priceInt/priceDec 直接挂在卡片下，
        //        没有独立的价格子容器），则**禁止**使用整体文本兜底：
        //        卡片文本含标题（如"中国传媒大学T恤7"），标题里的数字会被
        //        拼进价格（88.5 → 788.5）。
        //        这种结构下 ① 已能通过 priceInt+priceDec 拿到正确结果，
        //        若 ① 失败（如只有单个 priceBox 但那是另一种分支），整体文本也危险。
        if (root.__priceScoped) {
            return intFallback;
        }
        const whole = (root.innerText || root.textContent || '').trim();
        const wholePrice = whole ? extractPrice(whole) : '';
        //    整体文本若含小数，比整数兜底更可信
        if (wholePrice && wholePrice.indexOf('.') !== -1) return wholePrice;
        if (intFallback) return intFallback;
        return wholePrice;
    }

    // 辅助函数：提取图片URL
    function extractPicUrl(a) {
        let pic = a.pic_url || '';
        if (!pic) {
            // 尝试从其他字段获取
            pic = a.pic_path || a.img_url || a.image || '';
        }
        if (pic && !pic.startsWith('http')) {
            pic = 'https:' + pic;
        }
        return pic;
    }

    const list = [];
    // 方式1：从g_page_config全局变量（最可靠）
    try { if (typeof g_page_config !== 'undefined' && g_page_config.mods?.itemlist?.data?.auctions) {
        g_page_config.mods.itemlist.data.auctions.forEach(a => { 
            let price = a.view_price || a.price || '';
            list.push({
                title: (a.raw_title||a.title||'').replace(/<[^>]+>/g,''),
                url: (a.detail_url||'').startsWith('//') ? 'https:' + (a.detail_url||'') : (a.detail_url||''),
                price: extractPrice(price),
                seller: a.nick||'',
                location: a.item_loc||'',
                pic_url: extractPicUrl(a),
            });
        });
    } } catch(e) {}
    // 方式2：从script标签
    if (list.length === 0) { for (const s of document.querySelectorAll('script')) {
        const m = (s.textContent||'').match(/g_page_config\\s*=\\s*({.*?});/);
        if (m) try { const cfg = JSON.parse(m[1]); (cfg.mods?.itemlist?.data?.auctions||[]).forEach(a => {
            let price = a.view_price || a.price || '';
            list.push({
                title: (a.raw_title||a.title||'').replace(/<[^>]+>/g,''),
                url: (a.detail_url||'').startsWith('//') ? 'https:' + (a.detail_url||'') : (a.detail_url||''),
                price: extractPrice(price),
                seller: a.nick||'',
                location: a.item_loc||'',
                pic_url: extractPicUrl(a),
            });
        }); } catch(e) {}
    } }
    // 方式3：从DOM元素（带图片提取）
    if (list.length === 0) {
        document.querySelectorAll('[data-spm*="item"], .search-item, .item-card, [class*="Card"], .J_MouserOnverReq').forEach(el => { try {
            const link = el.querySelector('a[href*="item.taobao.com"], a[href*="detail.tmall.com"]');
            const titleEl = el.querySelector('[class*="Title"], [class*="title"], [class*="Name"], [class*="name"]');
            // 【重要】价格选择器必须先用 findPriceRoot 定位"外层价格容器"，
            // 直接 querySelector('[class*="price"]') 会命中 priceInt 叶子节点，丢失小数位。
            let price = '';
            const priceBox = findPriceRoot(el);
            if (priceBox) price = extractPriceFromContainer(priceBox);
            const priceRaw = getPriceRawText(el);
            const shopEl = el.querySelector('[class*="Shop"], [class*="shop"], [class*="Seller"], [class*="seller"]');
            const locEl = el.querySelector('[class*="location"], [class*="Location"], [class*="loc"], [class*="address"]');
            // 提取图片
            const imgEl = el.querySelector('img[class*="pic"], img[class*="img"], img[class*="Pic"], img[data-src], img[src*="alicdn"]');
            let pic_url = '';
            if (imgEl) {
                pic_url = imgEl.getAttribute('data-src') || imgEl.getAttribute('src') || '';
                if (pic_url && !pic_url.startsWith('http')) pic_url = 'https:' + pic_url;
            }
            const title = titleEl ? (titleEl.textContent || titleEl.innerText || '').trim() : '';
            const seller = shopEl ? (shopEl.textContent || '').trim() : '';
            const location = locEl ? (locEl.textContent || '').trim() : '';
            let url = link ? (link.href || '') : '';
            if (url && url.startsWith('//')) url = 'https:' + url;
            if (title && url && title.length > 2) list.push({ title, url, price, price_raw: priceRaw, seller, location, pic_url });
        } catch(e) {} });
    }
    // 方式4：从所有商品链接（带图片提取）
    if (list.length === 0) { const seen = new Set();
        document.querySelectorAll('a[href*="item.taobao.com"], a[href*="detail.tmall.com"]').forEach(link => { try {
            let url = link.href || ''; if (url && url.startsWith('//')) url = 'https:' + url;
            if (seen.has(url)) return; seen.add(url);
            let parent = link.closest('[class*="item"], [class*="card"], [class*="Card"], li, .search-item, [class*="Item"]') || link.parentElement;
            let title = link.textContent || link.title || '';
            if (!title || title.length < 3) { title = parent ? (parent.textContent || '').trim() : ''; title = title.substring(0, 120); }
            let price = '';
            let priceRaw = '';
            if (parent) {
                const priceBox = findPriceRoot(parent);
                if (priceBox) price = extractPriceFromContainer(priceBox);
                priceRaw = getPriceRawText(parent);
            }
            let location = '';
            if (parent) { const lEl = parent.querySelector('[class*="location"], [class*="Location"]'); if (lEl) location = (lEl.textContent || '').trim(); }
            // 提取图片
            let pic_url = '';
            if (parent) { const imgEl = parent.querySelector('img[class*="pic"], img[class*="img"], img[data-src], img[src*="alicdn"]');
                if (imgEl) {
                    pic_url = imgEl.getAttribute('data-src') || imgEl.getAttribute('src') || '';
                    if (pic_url && !pic_url.startsWith('http')) pic_url = 'https:' + pic_url;
                }
            }
            if (title && title.length > 2) list.push({ title: title.replace(/<[^>]+>/g,'').trim(), url, price, price_raw: priceRaw, seller: '', location, pic_url });
        } catch(e) {} });
    }
    const seen = new Set(); const uniqueList = [];
    for (const item of list) { if (!seen.has(item.url)) { seen.add(item.url); uniqueList.push(item); } }
    return uniqueList;
}
"""


def random_sleep(min_sec, max_sec):
    """随机休眠一段时间，用于模拟人类行为，避免被反爬"""
    delay = random.uniform(min_sec, max_sec)
    time.sleep(delay)

def need_ai_price_check(price, price_raw):
    """
    判断本地提取的价格是否需要AI复核。
    返回: (是否需要, 原因说明)
    """
    from backend.config import (
        AI_PRICE_VERIFY, AI_PRICE_TRIGGER_ON_EMPTY,
        AI_PRICE_TRIGGER_ON_DECIMAL_LOSS, AI_PRICE_TRIGGER_ON_NOISE,
    )
    if not AI_PRICE_VERIFY:
        return False, ""

    raw = (price_raw or "").strip()

    # 条件1：本地没提取到价格，但原始文本里有内容 → 让AI试试
    if AI_PRICE_TRIGGER_ON_EMPTY and not price and raw:
        return True, "本地未提取到价格"

    # 条件2：价格区原始文本含"有效小数"，但提取结果没有小数位 → 疑似小数被截断（如 5.32→5）
    #       注意：整数价常显示为 ¥128.00，这种"小数位全为0"不算丢失，不触发
    if AI_PRICE_TRIGGER_ON_DECIMAL_LOSS and price and "." not in str(price) and raw:
        if re.search(r'\d{1,5}[.．](?!0+\b)\d{1,2}', raw):
            return True, "疑似小数位丢失"

    # 条件3：价格区文本含销量类干扰数字 → 价格可能取错
    if AI_PRICE_TRIGGER_ON_NOISE and raw:
        if re.search(r'(已售|月销|销量|人付款|人已买|人收货|条评价|人收藏|成交)', raw):
            return True, "价格区含销量信息"

    return False, ""


def resolve_price(price, price_raw, title="", progress_cb=None):
    """
    价格最终确认：本地规则提取结果 + 可选AI复核。

    参数:
        price: 本地规则提取到的价格字符串
        price_raw: 价格区域原始文本
        title: 商品标题（仅用于日志）
        progress_cb: 进度回调

    返回:
        (最终价格字符串, 是否使用了AI)
    """
    need, why = need_ai_price_check(price, price_raw)
    if not need:
        return price, False

    try:
        from backend.ai_verifier import verify_price_by_ai
        if not AI_VERIFIER_AVAILABLE:
            return price, False

        if progress_cb:
            progress_cb(f"   🔍 价格需AI复核（{why}）: {price_raw or '(空)'}")
        res = verify_price_by_ai(price_raw, progress_cb=progress_cb)
        if res.get("ai_used") and res.get("price"):
            ai_price = res["price"]
            # AI结果与本地结果不一致时，采用AI（AI能看到完整原文）
            if ai_price != price:
                logger.info(f"价格AI修正: '{price}' -> '{ai_price}' | 原文='{price_raw}' | 标题={title[:50]}")
            return ai_price, True
    except Exception as e:
        logger.warning(f"AI价格复核失败: {e}")

    return price, False


def is_book(title):
    # 注意：必须统一转小写，否则 BOOK_KWS 里的 "ISBN" 匹配不到小写 "isbn"
    t = title.lower()
    return any(k.lower() in t for k in BOOK_KWS)

def is_service_product(title):
    """
    判断标题是否为「非实物商品」（作品成果类 / 服务类），不计入商标侵权检测。

    【判定原则——作品/服务优先，命中即排除】
      1. 命中 WORK_KWS（实践作品/文字报告/作品集…）→ **跳过**（作品类）
      2. 否则命中 SERVICE_KWS（代做/代写/设计/论文辅导…）→ **跳过**（服务类）
      3. 都没命中 → 不跳过（交由后续步骤判定，最终会走"默认判侵权"）

    ⚠️ 注意：这里**不再**检查任何"实物载体词表"。
       标题里同时出现"笔记本""明信片"等词时，也**不**据此推断卖家实际卖实物
       —— 那是擅自推断，禁止。作品/服务词命中即直接排除。

    返回: (是否跳过, 命中的关键词, 类别)  类别 ∈ {"作品", "服务", ""}
    """
    t = title.lower()

    # 1. 作品/成果类（实践作品、文字报告、作品集等）—— 优先级最高
    for k in WORK_KWS:
        if k.lower() in t:
            return True, k, "作品"

    # 2. 服务类（代做、代写、设计、论文辅导等）
    for k in SERVICE_KWS:
        if k.lower() in t:
            return True, k, "服务"

    return False, "", ""

def is_in_beijing(location):
    """判断商品所在地是否在北京"""
    if not location:
        return False
    return '北京' in location

def has_trademark_keyword(title):
    """标题是否包含校名校徽等商标关键词"""
    t = title.lower()
    return any(k.lower() in t for k in TRADEMARK_KWS)

def has_infringement_category(title):
    """标题是否属于侵权商品类别（服装、文具、饰品等）"""
    t = title.lower()
    return any(k.lower() in t for k in INFRINGEMENT_CATEGORY_KWS)

def is_low_price(price_str):
    """判断价格是否低于低价阈值"""
    try:
        price = float(price_str)
        return price < LOW_PRICE_THRESHOLD
    except (ValueError, TypeError):
        return False

def is_suspected_infringement(title, price, location, use_ai=False, progress_cb=None):
    """
    商标侵权判定逻辑（五步核查）+ 可选AI增强

    【判定原则（唯一正确版本）】
      ① 标题不含校名校徽关键词            → 不侵权
      ② 命中 WORK_KWS（作品/成果类）      → 不侵权、**不截图**
      ③ 命中 SERVICE_KWS（服务类）        → 不侵权、**不截图**
      ④ is_book() 为真（书籍/教材）       → 不侵权、**不截图**
      ⑤ 以上都不命中                      → **直接判侵权**（默认判侵权）

    ⚠️ 第⑤步**不要求**标题出现"服装/文具/饰品"等类别词。
       类别词命中只往理由里加一句"商品类别匹配"，不影响结论。

    参数:
        title: 商品标题
        price: 价格
        location: 所在地
        use_ai: 是否启用AI增强判断（混合模式）
        progress_cb: 进度回调（用于AI调用时显示进度）

    返回:
        (是否侵权, 判定理由, ai_used)
        - ai_used: 是否使用了AI辅助判断
    """
    reasons = []
    
    # 步骤1：是否商业使用（标题含校名校徽+上架售卖）
    has_tm = has_trademark_keyword(title)
    if not has_tm:
        return False, "标题不含校名校徽关键词", False
    reasons.append("标题含校名校徽关键词")
    
    # 步骤2：比对标识是否相同/近似
    # 标题含"中国传媒大学"、"CUC"、"中传"、"校徽"等，视为相同/近似
    if "中国传媒大学" in title or "中传" in title:
        reasons.append("含完整校名/简称")
    if "CUC" in title.upper():
        reasons.append("含CUC缩写")
    if "校徽" in title:
        reasons.append("含校徽标识")
    
    # 步骤3：作品成果类 / 虚拟服务类排除（实践作品、文字报告、代做代写等不属于实物侵权）
    # 【必须在最前面】命中即返回，后面的书籍/类别判断都不参与。
    is_svc, svc_kw, svc_kind = is_service_product(title)
    if is_svc:
        return False, f"非实物产品（{svc_kind}类，命中\"{svc_kw}\"）", False
    reasons.append("实物产品")

    # 步骤3.5：书籍/教材排除（不在商标侵权检测范围内）
    if is_book(title):
        return False, "书籍/教材（不在检测范围）", False

    # 步骤3.6：默认判侵权（★ 关键规则）
    # 【规则】标题含校名校徽关键词，且不是作品类、不是服务类、不是书籍
    #         → 一律判侵权，**不再要求**命中"服装/文具/饰品"等类别词。
    #   类别词只用来补充理由说明，不作为判侵权的前置条件。
    if has_infringement_category(title):
        reasons.append("商品类别匹配")
    else:
        reasons.append("非书籍实体商品（默认判侵权）")
    
    # 步骤4：核查商家授权（无授权推定侵权）
    # 非北京商家 + 低价 = 无授权可能性大
    is_bj = is_in_beijing(location)
    if is_bj:
        reasons.append("北京商家（需人工核查授权）")
    else:
        reasons.append("非北京商家（推定无授权）")
    
    # 步骤5：是否造成混淆
    # 标题含"纪念"、"周边"、"文创"、"官方"等词，易造成混淆
    confusion_kws = ["纪念","周边","文创","官方","纪念品","纪念款"]
    if any(k in title for k in confusion_kws):
        reasons.append("易造成官方混淆")
    
    # 综合判定
    # 核心条件：有商标关键词 + 有商品类别匹配 = 侵权
    # 辅助条件：非北京 + 低价 = 高置信度侵权
    confidence = "高" if (not is_bj and is_low_price(price)) else ("中" if not is_bj else "低")
    reasons.append(f"置信度:{confidence}")
    
    rule_result = True
    rule_reason = "; ".join(reasons)
    
    # ========== AI增强判断（混合模式） ==========
    ai_used = False
    if use_ai and AI_VERIFIER_AVAILABLE:
        try:
            final_result, final_reason, ai_used = ai_enhanced_judgment(
                title=title,
                price=price,
                location=location,
                rule_result=rule_result,
                rule_reason=rule_reason,
                progress_cb=progress_cb,
            )
            return final_result, final_reason, ai_used
        except Exception:
            # AI调用失败，回退到规则结果
            pass
    
    return rule_result, rule_reason, ai_used


def detect_browser():
    """检测已安装的浏览器，返回 (browser_name, browser_path, user_data_dir)"""
    if os.name == 'nt':
        # Edge 用户数据目录
        edge_paths = [
            ("C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe", os.path.expanduser("~\\AppData\\Local\\Microsoft\\Edge\\User Data")),
            ("C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe", os.path.expanduser("~\\AppData\\Local\\Microsoft\\Edge\\User Data")),
        ]
        # Chrome 用户数据目录
        chrome_paths = [
            ("C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe", os.path.expanduser("~\\AppData\\Local\\Google\\Chrome\\User Data")),
            ("C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe", os.path.expanduser("~\\AppData\\Local\\Google\\Chrome\\User Data")),
        ]
        for p, udd in edge_paths:
            if os.path.exists(p): return "msedge", p, udd
        for p, udd in chrome_paths:
            if os.path.exists(p): return "chrome", p, udd
    return "chromium", None, None

COOKIE_FILE = BASE / "data" / "taobao_cookies.json"

def load_cookies(ctx):
    if not COOKIE_FILE.exists():
        logger.info("Cookie文件不存在，需要手动登录")
        return False
    try:
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            cookies = json.load(f)
        for c in cookies:
            c.pop('sameSite', None); c.pop('priority', None); c.pop('sameParty', None); c.pop('sourceScheme', None); c.pop('sourcePort', None)
        ctx.add_cookies(cookies)
        logger.info(f"成功加载 {len(cookies)} 个Cookie")
        return True
    except Exception as e:
        logger.error(f"加载Cookie失败: {e}")
        return False

def save_cookies(ctx):
    try:
        cookies = ctx.cookies()
        COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(COOKIE_FILE, "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
        logger.info(f"成功保存 {len(cookies)} 个Cookie到 {COOKIE_FILE}")
        return True
    except Exception as e:
        logger.error(f"保存Cookie失败: {e}")
        return False

def _handle_login(page, max_retries=3):
    for i in range(max_retries):
        try:
            is_login = page.evaluate(LOGIN_CHECK_JS)
            if not is_login: return False
            self_progress = getattr(page, '_progress', None) or (lambda m: None)
            self_progress("检测到登录弹窗，尝试关闭...")
            dismissed = page.evaluate(DISMISS_LOGIN_JS)
            page.wait_for_timeout(1000)
            if dismissed: self_progress("已关闭登录弹窗"); return True
        except: pass
        page.wait_for_timeout(500)
    return True

def _check_login_by_cookies(ctx):
    """通过Cookie检测是否已登录淘宝（最可靠方式）"""
    try:
        cookies = ctx.cookies()
        cookie_names = {c['name'] for c in cookies}
        login_cookies = {'_tb_token_', 'cookie2', 'l', 'uc1', 'uc3', 'tracknick', 'dnk', 'thw', 'unb'}
        matched = cookie_names & login_cookies
        if matched:
            logger.info(f"Cookie检测到登录标记: {matched}")
            return True
        return False
    except Exception as e:
        logger.warning(f"Cookie检测异常: {e}")
        return False

def _wait_for_login(page, ctx, timeout_minutes=10, stop_event=None):
    self_progress = getattr(page, '_progress', None) or (lambda m: None)
    self_progress("⚠️ 请在浏览器中手动登录淘宝（推荐扫码登录，短信登录可能被拦截）")
    self_progress(f"⏳ 等待登录中（最长{timeout_minutes}分钟）...")
    logger.info("开始等待登录...")
    start = time.time()
    while time.time() - start < timeout_minutes * 60:
        # 检查是否被用户终止
        if stop_event and stop_event.is_set():
            self_progress("🛑 用户终止等待登录")
            logger.info("用户终止等待登录")
            return False
        try:
            # 检查页面URL和状态
            current_url = page.url
            logger.debug(f"等待登录中 - 当前URL: {current_url}")
            
            # 检查页面是否还活着
            closed = page.evaluate("document.body === null")
            if closed:
                self_progress("⚠️ 页面已关闭，尝试重新导航到淘宝...")
                logger.warning("页面body为null，尝试重新导航")
                try:
                    page.goto("https://www.taobao.com", wait_until="domcontentloaded", timeout=15000)
                    page.wait_for_timeout(2000)
                    logger.info("重新导航到淘宝首页成功")
                except Exception as nav_e:
                    logger.error(f"重新导航失败: {nav_e}")
                    self_progress("❌ 页面无法恢复，登录失败")
                    return False
            
            # 方式1：Cookie检测（最可靠）
            if _check_login_by_cookies(ctx):
                self_progress("✅ 登录成功！等待页面稳定...")
                logger.info("登录成功（Cookie检测）！等待5秒稳定...")
                page.wait_for_timeout(5000)
                return True
            
            # 方式2：JS DOM检测（备选）
            logged_in = page.evaluate(IS_LOGGED_IN_JS)
            has_login_modal = page.evaluate(LOGIN_CHECK_JS)
            logger.debug(f"登录状态检查 - logged_in={logged_in}, has_login_modal={has_login_modal}")
            if logged_in is True and not has_login_modal:
                self_progress("✅ 登录成功！等待页面稳定...")
                logger.info("登录成功（DOM检测）！等待5秒稳定...")
                page.wait_for_timeout(5000)
                return True

        except Exception as e:
            err_str = str(e)
            logger.warning(f"等待登录异常: {err_str[:200]}")
            # 页面被关闭或导航到无效页面
            if "closed" in err_str.lower() or "detached" in err_str.lower() or "target" in err_str.lower():
                self_progress("⚠️ 浏览器页面状态异常，尝试重新导航到淘宝...")
                logger.warning("页面状态异常，尝试重新导航")
                try:
                    page.goto("https://www.taobao.com", wait_until="domcontentloaded", timeout=15000)
                    page.wait_for_timeout(2000)
                    logger.info("重新导航到淘宝首页成功")
                except Exception as nav_e:
                    logger.error(f"重新导航失败: {nav_e}")
                    self_progress("❌ 页面无法恢复，登录失败")
                    return False
        page.wait_for_timeout(3000)
    logger.warning("登录超时")
    self_progress("⏰ 登录超时"); return False




def check_login_status(page, ctx=None):
    try:
        # 方式1：Cookie检测（最可靠）
        if ctx and _check_login_by_cookies(ctx):
            return True
        _handle_login(page); page.wait_for_timeout(500)
        # 方式2：JS DOM检测
        logged_in = page.evaluate(IS_LOGGED_IN_JS)
        if logged_in is True: return True
        if logged_in is False: return False
        has_login_modal = page.evaluate(LOGIN_CHECK_JS)
        if not has_login_modal and ('taobao.com' in page.url or 'tmall.com' in page.url): return True
        return False
    except: return False


def check_captcha(page):
    try: return page.evaluate(CAPTCHA_CHECK_JS)
    except: return False

def handle_captcha(page, max_retries=3):
    self_progress = getattr(page, '_progress', None) or (lambda m: None)
    for i in range(max_retries):
        try:
            if not check_captcha(page): return True
            self_progress(f"🔐 检测到滑块验证，尝试自动关闭 ({i+1}/{max_retries})...")
            dismissed = page.evaluate(DISMISS_CAPTCHA_JS)
            page.wait_for_timeout(1500)
            if dismissed and not check_captcha(page): self_progress("✅ 滑块验证已关闭"); return True
        except: pass
        page.wait_for_timeout(1000)
    return False

def wait_for_captcha_solve(page, timeout_minutes=5):
    self_progress = getattr(page, '_progress', None) or (lambda m: None)
    self_progress("⚠️ 检测到淘宝滑块验证！")
    self_progress("👉 请在浏览器中手动拖动滑块完成验证")
    self_progress(f"⏳ 等待验证中（最长{timeout_minutes}分钟）...")
    start = time.time()
    while time.time() - start < timeout_minutes * 60:
        try:
            has_captcha = check_captcha(page)
            if not has_captcha:
                page.wait_for_timeout(1000)
                if not check_captcha(page):
                    self_progress("✅ 滑块验证通过！")
                    page.reload(wait_until="domcontentloaded")
                    page.wait_for_timeout(1500)
                    return True
        except:
            pass
        page.wait_for_timeout(2000)
    self_progress("⏰ 滑块验证超时"); return False

class Detector:
    def __init__(self, progress_cb=None, max_pages=10, existing_results=None, start_page=0):
        """
        Args:
            progress_cb: 进度回调函数
            max_pages: 本次要检测的页数
            existing_results: 已有的检测结果列表（用于增量检测）
            start_page: 起始页码（0=从第1页开始，n=从第n+1页开始）
        """
        self.progress = progress_cb or (lambda msg: print(msg))
        self._stop_event = threading.Event()
        self._browser = None
        self._ctx = None
        self.max_pages = max_pages
        # 增量检测支持
        self.existing_results = existing_results or []
        self.start_page = start_page  # 起始页码
    
    def stop(self):
        self._stop_event.set()
        self.progress("🛑 收到终止指令，正在停止检测...")
    
    def _check_stop(self):
        if self._stop_event.is_set():
            raise StopIteration("检测任务已被用户终止")
    
    def _navigate_and_handle_login(self, page, url, **kwargs):
        try:
            page.goto(url, **kwargs)
            page.wait_for_timeout(2000)
            _handle_login(page)
            if check_captcha(page):
                if not handle_captcha(page):
                    wait_for_captcha_solve(page)
        except Exception as e:
            self.progress(f"导航失败: {e}")
    
    def run(self) -> tuple[list, int, int, int, str]:
        if os.name == 'nt':
            browser_name, browser_path, user_data_dir = detect_browser()
            self.progress(f"检测到浏览器: {browser_name}")
        else:
            browser_name = "chromium"
            user_data_dir = None
        
        self.progress("启动浏览器...")
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            # ========== 启动浏览器 ==========
            # 使用最稳妥的方式：不指定用户数据目录，避免与已运行的浏览器冲突
            # Cookie通过之前保存的 taobao_cookies.json 文件加载
            launch_args = ["--no-sandbox", "--disable-blink-features=AutomationControlled"]
            
            # 先尝试用channel启动（使用系统已安装的Edge/Chrome）
            # 如果失败则回退到纯chromium
            browser = None
            if browser_name in ("msedge", "chrome"):
                try:
                    self.progress(f"尝试使用系统{browser_name}浏览器...")
                    browser = p.chromium.launch(
                        headless=False,
                        channel=browser_name,
                        args=launch_args,
                        timeout=15000,  # 15秒超时
                    )
                except Exception as e:
                    self.progress(f"⚠️ 系统{browser_name}启动失败: {str(e)[:60]}")
                    self.progress("回退到内置Chromium浏览器...")
                    browser = None
            
            if browser is None:
                try:
                    browser = p.chromium.launch(
                        headless=False,
                        args=launch_args,
                        timeout=30000,
                    )
                except Exception as e:
                    msg = str(e)
                    if "Executable doesn't exist" in msg or "playwright install" in msg:
                        raise RuntimeError(
                            "内置 Chromium 浏览器未安装。\n\n"
                            "请在项目目录下执行以下命令安装后重试：\n"
                            "    python -m playwright install chromium\n\n"
                            f"原始错误: {msg[:300]}"
                        )
                    raise
            self._browser = browser
            ctx = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="zh-CN", timezone_id="Asia/Shanghai",
            )
            self._ctx = ctx
            
            page = ctx.new_page()
            page.add_init_script(STEALTH_JS)
            page._progress = self.progress
            
            # ========== 第一步：登录验证 ==========
            self.progress("=" * 60)
            self.progress("第一步：登录验证")
            self.progress("=" * 60)
            
            # 先尝试加载已保存的Cookie文件
            if COOKIE_FILE.exists():
                self.progress("📂 加载本地登录凭证...")
                loaded = load_cookies(ctx)
                self.progress("✅ 登录凭证已加载" if loaded else "⚠️ 加载失败")
            
            self.progress("🌐 访问淘宝首页...")
            self._navigate_and_handle_login(page, "https://www.taobao.com", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)
            
            if not check_login_status(page, ctx):
                self.progress("⚠️ 请手动登录淘宝...")

                try:
                    login_btn = page.query_selector('.site-nav-login-info a, .J_Login, .btn-login')
                    if login_btn: login_btn.click(); page.wait_for_timeout(1000)
                except: pass
                if not _wait_for_login(page, ctx, timeout_minutes=1, stop_event=self._stop_event):
                    self.progress("❌ 登录失败"); return [], 0, 0, 0, ""

                save_cookies(ctx)
            
            # ========== 第二步：搜索 + 翻页 + 侵权识别 ==========
            self.progress("=" * 60)
            self.progress("第二步：搜索商品，商标侵权智能判定")
            self.progress("=" * 60)
            
            self.progress(f"🔍 搜索关键词: \"{KEYWORD}\"")
            self.progress(f"📄 最多翻页数: {self.max_pages} 页")
            
            # 增量检测：使用已有的结果
            results = list(self.existing_results)  # 复制已有结果
            page_num = self.start_page  # 从指定页码开始
            total_scanned = 0
            total_books = 0
            total_services = 0
            total_infringing = 0
            
            if self.existing_results:
                self.progress(f"📋 已有 {len(self.existing_results)} 个检测结果，继续增量检测...")
                self.progress(f"📄 从第 {self.start_page + 1} 页开始检测，共 {self.max_pages} 页")
            
            # 计算起始偏移量：淘宝每页44个商品，第n页偏移为 (n-1)*44
            s_offset = self.start_page * 44
            first_search_url = "https://s.taobao.com/search?q=" + urllib.parse.quote(KEYWORD) + "&s=" + str(s_offset)
            self.progress(f"🌐 访问搜索结果页（偏移量: {s_offset}）...")
            self._navigate_and_handle_login(page, first_search_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)
            
            # 记录已访问过的页码
            visited_pages = set()
            
            while page_num < self.start_page + self.max_pages:
                # 检查是否被用户终止
                if self._stop_event and self._stop_event.is_set():
                    self.progress("🛑 用户终止检测")
                    logger.info("用户终止检测（翻页循环）")
                    break

                current_page_display = page_num + 1
                visited_pages.add(current_page_display)
                self.progress(f"📄 第 {current_page_display} 页...")

                
                # 翻页（优先点击页码按钮，随机跳页）
                if page_num > 0:
                    random_sleep(2, 5)
                    
                    # 先获取当前页的页码信息，看看有哪些页码可用
                    page_info = page.evaluate(GET_PAGE_INFO_JS)
                    available = page_info.get('availablePages', [])
                    
                    # 过滤掉已访问过的页码
                    unvisited = [p for p in available if p not in visited_pages]
                    
                    if unvisited:
                        # 随机选一个未访问的页码
                        target_page = random.choice(unvisited)
                    else:
                        # 没有未访问的页码，就顺序+1
                        target_page = page_num + 1
                    
                    self.progress(f"   翻页到第 {target_page} 页...")
                    
                    # 方式1（首选）：点击页码按钮
                    clicked = page.evaluate(CLICK_PAGE_JS, target_page)
                    
                    if clicked:
                        self.progress(f"   ✅ 点击页码 {target_page} 成功")
                        page.wait_for_timeout(3000)
                    else:
                        # 方式2：滚动到底部再试
                        self.progress("   点击页码失败，尝试滚动到底部...")
                        try:
                            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                            page.wait_for_timeout(1500)
                            clicked = page.evaluate(CLICK_PAGE_JS, target_page)
                            if clicked:
                                self.progress(f"   ✅ 滚动后点击页码 {target_page} 成功")
                                page.wait_for_timeout(3000)
                            else:
                                # 方式3：尝试点击"下一页"按钮
                                self.progress("   尝试点击'下一页'按钮...")
                                try:
                                    next_btn = page.query_selector('.pagination .next, .page-next, .next-page, .J_Ajax.next, a[class*="next"]')
                                    if next_btn and next_btn.is_visible():
                                        next_btn.click()
                                        page.wait_for_timeout(3000)
                                        self.progress("   ✅ 点击'下一页'成功")
                                    else:
                                        raise Exception("未找到下一页按钮")
                                except:
                                    # 方式4（最后备选）：URL翻页
                                    self.progress(f"   ⚠️ 页码点击均失败，尝试URL翻页")
                                    s = page_num * 44
                                    search_url = "https://s.taobao.com/search?q=" + urllib.parse.quote(KEYWORD) + "&s=" + str(s)
                                    self._navigate_and_handle_login(page, search_url, wait_until="domcontentloaded", timeout=30000)
                                    page.wait_for_timeout(2000)
                        except Exception as e:
                            self.progress(f"   翻页异常: {e}")
                            # 最后备选：URL翻页
                            s = page_num * 44
                            search_url = "https://s.taobao.com/search?q=" + urllib.parse.quote(KEYWORD) + "&s=" + str(s)
                            self._navigate_and_handle_login(page, search_url, wait_until="domcontentloaded", timeout=30000)
                            page.wait_for_timeout(2000)
                
                # 检查滑块验证
                if check_captcha(page):
                    self.progress("⚠️ 搜索页出现滑块验证...")
                    if not handle_captcha(page):
                        if not wait_for_captcha_solve(page):
                            self.progress("❌ 滑块验证未通过，跳过本页")
                            page_num += 1
                            continue
                
                # 确认登录状态
                if not check_login_status(page, ctx):
                    self.progress("⚠️ 登录状态失效，重新登录...")

                    login_ok = _wait_for_login(page, ctx, timeout_minutes=5)

                    if not login_ok:
                        self.progress("❌ 重新登录失败")
                        break
                    save_cookies(ctx)
                
                # 滚动页面触发懒加载
                self.progress("   滚动页面加载商品...")
                try:
                    viewport_height = page.evaluate("window.innerHeight")
                    scroll_height = page.evaluate("document.body.scrollHeight")
                    for i in range(3):
                        scroll_to = min(viewport_height * (i + 1) * 0.8, scroll_height - viewport_height)
                        page.evaluate(f"window.scrollTo({{top: {scroll_to}, behavior: 'smooth'}})")
                        page.wait_for_timeout(random.randint(800, 1500))
                    page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
                    page.wait_for_timeout(800)
                except Exception:
                    pass
                
                # 提取商品
                items = page.evaluate(EXTRACT_ITEMS_JS)
                
                if not items:
                    self.progress(f"⚠️ 第{page_num + 1}页无商品数据，可能已到底或被风控")
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(2000)
                    items = page.evaluate(EXTRACT_ITEMS_JS)
                    if not items:
                        page_num += 1
                        continue
                
                self.progress(f"   当前页提取到 {len(items)} 个商品")
                
                # 遍历当前页商品
                for item in items:
                    # 检查是否被用户终止
                    if self._stop_event and self._stop_event.is_set():
                        self.progress("🛑 用户终止检测（商品遍历中）")
                        logger.info("用户终止检测（商品遍历中）")
                        break

                    title = item.get('title', '')
                    url = item.get('url', '')
                    if not url or not title:
                        continue
                    
                    total_scanned += 1

                    
                    # 书籍过滤
                    if is_book(title):
                        total_books += 1
                        continue
                    
                    # 虚拟服务类 / 作品成果类过滤
                    is_svc, svc_kw, svc_kind = is_service_product(title)
                    if is_svc:
                        total_services += 1
                        self.progress(f"   ⏭️ 跳过非实物（{svc_kind}类:{svc_kw}）: {title[:40]}...")
                        continue
                    
                    # 商标侵权智能判定（五步核查 + 可选AI增强）
                    location = item.get('location', '')
                    price = item.get('price', '')
                    price_raw = item.get('price_raw', '')
                    # 价格最终确认（本地规则 + 可选AI复核）
                    price, price_ai_used = resolve_price(
                        price, price_raw, title=title, progress_cb=self.progress
                    )
                    if price_ai_used:
                        self.progress(f"   💰 价格已由AI确认: {price or '(未取到)'}元")
                    is_inf, reason, ai_used = is_suspected_infringement(
                        title, price, location,
                        use_ai=True,  # 启用AI增强模式
                        progress_cb=self.progress,
                    )
                    
                    if not is_inf:
                        self.progress(f"   ⏭️ 跳过（{reason}）: {title[:40]}...")
                        continue

                    # 【硬保护】截图前二次确认：作品类/服务类绝不截图
                    # 防止 AI 增强层把规则已排除的作品类"救活"成侵权后误入截图流程
                    svc2, kw2, kind2 = is_service_product(title)
                    if svc2:
                        self.progress(f"   ⏭️ 跳过截图（非实物·{kind2}类:{kw2}）: {title[:40]}...")
                        total_services += 1
                        continue

                    total_infringing += 1
                    
                    # 侵权商品 -> 进入详情页截图
                    inf_count = len([r for r in results if r["是否侵权"] == "是"])
                    tag = "🤖" if ai_used else "📸"
                    self.progress(f"{tag} 截图侵权商品 #{inf_count + 1}: {title[:50]}...")
                    self.progress(f"   判定依据: {reason}")
                    
                    random_sleep(1.5, 3.5)
                    
                    fpath = ""
                    try:
                        detail_page = ctx.new_page()
                        detail_page.add_init_script(STEALTH_JS)
                        detail_page._progress = self.progress
                        detail_page.goto(url, wait_until="load", timeout=30000)
                        detail_page.wait_for_timeout(1500)
                        
                        if check_captcha(detail_page):
                            self.progress("   ⚠️ 详情页出现滑块验证...")
                            if not handle_captcha(detail_page):
                                wait_for_captcha_solve(detail_page)
                        
                        detail_page.evaluate("window.scrollTo(0, 300)")
                        detail_page.wait_for_timeout(800)
                        
                        fname = f"inf_{inf_count + 1:02d}_{item.get('seller','unknown')[:12]}_{item.get('price','0').replace('.','_')}.png"
                        fpath = str(SCREENSHOTS / fname)
                        detail_page.screenshot(path=fpath, full_page=False)
                        self.progress(f"   ✅ 截图已保存: {fname}")
                        detail_page.close()
                    except Exception as e:
                        self.progress(f"   ❌ 截图失败: {str(e)[:60]}")
                        try: detail_page.close()
                        except: pass
                    
                    # 获取商品主图URL（搜索结果页的缩略图，清晰可辨）
                    pic_url = item.get('pic_url', '')
                    
                    results.append({
                        "序号": len(results) + 1,
                        "商品名称": title[:120],
                        "商品URL": url,
                        "记录时间": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "价格": item.get('price', ''),
                        "是否侵权": "是",
                        "截图路径": fpath,
                        "主图URL": pic_url,  # 搜索结果页的主图URL，用于卡片显示
                    })
                
                # 每5页保存一次cookies
                if page_num % 5 == 0 and page_num > 0:
                    save_cookies(ctx)
                
                page_num += 1
            
            # ========== 第三步：生成报告 ==========
            inf_count = len([r for r in results if r["是否侵权"] == "是"])
            
            self.progress("=" * 60)
            self.progress("第三步：生成检测报告")
            self.progress("=" * 60)
            self.progress(f"📊 扫描商品总数: {total_scanned}")
            self.progress(f"🚫 侵权商品: {inf_count}")
            self.progress(f"📚 排除书籍: {total_books}")
            self.progress(f"🛠️ 排除虚拟服务类: {total_services}")
            self.progress(f"📍 非北京商家: {total_infringing}")
            self.progress(f"📄 翻页数: {page_num}")
            
            if inf_count == 0:
                self.progress("⚠️ 未找到任何侵权商品")
                ctx.close()
                try: browser.close()
                except: pass
                return results, inf_count, total_books, total_scanned, ""
            
            self.progress("📝 生成Excel报告...")
            from openpyxl import Workbook
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
            from openpyxl.drawing.image import Image as XlImage
            import openpyxl.utils
            
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            excel_path = REPORTS_DIR / f"侵权检测报告_{timestamp}.xlsx"
            
            wb = Workbook()
            ws = wb.active
            ws.title = "侵权检测报告"
            
            # 检查是否有AI验证结果，动态决定是否增加AI列
            has_ai_results = any(r.get("ai_result") for r in results)
            
            if has_ai_results:
                headers = ["序号","商品名称","商品截图","商品URL","记录时间","价格","是否侵权","AI侵权校验","AI置信度","AI建议"]
            else:
                headers = ["序号","商品名称","商品截图","商品URL","记录时间","价格","是否侵权"]
            
            hf = Font(bold=True, size=11, color="FFFFFF")
            hb = PatternFill("solid", fgColor="4472C4")
            ha = Alignment(horizontal="center", vertical="center", wrap_text=True)
            thin = Border(left=Side('thin'),right=Side('thin'),top=Side('thin'),bottom=Side('thin'))
            
            for ci, h in enumerate(headers, 1):
                c = ws.cell(row=1, column=ci, value=h)
                c.font=hf; c.fill=hb; c.alignment=ha; c.border=thin
            
            if has_ai_results:
                widths = [8,50,22,55,20,12,12,12,12,18]
            else:
                widths = [8,50,22,55,20,12,12]
            for ci,w in enumerate(widths,1):
                ws.column_dimensions[openpyxl.utils.get_column_letter(ci)].width = w
            
            black = Font(color="000000")
            red = Font(color="FF0000", bold=True)
            green = Font(color="27ae60", bold=True)
            orange = Font(color="e67e22", bold=True)

            for ri, r in enumerate(results, 2):
                c1 = ws.cell(row=ri, column=1, value=r.get("序号", ''))
                c1.border=thin; c1.alignment=Alignment(vertical="center",wrap_text=True); c1.font = black

                c2 = ws.cell(row=ri, column=2, value=r.get("商品名称", ''))
                c2.border=thin; c2.alignment=Alignment(vertical="center",wrap_text=True); c2.font = black

                img_path = r.get("截图路径", "")
                if img_path and os.path.exists(img_path):
                    try:
                        img = XlImage(img_path)
                        img.width = 120
                        img.height = 120 * img.height / img.width if img.width > 0 else 120
                        if img.height > 160: img.height = 160
                        ws.add_image(img, f"C{ri}")
                        ws.row_dimensions[ri].height = max(ws.row_dimensions[ri].height or 0, img.height + 4)
                    except Exception as e:
                        self.progress(f"   嵌入截图失败 (第{ri}行): {e}")

                c4 = ws.cell(row=ri, column=4, value=r.get("商品URL", ''))
                c4.border=thin; c4.alignment=Alignment(vertical="center",wrap_text=True)
                url = r.get("商品URL", '')
                if url:
                    c4.hyperlink = url
                    c4.font = Font(color="0563C1", underline="single")

                c5 = ws.cell(row=ri, column=5, value=r.get("记录时间", ''))
                c5.border=thin; c5.alignment=Alignment(vertical="center",wrap_text=True); c5.font = black

                c6 = ws.cell(row=ri, column=6, value=r.get("价格", ''))
                c6.border=thin; c6.alignment=Alignment(vertical="center",wrap_text=True); c6.font = black

                c7 = ws.cell(row=ri, column=7, value=r.get("是否侵权", ''))
                c7.border=thin; c7.alignment=Alignment(vertical="center",wrap_text=True); c7.font = red

                
                # AI验证结果列（如果有）
                if has_ai_results:
                    ai = r.get("ai_result", {})
                    if ai:
                        ai_inf = ai.get("is_infringement")
                        conf_score = ai.get("confidence_score", 0)
                        ai_sug = ai.get("suggestion", "建议复核")
                        
                        # AI侵权校验列：只填"是"或"否"
                        if ai_inf is True:
                            ai_text = "是"
                        elif ai_inf is False:
                            ai_text = "否"
                        else:
                            ai_text = "建议复核"
                        
                        # 根据分数决定建议和颜色
                        if ai_inf is True:
                            if conf_score >= 80:
                                ai_sug = "确认侵权"
                                ai_font = Font(color="FF0000", bold=True)
                            elif conf_score >= 60:
                                ai_sug = "酌情复核"
                                ai_font = Font(color="FF0000", bold=True)
                            else:
                                ai_sug = "建议复核"
                                ai_font = Font(color="FF0000", bold=True)
                        elif ai_inf is False:
                            ai_font = green
                        else:
                            ai_font = orange
                        
                        c8 = ws.cell(row=ri, column=8, value=ai_text)
                        c8.border=thin; c8.alignment=Alignment(horizontal="center", vertical="center", wrap_text=True); c8.font = ai_font
                        
                        c9 = ws.cell(row=ri, column=9, value=f"{conf_score}%")
                        c9.border=thin; c9.alignment=Alignment(horizontal="center", vertical="center", wrap_text=True); c9.font = ai_font
                        
                        c10 = ws.cell(row=ri, column=10, value=ai_sug)
                        c10.border=thin; c10.alignment=Alignment(vertical="center", wrap_text=True); c10.font = ai_font
                    else:
                        for ci in [8,9,10]:
                            c = ws.cell(row=ri, column=ci, value="-")
                            c.border=thin; c.alignment=Alignment(horizontal="center", vertical="center")

            
            wb.save(str(excel_path))
            self.progress(f"✅ Excel报告已保存: {excel_path}")
            self.progress(f"🖼️  截图保存在: {SCREENSHOTS}")
            
            try: ctx.close()
            except: pass
            try: browser.close()
            except: pass
            
            return results, inf_count, total_books, total_scanned, str(excel_path)


if __name__ == "__main__":
    d = Detector()
    d.run()

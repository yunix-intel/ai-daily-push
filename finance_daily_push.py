# -*- coding: utf-8 -*-
"""
财经日报（A股/港股）-> 企业微信/飞书，作为 AI 日报之后的「第二条」推送。

与 ai_daily_push.py 同仓库、同一次 GitHub Actions 运行：
  - AI 日报：推送图文卡片 -> ai_daily_dashboard.html（Pages 的 index.html）
  - 财经日报：推送 markdown（含总结/分析/策略）-> finance_dashboard.html（Pages 的 finance.html）
两个网页各自独立 URL，互不混排。

流程：
  1. 抓取指数行情快照（腾讯行情接口，GBK）作为事实锚点，避免 LLM 编造点位。
  2. 多来源抓取财经快讯（中文 RSS + 英文 RSS），去重并过滤到「过去 24 小时」。
  3. 英文条目用 LLM 批量翻译成中文（标题+摘要一起翻译，保留上下文）。
  4. LLM 第一次调用：识别过去 24 小时突发事件 + 生成今日总结/宏观分析/板块分析。
  5. LLM 第二次调用：基于上一步结论 + 行情快照，给出 A股/港股方向性策略建议（含免责声明）。
  6. 生成 finance_dashboard.html，并把要点推送为一条 markdown 消息。

LLM 配置（支持自建 OpenAI 兼容网关）：
  OPENAI_API_KEY   必填，缺失时跳过 LLM，仍生成网页与推送（分析区块标注未生成）
  OPENAI_BASE_URL  可选，默认 https://api.openai.com/v1
  OPENAI_MODEL     可选，默认 gpt-4o-mini

运行：
  python finance_daily_push.py            # 生成网页 + 推送
  python finance_daily_push.py --no-push  # 只生成网页，不推送（调试）
"""
import json, os, re, sys, urllib.parse, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

from ai_daily_push import (
    CST_OFFSET,
    HERE,
    UA,
    fetch_rss,
    fmt_cst,
    http_post_json,
    safe_md_url,
    translate_text,
    truncate_bytes,
)
from trading_calendar import (
    get_trading_status,
    format_date_cn,
    is_trading_day,
    get_last_trading_day,
)
from news_classifier import (
    classify_news_region_batch,
    score_news_importance_batch,
    identify_breaking_news,
)

# Windows 下重定向 stdout 默认走 GBK，日志里的 emoji（⚠️）会抛 UnicodeEncodeError
# 把整个流程带崩——日志细节绝不该杀掉任务。这里统一把标准流切成 UTF-8 且遇到
# 无法编码的字符降级替换而不是抛异常。
for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    if _stream is not None and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

# ----------------------------- 指数行情 -----------------------------
# 腾讯行情接口：GBK 编码，字段以 ~ 分隔（1=名称 3=最新价 31=涨跌额 32=涨跌幅）。
QUOTE_API = "https://qt.gtimg.cn/q="
QUOTE_CODES = [
    ("sh000001", "上证指数"),
    ("sz399001", "深证成指"),
    ("sz399006", "创业板指"),
    ("hkHSI", "恒生指数"),
    ("hkHSTECH", "恒生科技指数"),
]


def fetch_quotes():
    """返回 [{name, price, change, pct}]。单个字段解析失败就跳过该指数，不影响其余。"""
    url = QUOTE_API + ",".join(code for code, _ in QUOTE_CODES)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as response:
        text = response.read().decode("gbk", errors="replace")
    fallback_names = dict(QUOTE_CODES)
    quotes = []
    for chunk in text.split(";"):
        chunk = chunk.strip()
        if "=" not in chunk:
            continue
        var, value = chunk.split("=", 1)
        code = var.strip().removeprefix("v_")
        parts = value.strip().strip('"').split("~")
        if len(parts) <= 32:
            continue
        try:
            price = float(parts[3])
            change = float(parts[31])
            pct = float(parts[32])
        except (TypeError, ValueError):
            continue
        quotes.append({
            "name": parts[1].strip() or fallback_names.get(code, code),
            "price": price,
            "change": change,
            "pct": pct,
        })
    return quotes

# ----------------------------- 财经来源 -----------------------------
# 均为本机实测可用的源。中文源来自 rsshub 公共镜像，英文源为官方直连。
# rsshub 镜像列表：主镜像失败时自动尝试备用镜像（故障转移）
RSSHUB_MIRRORS = [
    "https://rsshub.rssforever.com",
    "https://rsshub.liumingye.cn",
    "https://rsshub.ktachibana.party",
]

FINANCE_FEEDS_ZH = [
    ("格隆汇快讯", "/gelonghui/live"),
    ("同花顺快讯", "/10jqka/realtimenews"),
    ("金十数据", "/jin10/flash"),
    ("第一财经", "/yicai/brief"),
    ("财新网", "/caixin/article"),
]
# 注：WSJ 的 RSSMarketsMain 源已停更（实测最新条目停在 2025-01-27），会被 24 小时
# 窗口全部丢弃，纯属浪费一次网络请求，故不收录。改用实测有当日内容的 Seeking Alpha。
# MarketWatch 的 RSS 源（无论 topstories 还是 realtimeheadlines）内容质量不符合要求：
# topstories 包含大量个人理财、职场建议等非市场资讯；realtimeheadlines 返回的是几个月前的旧闻。
FINANCE_FEEDS_EN = [
    ("Seeking Alpha", "https://seekingalpha.com/market_currents.xml"),
    ("Bloomberg Markets", "https://feeds.bloomberg.com/markets/news.rss"),
    ("CNBC Finance", "https://www.cnbc.com/id/10000664/device/rss/rss.html"),
]

# 财经语境的专有名词：避免 Fed/Nasdaq/Powell 这类被逐字直译成无意义中文。
FINANCE_TERMS = [
    "Federal Reserve", "Fed", "FOMC", "ECB", "Powell", "Treasury",
    "Nasdaq", "Dow Jones", "S&P 500", "Nikkei", "Hang Seng",
    "Nvidia", "Tesla", "Apple", "Microsoft", "Amazon", "Alphabet", "Meta",
    "Goldman Sachs", "Morgan Stanley", "JPMorgan", "BlackRock",
    "OPEC", "Brent", "WTI", "Bitcoin", "ETF", "IPO", "GDP", "CPI", "PPI", "PMI",
]


def _published_dt(raw):
    """把 RSS 的 pubDate 解析成带时区的 datetime；解析失败返回 None（当作未知时间保留）。"""
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _fetch_rss_with_mirrors(source_name, path, limit=20):
    """中文源：尝试所有 rsshub 镜像直到成功；英文源：直接调用 fetch_rss。"""
    # 如果是完整 URL（英文源），直接抓取
    if path.startswith("http://") or path.startswith("https://"):
        return fetch_rss(source_name, path, limit=limit)

    # 中文源：path 是相对路径，遍历镜像列表
    last_exc = None
    for idx, mirror in enumerate(RSSHUB_MIRRORS):
        url = mirror + path
        try:
            items = fetch_rss(source_name, url, limit=limit)
            if idx > 0:
                # 只有在非首个镜像成功时才打印（说明发生了故障转移）
                print(f"     [!] {source_name} 主镜像失败，已从备用镜像 #{idx+1} 成功抓取")
            return items
        except Exception as exc:
            last_exc = exc
            continue  # 尝试下一个镜像

    # 所有镜像都失败
    raise last_exc or RuntimeError(f"{source_name} 所有镜像均失败")


def fetch_finance_items(hours=24, per_feed=20):
    """抓取全部来源，去重并只保留过去 hours 小时内的条目。按国内/国外分组返回。

    发布时间无法解析的条目一律保留：宁可多收一条，也不要因为源的时间格式古怪而漏掉。
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    collected_zh, collected_en = [], []
    seen, dropped_old = set(), 0

    for source_name, url in FINANCE_FEEDS_ZH + FINANCE_FEEDS_EN:
        is_en = (source_name, url) in FINANCE_FEEDS_EN
        try:
            items = _fetch_rss_with_mirrors(source_name, url, limit=per_feed)
        except Exception as exc:
            print(f"     来源跳过：{source_name}（{exc}）")
            continue
        kept = 0
        for item in items:
            title = (item.get("title") or "").strip()
            key = re.sub(r"\W+", "", title.lower())
            if not title or not key or key in seen:
                continue
            published = _published_dt(item.get("published"))
            if published is not None and published < cutoff:
                dropped_old += 1
                continue
            seen.add(key)
            entry = {
                "title": title,
                "summary": (item.get("summary") or "").strip(),
                "link": item.get("link") or "",
                "source": source_name,
                "isEnglish": is_en,
                "published": published.isoformat() if published else "",
            }
            if is_en:
                collected_en.append(entry)
            else:
                collected_zh.append(entry)
            kept += 1
        print(f"     {source_name}：抓取 {len(items)} 条，入库 {kept} 条")

    total = len(collected_zh) + len(collected_en)
    print(f"     超出 {hours} 小时窗口丢弃：{dropped_old} 条")
    print(f"     合计入库：国内 {len(collected_zh)} 条 + 国际 {len(collected_en)} 条 = {total} 条")
    return {"domestic": collected_zh, "international": collected_en}


def translate_finance_items(items):
    """用 LLM 批量翻译英文条目为中文，保留原文；失败则保留英文原文。

    使用 LLM 批量翻译（一次请求翻多条），避免外部翻译 API 的限流问题。
    LLM 不可用时直接保留英文原文，不再尝试其他翻译接口。

    items: 列表，直接修改每个 item 的 title/summary，并添加 originalTitle/originalSummary
    """
    # 1. 保存原文
    for item in items:
        item["originalTitle"] = item["title"]
        item["originalSummary"] = item["summary"]

    # 2. 找出英文条目
    en_indexes = [i for i, item in enumerate(items) if item.get("isEnglish")]
    if not en_indexes:
        print("     无英文条目，跳过翻译")
        return items

    print(f"     检测到 {len(en_indexes)} 条英文新闻，准备批量翻译 ...")

    # 3. LLM 批量翻译
    try:
        pairs = [(i, items[i]["title"], items[i]["summary"]) for i in en_indexes]
        mapping = translate_batch_llm(pairs)
        done = 0
        for i in en_indexes:
            got = mapping.get(i)
            if not got:
                continue
            title_zh, summary_zh = got
            if title_zh:
                items[i]["title"] = title_zh
            if summary_zh:
                items[i]["summary"] = summary_zh
            if title_zh:
                done += 1

        if done > 0:
            print(f"     LLM 翻译完成：{done}/{len(en_indexes)} 条")
        else:
            print(f"     LLM 翻译未产出结果，保留英文原文")

        return items

    except Exception as exc:
        print(f"     [!] LLM 翻译失败，保留英文原文：{exc}")
        return items


def pre_translate_articles(items_international):
    """
    预翻译国际要闻全文（使用 ArticleTranslator）

    优先级：
    1. 核心必读（importance_score >= 7）
    2. 最多翻译 5 篇

    过滤规则：
    - 排除快讯链接
    - 只翻译完整文章页面

    Args:
        items_international: 国际要闻列表

    Returns:
        无返回值，直接修改 items 添加 translated_content 字段
    """
    from article_translator import batch_translate_articles

    # 创建 LLM 调用包装器
    def llm_caller(system_prompt, user_prompt, model=None):
        """LLM 调用包装器，返回纯文本"""
        try:
            # 使用翻译模型
            translate_model = _llm_config()[2]
            result = call_llm(system_prompt, user_prompt, model=model or translate_model)
            return result
        except Exception as e:
            print(f"     [WARN] LLM 调用失败: {e}")
            return None

    # 批量翻译文章
    try:
        translated_count = batch_translate_articles(
            items_international,
            llm_caller=llm_caller,
            max_count=5
        )
        print(f"     全文翻译完成：{translated_count} 篇")
    except Exception as e:
        print(f"     [!] 全文翻译失败：{e}")


# ----------------------------- 板块分类 -----------------------------
# 国内板块规则
SECTION_RULES_DOMESTIC = [
    ("宏观与政策", ["央行", "货币政策", "降准", "降息", "国常会", "财政", "CPI", "PPI", "PMI",
                    "GDP", "社融", "信贷", "汇率", "人民币", "国债", "国务院", "发改委"]),
    ("A股与港股", ["A股", "沪指", "上证", "深证", "创业板", "科创板", "北向", "南向", "港股", "恒生",
                   "新股", "IPO", "证监会", "交易所", "ETF", "北交所"]),
    ("公司与行业", ["财报", "业绩", "营收", "净利", "并购", "收购", "重组", "增持", "减持", "回购",
                    "定增", "分红", "中标", "签约", "产能", "涨价", "减产"]),
]

# 国际板块规则
SECTION_RULES_INTERNATIONAL = [
    ("全球宏观", ["美联储", "Fed", "FOMC", "加息", "降息", "欧央行", "ECB", "关税", "GDP", "CPI", "PMI"]),
    ("海外市场", ["美股", "纳斯达克", "道指", "标普", "欧股", "日经", "Nasdaq", "Dow Jones", "S&P 500"]),
    ("大宗商品", ["原油", "黄金", "白银", "比特币", "Brent", "WTI", "Bitcoin"]),
    ("公司与行业", ["财报", "业绩", "营收", "净利", "并购", "收购", "Nvidia", "Tesla", "Apple", "Microsoft"]),
]

DEFAULT_SECTION = "其他财经资讯"


def classify_sections(items, rules):
    """按关键词把条目分到板块；命中多个取第一个规则，未命中进兜底板块。空板块不展示。"""
    buckets = {label: [] for label, _ in rules}
    buckets[DEFAULT_SECTION] = []
    for item in items:
        text = f"{item['title']} {item['summary']}"
        placed = False
        for label, keywords in rules:
            if any(kw.lower() in text.lower() for kw in keywords):
                buckets[label].append(item)
                placed = True
                break
        if not placed:
            buckets[DEFAULT_SECTION].append(item)
    return [{"label": label, "items": bucket} for label, bucket in buckets.items() if bucket]

# ----------------------------- LLM（OpenAI 兼容） -----------------------------
# 两类任务分开用模型：
#   翻译量大、要求低 -> deepseek-v4-flash（便宜快）
#   总结/分析/策略需要推理 -> gpt-5.6-sol（实测 deepseek-v4-flash 在 57 条的分析
#   prompt 上会 504 超时，273s 无响应；gpt 系列 26s 返回）
MODEL_TRANSLATE_DEFAULT = "deepseek-v4-flash"
MODEL_ANALYSIS_DEFAULT = "gpt-5.6-sol"


def _llm_config():
    cfg_path = os.path.join(HERE, "push_config.json")
    cfg = {}
    if os.path.exists(cfg_path):
        try:
            cfg = json.load(open(cfg_path, encoding="utf-8"))
        except Exception:
            cfg = {}
    api_key = (os.environ.get("OPENAI_API_KEY") or cfg.get("openai_api_key", "")).strip()
    base_url = (os.environ.get("OPENAI_BASE_URL") or cfg.get("openai_base_url", "")
                or "https://api.openai.com/v1").strip().rstrip("/")
    translate_model = (os.environ.get("OPENAI_MODEL_TRANSLATE")
                       or cfg.get("openai_model_translate", "") or MODEL_TRANSLATE_DEFAULT).strip()
    analysis_model = (os.environ.get("OPENAI_MODEL_ANALYSIS")
                      or cfg.get("openai_model_analysis", "") or MODEL_ANALYSIS_DEFAULT).strip()
    return api_key, base_url, translate_model, analysis_model


def call_llm_json(system_prompt, user_prompt, retries=2, model=None, timeout=180):
    """调用 OpenAI 兼容接口并解析 JSON 对象。失败抛异常，由调用方决定降级。"""
    api_key, base_url, translate_model, _analysis_model = _llm_config()
    if not api_key:
        raise RuntimeError("未配置 OPENAI_API_KEY")
    payload = {
        "model": model or translate_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    last_exc = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(
                f"{base_url}/chat/completions",
                data=data,
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "Authorization": f"Bearer {api_key}",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
            content = body["choices"][0]["message"]["content"]
            # 有些网关会把 JSON 包在 ```json fence 里，剥掉再解析。
            content = re.sub(r"^\s*```(?:json)?|```\s*$", "", content.strip())
            return json.loads(content)
        except Exception as exc:
            last_exc = exc
            if attempt < retries:
                continue
    raise last_exc


TRANSLATE_SYSTEM = (
    "你是专业的财经翻译。把用户给出的英文财经标题和摘要翻译成简体中文，"
    "保持财经术语准确，公司名、指数名、人名保留通用译名或原文（如 Fed 译作美联储、"
    "Nasdaq 译作纳斯达克、Powell 译作鲍威尔）。不要增删信息，不要加评论。"
    "严格按要求的 JSON 结构输出，不要输出多余文字。"
)


def translate_batch_llm(pairs, batch_size=10):
    """用 LLM 批量翻译英文条目：pairs 为 [(idx, title, summary)]。

    返回 {idx: (title_zh, summary_zh)}。批量翻译避免外部 API 的限流问题。
    单批失败只影响该批，其余批次照常。
    """
    result = {}
    total_batches = (len(pairs) + batch_size - 1) // batch_size

    for start in range(0, len(pairs), batch_size):
        batch = pairs[start:start + batch_size]
        batch_num = start // batch_size + 1

        listing = []
        for idx, title, summary in batch:
            listing.append(json.dumps(
                {"id": idx, "title": title, "summary": summary[:300]},
                ensure_ascii=False
            ))

        user_prompt = (
            "把下面每条英文财经资讯的 title 和 summary 翻译成简体中文。\n"
            "输入（每行一个 JSON 对象）：\n" + "\n".join(listing) + "\n\n"
            '输出 JSON：{"items":[{"id":原样返回的id,"title":"中文标题","summary":"中文摘要"}]}\n'
            "summary 为空则中文 summary 也返回空字符串。必须覆盖全部输入条目。"
        )

        try:
            data = call_llm_json(TRANSLATE_SYSTEM, user_prompt, retries=1)
            items_translated = data.get("items") or []

            for row in items_translated:
                rid = row.get("id")
                if isinstance(rid, str) and rid.isdigit():
                    rid = int(rid)
                if rid is None:
                    continue

                title_zh = (row.get("title") or "").strip()
                summary_zh = (row.get("summary") or "").strip()

                result[rid] = (title_zh, summary_zh)

            print(f"     批次 {batch_num}/{total_batches}：{len(items_translated)}/{len(batch)} 条翻译成功")

        except Exception as exc:
            print(f"     批次 {batch_num}/{total_batches} 失败（该批保留英文）：{exc!r}")

    return result


def _news_digest(items, limit=45, summary_chars=120):
    lines = []
    for i, item in enumerate(items[:limit], 1):
        summary = re.sub(r"\s+", " ", item["summary"])[:summary_chars]
        lines.append(f"{i}. [{item['source']}] {item['title']}" + (f" — {summary}" if summary else ""))
    return "\n".join(lines)


def _quotes_digest(quotes):
    if not quotes:
        return "（行情数据抓取失败，本次无可用点位）"
    return "\n".join(f"- {q['name']}：{q['price']}（{q['change']:+.2f}，{q['pct']:+.2f}%）" for q in quotes)


DISCLAIMER = "本内容由程序基于公开信息自动生成，不构成投资建议。"

ANALYSIS_SYSTEM = (
    "你是一名严谨的中文财经分析师。只依据用户提供的新闻与行情数据作答，"
    "不得编造未提供的数字、点位、涨跌幅或事件。所有输出必须是简体中文。"
    "严格输出 JSON 对象，不要输出多余文字。"
)


def generate_analysis(items, quotes, market_label="国内"):
    """一次调用同时产出：突发事件清单 + 今日总结 + 宏观分析 + 板块分析。

    market_label: "国内" 或 "国际"，用于指导 LLM 聚焦相应市场
    """
    user_prompt = f"""下面是过去 24 小时的{market_label}财经快讯，以及最新的指数行情快照。

【指数行情快照】（唯一可引用的数字来源）
{_quotes_digest(quotes)}

【{market_label}财经快讯】
{_news_digest(items)}

请仅基于上述{market_label}快讯内容输出 JSON，字段如下：
{{
  "emergencyEvents": [
    {{"title": "事件标题（15字内）", "desc": "50字内说明发生了什么", "impact": "30字内说明对市场可能的影响方向"}}
  ],
  "summary": "{market_label}市场总结，150-250字，概括过去24小时最值得关注的几条线索",
  "macro": "宏观与资金面分析，150-250字，涉及政策、利率、汇率、外部市场",
  "sector": "板块与行业分析，150-250字，指出受关注或受压的方向"
}}

emergencyEvents **只收录上述{market_label}快讯中真正的突发/异常事件**：地缘冲突升级、监管黑天鹅、重大公司事故、
系统性风险信号、超预期政策转向等。常规业绩公告、例行数据发布、常规研报观点不算突发事件。
最多 5 条；如果快讯中确实没有突发事件，返回空数组。不要添加快讯列表之外的事件。
引用数字时只能使用上面行情快照里的数字。"""
    analysis_model = _llm_config()[3]
    return call_llm_json(ANALYSIS_SYSTEM, user_prompt, model=analysis_model)


STRATEGY_SYSTEM = (
    "你是一名严谨的中文投资策略研究员。只依据用户提供的分析结论与行情数据作答，"
    "不得编造数字。禁止给出具体买卖点位、目标价、具体个股买入指令，"
    "只给方向性判断（如偏谨慎/偏积极、关注哪类板块、需要观察什么信号）。"
    "严格输出 JSON 对象，不要输出多余文字，全部使用简体中文。"
)


def generate_strategy(analysis, quotes, trading_status=None):
    """
    生成策略建议

    根据交易日状态生成不同内容：
    - 常规交易日：今日策略建议
    - 非交易日：休市提示
    - 节后首日：假期影响分析与策略
    """
    if trading_status is None:
        # 默认使用当前日期判断
        import datetime
        trading_status = get_trading_status(datetime.date.today(), market='A')

    market_status = trading_status['market_status']
    last_trading_day = trading_status['last_trading_day']
    is_post_holiday = trading_status['is_post_holiday']

    # 准备突发事件文本
    events = analysis.get("emergencyEvents") or []
    events_text = "\n".join(f"- {e.get('title','')}：{e.get('impact','')}" for e in events) or "（无突发事件）"

    # 根据市场状态生成不同的策略
    if market_status in ('weekend', 'holiday'):
        # 非交易日：显示休市提示
        return {
            "aShare": f"今日休市（{format_date_cn(last_trading_day)}收盘数据）。下一交易日请关注市场动向。",
            "hkShare": f"今日休市（{format_date_cn(last_trading_day)}收盘数据）。下一交易日请关注市场动向。",
            "risk": "休市期间请关注国际市场动态和突发事件。" + DISCLAIMER,
            "is_trading_day": False,
            "last_trading_day": format_date_cn(last_trading_day)
        }

    elif is_post_holiday:
        # 节后首日：生成假期影响分析与策略
        days_off = trading_status['days_since_last_trading']

        user_prompt = f"""【指数行情快照】（截至上一交易日 {format_date_cn(last_trading_day)}）
{_quotes_digest(quotes)}

【市场总结】（上一交易日数据）
{analysis.get('summary', '')}

【宏观与资金面分析】
{analysis.get('macro', '')}

【板块与行业分析】
{analysis.get('sector', '')}

【突发事件及影响】
{events_text}

注意：今日是节后首个交易日（连续休市 {days_off} 天，上一交易日为 {format_date_cn(last_trading_day)}）。

请基于以上内容输出今日策略建议的 JSON：
{{
  "holiday_summary": "假期期间要闻回顾（80-150字），总结休市期间的重要事件和市场变化",
  "aShare": "A股今日策略（150-250字），结合假期期间的外围市场变化和上一交易日情况，给出今日开盘预判、关注方向和操作建议",
  "hkShare": "港股今日策略（150-250字），结合假期期间情况给出今日方向性判断",
  "risk": "风险提示（60-120字），只讲需要警惕的风险点，特别是假期期间的外围风险"
}}"""

        analysis_model = _llm_config()[3]
        strategy = call_llm_json(STRATEGY_SYSTEM, user_prompt, model=analysis_model)

        # 确保免责声明
        risk = (strategy.get("risk") or "").strip()
        if DISCLAIMER not in risk:
            strategy["risk"] = (risk + " " if risk else "") + DISCLAIMER

        strategy["is_trading_day"] = True
        strategy["is_post_holiday"] = True
        strategy["last_trading_day"] = format_date_cn(last_trading_day)

        return strategy

    else:
        # 常规交易日：正常的策略建议
        user_prompt = f"""【指数行情快照】（截至上一交易日 {format_date_cn(last_trading_day)}）
{_quotes_digest(quotes)}

【市场总结】
{analysis.get('summary', '')}

【宏观与资金面分析】
{analysis.get('macro', '')}

【板块与行业分析】
{analysis.get('sector', '')}

【突发事件及影响】
{events_text}

请基于以上内容（均为上一交易日数据）输出今日策略建议的 JSON：
{{
  "aShare": "A股策略建议，120-200字，基于上一交易日盘面情况给出今日方向性判断+值得关注的板块方向+需要观察的信号",
  "hkShare": "港股策略建议，120-200字，基于上一交易日情况给出今日方向性判断",
  "risk": "风险提示，60-120字，只讲需要警惕的风险点，不要写免责声明（程序会自动附加）"
}}"""

        analysis_model = _llm_config()[3]
        strategy = call_llm_json(STRATEGY_SYSTEM, user_prompt, model=analysis_model)

        # 确保免责声明
        risk = (strategy.get("risk") or "").strip()
        if DISCLAIMER not in risk:
            strategy["risk"] = (risk + " " if risk else "") + DISCLAIMER

        strategy["is_trading_day"] = True
        strategy["is_post_holiday"] = False
        strategy["last_trading_day"] = format_date_cn(last_trading_day)

        return strategy
    return strategy


ANALYSIS_FALLBACK = {
    "emergencyEvents": [],
    "summary": "（本次未生成 AI 分析：LLM 未配置或调用失败，下方要闻列表仍为完整抓取结果。）",
    "macro": "",
    "sector": "",
}
STRATEGY_FALLBACK = {
    "aShare": "",
    "hkShare": "",
    "risk": "本次策略分析未生成。" + DISCLAIMER,
}

# ----------------------------- 数据整形 -----------------------------
def translate_page_url(original_url):
    """生成网页翻译链接。Google 翻译服务在某些网络环境下不稳定，禁用翻译链接。
    用户可以直接点击"阅读原文"，浏览器会自动提供翻译功能（Chrome/Edge 内置翻译）。"""
    # Google Translate 网页代理在某些地区访问慢或被限制，且 Chrome/Edge 浏览器
    # 自带的"翻译此页"功能体验更好，所以暂时禁用这个链接。
    return ""
    # 原实现（已禁用）：
    # if not original_url or not re.match(r"^https?://", original_url):
    #     return ""
    # return "https://translate.google.com/translate?sl=auto&tl=zh-CN&u=" + urllib.parse.quote(original_url, safe="")


def shape_finance(sections_domestic, sections_international, quotes, analysis_domestic, analysis_international, strategy, money_flow_data=None, window_hours=24):
    """整合国内和国际市场数据，返回完整数据结构。"""
    now_utc = datetime.now(timezone.utc)

    # 国内要闻整形
    shaped_domestic, gi = [], 0
    for section in sections_domestic:
        items = []
        for item in section["items"]:
            gi += 1
            title = item.get("title", "")
            summary = item.get("summary", "")
            link = item.get("link", "")
            items.append({
                "idx": gi,
                "title": title,
                "originalTitle": item.get("originalTitle", title),
                "summary": summary,
                "originalSummary": item.get("originalSummary", summary),
                "source": item.get("source", ""),
                "original": link,
                "translatedPage": "",  # 国内源无需翻译
            })
        shaped_domestic.append({"label": section["label"], "items": items})

    # 国际要闻整形
    shaped_international = []
    for section in sections_international:
        items = []
        for item in section["items"]:
            gi += 1
            is_translated = item.get("isEnglish") and item.get("originalTitle") != item["title"]
            title = item.get("title", "")
            summary = item.get("summary", "")
            link = item.get("link", "")
            items.append({
                "idx": gi,
                "title": title,
                "originalTitle": item.get("originalTitle", title),
                "summary": summary,
                "originalSummary": item.get("originalSummary", summary),
                "source": item.get("source", ""),
                "original": link,
                "translatedPage": translate_page_url(link) if is_translated else "",
            })
        shaped_international.append({"label": section["label"], "items": items})

    meta = {
        "date": (now_utc + CST_OFFSET).strftime("%Y-%m-%d"),
        "windowStart": (now_utc - timedelta(hours=window_hours)).isoformat(),
        "windowEnd": now_utc.isoformat(),
        "generatedAt": now_utc.isoformat(),
        "total": gi,
        "domesticCount": sum(len(s["items"]) for s in shaped_domestic),
        "internationalCount": sum(len(s["items"]) for s in shaped_international),
    }

    return {
        "meta": meta,
        "quotes": quotes,
        "moneyFlow": money_flow_data or {},
        "domestic": {
            "emergencyEvents": analysis_domestic.get("emergencyEvents") or [],
            "analysis": {
                "summary": analysis_domestic.get("summary", ""),
                "macro": analysis_domestic.get("macro", ""),
                "sector": analysis_domestic.get("sector", ""),
            },
            "sections": shaped_domestic,
        },
        "international": {
            "emergencyEvents": analysis_international.get("emergencyEvents") or [],
            "analysis": {
                "summary": analysis_international.get("summary", ""),
                "macro": analysis_international.get("macro", ""),
                "sector": analysis_international.get("sector", ""),
            },
            "sections": shaped_international,
        },
        "strategy": {
            "aShare": strategy.get("aShare", ""),
            "hkShare": strategy.get("hkShare", ""),
            "risk": strategy.get("risk", ""),
        },
    }



def build_finance_html(data):
    """生成财经日报 HTML，使用外部模板文件。"""
    # "</" 转义成 "<\/"：标题里若含字面 </script> 会提前闭合脚本标签导致注入。
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")

    # 读取模板文件
    template_path = os.path.join(HERE, "finance_dashboard_template.html")
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    return template.replace("__DATA_PLACEHOLDER__", payload)

# ----------------------------- Markdown 推送正文 -----------------------------
def build_finance_markdown(data, dashboard_url):
    meta = data["meta"]
    date_human = fmt_cst(meta["date"] + "T00:00:00+08:00", "%Y年%m月%d日 {wd}")
    lines = [f"# 💹 财经日报 · {date_human}"]

    quotes = data.get("quotes") or []
    if quotes:
        parts = [f"{q['name']} {q['price']}（{q['pct']:+.2f}%）" for q in quotes]
        lines.append("> " + " ｜ ".join(parts))

    # 策略建议（放在最前面，用户最关心）
    sg = data.get("strategy") or {}
    if sg.get("aShare") or sg.get("hkShare"):
        # 根据是否为节后首日显示不同标题和内容
        if sg.get("is_post_holiday"):
            lines.append("\n## 🎯 今日策略建议")
            # 节后首日：显示假期综述
            if sg.get("holiday_summary"):
                lines.append(f"\n**假期期间要闻回顾**\n> {sg['holiday_summary']}")
            if sg.get("aShare"):
                lines.append(f"\n**A 股**：{sg['aShare']}")
            if sg.get("hkShare"):
                lines.append(f"\n**港股**：{sg['hkShare']}")
        elif sg.get("is_trading_day") == False:
            # 非交易日：休市提示
            lines.append("\n## 🎯 市场状态")
            lines.append(f"> 今日休市（数据截至{sg.get('last_trading_day', '上一交易日')}）")
        else:
            # 常规交易日
            lines.append("\n## 🎯 今日策略建议")
            if sg.get("aShare"):
                lines.append(f"> **A 股**：{sg['aShare']}")
            if sg.get("hkShare"):
                lines.append(f"> **港股**：{sg['hkShare']}")

    # 国内要闻
    domestic = data.get("domestic") or {}
    if domestic.get("sections"):
        lines.append(f"\n## 🇨🇳 国内要闻（{meta.get('domesticCount', 0)} 条）")

        events_dom = domestic.get("emergencyEvents") or []
        if events_dom:
            lines.append("\n**🚨 突发事件**")
            for i, e in enumerate(events_dom, 1):
                lines.append(f"> {i}. **{e.get('title','')}** {e.get('desc','')}")

        an_dom = domestic.get("analysis") or {}
        if an_dom.get("summary"):
            lines.append(f"\n**市场总结**\n> {an_dom['summary']}")

    # 国际要闻
    international = data.get("international") or {}
    if international.get("sections"):
        lines.append(f"\n## 🌍 国际要闻（{meta.get('internationalCount', 0)} 条）")

        events_intl = international.get("emergencyEvents") or []
        if events_intl:
            lines.append("\n**🚨 突发事件**")
            for i, e in enumerate(events_intl, 1):
                lines.append(f"> {i}. **{e.get('title','')}** {e.get('desc','')}")

        an_intl = international.get("analysis") or {}
        if an_intl.get("summary"):
            lines.append(f"\n**市场总结**\n> {an_intl['summary']}")

    body = "\n".join(lines)

    # 尾部是「必须保留」的部分：免责声明属于投资类内容的合规要求，网页链接是这条
    # 推送的核心入口。整篇 markdown 常超过企业微信 4096 字节上限，若直接从尾部
    # 截断会把这两样一起截掉（实测 4563 字节时两者全丢），所以分开处理。
    tail_lines = []
    if sg.get("risk"):
        tail_lines.append(f"\n> _{sg['risk']}_")
    tail_lines.append(f"\n> 共收录 **国内 {meta.get('domesticCount', 0)}** 条 + **国际 {meta.get('internationalCount', 0)}** 条")
    if dashboard_url:
        tail_lines.append(f"\n[💹 查看财经日报完整网页]({safe_md_url(dashboard_url)})")
    return body, "\n".join(tail_lines)


def compose_markdown(body, tail, max_bytes):
    """把正文压缩到 max_bytes 以内，但完整保留 tail（免责声明 + 网页链接）。"""
    tail_bytes = len(("\n" + tail).encode("utf-8"))
    budget = max_bytes - tail_bytes
    if budget <= 0:
        # 极端情况：尾部本身就超预算，宁可只发尾部，也要保住免责声明和链接。
        return tail
    return truncate_bytes(body, budget) + "\n" + tail


def push_wecom_news_card(webhook, dashboard_url):
    """企业微信群机器人：图文卡片（news 类型），点击打开财经日报网页。"""
    news = {
        "msgtype": "news",
        "news": {
            "articles": [{
                "title": "💹 查看完整财经日报（网页版）",
                "description": "财经日报 · 股指 · 突发事件 · 市场分析 · 策略建议 · 点击打开",
                "url": dashboard_url,
                "picurl": "https://picsum.photos/id/1067/600/400",  # 财经主题配图
            }]
        },
    }
    return http_post_json(webhook, news)


def push_markdown(webhook, body, tail):
    """企业微信群机器人 markdown 消息（上限 4096 字节，留余量到 3900）。"""
    content = compose_markdown(body, tail, 3900)
    return http_post_json(webhook, {"msgtype": "markdown", "markdown": {"content": content}})


def push_feishu_markdown(webhook, title, body, tail, dashboard_url=None):
    elements = [{"tag": "div", "text": {"tag": "markdown", "content": compose_markdown(body, tail, 3800)}}]
    if dashboard_url:
        elements.append({
            "tag": "action",
            "actions": [{
                "tag": "button",
                "text": {"tag": "plain_text", "content": "💹 查看完整网页"},
                "type": "primary",
                "url": dashboard_url,
            }],
        })
    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {"template": "orange", "title": {"tag": "plain_text", "content": title}},
            "elements": elements,
        },
    }
    return http_post_json(webhook, payload)

# ----------------------------- 主流程 -----------------------------
def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-push", action="store_true")
    ap.add_argument("--hours", type=int, default=24, help="收录窗口小时数，默认 24")
    ap.add_argument("--dashboard-url", default=None)
    args = ap.parse_args()

    cfg_path = os.path.join(HERE, "push_config.json")
    cfg = {}
    if os.path.exists(cfg_path):
        cfg = json.load(open(cfg_path, encoding="utf-8"))
    dashboard_url = (args.dashboard_url
                     or os.environ.get("FINANCE_DASHBOARD_URL")
                     or cfg.get("finance_dashboard_url", "")).strip()

    print("[1/6] 抓取指数行情 ...")
    try:
        quotes = fetch_quotes()
        for q in quotes:
            print(f"     {q['name']}：{q['price']}（{q['pct']:+.2f}%）")
    except Exception as exc:
        quotes = []
        print(f"     [!] 行情抓取失败，继续执行：{exc!r}")

    print("[1.5/6] 抓取资金流向数据 ...")
    money_flow_data = None
    try:
        from scrapers.money_flow_scraper import MoneyFlowScraper
        scraper = MoneyFlowScraper()

        north_flow = scraper.fetch_north_flow()
        sector_flow = scraper.fetch_sector_flow(top_n=5)
        stock_flow = scraper.fetch_stock_flow(top_n=10)

        money_flow_data = {
            "north_flow": north_flow,
            "sector_flow": sector_flow,
            "stock_flow": stock_flow
        }

        print(f"     北向资金合计：{north_flow.get('total_flow', 0):+.2f} 亿元")
        if sector_flow and sector_flow.get('top_inflow'):
            print(f"     行业流入 Top 1：{sector_flow['top_inflow'][0].get('name', 'N/A')}")
        if stock_flow and stock_flow.get('top_inflow'):
            print(f"     个股流入 Top 1：{stock_flow['top_inflow'][0].get('name', 'N/A')}")
    except Exception as exc:
        print(f"     [!] 资金流向抓取失败，继续执行：{exc!r}")

    print(f"[2/5] 抓取财经快讯（过去 {args.hours} 小时）...")
    items_grouped = fetch_finance_items(hours=args.hours)

    # 合并国内外新闻进行智能分类
    all_items = items_grouped["domestic"] + items_grouped["international"]

    if not all_items:
        print("     [!] 未抓到任何财经条目，终止本次财经日报（不影响 AI 日报）。")
        return

    print(f"     [2.1] LLM 智能分类（区域+重要性）...")
    try:
        # 包装 call_llm_json，使其返回字符串供 news_classifier 使用
        def llm_wrapper(system_prompt, user_prompt, model=None):
            result = call_llm_json(system_prompt, user_prompt, model=model)
            # call_llm_json 返回 dict，转为 JSON 字符串
            return json.dumps(result, ensure_ascii=False)

        # 区域重新分类（解决格隆汇等来源的分类问题）
        try:
            regions = classify_news_region_batch(all_items, llm_wrapper)
        except Exception as e:
            print(f"     [!] 区域分类失败，使用原始分类：{e}")
            regions = []

        # 重要性评分
        try:
            scores = score_news_importance_batch(all_items, llm_wrapper)
        except Exception as e:
            print(f"     [!] 重要性评分失败，使用默认分数：{e}")
            scores = []

        # 更新分类和评分
        if regions and len(regions) == len(all_items):
            for i, item in enumerate(all_items):
                item['region'] = regions[i]
                item['importance_score'] = scores[i] if i < len(scores) else 5

            # 重新分组
            items_domestic = [item for item in all_items if item.get('region') == 'domestic']
            items_international = [item for item in all_items if item.get('region') == 'international']

            print(f"     重新分类：国内 {len(items_domestic)} 条，国际 {len(items_international)} 条")

            # 按重要性排序
            items_domestic.sort(key=lambda x: x.get('importance_score', 5), reverse=True)
            items_international.sort(key=lambda x: x.get('importance_score', 5), reverse=True)
        else:
            # 分类失败，使用原始分组
            items_domestic = items_grouped["domestic"]
            items_international = items_grouped["international"]
            # 默认评分
            for item in items_domestic + items_international:
                item['importance_score'] = 5
            print(f"     使用原始分类：国内 {len(items_domestic)} 条，国际 {len(items_international)} 条")

    except Exception as exc:
        print(f"     [!] 智能分类模块异常：{exc}")
        items_domestic = items_grouped["domestic"]
        items_international = items_grouped["international"]
        # 默认评分
        for item in items_domestic + items_international:
            item['importance_score'] = 5

    # 翻译国际新闻
    if items_international:
        print("     [2.2] 翻译国际要闻标题摘要 ...")
        translate_finance_items(items_international)

    # 预翻译核心文章全文
    if items_international:
        print("     [2.3] 预翻译核心文章全文 ...")
        try:
            pre_translate_articles(items_international)
        except Exception as exc:
            print(f"     [!] 全文翻译失败，跳过：{exc}")

    # 识别突发事件
    print("     [2.4] 识别突发事件 ...")
    try:
        # 使用相同的 llm_wrapper
        def llm_wrapper(system_prompt, user_prompt, model=None):
            result = call_llm_json(system_prompt, user_prompt, model=model)
            return json.dumps(result, ensure_ascii=False)

        breaking_events_domestic = identify_breaking_news(items_domestic, llm_wrapper) if items_domestic else []
        breaking_events_international = identify_breaking_news(items_international, llm_wrapper) if items_international else []
        print(f"     突发事件：国内 {len(breaking_events_domestic)} 个，国际 {len(breaking_events_international)} 个")

        # 分析突发事件影响
        if breaking_events_domestic or breaking_events_international:
            print("     [2.5] 分析突发事件影响 ...")
            try:
                from event_impact_analyzer import EventImpactAnalyzer

                # 创建 LLM 调用包装器
                def impact_llm_caller(system_prompt, user_prompt, model=None):
                    return call_llm_json(system_prompt, user_prompt, model=model)

                analyzer = EventImpactAnalyzer(llm_caller=impact_llm_caller)

                # 分析国内突发事件
                if breaking_events_domestic:
                    breaking_events_domestic = analyzer.analyze_events_batch(breaking_events_domestic)

                # 分析国际突发事件
                if breaking_events_international:
                    breaking_events_international = analyzer.analyze_events_batch(breaking_events_international)

                print(f"     影响分析完成")
            except Exception as exc:
                print(f"     [!] 影响分析失败，跳过：{exc}")

    except Exception as exc:
        print(f"     [!] 突发事件识别失败：{exc}")
        breaking_events_domestic = []
        breaking_events_international = []

    # 分层：核心必读（8-10分）、重要要闻（5-7分）
    must_read_domestic = [item for item in items_domestic if item.get('importance_score', 0) >= 8]
    important_domestic = [item for item in items_domestic if 5 <= item.get('importance_score', 0) < 8]

    must_read_international = [item for item in items_international if item.get('importance_score', 0) >= 8]
    important_international = [item for item in items_international if 5 <= item.get('importance_score', 0) < 8]

    print(f"     国内：核心必读 {len(must_read_domestic)} 条，重要要闻 {len(important_domestic)} 条")
    print(f"     国际：核心必读 {len(must_read_international)} 条，重要要闻 {len(important_international)} 条")

    # 分板块
    sections_domestic = classify_sections(items_domestic, SECTION_RULES_DOMESTIC) if items_domestic else []
    sections_international = classify_sections(items_international, SECTION_RULES_INTERNATIONAL) if items_international else []
    print(f"     国内板块：{[(s['label'], len(s['items'])) for s in sections_domestic]}")
    print(f"     国际板块：{[(s['label'], len(s['items'])) for s in sections_international]}")

    print("[3/5] LLM 生成市场分析（国内 + 国际）...")
    # 国内市场分析
    analysis_domestic_ok = False
    if items_domestic:
        try:
            analysis_domestic = generate_analysis(items_domestic, quotes, market_label="国内")
            analysis_domestic_ok = bool(analysis_domestic.get("summary"))
            print(f"     国内：突发事件 {len(analysis_domestic.get('emergencyEvents') or [])} 条，总结 {len(analysis_domestic.get('summary',''))} 字")
        except Exception as exc:
            analysis_domestic = dict(ANALYSIS_FALLBACK)
            print(f"     [!] 国内分析生成失败：{exc!r}")
    else:
        analysis_domestic = dict(ANALYSIS_FALLBACK)
        print("     跳过国内分析（无国内新闻）")

    # 国际市场分析
    analysis_international_ok = False
    if items_international:
        try:
            analysis_international = generate_analysis(items_international, quotes, market_label="国际")
            analysis_international_ok = bool(analysis_international.get("summary"))
            print(f"     国际：突发事件 {len(analysis_international.get('emergencyEvents') or [])} 条，总结 {len(analysis_international.get('summary',''))} 字")
        except Exception as exc:
            analysis_international = dict(ANALYSIS_FALLBACK)
            print(f"     [!] 国际分析生成失败：{exc!r}")
    else:
        analysis_international = dict(ANALYSIS_FALLBACK)
        print("     跳过国际分析（无国际新闻）")

    print("[4/5] LLM 生成 A股/港股策略建议 ...")

    # 获取交易日状态
    import datetime
    today = datetime.date.today()
    trading_status = get_trading_status(today, market='A')

    print(f"     交易日状态：{trading_status['market_status']}")
    print(f"     上一交易日：{format_date_cn(trading_status['last_trading_day'])}")
    if trading_status['is_post_holiday']:
        print(f"     节后首日：连续休市 {trading_status['days_since_last_trading']} 天")

    # 策略需要综合国内外分析
    if analysis_domestic_ok or analysis_international_ok:
        try:
            # 合并两个市场的分析结论作为策略生成的输入
            combined_analysis = {
                "summary": (analysis_domestic.get("summary", "") + "\n\n" + analysis_international.get("summary", "")).strip(),
                "macro": (analysis_domestic.get("macro", "") + "\n\n" + analysis_international.get("macro", "")).strip(),
                "sector": (analysis_domestic.get("sector", "") + "\n\n" + analysis_international.get("sector", "")).strip(),
                "emergencyEvents": (analysis_domestic.get("emergencyEvents") or []) + (analysis_international.get("emergencyEvents") or []),
            }
            strategy = generate_strategy(combined_analysis, quotes, trading_status)
            print(f"     A股 {len(strategy.get('aShare',''))} 字，港股 {len(strategy.get('hkShare',''))} 字")
        except Exception as exc:
            strategy = dict(STRATEGY_FALLBACK)
            print(f"     [!] 策略生成失败，使用占位文案：{exc!r}")
    else:
        strategy = dict(STRATEGY_FALLBACK)
        print("     跳过：上一步分析未生成")

    data = shape_finance(sections_domestic, sections_international, quotes,
                        analysis_domestic, analysis_international, strategy,
                        money_flow_data=money_flow_data, window_hours=args.hours)

    out_html = os.path.join(HERE, "finance_dashboard.html")
    open(out_html, "w", encoding="utf-8").write(build_finance_html(data))
    print(f"     已写入 {out_html}")

    body, tail = build_finance_markdown(data, dashboard_url)
    preview = compose_markdown(body, tail, 3900)
    print(f"     Markdown 正文 {len(body.encode('utf-8'))} 字节 + 保留尾部 {len(tail.encode('utf-8'))} 字节"
          f" -> 实际发送 {len(preview.encode('utf-8'))} 字节")

    if args.no_push:
        print("[5/5] --no-push：跳过推送。")
        print("—— 图文卡片模式预览 ——")
        if dashboard_url:
            print(f"标题: 💹 查看完整财经日报（网页版）")
            print(f"描述: 财经日报 · 股指 · 突发事件 · 市场分析 · 策略建议 · 点击打开")
            print(f"链接: {dashboard_url}")
        else:
            print("（未配置 dashboard_url，无法发送图文卡片）")
        return

    webhook = (os.environ.get("WECOM_WEBHOOK") or cfg.get("wecom_webhook", "")).strip()
    feishu_webhook = (os.environ.get("FEISHU_WEBHOOK") or cfg.get("feishu_webhook", "")).strip()

    if webhook:
        print("[5/5] 推送财经日报到企业微信群机器人 ...")
        if dashboard_url:
            print("     使用图文卡片模式（news）")
            try:
                resp = push_wecom_news_card(webhook, dashboard_url)
                print("     企业微信返回：", resp)
                if isinstance(resp, dict) and resp.get("errcode", 0) != 0:
                    print("     [!] 推送失败：", resp)
            except Exception as exc:
                print("     [!] 企业微信推送异常：", repr(exc))
        else:
            print("     无 dashboard_url，降级为 markdown 模式")
            try:
                resp = push_markdown(webhook, body, tail)
                print("     企业微信返回：", resp)
                if isinstance(resp, dict) and resp.get("errcode", 0) != 0:
                    print("     [!] 推送失败：", resp)
            except Exception as exc:
                print("     [!] 企业微信推送异常：", repr(exc))
        return

    if feishu_webhook:
        print("[5/5] 推送财经日报到飞书群机器人 ...")
        title = f"财经日报 · {fmt_cst(data['meta']['date'] + 'T00:00:00+08:00', '%m月%d日 {wd}')}"
        try:
            resp = push_feishu_markdown(feishu_webhook, title, body, tail, dashboard_url)
            print("     飞书返回：", resp)
        except Exception as exc:
            print("     [!] 飞书推送异常：", repr(exc))
        return

    print("[5/5] 未配置推送渠道（WECOM_WEBHOOK / FEISHU_WEBHOOK），仅生成网页。")

    # 微信公众号发布（独立于推送渠道）
    wechat_cfg = cfg.get("wechat_official", {}) or {}
    wechat_enabled = wechat_cfg.get("enabled", False)
    wechat_appid = (os.environ.get("WECHAT_APPID") or wechat_cfg.get("appid", "")).strip()
    wechat_appsecret = (os.environ.get("WECHAT_APPSECRET") or wechat_cfg.get("appsecret", "")).strip()

    if wechat_enabled and wechat_appid and wechat_appsecret:
        print("\n[额外] 发布到微信公众号...")
        try:
            from wechat_official import publish_to_wechat
            from wechat_content_formatter import format_finance_daily_for_wechat
            from cover_generator import get_or_create_cover, create_default_cover

            # 格式化内容
            article_title, article_content, article_digest = format_finance_daily_for_wechat(data)

            # 获取或生成封面图
            date_str = data['meta']['date']
            cover_path = get_or_create_cover(date_str, cover_type="finance")

            # 如果封面生成失败，使用默认封面
            if not cover_path or not os.path.exists(cover_path):
                print("     使用默认封面...")
                cover_path = create_default_cover(cover_type="finance")

            if cover_path and os.path.exists(cover_path):
                # 发布到公众号
                publish_id = publish_to_wechat(
                    appid=wechat_appid,
                    appsecret=wechat_appsecret,
                    title=article_title,
                    content=article_content,
                    author="AI Daily Push",
                    digest=article_digest,
                    content_source_url=dashboard_url,
                    thumb_image_path=cover_path
                )

                if publish_id:
                    print(f"     ✓ 公众号发布成功！publish_id: {publish_id}")
                else:
                    print("     [!] 公众号发布失败")
            else:
                print("     [!] 封面图不可用，跳过公众号发布")

        except ImportError as e:
            print(f"     [!] 缺少微信公众号发布模块：{e!r}")
        except Exception as e:
            print(f"     [!] 公众号发布异常：{e!r}")
    elif wechat_enabled:
        print("\n[额外] 微信公众号已启用但缺少 appid/appsecret，跳过发布")


if __name__ == "__main__":
    main()

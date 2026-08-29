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
  3. 英文条目翻译成中文（复用 ai_daily_push 的 MyMemory + 专有名词占位保护）。
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
    "https://rsshub.app",
]

FINANCE_FEEDS_ZH = [
    ("格隆汇快讯", "/gelonghui/live"),
    ("同花顺快讯", "/10jqka/realtimenews"),
    ("金十数据", "/jin10/flash"),
]
# 注：WSJ 的 RSSMarketsMain 源已停更（实测最新条目停在 2025-01-27），会被 24 小时
# 窗口全部丢弃，纯属浪费一次网络请求，故不收录。改用实测有当日内容的 Seeking Alpha。
FINANCE_FEEDS_EN = [
    ("Seeking Alpha", "https://seekingalpha.com/market_currents.xml"),
    ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
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
    for mirror in RSSHUB_MIRRORS:
        url = mirror + path
        try:
            return fetch_rss(source_name, url, limit=limit)
        except Exception as exc:
            last_exc = exc
            continue  # 尝试下一个镜像

    # 所有镜像都失败
    raise last_exc or RuntimeError(f"{source_name} 所有镜像均失败")


def fetch_finance_items(hours=24, per_feed=20):
    """抓取全部来源，去重并只保留过去 hours 小时内的条目。

    发布时间无法解析的条目一律保留：宁可多收一条，也不要因为源的时间格式古怪而漏掉。
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    collected, seen, dropped_old = [], set(), 0
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
            collected.append({
                "title": title,
                "summary": (item.get("summary") or "").strip(),
                "link": item.get("link") or "",
                "source": source_name,
                "isEnglish": is_en,
                "published": published.isoformat() if published else "",
            })
            kept += 1
        print(f"     {source_name}：抓取 {len(items)} 条，入库 {kept} 条")
    print(f"     超出 {hours} 小时窗口丢弃：{dropped_old} 条；合计入库 {len(collected)} 条")
    return collected


def translate_finance_items(items, give_up_after=4):
    """英文条目译为中文，保留原文；失败则回退英文原文，不中断整体流程。

    优先走 LLM 批量翻译（一次请求翻多条）：MyMemory 是按 IP 限流的免费接口，
    逐条调用几十条必然被打成 429，且每次失败要重试到超时（实测单条约 17s）。
    LLM 不可用（未配置 key 等）时退回 MyMemory 逐条翻译，并保留熔断：
    连续 give_up_after 条失败就放弃剩余翻译，避免把 CI 拖死。
    """
    for item in items:
        item["originalTitle"] = item["title"]
        item["originalSummary"] = item["summary"]

    en_indexes = [i for i, item in enumerate(items) if item.get("isEnglish")]
    if not en_indexes:
        print("     无英文条目，跳过翻译")
        return items

    # ---- 首选：LLM 批量翻译 ----
    api_key = _llm_config()[0]
    if api_key:
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
        print(f"     LLM 翻译完成：{done}/{len(en_indexes)} 条（未译的保留英文原文）")
        if done:
            return items
        print("     LLM 翻译未产出结果，回退 MyMemory 逐条翻译")

    # ---- 回退：MyMemory 逐条 + 熔断 ----
    translated, failed, consecutive_fail = 0, 0, 0
    gave_up = False
    for i in en_indexes:
        if gave_up:
            break
        item = items[i]
        ok = True
        try:
            item["title"] = translate_text(item["originalTitle"], terms=FINANCE_TERMS)
        except Exception as exc:
            ok = False
            print(f"     标题翻译失败，保留英文：{exc}")
        try:
            if item["originalSummary"]:
                item["summary"] = translate_text(item["originalSummary"], terms=FINANCE_TERMS)
        except Exception as exc:
            ok = False
            print(f"     摘要翻译失败，保留英文：{exc}")
        if ok:
            translated += 1
            consecutive_fail = 0
        else:
            failed += 1
            consecutive_fail += 1
            if consecutive_fail >= give_up_after:
                gave_up = True
                print(f"     [!] 连续 {consecutive_fail} 条翻译失败（疑似接口限流），"
                      f"放弃剩余翻译，全部保留英文原文。")
    print(f"     MyMemory 翻译完成：{translated} 条，失败：{failed} 条" + ("（已提前放弃）" if gave_up else ""))
    return items

# ----------------------------- 板块分类 -----------------------------
SECTION_RULES = [
    ("宏观与政策", ["央行", "货币政策", "降准", "降息", "加息", "国常会", "财政", "CPI", "PPI", "PMI",
                    "GDP", "社融", "信贷", "汇率", "人民币", "国债", "美联储", "Fed", "FOMC", "关税"]),
    ("A股与港股", ["A股", "沪指", "上证", "深证", "创业板", "科创板", "北向", "南向", "港股", "恒生",
                   "新股", "IPO", "证监会", "交易所", "ETF", "北交所"]),
    ("全球市场", ["美股", "纳斯达克", "道指", "标普", "欧股", "日经", "原油", "黄金", "白银", "比特币",
                  "美元", "欧元", "Nasdaq", "Dow Jones", "S&P 500", "Brent", "WTI", "Bitcoin"]),
    ("公司与行业", ["财报", "业绩", "营收", "净利", "并购", "收购", "重组", "增持", "减持", "回购",
                    "定增", "分红", "中标", "签约", "产能", "涨价", "减产"]),
]
DEFAULT_SECTION = "其他财经资讯"


def classify_sections(items):
    """按关键词把条目分到板块；命中多个取第一个规则，未命中进兜底板块。空板块不展示。"""
    buckets = {label: [] for label, _ in SECTION_RULES}
    buckets[DEFAULT_SECTION] = []
    for item in items:
        text = f"{item['title']} {item['summary']}"
        placed = False
        for label, keywords in SECTION_RULES:
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


def translate_batch_llm(pairs, batch_size=12):
    """用 LLM 批量翻译英文条目：pairs 为 [(idx, title, summary)]。

    返回 {idx: (title_zh, summary_zh)}。相比逐条调 MyMemory（每条 2 次请求、
    且会被按 IP 限流打成 429），这里一次请求翻多条，几十条只需几次调用。
    单批失败只影响该批，其余批次照常。
    """
    result = {}
    for start in range(0, len(pairs), batch_size):
        batch = pairs[start:start + batch_size]
        listing = []
        for idx, title, summary in batch:
            listing.append(json.dumps({"id": idx, "title": title, "summary": summary[:300]}, ensure_ascii=False))
        user_prompt = (
            "把下面每条英文财经资讯的 title 和 summary 翻译成简体中文。\n"
            "输入（每行一个 JSON 对象）：\n" + "\n".join(listing) + "\n\n"
            '输出 JSON：{"items":[{"id":原样返回的id,"title":"中文标题","summary":"中文摘要"}]}\n'
            "summary 为空则中文 summary 也返回空字符串。必须覆盖全部输入条目。"
        )
        try:
            data = call_llm_json(TRANSLATE_SYSTEM, user_prompt, retries=1)
            for row in data.get("items") or []:
                rid = row.get("id")
                if isinstance(rid, str) and rid.isdigit():
                    rid = int(rid)
                if rid is None:
                    continue
                result[rid] = ((row.get("title") or "").strip(), (row.get("summary") or "").strip())
            print(f"     LLM 翻译批次 {start // batch_size + 1}：{len(batch)} 条送译")
        except Exception as exc:
            print(f"     LLM 翻译批次 {start // batch_size + 1} 失败（该批保留英文）：{exc!r}")
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


def generate_analysis(items, quotes):
    """一次调用同时产出：突发事件清单 + 今日总结 + 宏观分析 + 板块分析。"""
    user_prompt = f"""下面是过去 24 小时的财经快讯，以及最新的指数行情快照。

【指数行情快照】（唯一可引用的数字来源）
{_quotes_digest(quotes)}

【财经快讯】
{_news_digest(items)}

请输出 JSON，字段如下：
{{
  "emergencyEvents": [
    {{"title": "事件标题（15字内）", "desc": "50字内说明发生了什么", "impact": "30字内说明对A股/港股可能的影响方向"}}
  ],
  "summary": "今日总结，150-250字，概括过去24小时最值得关注的几条线索",
  "macro": "宏观与资金面分析，150-250字，涉及政策、利率、汇率、外部市场",
  "sector": "板块与行业分析，150-250字，指出受关注或受压的方向"
}}

emergencyEvents 只收录真正的突发/异常事件：地缘冲突升级、监管黑天鹅、重大公司事故、
系统性风险信号、超预期政策转向等。常规业绩公告、例行数据发布、常规研报观点不算突发事件。
最多 5 条；如果确实没有突发事件，返回空数组。
引用数字时只能使用上面行情快照里的数字。"""
    analysis_model = _llm_config()[3]
    return call_llm_json(ANALYSIS_SYSTEM, user_prompt, model=analysis_model)


STRATEGY_SYSTEM = (
    "你是一名严谨的中文投资策略研究员。只依据用户提供的分析结论与行情数据作答，"
    "不得编造数字。禁止给出具体买卖点位、目标价、具体个股买入指令，"
    "只给方向性判断（如偏谨慎/偏积极、关注哪类板块、需要观察什么信号）。"
    "严格输出 JSON 对象，不要输出多余文字，全部使用简体中文。"
)


def generate_strategy(analysis, quotes):
    events = analysis.get("emergencyEvents") or []
    events_text = "\n".join(f"- {e.get('title','')}：{e.get('impact','')}" for e in events) or "（无突发事件）"
    user_prompt = f"""【指数行情快照】（唯一可引用的数字来源）
{_quotes_digest(quotes)}

【今日总结】
{analysis.get('summary', '')}

【宏观与资金面分析】
{analysis.get('macro', '')}

【板块与行业分析】
{analysis.get('sector', '')}

【突发事件及影响】
{events_text}

请基于以上内容输出 JSON：
{{
  "aShare": "今日A股策略建议，120-200字，方向性判断+值得关注的板块方向+需要观察的信号",
  "hkShare": "今日港股策略建议，120-200字，同样是方向性判断",
  "risk": "风险提示，60-120字，只讲需要警惕的风险点，不要写免责声明（程序会自动附加）"
}}"""
    analysis_model = _llm_config()[3]
    strategy = call_llm_json(STRATEGY_SYSTEM, user_prompt, model=analysis_model)
    # 免责声明由代码兜底拼接，不依赖模型：实测模型会把这句话漏字（"自动成"），
    # 而这是投资类内容必须准确出现的措辞，不能交给模型自由发挥。
    risk = (strategy.get("risk") or "").strip()
    if DISCLAIMER not in risk:
        strategy["risk"] = (risk + " " if risk else "") + DISCLAIMER
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
    if not original_url or not re.match(r"^https?://", original_url):
        return ""
    return "https://translate.google.com/translate?sl=auto&tl=zh-CN&u=" + urllib.parse.quote(original_url, safe="")


def shape_finance(sections, quotes, analysis, strategy, window_hours=24):
    now_utc = datetime.now(timezone.utc)
    shaped, gi = [], 0
    for section in sections:
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
        shaped.append({"label": section["label"], "items": items})
    meta = {
        "date": (now_utc + CST_OFFSET).strftime("%Y-%m-%d"),
        "windowStart": (now_utc - timedelta(hours=window_hours)).isoformat(),
        "windowEnd": now_utc.isoformat(),
        "generatedAt": now_utc.isoformat(),
        "total": gi,
    }
    return {
        "meta": meta,
        "quotes": quotes,
        "emergencyEvents": analysis.get("emergencyEvents") or [],
        "analysis": {
            "summary": analysis.get("summary", ""),
            "macro": analysis.get("macro", ""),
            "sector": analysis.get("sector", ""),
        },
        "strategy": {
            "aShare": strategy.get("aShare", ""),
            "hkShare": strategy.get("hkShare", ""),
            "risk": strategy.get("risk", ""),
        },
        "sections": shaped,
    }

# ----------------------------- HTML -----------------------------
HTML_TMPL = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>财经日报 · 晨报仪表盘</title>
<style>
  :root{--bg:#0e1014;--bg2:#151922;--card:#171c26;--card-hover:#1e2531;--border:#272f3d;--text:#e8ecf3;--muted:#9aa4b2;--accent:#f0b429;--accent2:#37e0b0;--up:#ff5b5b;--down:#3ddc84;--warn:#ff7a45;--chip:#222b39;--shadow:rgba(0,0,0,.45);}
  *{box-sizing:border-box;margin:0;padding:0}
  html{scroll-behavior:smooth}
  body{background:radial-gradient(1200px 600px at 80% -10%, #2a2213 0%, var(--bg) 55%) fixed;color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;line-height:1.6;-webkit-font-smoothing:antialiased}
  a{color:inherit;text-decoration:none}
  .wrap{max-width:1180px;margin:0 auto;padding:0 18px}
  .hero{padding:30px 0 16px}
  .kicker{display:inline-flex;align-items:center;gap:8px;font-size:13px;letter-spacing:.18em;color:var(--accent);border:1px solid var(--border);padding:5px 12px;border-radius:999px;background:var(--bg2)}
  .hero h1{font-size:clamp(24px,4vw,36px);font-weight:800;margin:12px 0 4px;letter-spacing:-.5px}
  .hero h1 .sub{color:var(--accent)}
  .hero .date{font-size:15px;color:var(--text);font-weight:600}
  .hero .window{font-size:13px;color:var(--muted);margin-top:2px}
  .quotes{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}
  .quote{display:inline-flex;align-items:baseline;gap:7px;background:var(--card);border:1px solid var(--border);border-radius:10px;padding:7px 13px}
  .quote .qn{font-size:12.5px;color:var(--muted)}
  .quote .qp{font-size:15px;font-weight:800}
  .quote .qc{font-size:12.5px;font-weight:700}
  .quote.up .qp,.quote.up .qc{color:var(--up)}
  .quote.down .qp,.quote.down .qc{color:var(--down)}
  .stats{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
  .stat{display:inline-flex;align-items:baseline;gap:5px;background:var(--card);border:1px solid var(--border);border-radius:999px;padding:5px 12px}
  .stat .num{font-size:14px;font-weight:800;color:var(--accent)}
  .stat .lbl{font-size:12px;color:var(--muted)}
  .stat.total .num{color:var(--accent2)}
  .block{margin:14px 0 0;background:var(--card);border:1px solid var(--border);border-radius:12px;padding:14px 16px}
  .block h2{font-size:14px;font-weight:800;color:var(--accent2);margin-bottom:8px;display:flex;align-items:center;gap:6px}
  .block p{font-size:13.5px;color:#c9d1dc;margin-bottom:8px}
  .block p:last-child{margin-bottom:0}
  .block .sub-h{font-size:12.5px;font-weight:800;color:var(--accent);margin:10px 0 3px}
  .block.emergency{background:linear-gradient(135deg,#33210f,#1d1710);border-color:var(--warn)}
  .block.emergency h2{color:var(--warn)}
  .block.emergency ol{list-style:none;counter-reset:ev}
  .block.emergency li{counter-increment:ev;display:flex;gap:8px;padding:5px 0;border-bottom:1px dashed var(--border)}
  .block.emergency li:last-child{border-bottom:none}
  .block.emergency li::before{content:counter(ev);flex:0 0 auto;width:18px;height:18px;border-radius:5px;background:var(--warn);color:#1a1109;font-size:11px;font-weight:800;display:flex;align-items:center;justify-content:center;margin-top:2px}
  .ev-t{font-size:13.5px;font-weight:700}
  .ev-d{font-size:12.5px;color:#c9d1dc}
  .ev-i{font-size:12px;color:var(--accent)}
  .block.strategy{background:linear-gradient(135deg,#12281f,#141a18);border-color:var(--accent2)}
  .risk{font-size:12px;color:#9aa4b2;border-top:1px solid var(--border);padding-top:8px;margin-top:8px}
  .nav{position:sticky;top:0;z-index:20;background:rgba(14,16,20,.82);backdrop-filter:blur(10px);border-bottom:1px solid var(--border);margin-top:14px}
  .nav .wrap{display:flex;gap:10px;overflow-x:auto;padding:12px 18px;scrollbar-width:thin}
  .nav a{flex:0 0 auto;font-size:13.5px;color:var(--muted);border:1px solid var(--border);background:var(--bg2);padding:7px 13px;border-radius:999px;white-space:nowrap;transition:.15s}
  .nav a:hover{color:var(--text);border-color:var(--accent)}
  .nav a b{color:var(--accent);font-weight:700;margin-left:6px}
  main{padding:28px 0 10px}
  .section{margin-bottom:38px;scroll-margin-top:64px}
  .section-head{display:flex;align-items:baseline;gap:12px;margin-bottom:16px;border-left:4px solid var(--accent);padding-left:12px}
  .section-head h2{font-size:21px;font-weight:750}
  .section-head .count{font-size:14px;color:var(--muted)}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(310px,1fr));gap:16px}
  .card{display:flex;flex-direction:column;background:var(--card);border:1px solid var(--border);border-radius:16px;padding:18px;transition:.18s}
  .card:hover{background:var(--card-hover);border-color:#4a4230;transform:translateY(-2px);box-shadow:0 10px 26px var(--shadow)}
  .card .top{display:flex;align-items:center;justify-content:space-between;margin-bottom:11px}
  .card .idx{display:inline-flex;align-items:center;justify-content:center;width:34px;height:34px;border-radius:10px;background:linear-gradient(135deg,var(--accent),#c98f10);color:#1a1109;font-weight:800;font-size:15px;flex:0 0 auto}
  .chip{font-size:12px;color:var(--muted);background:var(--chip);border:1px solid var(--border);padding:4px 10px;border-radius:999px;max-width:62%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .card h3{font-size:16.5px;font-weight:700;line-height:1.45;margin-bottom:9px}
  .card h3 a:hover{color:var(--accent)}
  .card .summary{font-size:14px;color:#c4ccd8;flex:1;margin-bottom:10px}
  .card .original-text{font-size:12.5px;color:var(--muted);border-top:1px solid var(--border);padding-top:10px;margin-bottom:14px}
  .card .foot{display:flex;align-items:center;justify-content:space-between;gap:10px}
  .src{font-size:12.5px;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .linkgroup{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}
  .orig{font-size:13px;font-weight:600;color:var(--accent);border:1px solid var(--border);padding:6px 12px;border-radius:10px;background:var(--bg2);white-space:nowrap;transition:.15s}
  .orig:hover{background:var(--accent);color:#1a1109;border-color:var(--accent)}
  footer{border-top:1px solid var(--border);margin-top:18px;padding:26px 0 50px;color:var(--muted);font-size:13.5px}
  .note{font-size:12.5px;color:#6f7a8a;margin-top:10px}
  @media (max-width:560px){.hero{padding:22px 0 12px}.grid{grid-template-columns:1fr}}
</style>
</head>
<body>
<header class="hero"><div class="wrap">
  <span class="kicker">● 财经日报 · 多来源聚合</span>
  <h1>财经日报 <span class="sub">晨报仪表盘</span></h1>
  <div class="date" id="heroDate">—</div>
  <div class="window" id="heroWindow">—</div>
  <div class="quotes" id="heroQuotes"></div>
  <div class="stats" id="heroStats"></div>
  <div class="block emergency" id="emergency" style="display:none">
    <h2>🚨 过去 24 小时突发事件</h2>
    <ol id="emergencyList"></ol>
  </div>
  <div class="block" id="summaryBlock" style="display:none">
    <h2>📝 今日总结</h2>
    <p id="summaryText"></p>
  </div>
  <div class="block" id="analysisBlock" style="display:none">
    <h2>📈 市场分析汇总</h2>
    <div id="analysisBody"></div>
  </div>
  <div class="block strategy" id="strategyBlock" style="display:none">
    <h2>🎯 今日策略建议</h2>
    <div id="strategyBody"></div>
  </div>
</div></header>
<nav class="nav"><div class="wrap" id="navLinks"></div></nav>
<main class="wrap" id="main"></main>
<footer><div class="wrap">
  <div id="footerMeta">—</div>
  <div class="note">本站仅作信息聚合与自动化分析展示，资讯版权归原作者所有；分析与策略由程序自动生成，不构成投资建议。</div>
</div></footer>
<script>
const DATA = __DATA__;
function fmtBeijing(iso, opts){try{const dt=new Date(iso);const o=Object.assign({timeZone:'Asia/Shanghai',hour12:false},opts||{});return new Intl.DateTimeFormat('zh-CN',o).format(dt);}catch(e){return iso;}}
function truncate(s,n){const arr=Array.from(s||'');if(arr.length<=n)return s||'';return arr.slice(0,n-1).join('')+'…';}
function esc(s){return (s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function safeUrl(u){try{const p=new URL(u,location.href).protocol;return (p==='http:'||p==='https:')?u:'#';}catch(e){return '#';}}
(function render(){
  const meta=DATA.meta, sections=DATA.sections||[];
  document.getElementById('heroDate').textContent=fmtBeijing(meta.date+'T00:00:00+08:00',{year:'numeric',month:'long',day:'numeric',weekday:'long'})+'（北京时间）';
  document.getElementById('heroWindow').textContent='收录窗口：'+fmtBeijing(meta.windowStart,{month:'long',day:'numeric',hour:'2-digit',minute:'2-digit'})+' — '+fmtBeijing(meta.windowEnd,{month:'long',day:'numeric',hour:'2-digit',minute:'2-digit'})+'（北京时间，过去 24 小时）';
  const quotes=DATA.quotes||[];
  document.getElementById('heroQuotes').innerHTML=quotes.map(q=>{
    const cls=q.pct>0?'up':(q.pct<0?'down':'');
    const sign=q.pct>0?'+':'';
    return '<span class="quote '+cls+'"><span class="qn">'+esc(q.name)+'</span><span class="qp">'+q.price+'</span><span class="qc">'+sign+q.pct.toFixed(2)+'%</span></span>';
  }).join('');
  let st='<div class="stat total"><div class="num">'+meta.total+'</div><div class="lbl">总条数</div></div>';
  sections.forEach(s=>{st+='<div class="stat"><div class="num">'+s.items.length+'</div><div class="lbl">'+esc(s.label)+'</div></div>';});
  document.getElementById('heroStats').innerHTML=st;
  const events=DATA.emergencyEvents||[];
  if(events.length){
    document.getElementById('emergency').style.display='';
    document.getElementById('emergencyList').innerHTML=events.map(e=>
      '<li><div><div class="ev-t">'+esc(e.title)+'</div><div class="ev-d">'+esc(e.desc)+'</div>'+
      (e.impact?'<div class="ev-i">影响：'+esc(e.impact)+'</div>':'')+'</div></li>').join('');
  }
  const an=DATA.analysis||{};
  if(an.summary){document.getElementById('summaryBlock').style.display='';document.getElementById('summaryText').textContent=an.summary;}
  let ab='';
  if(an.macro) ab+='<div class="sub-h">宏观与资金面</div><p>'+esc(an.macro)+'</p>';
  if(an.sector) ab+='<div class="sub-h">板块与行业</div><p>'+esc(an.sector)+'</p>';
  if(ab){document.getElementById('analysisBlock').style.display='';document.getElementById('analysisBody').innerHTML=ab;}
  const sg=DATA.strategy||{};
  let sb='';
  if(sg.aShare) sb+='<div class="sub-h">A 股</div><p>'+esc(sg.aShare)+'</p>';
  if(sg.hkShare) sb+='<div class="sub-h">港股</div><p>'+esc(sg.hkShare)+'</p>';
  if(sg.risk) sb+='<div class="risk">'+esc(sg.risk)+'</div>';
  if(sb){document.getElementById('strategyBlock').style.display='';document.getElementById('strategyBody').innerHTML=sb;}
  let nav='';sections.forEach((s,i)=>{nav+='<a href="#sec-'+i+'">'+esc(s.label)+'<b>'+s.items.length+'</b></a>';});
  document.getElementById('navLinks').innerHTML=nav;
  let main='';sections.forEach((s,i)=>{main+='<section class="section" id="sec-'+i+'"><div class="section-head"><h2>'+esc(s.label)+'</h2><span class="count">'+s.items.length+' 条</span></div><div class="grid">';
    s.items.forEach(it=>{const orig=safeUrl(it.original||'#');const tp=safeUrl(it.translatedPage||'');
      main+='<article class="card"><div class="top"><span class="idx">'+it.idx+'</span><span class="chip" title="'+esc(it.source)+'">'+esc(it.source)+'</span></div>';
      main+='<h3><a href="'+esc(orig)+'" target="_blank" rel="noopener noreferrer">'+esc(it.title)+'</a></h3>';
      main+='<p class="summary">'+esc(truncate(it.summary,120))+'</p>';
      if(it.originalTitle!==it.title||it.originalSummary!==it.summary) main+='<p class="original-text"><b>原文</b><br>'+esc(truncate(it.originalTitle,120))+'<br>'+esc(truncate(it.originalSummary,260))+'</p>';
      main+='<div class="foot"><span class="src">'+esc(it.source)+'</span><span class="linkgroup">'+(tp&&tp!=='#'?'<a class="orig" href="'+esc(tp)+'" target="_blank" rel="noopener noreferrer">翻译全文 ↗</a>':'')+'<a class="orig" href="'+esc(orig)+'" target="_blank" rel="noopener noreferrer">阅读原文 ↗</a></span></div></article>';});
    main+='</div></section>';});
  document.getElementById('main').innerHTML=main;
  document.getElementById('footerMeta').innerHTML='本期共 <b style="color:var(--accent2)">'+meta.total+'</b> 条 · 数据来源：格隆汇、同花顺、金十数据、Seeking Alpha、MarketWatch、CNBC Finance · 行情：腾讯财经';
})();
</script>
</body></html>"""


def build_finance_html(data):
    # "</" 转义成 "<\/"：标题里若含字面 </script> 会提前闭合脚本标签导致注入。
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return HTML_TMPL.replace("__DATA__", payload)

# ----------------------------- Markdown 推送正文 -----------------------------
def build_finance_markdown(data, dashboard_url):
    meta = data["meta"]
    date_human = fmt_cst(meta["date"] + "T00:00:00+08:00", "%Y年%m月%d日 {wd}")
    lines = [f"# 💹 财经日报 · {date_human}"]

    quotes = data.get("quotes") or []
    if quotes:
        parts = [f"{q['name']} {q['price']}（{q['pct']:+.2f}%）" for q in quotes]
        lines.append("> " + " ｜ ".join(parts))

    events = data.get("emergencyEvents") or []
    if events:
        lines.append("\n## 🚨 过去 24 小时突发事件")
        for i, e in enumerate(events, 1):
            lines.append(f"> **{i}. {e.get('title','')}**")
            if e.get("desc"):
                lines.append(f"> {e['desc']}")
            if e.get("impact"):
                lines.append(f"> 影响：{e['impact']}")

    an = data.get("analysis") or {}
    if an.get("summary"):
        lines.append("\n## 📝 今日总结")
        lines.append(f"> {an['summary']}")
    if an.get("macro") or an.get("sector"):
        lines.append("\n## 📈 市场分析汇总")
        if an.get("macro"):
            lines.append(f"> **宏观与资金面**：{an['macro']}")
        if an.get("sector"):
            lines.append(f"> **板块与行业**：{an['sector']}")

    sg = data.get("strategy") or {}
    if sg.get("aShare") or sg.get("hkShare"):
        lines.append("\n## 🎯 今日策略建议")
        if sg.get("aShare"):
            lines.append(f"> **A 股**：{sg['aShare']}")
        if sg.get("hkShare"):
            lines.append(f"> **港股**：{sg['hkShare']}")
    body = "\n".join(lines)

    # 尾部是「必须保留」的部分：免责声明属于投资类内容的合规要求，网页链接是这条
    # 推送的核心入口。整篇 markdown 常超过企业微信 4096 字节上限，若直接从尾部
    # 截断会把这两样一起截掉（实测 4563 字节时两者全丢），所以分开处理。
    tail_lines = []
    if sg.get("risk"):
        tail_lines.append(f"\n> _{sg['risk']}_")
    tail_lines.append(f"\n> 过去 24 小时共收录 **{meta['total']}** 条财经资讯")
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

    print("[1/5] 抓取指数行情 ...")
    try:
        quotes = fetch_quotes()
        for q in quotes:
            print(f"     {q['name']}：{q['price']}（{q['pct']:+.2f}%）")
    except Exception as exc:
        quotes = []
        print(f"     [!] 行情抓取失败，继续执行：{exc!r}")

    print(f"[2/5] 抓取财经快讯（过去 {args.hours} 小时）...")
    items = fetch_finance_items(hours=args.hours)
    if not items:
        print("     [!] 未抓到任何财经条目，终止本次财经日报（不影响 AI 日报）。")
        return
    translate_finance_items(items)
    sections = classify_sections(items)
    print(f"     板块：{[(s['label'], len(s['items'])) for s in sections]}")

    print("[3/5] LLM 生成突发事件 + 总结 + 市场分析 ...")
    analysis_ok = False
    try:
        analysis = generate_analysis(items, quotes)
        analysis_ok = bool(analysis.get("summary"))
        print(f"     突发事件 {len(analysis.get('emergencyEvents') or [])} 条，总结 {len(analysis.get('summary',''))} 字")
    except Exception as exc:
        analysis = dict(ANALYSIS_FALLBACK)
        print(f"     [!] 分析生成失败，使用占位文案：{exc!r}")

    print("[4/5] LLM 生成 A股/港股策略建议 ...")
    # 必须用显式的 analysis_ok 标志：兜底赋的是 dict(ANALYSIS_FALLBACK) 副本，
    # 用 `is not ANALYSIS_FALLBACK` 判断永远为真，会把占位文案当成真分析喂给策略模型。
    if analysis_ok:
        try:
            strategy = generate_strategy(analysis, quotes)
            print(f"     A股 {len(strategy.get('aShare',''))} 字，港股 {len(strategy.get('hkShare',''))} 字")
        except Exception as exc:
            strategy = dict(STRATEGY_FALLBACK)
            print(f"     [!] 策略生成失败，使用占位文案：{exc!r}")
    else:
        strategy = dict(STRATEGY_FALLBACK)
        print("     跳过：上一步分析未生成")

    data = shape_finance(sections, quotes, analysis, strategy, window_hours=args.hours)

    out_html = os.path.join(HERE, "finance_dashboard.html")
    open(out_html, "w", encoding="utf-8").write(build_finance_html(data))
    print(f"     已写入 {out_html}")

    body, tail = build_finance_markdown(data, dashboard_url)
    preview = compose_markdown(body, tail, 3900)
    print(f"     Markdown 正文 {len(body.encode('utf-8'))} 字节 + 保留尾部 {len(tail.encode('utf-8'))} 字节"
          f" -> 实际发送 {len(preview.encode('utf-8'))} 字节")

    if args.no_push:
        print("[5/5] --no-push：跳过推送。")
        print("—— Markdown 预览（实际发送内容）——")
        print(preview)
        return

    webhook = (os.environ.get("WECOM_WEBHOOK") or cfg.get("wecom_webhook", "")).strip()
    feishu_webhook = (os.environ.get("FEISHU_WEBHOOK") or cfg.get("feishu_webhook", "")).strip()

    if webhook:
        print("[5/5] 推送财经日报到企业微信群机器人 ...")
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


if __name__ == "__main__":
    main()

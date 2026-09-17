# -*- coding: utf-8 -*-
"""
AI 日报 -> pushplus(个人微信) 每日推送管线（单文件，可独立运行）

流程：
  1. 拉取 AI HOT 当日日报；若当日未生成则回退到最近一期（按官方 skill 规则）。
  2. 同步抓取多个 AI 资讯 RSS 来源，去重后合并到仪表盘。
  3. 采集市场数据（OpenRouter + Artificial Analysis）。
  4. 生成单文件 HTML 仪表盘（内联 CSS/JS，六版块，全局连续编号，≤60 字摘要，北京时间）。
  5. 渲染 Markdown 摘要（六版块要点 + 原文链接）。
  6. 推送 markdown 消息到 pushplus，再由 pushplus 转发到你的个人微信；
     若配置了 dashboard_url 则附上仪表盘链接。

配置：同目录 push_config.json
  {
    "pushplus_token": "你的PUSHPLUS_TOKEN",   # 微信扫码 pushplus.plus 获取
    "dashboard_url": ""          # 可选：已托管仪表盘的公网地址；留空则用 AI HOT 日报页作回退链接
  }
  也可通过环境变量覆盖（GitHub Actions 推荐用 Secrets）：
    PUSHPLUS_TOKEN、PUSHPLUS_API(默认 https://www.pushplus.plus/send)、DASHBOARD_URL

运行：
  python ai_daily_push.py            # 拉取+生成+推送
  python ai_daily_push.py --no-push  # 仅生成 HTML，不推送（调试用）
  python ai_daily_push.py --date 2026-08-01  # 指定日期（调试/补推）

注意：网络请求在受限环境下需放行外网（本机直跑即可）。
"""
import json, sys, os, re, html, time, threading, urllib.parse, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed


def _read_with_deadline(response, timeout):
    """限时读完响应体（总耗时上限）。

    urllib 的 timeout 只是 socket 空闲超时：网关排队/慢滴灌时每次 read
    都有数据，总耗时 30 分钟也触发不了（qwen3.8-flash 线上实测 30m27s）。
    另起线程读，主线程按 timeout join，超时关连接抛 TimeoutError，
    上层走已有 fallback（翻译保留原文/分析记未生成），不再无限等。
    """
    out, err = [], []

    def _read():
        try:
            out.append(response.read())
        except Exception as e:  # noqa: BLE001 - 透传给主线程
            err.append(e)

    t = threading.Thread(target=_read, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        try:
            response.close()
        except Exception:  # noqa: BLE001 - 关闭尽力而为
            pass
        raise TimeoutError(f"LLM 响应读取超过总限时 {timeout}s（疑似网关排队/慢滴灌）")
    if err:
        raise err[0]
    return out[0] if out else b""


_DEEPSEEK_MAX_CONCURRENCY = max(1, int(os.getenv("DEEPSEEK_MAX_CONCURRENCY", "2")))
_DEEPSEEK_SEMAPHORE = threading.BoundedSemaphore(_DEEPSEEK_MAX_CONCURRENCY)
# Keep the default job budget bounded: callers can opt into slower retries via env.
_LLM_MAX_RETRIES = max(0, int(os.getenv("LLM_MAX_RETRIES", "0")))
_LLM_TIMEOUT = max(1, int(os.getenv("LLM_TIMEOUT", "15")))
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

# 导入监控装饰器
try:
    from monitor_decorator import monitor_task
    MONITORING_AVAILABLE = True
except ImportError:
    # 如果监控模块不可用，创建一个空装饰器
    def monitor_task(name):
        def decorator(func):
            return func
        return decorator
    MONITORING_AVAILABLE = False

# 导入市场数据模块
try:
    from analyzers.market_data_aggregator import MarketDataAggregator, build_token_trend
    from analyzers.market_report_formatter import MarketReportFormatter
    MARKET_DATA_AVAILABLE = True
except ImportError as e:
    print(f"  [WARN] 市场数据模块导入失败：{e}")
    MARKET_DATA_AVAILABLE = False

BASE = "https://aihot.virxact.com/api/v1"
UA = "aihot-skill/1.2.1 (+https://aihot.virxact.com/aihot-skill/)"
# 中国标准时间 = UTC+8（无夏令时），无需 tzdata 依赖
CST_OFFSET = timedelta(hours=8)
HERE = __import__("os").path.dirname(__import__("os").path.abspath(__file__))

# Windows 下重定向 stdout 默认走 GBK，日志/预览里的 emoji（⭐ 等）会抛
# UnicodeEncodeError 把整个流程带崩——打印细节绝不该杀掉任务。统一把标准流切成
# UTF-8，且无法编码时降级替换而不是抛异常。
for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    if _stream is not None and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

# ----------------------------- 网络 -----------------------------
def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

def http_get_or_none(url):
    try:
        return http_get(url)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise

# ----------------------------- 拉取日报 -----------------------------
def fetch_daily(date_str):
    """先试当日；404 则回退到最近一期（按 skill 规则：只查一次 dailies?limit=7 取最近日期）。"""
    data = http_get_or_none(f"{BASE}/dailies/{date_str}")
    if data:
        return data, date_str, False
    # 回退：取最近 7 期索引
    idx = http_get(f"{BASE}/dailies?limit=7")
    items = (idx.get("items") or idx.get("dailies") or []) if isinstance(idx, dict) else []
    if not items:
        raise RuntimeError("当日日报不存在，且日报索引为空，无法回退。")
    # 取最近日期
    latest = max(items, key=lambda x: x.get("date", ""))
    d2 = latest.get("date")
    data2 = http_get(f"{BASE}/dailies/{d2}")
    return data2, d2, True


def _parse_history_time(value):
    """Parse a history timestamp as UTC, returning None for invalid values."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _latest_history_boundary(history_data, before):
    """Return the latest valid delivery boundary from current or legacy history."""
    if isinstance(history_data, list):
        records = history_data
    elif isinstance(history_data, dict):
        records = history_data.get("records") if isinstance(history_data.get("records"), list) else [history_data]
    else:
        return None

    candidates = []
    for record in records:
        if not isinstance(record, dict):
            continue
        raw = next((record.get(field) for field in (
            "delivery_completed_at", "lastPushTime", "timestamp", "pipeline_completed_at"
        ) if record.get(field)), None)
        parsed = _parse_history_time(raw)
        if parsed is not None and parsed < before:
            candidates.append(parsed)
    return max(candidates, default=None)

# ----------------------------- 多来源聚合 -----------------------------
RSS_FEEDS = [
    ("VentureBeat AI", "https://venturebeat.com/category/ai/feed/"),
    ("Hugging Face Blog", "https://huggingface.co/blog/feed.xml"),
    ("arXiv cs.AI", "https://rss.arxiv.org/rss/cs.AI"),
    ("TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/"),
]


def fetch_rss(source_name, url, limit=8):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/atom+xml, application/xml"})
    with urllib.request.urlopen(req, timeout=30) as response:
        root = ET.fromstring(response.read())
    entries = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
    result = []
    for entry in entries[:limit]:
        def text(*names):
            for name in names:
                node = entry.find(name)
                if node is not None and node.text:
                    value = html.unescape(node.text)
                    value = re.sub(r"<[^>]+>", " ", value)
                    return re.sub(r"\s+", " ", value).strip()
            return ""
        link = text("link", "{http://www.w3.org/2005/Atom}link")
        atom_link = entry.find("{http://www.w3.org/2005/Atom}link")
        if atom_link is not None:
            link = atom_link.get("href", link)
        summary = text(
            "description", "summary",
            "{http://www.w3.org/2005/Atom}summary",
            "{http://www.w3.org/2005/Atom}content",
            "{http://purl.org/rss/1.0/modules/content/}encoded",
        )
        result.append({
            "title": text("title", "{http://www.w3.org/2005/Atom}title"),
            "summary": summary,
            "summary_status": "available" if summary else "source_empty",
            "link": link,
            "source": source_name,
            # 财经日报要按「过去 24 小时」过滤，这里一并取出发布时间；AI 日报不读这个字段。
            "published": text("pubDate", "{http://www.w3.org/2005/Atom}updated", "{http://www.w3.org/2005/Atom}published"),
        })
    return result


EXTRA_SECTION_LABEL = "全网 AI 资讯"

# ----------------------------- 智能分类规则 -----------------------------
# 按内容性质重新分类，而不是直接使用 AI HOT 的官方分类
SECTION_RULES = [
    ("📊 行业趋势", ["ARR", "营收", "年度经常性收入", "revenue", "token", "API调用", "用户增长",
                      "市场规模", "市值", "股价", "财报", "季度", "年报", "增长率", "同比", "环比"]),
    ("🏢 产业动态", ["融资", "收购", "并购", "IPO", "上市", "投资", "亿美元", "轮融资",
                      "发布", "推出", "宣布", "更新", "升级", "裁员", "重组", "合作", "partnership",
                      "封杀", "禁令", "监管"]),
    ("📰 行业资讯", ["分析", "报告", "调查", "研究显示", "趋势", "预测", "展望", "观点", "评论",
                      "市场", "竞争", "政策", "法规", "诉讼", "起诉"]),
    ("💼 商业应用", ["企业", "客户", "落地", "案例", "方案", "B2B", "B2C", "SaaS",
                      "部署", "实施", "采用", "使用", "效率", "降本", "增效"]),
    ("🛠️ 开发者工具", ["开源", "GitHub", "API", "SDK", "框架", "库", "工具", "模型", "dataset",
                       "Hugging Face", "版本", "release", "支持"]),
    ("🔬 学术研究", ["arXiv", "论文", "研究", "breakthrough", "算法", "architecture", "训练",
                      "benchmark", "SOTA", "实验", "方法", "technique", "提出"]),
]
DEFAULT_SECTION = "其他资讯"  # 未命中任何规则的兜底分类


def classify_ai_items(items):
    """智能分类：按关键词加权打分将条目分到对应板块。

    不用「命中即停」：SECTION_RULES 里的词非常宽（「模型」「市场」「使用」都在列），
    先命中哪条全看规则书写顺序，一条讲财报的新闻只要捎带一句「发布」
    就会被前面的规则截走。改成打分——标题命中权重高于摘要，取分最高的板块，
    同分时按 SECTION_RULES 的先后顺序决定，保留原有的优先级意图。

    items: AI HOT + RSS 聚合后的所有条目（扁平列表）
    返回：按新分类规则组织的 sections
    """
    buckets = {label: [] for label, _ in SECTION_RULES}
    buckets[DEFAULT_SECTION] = []

    for item in items:
        title = f"{item.get('title', '')} {item.get('originalTitle', '')}".lower()
        summary = str(item.get('summary', '')).lower()

        best_label, best_score = None, 0
        for label, keywords in SECTION_RULES:
            score = 0
            for kw in keywords:
                kw = kw.lower()
                if kw in title:
                    score += 3
                elif kw in summary:
                    score += 1
            # 严格大于：同分时先定义的规则胜出
            if score > best_score:
                best_label, best_score = label, score

        buckets[best_label if best_label else DEFAULT_SECTION].append(item)

    # 只返回非空板块，按定义顺序排列
    result = []
    for label, _ in SECTION_RULES:
        if buckets[label]:
            result.append({"label": label, "items": buckets[label]})
    if buckets[DEFAULT_SECTION]:
        result.append({"label": DEFAULT_SECTION, "items": buckets[DEFAULT_SECTION]})

    return result


def aggregate_sources(primary):
    """聚合 AI HOT 和 RSS 源，然后统一重新分类。"""
    # 收集所有条目（扁平化）
    all_items = []
    seen = set()

    # 从 AI HOT 收集
    for s in primary.get("sections", []):
        for item in s.get("items", []):
            key = re.sub(r"\W+", "", item.get("title", "").lower())
            if key and key not in seen:
                seen.add(key)
                all_items.append(item)

    # RSS 源彼此独立；并行只返回数据，去重和分类仍在主线程完成。
    from concurrent.futures import ThreadPoolExecutor

    def fetch_one(feed):
        source_name, url = feed
        try:
            return source_name, fetch_rss(source_name, url), None
        except Exception as exc:
            return source_name, [], exc

    with ThreadPoolExecutor(max_workers=max(1, min(4, len(RSS_FEEDS))), thread_name_prefix="ai-rss") as executor:
        fetched = list(executor.map(fetch_one, RSS_FEEDS))

    for source_name, source_items, error in fetched:
        if error is not None:
            print(f"     来源跳过：{source_name}（{error}）")
            continue
        for item in source_items:
            key = re.sub(r"\W+", "", item["title"].lower())
            if item["title"] and key and key not in seen:
                seen.add(key)
                all_items.append({
                    "title": item["title"], "summary": item["summary"],
                    "summaryStatus": item.get("summary_status", "available"),
                    "source": {"name": item["source"]},
                    "links": {"original": item["link"], "aihot": item["link"]}
                })
        print(f"     {source_name}：抓取 {len(source_items)} 条")

    source_empty_count = sum(
        item.get("summaryStatus") == "source_empty" for item in all_items
    )
    if source_empty_count:
        print(f"     [INFO] 上游未提供摘要：{source_empty_count} 条（不计入翻译失败）")

    # 统一智能分类
    sections = classify_ai_items(all_items)

    # 计算实际收录窗口（基于 cron 时间）
    from datetime import datetime, timezone, timedelta
    import subprocess
    now_utc = datetime.now(timezone.utc)

    # 读取 cron 配置（小时:分钟）
    cron_hour = int(os.getenv('CRON_HOUR', '23'))
    cron_minute = int(os.getenv('CRON_MINUTE', '23'))

    # 计算窗口结束时间（今天的 cron 时间）
    window_end = now_utc.replace(hour=cron_hour, minute=cron_minute, second=0, microsecond=0)
    if now_utc.hour < cron_hour or (now_utc.hour == cron_hour and now_utc.minute < cron_minute):
        # 还没到今天的 cron 时间，使用昨天的
        window_end -= timedelta(days=1)

    # 尝试从push_history.json读取上次推送时间（解决周末/长假问题）
    window_start = window_end - timedelta(hours=24)  # 默认24小时
    try:
        history_file = os.path.join(HERE, 'push_history.json')
        if os.path.exists(history_file):
            with open(history_file, 'r', encoding='utf-8') as f:
                history_data = json.load(f)
            last_push_time = _latest_history_boundary(history_data, window_end)
            if last_push_time:
                # History timestamps are real delivery boundaries. Never allow a
                # delayed run to push the next collection window beyond its cron anchor.
                window_start = min(last_push_time, window_end)

                days_span = (window_end - window_start).total_seconds() / 86400
                if days_span > 1.5:
                    print(f"     [INFO] 收录窗口跨越 {days_span:.1f} 天（周末/长假）")
    except Exception as e:
        print(f"     [WARN] 无法读取上次推送时间，使用默认24小时窗口：{e}")

    return {
        "date": primary.get("date", ""),
        "windowStart": window_start.isoformat(),  # 覆盖
        "windowEnd": window_end.isoformat(),      # 覆盖
        "generatedAt": now_utc.isoformat(),
        "attribution": primary.get("attribution", {}),
        "links": primary.get("links", {}),
        "sections": sections
    }

TRANSLATE_API = "https://api.mymemory.translated.net/get"

# 常见 AI 公司/产品专有名词：翻译引擎会按字面英文单词误译（如 Anthropic->人性、
# Google DeepMind 拆词、Meta->元）。翻译前用占位符保护，翻译后还原为原文名。
PROTECTED_TERMS = [
    "Anthropic", "OpenAI", "DeepMind", "Google DeepMind", "Meta", "xAI", "Grok",
    "Midjourney", "Databricks", "Hugging Face", "GitHub", "TechCrunch",
    "VentureBeat", "Claude", "Gemini", "ChatGPT", "Llama", "Mistral",
]
# 长名称先匹配（如 "Google DeepMind" 先于 "Meta"），避免子串被提前替换。
PROTECTED_TERMS.sort(key=len, reverse=True)


def _protect_terms(text, terms=None):
    """用占位符保护专有名词。token 用 ASCII 字母数字（QQZ...ZQQ）而非符号，
    降低被翻译引擎当作普通文本插入空格/标点的概率。
    terms 为 None 时用 AI 语境的 PROTECTED_TERMS；财经日报会传入自己的术语表。"""
    placeholders = {}
    # 长名称先匹配（如 "Federal Reserve" 先于 "Fed"），避免子串被提前替换。
    term_list = sorted(terms, key=len, reverse=True) if terms else PROTECTED_TERMS
    for i, term in enumerate(term_list):
        token = f"QQZ{i}ZQQ"
        pattern = re.compile(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])")
        if pattern.search(text):
            text = pattern.sub(token, text)
            placeholders[token] = term
    return text, placeholders


def _restore_terms(text, placeholders):
    """还原占位符；翻译引擎可能在字符间插入空格/标点（如 "QQZ 6 ZQQ"），
    用逐字符可插入空白的正则容忍这种变形。"""
    for token, term in placeholders.items():
        loose_pattern = re.compile(r"[\s\-_]*".join(re.escape(ch) for ch in token))
        text = loose_pattern.sub(term, text)
    return text


def _has_leftover_placeholder(text):
    return bool(re.search(r"QQZ\s*\d+\s*ZQQ", text))


def translate_text(text, target="zh-CN", retries=3, terms=None):
    if not text or not re.search(r"[A-Za-z]", text):
        return text
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()[:490]
    protected_text, placeholders = _protect_terms(text, terms=terms)
    query = urllib.parse.urlencode({"q": protected_text, "langpair": f"en|{target}"})
    req = urllib.request.Request(f"{TRANSLATE_API}?{query}", headers={"User-Agent": "Mozilla/5.0"})
    last_exc = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
            translated = payload.get("responseData", {}).get("translatedText", "")
            if not translated or payload.get("responseStatus") not in (200, "200"):
                raise ValueError(f"响应异常：{payload.get('responseStatus')}")
            translated = html.unescape(translated).strip()
            restored = _restore_terms(translated, placeholders)
            if _has_leftover_placeholder(restored):
                # 占位符被翻译引擎改写到无法识别的形态，宁可整体失败回退英文原文，
                # 也不能把 "QQZ6ZQQ" 这类残留展示给用户。
                raise ValueError(f"占位符还原失败，残留未识别：{restored[:80]}")
            return restored
        except (urllib.error.HTTPError, urllib.error.URLError, ValueError) as exc:
            last_exc = exc
            time.sleep(2 * (attempt + 1))
            continue
    raise last_exc


# --------------------------- LLM 翻译（OpenAI 兼容） ---------------------------
# MyMemory 是免费接口、按 IP 限流，逐条翻译 36 条要发 72 次请求，必然 429。
# 配置了自建网关就走网关批量翻译：一次请求 10 条，请求数降两个数量级；
# 没配 key 时仍回退到 MyMemory，保持无配置也能跑。
AI_MODEL_TRANSLATE_DEFAULT = ""

AI_TRANSLATE_SYSTEM = (
    "你是专业的科技/AI 领域翻译。把用户给出的英文标题和摘要翻译成简体中文，"
    "术语准确，公司名与产品名保留通用译名或英文原文"
    "（如 OpenAI、Anthropic、Claude、ChatGPT 保持原文）。"
    "不要增删信息，不要加评论。严格按要求的 JSON 结构输出，不要输出多余文字。"
)


_BASE_URL_WARNED = False


def _warn_if_default_base_url(base_url, api_key):
    """没配 OPENAI_BASE_URL 时大声报警，不要静默走 api.openai.com。

    未设置翻译模型时不主动指定模型，由 OPENAI_MODEL_TRANSLATE 或配置文件提供。
    """
    global _BASE_URL_WARNED
    if _BASE_URL_WARNED or not api_key:
        return
    if base_url == "https://api.openai.com/v1":
        _BASE_URL_WARNED = True
        print("  [WARN] 未设置 OPENAI_BASE_URL，将请求官方 api.openai.com。")
        print("         若 key 属于自建网关，请求会以 401 失败，且 key 已发往第三方。")
        print("         请设置 OPENAI_BASE_URL 或在 push_config.json 填 openai_base_url。")


def _ai_llm_config():
    """读取 LLM 配置。与财经日报共用同一组环境变量。"""
    cfg_path = os.path.join(HERE, "push_config.json")
    cfg = {}
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
    api_key = (os.environ.get("OPENAI_API_KEY") or cfg.get("openai_api_key", "")).strip()
    base_url = (os.environ.get("OPENAI_BASE_URL") or cfg.get("openai_base_url", "")
                or "https://api.openai.com/v1").strip().rstrip("/")
    model = (os.environ.get("OPENAI_MODEL_TRANSLATE")
             or cfg.get("openai_model_translate", "") or AI_MODEL_TRANSLATE_DEFAULT).strip()
    _warn_if_default_base_url(base_url, api_key)
    return api_key, base_url, model


def call_ai_llm_json(system_prompt, user_prompt, retries=None, timeout=None):
    """调用 OpenAI 兼容接口并解析 JSON 对象。失败抛异常，由调用方降级。

    timeout 默认取 LLM_TIMEOUT（线上 90s）：socket 空闲超时 + 下方
    _read_with_deadline 总限时双保险，网关排队/慢滴灌最多等 90s，
    超时批次走逐条回退，不再无限拖住整个 job。
    """
    retries = _LLM_MAX_RETRIES if retries is None else retries
    timeout = _LLM_TIMEOUT if timeout is None else timeout
    api_key, base_url, model = _ai_llm_config()
    if not api_key:
        raise RuntimeError("未配置 OPENAI_API_KEY")
    payload = {
        "model": model,
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
                    # 部分网关模型（如 muse-spark）缺该头会被路由层 400 拒掉
                    #（MissingSessionID）。值从 X_OPENCODE_SESSION 取，未配置则不带。
                    **({"x-opencode-session": os.environ["X_OPENCODE_SESSION"]}
                       if os.environ.get("X_OPENCODE_SESSION") else {}),
                },
            )
            with _DEEPSEEK_SEMAPHORE:
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    body = json.loads(_read_with_deadline(response, timeout).decode("utf-8"))
            content = body["choices"][0]["message"]["content"]
            # 有些网关会把 JSON 包在 ```json fence 里，剥掉再解析。
            content = re.sub(r"^\s*```(?:json)?|```\s*$", "", content.strip())
            return json.loads(content)
        except Exception as exc:
            last_exc = exc
            if attempt < retries:
                # 504/429 是网关瞬时压力，退避后再试比立刻重撞成功率高。
                time.sleep(3 * (attempt + 1))
                continue
    raise last_exc


def call_ai_llm_json_stream(system_prompt, user_prompt, retries=None, timeout=None,
                           max_tokens=1500):
    """流式版 JSON 调用（翻译专用）。

    非流式要等网关整段生成完才回包：排队 30 分钟，请求就干等 30 分钟；
    且 urllib 的 socket 超时在慢滴灌下永远触发不了（_read_with_deadline 是兜底）。
    流式把等待切成两段，各管一段：
    - urlopen 的 timeout = 首字节预算（建连 + 排队；网关出队开始生成即回响应头，
      本地实测拥堵 transient，平时首字节约 4s，预算给 45s）；
    - 循环内墙钟检查 = 总预算 timeout，超了立刻放弃。
    某段超限立刻抛错，由调用方重试一次（重排队是 lottery，transient 拥堵常能秒过），
    再失败该批保留英文，不拖住其他批次。网关若回非 SSE 整包则按普通 JSON 解析。
    """
    retries = _LLM_MAX_RETRIES if retries is None else retries
    timeout = _LLM_TIMEOUT if timeout is None else timeout
    first_byte_budget = min(45, timeout)
    api_key, base_url, model = _ai_llm_config()
    if not api_key:
        raise RuntimeError("未配置 OPENAI_API_KEY")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
        "stream": True,
        "max_tokens": max_tokens,
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
                    # 部分网关模型（如 muse-spark）缺该头会被路由层 400 拒掉
                    #（MissingSessionID）。值从 X_OPENCODE_SESSION 取，未配置则不带。
                    **({"x-opencode-session": os.environ["X_OPENCODE_SESSION"]}
                       if os.environ.get("X_OPENCODE_SESSION") else {}),
                },
            )
            start = time.monotonic()
            with _DEEPSEEK_SEMAPHORE:
                # 出队即回头：这个 timeout 只盖建连 + 排队，不盖生成。
                with urllib.request.urlopen(req, timeout=first_byte_budget) as response:
                    ctype = response.headers.get("Content-Type", "")
                    if "text/event-stream" not in ctype:
                        # 网关没按流式回：按普通整包解析（总限时仍由外层调用方保障）。
                        body = json.loads(response.read().decode("utf-8"))
                        content = body["choices"][0]["message"]["content"]
                    else:
                        parts = []
                        for line in response:
                            if time.monotonic() - start >= timeout:
                                raise TimeoutError(
                                    f"流式生成超过总限时 {timeout}s，放弃")
                            s = line.decode("utf-8", errors="replace").strip()
                            if not s.startswith("data:"):
                                continue
                            d = s[5:].strip()
                            if d == "[DONE]":
                                break
                            try:
                                choices = json.loads(d).get("choices") or []
                            except Exception:  # noqa: BLE001 - 心跳/注释行直接跳过
                                continue
                            if not choices:
                                continue  # new-api 发的空 choices 占位 chunk
                            delta = (choices[0].get("delta") or {}).get("content") or ""
                            parts.append(delta)
                        content = "".join(parts)
            content = re.sub(r"^\s*```(?:json)?|```\s*$", "", content.strip())
            return json.loads(content)
        except Exception as exc:
            last_exc = exc
            if attempt < retries:
                print(f"     流式翻译失败（{exc!r}），重试 {attempt + 1}/{retries}...")
                time.sleep(3 * (attempt + 1))
                continue
    raise last_exc


def translate_batch_llm_ai(pairs, batch_size=5):
    """批量翻译：pairs 为 [(key, title, summary)]，返回 {key: (title_zh, summary_zh)}。

    策略（qwen 通道排队波动大：串行 10 条一批会被单个慢请求拖死）：
    - 小批量（默认 5 条）：单请求 completion 减半，出队 + 生成更快；
    - 批次并行（4 worker，受 _DEEPSEEK_SEMAPHORE 限流）：一批卡住不挡其他批；
    - 流式 + 每批重试 1 次：排队多为 transient，重排常能秒过；
    单批失败只影响该批（保留英文），其余批次照常；调用方对漏项再逐条回退。
    """
    batches = [pairs[i:i + batch_size] for i in range(0, len(pairs), batch_size)]
    total_batches = len(batches)
    result = {}

    def _translate_one(batch_num, batch):
        listing = [
            json.dumps({"id": key, "title": title, "summary": (summary or "")[:300]},
                       ensure_ascii=False)
            for key, title, summary in batch
        ]
        user_prompt = (
            "把下面每条英文资讯的 title 和 summary 翻译成简体中文。\n"
            "输入（每行一个 JSON 对象）：\n" + "\n".join(listing) + "\n\n"
            '输出 JSON：{"items":[{"id":原样返回的id,"title":"中文标题","summary":"中文摘要"}]}\n'
            "summary 为空则中文 summary 也返回空字符串。必须覆盖全部输入条目。"
        )
        data = call_ai_llm_json_stream(AI_TRANSLATE_SYSTEM, user_prompt, retries=1)
        mapping = {}
        for row in data.get("items") or []:
            rid = row.get("id")
            if isinstance(rid, str) and rid.isdigit():
                rid = int(rid)
            if rid is None:
                continue
            mapping[rid] = ((row.get("title") or "").strip(),
                            (row.get("summary") or "").strip())
        return mapping, len(batch)

    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(_translate_one, i + 1, b): i + 1
                for i, b in enumerate(batches)}
        for fut in as_completed(futs):
            batch_num = futs[fut]
            try:
                mapping, n = fut.result()
                result.update(mapping)
                print(f"     批次 {batch_num}/{total_batches}：{len(mapping)}/{n} 条翻译成功")
            except Exception as exc:
                print(f"     批次 {batch_num}/{total_batches} 失败（该批保留英文）：{exc!r}")
    return result


def _needs_translation(text):
    """含拉丁字母且不含中文才需要翻译。"""
    s = (text or "").strip()
    if not s or not re.search(r"[A-Za-z]", s):
        return False
    return not any('一' <= c <= '鿿' for c in s)


def translate_items(report, give_up_after=6):
    """英文条目译中文并保留原文；失败回退原文，不中断整体流程。

    优先走自建网关批量翻译（5 条一批、4 路并行、流式），配置缺失或整体失败时才逐条走 MyMemory。
    MyMemory 是免费接口、按 IP 限流：逐条翻 36 条要发 72 次请求，实测必被 429，
    且被限流后每条都要重试到超时（约 17s），几十条能拖十几分钟。
    """
    all_items = [item for section in report.get("sections", [])
                 for item in section.get("items", [])]
    for item in all_items:
        item["originalTitle"] = item.get("title", "")
        item["originalSummary"] = item.get("summary", "")

    if os.getenv("TRANSLATION_ENABLED", "1").strip().lower() not in ("1", "true", "yes", "on"):
        print("     已关闭标题和摘要翻译，保留英文原文")
        return report

    pending = [i for i, item in enumerate(all_items)
               if _needs_translation(item.get("title")) or _needs_translation(item.get("summary"))]
    if not pending:
        print("     无需翻译的英文条目")
        return report

    api_key, _base_url, model = _ai_llm_config()
    if api_key:
        print(f"     检测到 {len(pending)} 条英文条目，用 {model} 批量翻译 ...")
        pairs = [(i, all_items[i].get("title", ""), all_items[i].get("summary", ""))
                 for i in pending]
        mapping = translate_batch_llm_ai(pairs)
        completed = set()
        for i, (title_zh, summary_zh) in mapping.items():
            if i not in pending:
                continue
            item = all_items[i]
            if title_zh:
                item["title"] = title_zh
            if summary_zh:
                item["summary"] = summary_zh
            if not (_needs_translation(item.get("title"))
                    or _needs_translation(item.get("summary"))):
                completed.add(i)
        leftover = [i for i in pending
                    if _needs_translation(all_items[i].get("title"))
                    or _needs_translation(all_items[i].get("summary"))]
        if leftover:
            print(f"     仍有 {len(leftover)} 条未翻译，补翻一轮 ...")
            retry_pairs = [(i, all_items[i].get("title", ""), all_items[i].get("summary", ""))
                           for i in leftover]
            for i, (title_zh, summary_zh) in translate_batch_llm_ai(retry_pairs, batch_size=5).items():
                item = all_items[i]
                if title_zh:
                    item["title"] = title_zh
                if summary_zh:
                    item["summary"] = summary_zh
                if not (_needs_translation(item.get("title"))
                        or _needs_translation(item.get("summary"))):
                    completed.add(i)
        print(f"     LLM 翻译完成：{len(completed)}/{len(pending)} 条")
        # 补翻之后仍是英文的条目，交给免费接口兜底。
        # 之前只要 done>0 就直接 return，网关部分 504 时
        # （例如 21/31 成功）剩下的 10 条会原样以英文出现在页面上。
        still_en = [i for i in pending
                    if _needs_translation(all_items[i].get("title"))
                    or _needs_translation(all_items[i].get("summary"))]
        if not still_en:
            return report
        if completed:
            print(f"     [!] 仍有 {len(still_en)} 条为英文，保留原文；本次不再调用免费接口")
            return report
        # 网关整体不可用时也保留原文。逐条 MyMemory 最坏会产生数十个
        # 20 秒请求，曾让 --no-push 在五分钟外层门禁内无法结束。
        print("     [!] LLM 翻译全部失败，保留英文原文")
        return report

    translated, failed, consecutive_fail = 0, 0, 0
    gave_up = False
    for i in pending:
        item = all_items[i]
        if gave_up:
            continue
        ok = True
        try:
            item["title"] = translate_text(item["title"])
            time.sleep(1.2)
        except Exception as exc:
            ok = False
            print(f"     标题翻译失败，保留英文原文：{exc}")
        try:
            item["summary"] = translate_text(item["summary"])
            time.sleep(1.2)
        except Exception as exc:
            ok = False
            print(f"     摘要翻译失败，保留英文原文：{exc}")
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
    print(f"     翻译完成：{translated} 条，失败：{failed} 条" + ("（已提前放弃）" if gave_up else ""))
    return report

# ----------------------------- 重要新闻打分 -----------------------------
# 没有编辑排序信号可用（RSS 只有时间顺序），用启发式打分挑「今日重点」：
# 大公司/大产品名 + 重大事件关键词命中越多分越高；同分按原始序号靠前优先。
COMPANY_WEIGHTS = {
    "OpenAI": 3, "Anthropic": 3, "Google": 3, "DeepMind": 3, "Microsoft": 3, "Meta": 3,
    "xAI": 3, "Nvidia": 3, "Amazon": 3, "Apple": 3,
    "Claude": 2, "ChatGPT": 2, "Gemini": 2, "Grok": 2, "Llama": 2, "Mistral": 2,
}
EVENT_KEYWORDS = [
    "融资", "收购", "诉讼", "发布", "上市", "裁员", "突破", "首个", "全球首",
    "亿美元", "估值", "封杀", "禁令", "漏洞", "攻击", "事故", "IPO",
]


def _score_importance(text, section_label):
    score = 0.0
    for term, weight in COMPANY_WEIGHTS.items():
        pattern = re.compile(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])", re.IGNORECASE)
        if pattern.search(text):
            score += weight
    for kw in EVENT_KEYWORDS:
        if kw in text:
            score += 2
    if section_label and section_label != EXTRA_SECTION_LABEL:
        score += 1  # AI HOT 自身分类版块比"全网 AI 资讯"兜底桶更可信
    return score


def calculate_similarity(title1, title2):
    """计算两个标题的相似度（Jaccard相似度）"""
    import re
    words1 = set(re.findall(r'\w+', title1.lower()))
    words2 = set(re.findall(r'\w+', title2.lower()))

    if not words1 or not words2:
        return 0.0

    intersection = words1 & words2
    union = words1 | words2

    return len(intersection) / len(union)


def pick_highlights(flat_items, top_n=5):
    """flat_items: [(entry_dict, section_label), ...]。按打分+原始序号排序取前 N 条，自动去重。"""
    ranked = sorted(
        flat_items,
        key=lambda pair: (-_score_importance(pair[0]["title"] + " " + pair[0].get("originalTitle", ""), pair[1]), pair[0]["idx"]),
    )

    # 去重：检查标题相似度
    selected = []
    for entry, label in ranked:
        if len(selected) >= top_n:
            break

        # 检查是否与已选新闻重复
        is_duplicate = False
        for existing_entry in selected:
            similarity = calculate_similarity(
                entry.get("title", ""),
                existing_entry.get("title", "")
            )
            if similarity > 0.6:  # 相似度阈值60%
                is_duplicate = True
                break

        if not is_duplicate:
            selected.append(entry)

    return selected

# ----------------------------- 数据整形 -----------------------------
# 全文翻译每条要抓一次原文网页 + 过一次 LLM，见 shape() 里的预算控制。
MAX_PAGE_TRANSLATIONS = 5

# 同域名两次抓取的最小间隔（秒），按域名分别计时。
PAGE_FETCH_INTERVAL = 5.0
_LAST_FETCH_AT = {}


def translate_page_with_llm(original_url, title):
    """使用DeepSeek API翻译网页全文

    返回翻译后的文本，存储为静态HTML文件供用户访问
    """
    try:
        import requests
        from bs4 import BeautifulSoup

        # 1. 抓取原文网页
        # 同一域名连着抓会被限流（VentureBeat 实测第 3 条起就 429）。
        # 记录上次抓该域名的时间，不足间隔就先等一会儿。
        host = urllib.parse.urlparse(original_url).netloc
        last = _LAST_FETCH_AT.get(host)
        if last is not None:
            wait = PAGE_FETCH_INTERVAL - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
        _LAST_FETCH_AT[host] = time.monotonic()

        headers = {
            # 必须是完整的浏览器 UA。截断成 "...AppleWebKit/537.36" 少了
            # Chrome/Safari 后缀，是典型的爬虫特征，VentureBeat 会直接回 429。
            'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                           'AppleWebKit/537.36 (KHTML, like Gecko) '
                           'Chrome/120.0.0.0 Safari/537.36'),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        response = requests.get(original_url, headers=headers, timeout=30)
        response.raise_for_status()

        # 2. 提取正文
        soup = BeautifulSoup(response.content, 'html.parser')

        # 移除脚本和样式
        for script in soup(['script', 'style', 'nav', 'footer', 'aside']):
            script.decompose()

        # 提取文章正文（尝试多种选择器）
        article = None
        for selector in ['article', '.article', '.post-content', '.entry-content', 'main']:
            article = soup.select_one(selector)
            if article:
                break

        if not article:
            article = soup.find('body')

        if not article:
            return None

        # 提取文本段落
        paragraphs = []
        for p in article.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'li']):
            text = p.get_text(strip=True)
            if len(text) > 20:  # 过滤太短的段落
                paragraphs.append(text)

        full_text = '\n\n'.join(paragraphs[:50])  # 最多50段

        if not full_text or len(full_text) < 100:
            return None

        # 3. 调用DeepSeek翻译
        prompt = f"""请将以下英文文章翻译成中文，保持原文的段落结构：

{full_text}

要求：
1. 准确翻译，保持原意
2. 语言流畅自然
3. 保留专业术语的英文（如API、AI等）
4. 不要添加额外的说明或评论
"""

        api_key = os.environ.get("OPENAI_API_KEY", "")
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        if not api_key:
            return None

        response = requests.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                # 不能写死模型名：自建网关只挂了自己那几个模型，
                # 硬编码 deepseek-chat 在网关上不存在，必然报错。
                "model": _ai_llm_config()[2],
                "messages": [
                    {"role": "system", "content": "你是一个专业的英译中翻译助手。"},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 4000
            },
            # 全文翻译输入几千字符、输出四千 token，实测网关要 80~160s。
            # 卡 60s 基本每篇都超时，「查看中文全文」永远出不来。
            timeout=240
        )

        if response.status_code == 200:
            result = response.json()
            translated_text = result['choices'][0]['message']['content']

            # 4. 生成HTML文件
            html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - 全文翻译</title>
    <style>
        body {{
            max-width: 800px;
            margin: 40px auto;
            padding: 0 20px;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            line-height: 1.8;
            color: #333;
            background: #f5f5f5;
        }}
        .container {{
            background: white;
            padding: 40px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        h1 {{
            font-size: 28px;
            margin-bottom: 10px;
            color: #1a1a1a;
        }}
        .meta {{
            color: #666;
            font-size: 14px;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 1px solid #eee;
        }}
        .content {{
            font-size: 16px;
            white-space: pre-wrap;
            text-align: justify;
        }}
        .footer {{
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            color: #999;
            font-size: 14px;
        }}
        a {{
            color: #0066cc;
            text-decoration: none;
        }}
        a:hover {{
            text-decoration: underline;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{title}</h1>
        <div class="meta">
            由 DeepSeek AI 翻译 | <a href="{original_url}" target="_blank">查看原文 ↗</a>
        </div>
        <div class="content">{translated_text}</div>
        <div class="footer">
            本翻译由 AI 自动生成，仅供参考
        </div>
    </div>
</body>
</html>"""

            # 保存到文件
            import hashlib
            url_hash = hashlib.md5(original_url.encode()).hexdigest()[:12]
            filename = f"translated_{url_hash}.html"
            filepath = os.path.join(os.path.dirname(__file__), filename)

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html_content)

            return filename

        return None

    except Exception as e:
        print(f"     [WARN] 翻译失败: {e}")
        return None


def translate_page_url(original_url):
    """生成翻译页面的URL

    返回相对路径，指向本地生成的翻译HTML文件
    """
    if not original_url or not re.match(r"^https?://", original_url):
        return ""

    # 生成URL hash作为文件名
    import hashlib
    url_hash = hashlib.md5(original_url.encode()).hexdigest()[:12]
    filename = f"translated_{url_hash}.html"

    # 检查文件是否已存在
    filepath = os.path.join(os.path.dirname(__file__), filename)
    if os.path.exists(filepath):
        return filename

    # 文件不存在，返回空（前端将隐藏按钮）
    # 实际翻译在后台任务中完成
    return ""


def create_market_insights_section(market_insights):
    """
    将市场洞察数据转换为新闻条目格式

    Args:
        market_insights: 整合后的市场数据

    Returns:
        格式化的板块数据
    """
    items = []
    idx = 0

    highlights = market_insights.get('highlights', {})

    # 官方公告数据
    for item in highlights.get('official_announcements', [])[:5]:
        idx += 1
        items.append({
            'idx': f"M{idx}",
            'title': item['text'],
            'summary': f"数据来源：{item.get('source', '新闻报道')} | 类型：{item.get('type', 'data')}",
            'source': '市场数据',
            'original': '',
            'aihot': '',
            'translatedPage': ''
        })

    # 市场使用趋势
    for item in highlights.get('market_usage', [])[:3]:
        idx += 1
        items.append({
            'idx': f"M{idx}",
            'title': f"📈 {item['text']}",
            'summary': f"数据来源：OpenRouter 实时统计 | 查看详情：https://openrouter.ai/rankings",
            'source': 'OpenRouter',
            'original': 'https://openrouter.ai/rankings',
            'aihot': '',
            'translatedPage': ''
        })

    # 性能基准
    for item in highlights.get('performance_benchmarks', [])[:3]:
        idx += 1
        items.append({
            'idx': f"M{idx}",
            'title': f"⚡ {item['text']}",
            'summary': f"数据来源：Artificial Analysis 性能测试 | 查看详情：https://artificialanalysis.ai",
            'source': 'Artificial Analysis',
            'original': 'https://artificialanalysis.ai',
            'aihot': '',
            'translatedPage': ''
        })

    if not items:
        return None

    return {
        'label': '📊 行业数据洞察',
        'items': items
    }


def _format_trend_cards(trends, start_idx=1):
    """把 TrendAnalyzer 的结果转成统一的卡片格式。

    两类内容：价格变动（成本变化）和榜单进出/名次移动（模型分布变化）。
    价格只保留变动最大的 5 条：全量输出会把十几条同质条目铺满页面，看不出重点。
    """
    cards = []
    now_iso = datetime.now(timezone.utc).isoformat()

    def _add(title, summary, source):
        cards.append({
            "idx": start_idx + len(cards),
            "title": title,
            "summary": summary,
            "link": "#",
            "source": source,
            "pubDate": now_iso,
        })

    price_trends = trends.get("price_trends") or []
    ranked = sorted(price_trends, key=lambda t: abs(t.get("change_percent", 0)), reverse=True)[:5]
    for t in ranked:
        pct = t.get("change_percent", 0)
        arrow = "📈 上调" if pct > 0 else "📉 下调"
        _add(f"{arrow} {t.get('model', '')} 价格{abs(pct):.1f}%",
             f"对比 {t.get('from_date', '')}："
             f"${t.get('old_price', 0):.4f} → ${t.get('new_price', 0):.4f} / 1M tokens",
             "OpenRouter 历史对比")

    rt = trends.get("ranking_trends") or {}
    if isinstance(rt, dict):
        base = rt.get("compared_with") or "上一快照"
        if rt.get("entered"):
            _add(f"🆕 新进榜 {len(rt['entered'])} 个模型",
                 "、".join(rt["entered"][:6]) + f"（对比 {base}）", "OpenRouter 榜单变化")
        if rt.get("exited"):
            _add(f"⬇️ 掉出榜单 {len(rt['exited'])} 个模型",
                 "、".join(rt["exited"][:6]) + f"（对比 {base}）", "OpenRouter 榜单变化")
        for m in (rt.get("moved") or [])[:3]:
            delta = m.get("delta", 0)
            _add(f"{'⬆️' if delta > 0 else '⬇️'} {m.get('model', '')} 排名"
                 f"{'上升' if delta > 0 else '下降'} {abs(delta)} 位",
                 f"第 {m.get('from_rank')} 名 → 第 {m.get('to_rank')} 名（对比 {base}）",
                 "OpenRouter 榜单变化")

    history_status = trends.get("history_status")
    if history_status == "missing":
        _add("历史趋势待建立",
             trends.get("note") or "最近 7 天没有可用的 OpenRouter 历史快照。",
             "OpenRouter 历史状态")
    elif history_status == "restored" and not cards:
        compared_with = trends.get("compared_with") or rt.get("compared_with") or "上一快照"
        _add("历史快照已恢复，本次无变化",
             f"已读取 {trends.get('history_count', 0)} 份历史快照；最近对比日期：{compared_with}。",
             "OpenRouter 历史状态")

    return cards


def shape(report, market_insights=None, news_metrics=None, token_usage=None):
    sections, gi = [], 0
    flat_for_ranking = []
    # 全文翻译要抓原文网页，几十条顺序抓同一批域名会被 429 限流
    # （VentureBeat 实测第 6 条起就开始拒），且每条都要过一次 LLM。
    # 只给靠前的若干条做，够用且不会把整轮跑成限流风暴。
    page_translate_budget = MAX_PAGE_TRANSLATIONS

    for s in report.get("sections", []):
        label = s.get("label", "")
        its = []
        for it in s.get("items", []):
            gi += 1
            title = it.get("title", "")
            original_title = it.get("originalTitle", title)
            original_link = it.get("links", {}).get("original", "")
            is_translated = bool(original_title) and original_title != title

            # 全文翻译结果由 translate_page_with_llm() 写入 translatedPage；
            # 同时兼容 ArticleTranslator 写入的 translated_content，避免数据丢失。
            translated_page = it.get("translatedPage", "")
            translated_content = it.get("translated_content", "")

            # 判断是否需要翻译：有原文链接，且标题中包含英文或已被翻译
            needs_translation = bool(original_link) and (
                is_translated or
                bool(re.search(r'[a-zA-Z]{3,}', original_title))  # 包含3个以上连续英文字母
            )

            # 全文翻译默认关闭；标题和摘要翻译仍由 TRANSLATION_ENABLED 控制。
            full_text_translation_enabled = os.getenv(
                "FULL_TEXT_TRANSLATION_ENABLED", "0"
            ).strip().lower() in ("1", "true", "yes", "on")
            # 生成翻译页面（走配置的 LLM 网关）
            if (full_text_translation_enabled and not translated_page
                    and needs_translation and original_link.startswith("http")
                    and page_translate_budget > 0):
                page_translate_budget -= 1
                try:
                    translated_file = translate_page_with_llm(original_link, title)
                    if translated_file:
                        translated_page = translated_file
                except Exception as e:
                    print(f"     [WARN] 全文翻译失败 ({title[:30]}...): {e}")

            entry = {
                "idx": gi,
                "title": title,
                "originalTitle": original_title,
                "summary": it.get("summary", ""),
                "originalSummary": it.get("originalSummary", it.get("summary", "")),
                "summaryStatus": it.get("summaryStatus", "available" if it.get("summary") else "source_empty"),
                "source": it.get("source", {}).get("name", ""),
                "original": original_link,
                "aihot": it.get("links", {}).get("aihot", ""),
                "translatedPage": translated_page,
                "translated_content": translated_content,
            }
            its.append(entry)
            flat_for_ranking.append((entry, label))
        sections.append({"label": label, "items": its})

    # 添加市场数据洞察板块（放在最后）
    if market_insights:
        market_items = []
        for insight in market_insights:
            gi += 1
            market_items.append({
                "idx": gi,
                "title": insight.get("title", ""),
                "originalTitle": "",
                "summary": insight.get("summary", ""),
                "originalSummary": "",
                "source": insight.get("source", ""),
                "original": insight.get("link", ""),
                "aihot": "",
                "translatedPage": "",
            })
        # 顶部的「📊 行业数据洞察」分隔条渲染的是 newsMetrics（ARR/Token/定价等），
        # 这里是另一批数据（OpenRouter 榜单、价格趋势）。两处同名会让人以为
        # 页面重复了一块，改成区分得开的名字。
        sections.append({"label": "📈 市场数据与趋势", "items": market_items})

    meta = {
        "date": report.get("date", ""),
        "windowStart": report.get("windowStart", ""),
        "windowEnd": report.get("windowEnd", ""),
        "generatedAt": report.get("generatedAt", ""),
        "total": gi,
        "sourceEmptyCount": sum(
            entry.get("summaryStatus") == "source_empty"
            for entry, _label in flat_for_ranking
        ),
        "source": report.get("attribution", {}),
        "dailyUrl": report.get("links", {}).get("aihot", ""),
    }
    highlights = pick_highlights(flat_for_ranking, top_n=min(5, gi)) if gi else []
    return {
        "meta": meta,
        "sections": sections,
        "highlights": highlights,
        "newsMetrics": news_metrics or {},
        "tokenUsage": token_usage or {}
    }

# ----------------------------- HTML 生成 -----------------------------
HTML_TMPL = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI 日报 · 晨报仪表盘</title>
<style>
  :root{--bg:#0e1014;--bg2:#151922;--card:#171c26;--card-hover:#1e2531;--border:#272f3d;--text:#e8ecf3;--muted:#9aa4b2;--accent:#5b9dff;--accent2:#37e0b0;--chip:#222b39;--shadow:rgba(0,0,0,.45);}
  *{box-sizing:border-box;margin:0;padding:0}
  html{scroll-behavior:smooth}
  body{background:radial-gradient(1200px 600px at 80% -10%, #1a2233 0%, var(--bg) 55%) fixed;color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;line-height:1.6;-webkit-font-smoothing:antialiased;padding-top:56px}
  a{color:inherit;text-decoration:none}
  .global-nav{position:fixed;top:0;left:0;right:0;background:rgba(14,16,20,0.95);backdrop-filter:blur(10px);border-bottom:1px solid var(--border);z-index:1000;padding:12px 0}
  .global-nav .wrap{max-width:1160px;margin:0 auto;padding:0 20px;display:flex;gap:20px;align-items:center}
  .global-nav a{color:var(--text);text-decoration:none;font-size:14px;font-weight:600;padding:6px 12px;border-radius:6px;transition:all .2s}
  .global-nav a:hover{background:var(--card-hover);color:var(--accent)}
  .global-nav a.active{background:var(--accent);color:#0c1320}
  .wrap{max-width:1180px;margin:0 auto;padding:0 18px}
  .hero{padding:30px 0 16px}
  .kicker{display:inline-flex;align-items:center;gap:8px;font-size:13px;letter-spacing:.18em;color:var(--accent2);text-transform:uppercase;border:1px solid var(--border);padding:5px 12px;border-radius:999px;background:var(--bg2)}
  .hero h1{font-size:clamp(24px,4vw,36px);font-weight:800;margin:12px 0 4px;letter-spacing:-.5px}
  .hero h1 .sub{color:var(--accent)}
  .hero .date{font-size:15px;color:var(--text);font-weight:600}
  .hero .window{font-size:13px;color:var(--muted);margin-top:2px}
  .stats{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}
  .stat{display:inline-flex;align-items:baseline;gap:5px;background:var(--card);border:1px solid var(--border);border-radius:999px;padding:5px 12px}
  .stat .num{font-size:14px;font-weight:800;color:var(--accent)}
  .stat .lbl{font-size:12px;color:var(--muted)}
  .stat.total .num{color:var(--accent2)}
  .nav{position:sticky;top:0;z-index:20;background:rgba(14,16,20,.82);backdrop-filter:blur(10px);border-bottom:1px solid var(--border);margin-top:14px}
  .nav .wrap{display:flex;gap:10px;overflow-x:auto;padding:12px 18px;scrollbar-width:thin}
  .nav a{flex:0 0 auto;font-size:13.5px;color:var(--muted);border:1px solid var(--border);background:var(--bg2);padding:7px 13px;border-radius:999px;white-space:nowrap;transition:.15s}
  .nav a:hover{color:var(--text);border-color:var(--accent)}
  .nav a b{color:var(--accent);font-weight:700;margin-left:6px}
  main{padding:34px 0 10px}
  .section{margin-bottom:42px;scroll-margin-top:64px}
  .section-head{display:flex;align-items:baseline;gap:12px;margin-bottom:18px;border-left:4px solid var(--accent);padding-left:12px}
  .section-head h2{font-size:23px;font-weight:750}
  .section-head .count{font-size:14px;color:var(--muted)}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(310px,1fr));gap:16px}
  .card{display:flex;flex-direction:column;background:var(--card);border:1px solid var(--border);border-radius:16px;padding:18px;transition:.18s;position:relative;overflow:hidden}
  .card:hover{background:var(--card-hover);border-color:#33405a;transform:translateY(-2px);box-shadow:0 10px 26px var(--shadow)}
  .card .top{display:flex;align-items:center;justify-content:space-between;margin-bottom:11px}
  .card .idx{display:inline-flex;align-items:center;justify-content:center;width:34px;height:34px;border-radius:10px;background:linear-gradient(135deg,var(--accent),#3b6fd4);color:#fff;font-weight:800;font-size:15px;flex:0 0 auto}
  .chip{font-size:12px;color:var(--muted);background:var(--chip);border:1px solid var(--border);padding:4px 10px;border-radius:999px;max-width:62%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .card h3{font-size:16.5px;font-weight:700;line-height:1.45;margin-bottom:9px;text-align:left}
  .card h3 a:hover{color:var(--accent)}
  .card .summary{font-size:14px;color:#c4ccd8;flex:1;margin-bottom:10px;text-align:left}
  .card .original-text{font-size:12.5px;color:var(--muted);border-top:1px solid var(--border);padding-top:10px;margin-bottom:14px}
  .card .foot{display:flex;align-items:center;justify-content:space-between;gap:10px}
  .src{font-size:12.5px;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .linkgroup{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}
  .orig{font-size:13px;font-weight:600;color:var(--accent);border:1px solid var(--border);padding:6px 12px;border-radius:10px;background:var(--bg2);white-space:nowrap;transition:.15s}
  .orig:hover{background:var(--accent);color:#0c1320;border-color:var(--accent)}
  footer{border-top:1px solid var(--border);margin-top:18px;padding:26px 0 50px;color:var(--muted);font-size:13.5px}
  footer .wrap{display:flex;flex-wrap:wrap;gap:8px 18px;align-items:center;justify-content:space-between}
  footer a{color:var(--accent);border-bottom:1px dotted var(--accent)}
  .note{font-size:12.5px;color:#6f7a8a;margin-top:10px;width:100%}
  .highlights{margin:14px 0 4px;background:linear-gradient(135deg,#1c2740,#171c26);border:1px solid var(--accent);border-radius:12px;padding:12px 16px}
  .highlights h2{font-size:14px;font-weight:800;color:var(--accent2);margin-bottom:6px;display:flex;align-items:center;gap:6px}
  .highlights ol{list-style:none;counter-reset:hl}
  .highlights li{counter-increment:hl;display:flex;gap:8px;padding:4px 0;border-bottom:1px dashed var(--border)}
  .highlights li:last-child{border-bottom:none}
  .highlights li::before{content:counter(hl);flex:0 0 auto;width:18px;height:18px;border-radius:5px;background:var(--accent);color:#0c1320;font-size:11px;font-weight:800;display:flex;align-items:center;justify-content:center;margin-top:1px}
  .highlights a{font-size:13.5px;font-weight:600}
  .highlights a:hover{color:var(--accent)}
  .highlights .hl-src{font-size:11.5px;color:var(--muted);margin-left:6px}
  @media (max-width:560px){.hero{padding:22px 0 12px}.grid{grid-template-columns:1fr}}
</style>
</head>
<body>
<nav class="global-nav"><div class="wrap">
  <a href="index.html" class="active">AI 日报</a>
  <a href="finance.html">财经日报</a>
  <a href="monitor.html">推送监控</a>
</div></nav>
<header class="hero"><div class="wrap">
  <span class="kicker">● AI 日报 · 多来源聚合</span>
  <h1>AI 日报 <span class="sub">晨报仪表盘</span></h1>
  <div class="date" id="heroDate">—</div>
  <div class="window" id="heroWindow">—</div>
  <div class="stats" id="heroStats"></div>
  <div class="highlights" id="highlights" style="display:none">
    <h2>⭐ 今日重要新闻</h2>
    <ol id="highlightsList"></ol>
  </div>
</div></header>
<nav class="nav"><div class="wrap" id="navLinks"></div></nav>
<main class="wrap" id="main"></main>
<footer><div class="wrap">
  <div id="footerMeta">—</div>
  <div class="note">本站仅作信息聚合展示，资讯内容版权归原作者所有；数据来自 AI HOT 及各资讯源的公开 RSS，引用请以第三方原文为准。</div>
</div></footer>
<script>
const DATA = __DATA__;
function fmtBeijing(iso, opts){try{const dt=new Date(iso);const o=Object.assign({timeZone:'Asia/Shanghai',hour12:false},opts||{});return new Intl.DateTimeFormat('zh-CN',o).format(dt);}catch(e){return iso;}}
function truncate(s,n){const arr=Array.from(s||'');if(arr.length<=n)return s||'';return arr.slice(0,n-1).join('')+'…';}
function esc(s){return (s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function safeUrl(u){try{const p=new URL(u,location.href).protocol;return (p==='http:'||p==='https:')?u:'#';}catch(e){return '#';}}
(function render(){
  const meta=DATA.meta, sections=DATA.sections;
  document.getElementById('heroDate').textContent=fmtBeijing(meta.date+'T00:00:00+08:00',{year:'numeric',month:'long',day:'numeric',weekday:'long'})+'（北京时间）';
  document.getElementById('heroWindow').textContent='收录窗口：'+fmtBeijing(meta.windowStart,{month:'long',day:'numeric',hour:'2-digit',minute:'2-digit'})+' — '+fmtBeijing(meta.windowEnd,{month:'long',day:'numeric',hour:'2-digit',minute:'2-digit'})+'（北京时间）';
  let st='<div class="stat total"><div class="num">'+meta.total+'</div><div class="lbl">总条数</div></div>';
  if(meta.sourceEmptyCount){st+='<div class="stat"><div class="num">'+meta.sourceEmptyCount+'</div><div class="lbl">上游未提供摘要</div></div>';}
  sections.forEach(s=>{st+='<div class="stat"><div class="num">'+s.items.length+'</div><div class="lbl">'+esc(s.label)+'</div></div>';});
  document.getElementById('heroStats').innerHTML=st;
  const highlights=DATA.highlights||[];
  if(highlights.length){
    document.getElementById('highlights').style.display='';
    document.getElementById('highlightsList').innerHTML=highlights.map(it=>{
      const tl=safeUrl(it.aihot||it.original||'#');
      return '<li><a href="'+esc(tl)+'" target="_blank" rel="noopener noreferrer">'+esc(it.title)+'</a><span class="hl-src">— '+esc(it.source)+'</span></li>';
    }).join('');
  }
  let nav='';sections.forEach((s,i)=>{nav+='<a href="#sec-'+i+'">'+esc(s.label)+'<b>'+s.items.length+'</b></a>';});
  // 添加新闻指标导航（如果有数据）
  const newsMetrics=DATA.newsMetrics||{};
  // OpenRouter 直抓的周 token 用量（总量 + 分模型份额 + 环比），不再用新闻抽取
  const tokenUsage=DATA.tokenUsage||{};
  const hasMetrics=Object.values(newsMetrics).some(arr=>arr&&arr.length>0);
  if(hasMetrics){nav+='<a href="#metrics-section">📊 行业数据<b>•</b></a>';}
  document.getElementById('navLinks').innerHTML=nav;
  let main='';

  // 渲染新闻指标板块（优先展示）
  if(hasMetrics){
    main+='<div class="market-divider" id="metrics-section"><h2>📊 行业数据洞察</h2></div>';

    // ARR/营收
    if(newsMetrics.ARR&&newsMetrics.ARR.length>0){
      main+='<div class="block"><h2>💰 ARR / 营收数据</h2><ul style="list-style:none;padding:0">';
      newsMetrics.ARR.forEach(m=>{
        const company=esc(m.company||'');
        const name=esc(m.metric_name||'');
        const val=m.value||0;
        const unit=m.unit||'';
        let valStr='';
        if(unit==='USD'){
          valStr=val>=1e9?'$'+(val/1e9).toFixed(1)+'B':val>=1e6?'$'+(val/1e6).toFixed(1)+'M':'$'+val.toFixed(0);
        }else if(unit==='亿美元'){
          valStr=val+' 亿美元';
        }else{
          valStr=val.toLocaleString()+' '+unit;
        }
        const ctx=m.context?'（'+esc(m.context)+'）':'';
        const conf=(m.confidence||0)*100;
        main+='<li style="padding:10px;border-bottom:1px solid var(--border)"><span style="color:var(--accent2);font-weight:600">'+company+'</span> '+name+' <span style="color:var(--accent);font-size:18px;font-weight:700">'+valStr+'</span> '+ctx+' <span style="color:var(--muted);font-size:12px">置信度 '+conf.toFixed(0)+'%</span></li>';
      });
      main+='</ul></div>';
    }

    // 融资/估值
    if(newsMetrics.融资&&newsMetrics.融资.length>0){
      main+='<div class="block"><h2>💸 融资 / 估值</h2><ul style="list-style:none;padding:0">';
      newsMetrics.融资.forEach(m=>{
        const company=esc(m.company||'');
        const name=esc(m.metric_name||'');
        const val=m.value||0;
        const unit=m.unit||'';
        let valStr='';
        if(unit==='USD'){
          valStr=val>=1e9?'$'+(val/1e9).toFixed(1)+'B':val>=1e6?'$'+(val/1e6).toFixed(1)+'M':'$'+val.toFixed(0);
        }else if(unit==='亿美元'){
          valStr=val+' 亿美元';
        }else{
          valStr=val.toLocaleString()+' '+unit;
        }
        const ctx=m.context?'（'+esc(m.context)+'）':'';
        main+='<li style="padding:10px;border-bottom:1px solid var(--border)"><span style="color:var(--accent2);font-weight:600">'+company+'</span> '+name+' <span style="color:var(--accent);font-size:18px;font-weight:700">'+valStr+'</span> '+ctx+'</li>';
      });
      main+='</ul></div>';
    }

    // 用户数据
    if(newsMetrics.用户数&&newsMetrics.用户数.length>0){
      main+='<div class="block"><h2>👥 用户数据</h2><ul style="list-style:none;padding:0">';
      newsMetrics.用户数.forEach(m=>{
        const company=esc(m.company||'');
        const name=esc(m.metric_name||'');
        const val=m.value||0;
        const unit=m.unit||'';
        let valStr='';
        if(val>=1e8){
          valStr=(val/1e8).toFixed(1)+' 亿'+unit;
        }else if(val>=1e4){
          valStr=(val/1e4).toFixed(1)+' 万'+unit;
        }else{
          valStr=val.toLocaleString()+' '+unit;
        }
        const ctx=m.context?'（'+esc(m.context)+'）':'';
        main+='<li style="padding:10px;border-bottom:1px solid var(--border)"><span style="color:var(--accent2);font-weight:600">'+company+'</span> '+name+' <span style="color:var(--accent);font-size:18px;font-weight:700">'+valStr+'</span> '+ctx+'</li>';
      });
      main+='</ul></div>';
    }

    // Token 使用量与份额：OpenRouter 直抓（DATA.tokenUsage），空数据时整块隐藏
    const tokenList=tokenUsage.list||[];
    if(tokenList.length>0){
      const totalTok=tokenUsage.total_weekly_tokens||0;
      const totalStr=totalTok>=1e12?(totalTok/1e12).toFixed(1)+'T tokens':totalTok>=1e9?(totalTok/1e9).toFixed(1)+'B tokens':Number(totalTok).toLocaleString('en-US')+' tokens';
      main+='<div class="block"><h2>🪙 Token 使用量与份额</h2><div style="padding:10px;color:var(--accent);font-size:18px;font-weight:700">近一周 '+totalStr+'</div><ul style="list-style:none;padding:0">';
      tokenList.forEach(m=>{
        const arrow=m.wow_direction==='positive'?'↗':(m.wow_direction==='negative'?'↘':'→');
        const wow=m.wow_change&&m.wow_change!=='N/A'?(' '+arrow+' '+esc(String(m.wow_change))):'';
        const share=(m.market_share!=null&&m.market_share!=='')?(' 份额 '+m.market_share+'%'):'';
        main+='<li style="padding:10px;border-bottom:1px solid var(--border)"><span style="color:var(--accent2);font-weight:600">'+esc(m.model||'')+'</span> <span style="color:var(--accent);font-size:18px;font-weight:700">'+esc(m.weekly_tokens_display||'')+'</span>'+share+wow+'</li>';
      });
      main+='</ul>';
      const tokHist=tokenUsage.history||[];
      const tokTrend=tokenUsage.trend||{};
      if(tokHist.length>=2){
        const tokVals=tokHist.map(p=>Number(p.total_weekly_tokens)).filter(v=>isFinite(v)&&v>0);
        if(tokVals.length>=2){
          const tw=300,th=56,tpad=4;
          const tmn=Math.min.apply(null,tokVals),tmx=Math.max.apply(null,tokVals),tsp=(tmx-tmn)||1;
          const tst=(tw-tpad*2)/(tokVals.length-1);
          let tdd='';
          tokVals.forEach((v,i)=>{tdd+=(i?'L':'M')+(tpad+i*tst).toFixed(1)+' '+(th-tpad-(v-tmn)/tsp*(th-tpad*2)).toFixed(1);});
          const tup=tokVals[tokVals.length-1]>=tokVals[0];
          main+='<div style="margin:6px 10px 2px"><svg viewBox="0 0 '+tw+' '+th+'" style="width:100%;height:auto;display:block"><path d="'+tdd+'" fill="none" stroke="'+(tup?'#16a34a':'#dc2626')+'" stroke-width="2"/></svg>'
            +'<div style="display:flex;justify-content:space-between;color:var(--muted);font-size:11px"><span>'+esc(tokHist[0].date||'')+' '+(tmn/1e12).toFixed(1)+'T</span><span>近'+tokVals.length+'日周总量</span><span>'+esc(tokHist[tokHist.length-1].date||'')+' '+(tmx/1e12).toFixed(1)+'T</span></div></div>';
        }
        if(tokTrend.arr){
          const arrStr=(tokTrend.arr>=1e15?(tokTrend.arr/1e15).toFixed(2)+'P':(tokTrend.arr/1e12).toFixed(1)+'T')+' tokens/年';
          const arrChg=(tokTrend.arr_change_pct==null||tokTrend.arr_change_pct===''?'--':((tokTrend.arr_change_pct>0?'+':'')+Number(tokTrend.arr_change_pct).toFixed(2)+'%'));
          const arrSlope=(tokTrend.slope_annualized_pct==null||tokTrend.slope_annualized_pct===''?'':(' · 窗口年化增速 '+(tokTrend.slope_annualized_pct>0?'+':'')+Number(tokTrend.slope_annualized_pct).toFixed(1)+'%'));
          main+='<div style="padding:0 10px;color:var(--accent2);font-size:13px">ARR '+arrStr+'（环比 '+arrChg+arrSlope+'）</div>';
        } else {
          const first=tokHist[0],last=tokHist[tokHist.length-1];
          const pct=(last.total_weekly_tokens/first.total_weekly_tokens-1)*100;
          const arrow=pct>=0?'↗':'↘';
          main+='<div style="padding:0 10px;color:var(--accent2);font-size:13px">近'+tokHist.length+'日总量：'+(first.total_weekly_tokens/1e12).toFixed(1)+'T → '+(last.total_weekly_tokens/1e12).toFixed(1)+'T（'+arrow+' '+Math.abs(pct).toFixed(1)+'%）</div>';
        }
      }
      if(tokenUsage.note){main+='<div style="padding:0 10px 10px;color:#888;font-size:12px">'+esc(tokenUsage.note)+'</div>';}
      main+='</div>';
    }
    // 定价 / 成本变化
    // news_metrics_extractor 一直在抽「定价」这一类，但之前没有对应渲染块，
    // 抽到的数据直接被丢掉，页面上看不到成本/价格变化。
    if(newsMetrics.定价&&newsMetrics.定价.length>0){
      main+='<div class="block"><h2>💵 定价 / 成本变化</h2><ul style="list-style:none;padding:0">';
      newsMetrics.定价.forEach(m=>{
        const company=esc(m.company||'');
        const name=esc(m.metric_name||'');
        const val=m.value||0;
        const unit=esc(m.unit||'');
        const valStr=(typeof val==='number'?val.toLocaleString('en-US'):esc(String(val)))+(unit?' '+unit:'');
        const ctx=m.context?'（'+esc(m.context)+'）':'';
        main+='<li style="padding:10px;border-bottom:1px solid var(--border)"><span style="color:var(--accent2);font-weight:600">'+company+'</span> '+name+' <span style="color:var(--accent);font-size:18px;font-weight:700">'+valStr+'</span> '+ctx+'</li>';
      });
      main+='</ul></div>';
    }
  }

  // 渲染新闻板块
  sections.forEach((s,i)=>{main+='<section class="section" id="sec-'+i+'"><div class="section-head"><h2>'+esc(s.label)+'</h2><span class="count">'+s.items.length+' 条</span></div><div class="grid">';
    s.items.forEach(it=>{const orig=safeUrl(it.original||it.aihot||'#');const tl=safeUrl(it.aihot||it.original||'#');const tp=safeUrl(it.translatedPage||'');
      main+='<article class="card"><div class="top"><span class="idx">'+it.idx+'</span><span class="chip" title="'+esc(it.source)+'">'+esc(it.source)+'</span></div>';
      main+='<h3><a href="'+esc(tl)+'" target="_blank" rel="noopener noreferrer">'+esc(it.title)+'</a></h3>';
      const summary=it.summaryStatus==='source_empty'?'上游未提供摘要，请查看原文。':truncate(it.summary,120);
      main+='<p class="summary">'+esc(summary)+'</p>';
      if(it.originalTitle!==it.title||it.originalSummary!==it.summary) main+='<p class="original-text"><b>原文</b><br>'+esc(truncate(it.originalTitle,120))+'<br>'+esc(truncate(it.originalSummary,260))+'</p>';
      main+='<div class="foot"><span class="src">'+esc(it.source)+'</span><span class="linkgroup">'+(tp&&tp!=='#'?'<a class="orig" href="'+esc(tp)+'" target="_blank" rel="noopener noreferrer">翻译全文 ↗</a>':'')+'<a class="orig" href="'+esc(orig)+'" target="_blank" rel="noopener noreferrer">阅读原文 ↗</a></span></div></article>';});
    main+='</div></section>';});
  document.getElementById('main').innerHTML=main;
  const sn=(meta.source&&meta.source.name)||'AI HOT', su=(meta.source&&meta.source.url)||meta.dailyUrl||'https://aihot.virxact.com';
  document.getElementById('footerMeta').innerHTML='本期共 <b style="color:var(--accent2)">'+meta.total+'</b> 条 · 数据来源：AI HOT、VentureBeat AI、Hugging Face Blog、arXiv cs.AI、TechCrunch AI · 日报主页：<a href="'+esc(safeUrl(meta.dailyUrl))+'" target="_blank" rel="noopener noreferrer">'+esc(meta.dailyUrl)+'</a>';
})();
</script>
</body></html>"""

def build_html(data, standalone=False):
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = HTML_TMPL.replace("__DATA__", payload)
    return strip_push_nav(html) if standalone else html

def strip_push_nav(html):
    """去掉推送落地页的站内导航（global-nav + 板块 nav），内容与脚本不动。

    navLinks 容器删掉后，原 `getElementById('navLinks').innerHTML=nav` 会拿到
    null 使整段 render 抛错，所以一并改成守卫写法。
    """
    html = re.sub(r'<nav class="global-nav">.*?</nav>', '', html, flags=re.S)
    html = re.sub(r'<nav class="nav">.*?</nav>', '', html, flags=re.S)
    return html.replace(
        "document.getElementById('navLinks').innerHTML=nav;",
        "var _nl=document.getElementById('navLinks');if(_nl){_nl.innerHTML=nav;}")

def derive_push_dashboard_url(dashboard_url):
    """把 Pages 版仪表盘地址推导成推送专用无导航落地页地址。

    空输入回空字符串，保持与现有 dashboard_url 配置兼容。
    """
    url = (dashboard_url or "").strip()
    if not url:
        return ""
    for full, push in (("ai_daily_dashboard.html", "ai_push_standalone.html"),
                       ("finance_dashboard.html", "finance_push_standalone.html")):
        if url.endswith(full):
            return url[: -len(full)] + push
    if url.lower().endswith(".html"):
        return url[:-len(".html")] + "_push_standalone.html"
    return url

def safe_md_url(url):
    """只放行 http/https，并转义会破坏 markdown 链接语法的字符，
    防止不可信 RSS 来源的 link 字段注入第二个链接或 javascript: 协议。"""
    url = (url or "").strip()
    scheme = url.split(":", 1)[0].lower() if ":" in url else ""
    if scheme not in ("http", "https"):
        return "#"
    for ch, enc in ((")", "%29"), ("(", "%28"), (" ", "%20"), ("\n", ""), ("\r", "")):
        url = url.replace(ch, enc)
    return url

# ----------------------------- Markdown 摘要 -----------------------------
def build_markdown(data, dashboard_url):
    meta, sections = data["meta"], data["sections"]
    highlights = data.get("highlights", [])
    date_human = fmt_cst(meta["date"] + "T00:00:00+08:00", "%Y年%m月%d日 {wd}")
    ws = fmt_cst(meta["windowStart"], "%m/%d %H:%M")
    we = fmt_cst(meta["windowEnd"], "%m/%d %H:%M")
    lines = []
    lines.append(f"# AI 日报 · {date_human}")
    lines.append(f"> 总条数 **{meta['total']}** · 收录窗口 {ws}–{we}（北京时间）")
    if highlights:
        lines.append("\n## ⭐ 今日重要新闻")
        for it in highlights:
            link = safe_md_url(it["original"] or it["aihot"] or "#")
            title = it["title"].replace("[", "【").replace("]", "】")
            lines.append(f"> **{it['idx']}.** [{title}]({link})　*— {it['source']}*")
    for s in sections:
        lines.append(f"## {s['label']}（{len(s['items'])}）")
        for it in s["items"]:
            link = safe_md_url(it["original"] or it["aihot"] or "#")
            title = it["title"].replace("[", "【").replace("]", "】")
            lines.append(f"> **{it['idx']}.** [{title}]({link})　*— {it['source']}*")
            if it.get("originalTitle") and it["originalTitle"] != it["title"]:
                lines.append(f"> English: {it['originalTitle']}")
    if dashboard_url:
        lines.append(f"\n[📊 查看完整仪表盘]({safe_md_url(dashboard_url)})")
    else:
        lines.append(f"\n[📊 AI HOT 日报主页]({safe_md_url(meta['dailyUrl'])})")
    return "\n".join(lines)

def fmt_cst(iso, fmt):
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00")) + CST_OFFSET
        # 中文星期（用 {wd} 占位，避免被 strftime 先行展开）
        wk = ["星期一","星期二","星期三","星期四","星期五","星期六","星期日"][dt.weekday()]
        return dt.strftime(fmt).replace("{wd}", wk)
    except Exception:
        return iso

# ----------------------------- 推送（企业微信 / pushplus） -----------------------------

def http_post_json(url, payload, timeout=30):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data,
        headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))

def _truncate_by_bytes(s, max_bytes):
    """按字符截断到 UTF-8 字节数 <= max_bytes，不截断半个字符，max_bytes<=0 时返回空串。"""
    if max_bytes <= 0:
        return ""
    out, total = [], 0
    for ch in s:
        b = len(ch.encode("utf-8"))
        if total + b > max_bytes:
            break
        out.append(ch); total += b
    return "".join(out)

def truncate_bytes(s, max_bytes):
    """截断到 UTF-8 字节数 <= max_bytes（含省略提示），避免截断半个中文字。"""
    if len(s.encode("utf-8")) <= max_bytes:
        return s
    suffix = "\n…（完整版见仪表盘链接）"
    budget = max_bytes - len(suffix.encode("utf-8"))
    if budget <= 0:
        return _truncate_by_bytes(suffix.strip(), max_bytes)
    return _truncate_by_bytes(s, budget) + suffix

def push_wecom_webhook(webhook, markdown, dashboard_url=None, title_prefix="AI 日报"):
    """企业微信群机器人 -> 个人微信。无需 access_token、无需 IP 白名单。
    只发一条：有 dashboard_url 时发 news 图文卡片（按钮卡片，点击打开完整仪表盘网页），
    否则退化为 markdown 摘要（没有网页链接可跳转，只能把要点直接发出来）。"""
    if dashboard_url:
        news = {
            "msgtype": "news",
            "news": {
                "articles": [{
                    "title": f"{title_prefix} 📊 查看完整仪表盘",
                    "description": f"{title_prefix} · 全部版块 · 卡片式网页，点击打开",
                    "url": dashboard_url,
                    "picurl": "https://picsum.photos/id/1015/600/400",
                }]
            },
        }
        return [http_post_json(webhook, news)]
    content = truncate_bytes(markdown, 3900)  # 群机器人 markdown 上限 4096 字节
    return [http_post_json(webhook, {"msgtype": "markdown", "markdown": {"content": content}})]


def push_feishu(webhook, title, markdown, dashboard_url=None):
    """飞书群机器人（interactive 卡片）-> 飞书个人。无需 IP 白名单。"""
    elements = [
        {"tag": "h1", "content": title},
        {"tag": "div", "text": {"tag": "markdown", "content": truncate_bytes(markdown, 3800)}},
    ]
    if dashboard_url:
        elements.append({
            "tag": "action",
            "actions": [{
                "tag": "button",
                "text": {"tag": "plain_text", "content": "📊 查看完整网页"},
                "type": "primary",
                "url": dashboard_url,
            }],
        })
    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "template": "blue",
                "title": {"tag": "plain_text", "content": "AI 日报 · " + title},
            },
            "elements": elements,
        },
    }
    return http_post_json(webhook, payload)


def push_wecom(corpid, corpsecret, agentid, touser, markdown):
    """企业微信自建应用消息 -> 个人微信（无需认证、免身份证、全文）。"""
    base = os.environ.get("WECOM_BASE", "https://qyapi.weixin.qq.com").rstrip("/")
    tok = http_get(f"{base}/cgi-bin/gettoken?corpid={corpid}&corpsecret={corpsecret}")
    if not tok.get("access_token"):
        raise RuntimeError(f"企业微信获取 access_token 失败：{tok}")
    content = truncate_bytes(markdown, 3900)  # 企业微信 markdown 上限 4096 字节
    url = f"{base}/cgi-bin/message/send?access_token={tok['access_token']}"
    payload = {
        "touser": touser,
        "msgtype": "markdown",
        "agentid": int(agentid),
        "markdown": {"content": content},
        "enable_duplicate_check": 1,
        "duplicate_check_interval": 1800,
    }
    return http_post_json(url, payload)


def push_pushplus(token, markdown, title, api="https://www.pushplus.plus/send", topic=None):
    _p = {
        "token": token,
        "title": title,
        "content": markdown,
        "template": "markdown",
    }
    if topic:
        _p["topic"] = topic
    payload = json.dumps(_p, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(api,
        data=payload, headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

# ----------------------------- 主流程 -----------------------------
@monitor_task("ai_daily")
def main():
    import argparse, os
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-push", action="store_true")
    ap.add_argument("--date", default=None)
    ap.add_argument("--dashboard-url", default=None, help="覆盖配置中的 dashboard_url（用于注入部署后的公网地址）")
    args = ap.parse_args()

    cfg_path = os.path.join(HERE, "push_config.json")
    cfg = {}
    if os.path.exists(cfg_path):
        with open(cfg_path, encoding="utf-8") as f:
            cfg = json.load(f)
    # ---- 渠道配置：企业微信（默认）> pushplus（备选）----
    wecom = cfg.get("wecom", {}) or {}
    corpid = (os.environ.get("WECOM_CORPID") or wecom.get("corpid", "")).strip()
    corpsecret = (os.environ.get("WECOM_CORPSECRET") or wecom.get("corpsecret", "")).strip()
    agentid = str(os.environ.get("WECOM_AGENTID") or wecom.get("agentid", "")).strip()
    touser = (os.environ.get("WECOM_TOUSER") or wecom.get("touser", "@all")).strip() or "@all"
    token = (os.environ.get("PUSHPLUS_TOKEN") or cfg.get("pushplus_token", "")).strip()
    api = os.environ.get("PUSHPLUS_API", "https://www.pushplus.plus/send").strip()
    topic = (os.environ.get("PUSHPLUS_TOPIC") or cfg.get("pushplus_topic", "")).strip()
    dashboard_url = (args.dashboard_url
                     or os.environ.get("DASHBOARD_URL")
                     or cfg.get("dashboard_url", "")).strip()

    # 目标日期（北京时间）
    if args.date:
        date_str = args.date
    else:
        date_str = (datetime.now(timezone.utc) + CST_OFFSET).strftime("%Y-%m-%d")

    print(f"[1/4] 拉取日报 {date_str} ...")
    try:
        from llm_helpers import _llm_config as _ai_llm_config
        _ak, _bu, _tm, _am = _ai_llm_config()
        print(f"  [LLM配置] key={'已配置(长度%d)' % len(_ak) if _ak else '未配置'} "
              f"base={_bu or '(空)'} translate={_tm or '(未配置)'} analysis={_am or '(未配置)'}")
        if not _am:
            print("  [WARN] 分析模型为空：指标抽取/趋势解读将跳过，不会发 LLM 请求。")
    except Exception as _e:
        print(f"  [WARN] LLM 配置读取失败：{_e!r}")
    raw, used_date, fell_back = fetch_daily(date_str)
    if fell_back:
        print(f"     当日未生成，已回退到最近一期：{used_date}")
    combined_report = aggregate_sources(raw["report"])
    combined_report = translate_items(combined_report)

    # 提取市场数据洞察
    market_insights = []
    news_metrics = {}  # 新闻指标数据（dict：分组指标；空 dict 表示本次未抽到，前端整块隐藏）
    token_usage_payload = {}  # 直抓的周 token 用量（OpenRouter 网关口径，供页面Token/份额块渲染）

    if MARKET_DATA_AVAILABLE:
        try:
            print("[1.5/4] 采集市场数据洞察 ...")
            aggregator = MarketDataAggregator()
            formatter = MarketReportFormatter()

            # 聚合数据（暂不传入新闻项）
            print("     [DEBUG] 开始调用 MarketDataAggregator.aggregate() ...")
            aggregated = aggregator.aggregate(news_items=None)
            print(f"     [DEBUG] 聚合完成，返回数据: {len(aggregated) if aggregated else 0} 条")
            # 直抓 Token 用量透传给页面（总量 + 份额 + 环比，不走新闻抽取）
            mt = aggregated.get("market_trends", {}) if isinstance(aggregated, dict) else {}
            token_usage_payload = {
                "total_weekly_tokens": mt.get("total_weekly_tokens", 0),
                "list": mt.get("token_usage", []),
                "note": mt.get("token_usage_note", ""),
                "history": mt.get("token_history", []),
                "trend": build_token_trend(mt.get("token_history", [])),
            }

            # 格式化为卡片
            print("     [DEBUG] 开始格式化为HTML卡片 ...")
            market_cards = formatter.format_for_html(aggregated)
            print(f"     [DEBUG] 格式化完成，生成卡片: {len(market_cards) if market_cards else 0} 个")

            # 转换为统一格式
            for i, card in enumerate(market_cards):
                market_insights.append({
                    "idx": i + 1,
                    "title": card["title"],
                    "summary": card["content"],
                    "link": "#",
                    "source": card["source"],
                    "pubDate": datetime.now(timezone.utc).isoformat()
                })

            if market_insights:
                print(f"     ✓ 市场数据：{len(market_insights)} 个指标卡片")
            else:
                print(f"     [WARN] 市场数据采集完成但无数据返回")
                # 添加降级显示
                market_insights.append({
                    "idx": 1,
                    "title": "市场数据暂不可用",
                    "summary": "OpenRouter 或 Artificial Analysis API 暂时无法访问，请稍后刷新。",
                    "link": "#",
                    "source": "System",
                    "pubDate": datetime.now(timezone.utc).isoformat()
                })

            # 趋势分析：拿今天的聚合结果和 data/market_data 里的历史快照对比。
            # analyzers 里一直有 TrendAnalyzer，但从没接进主流程，
            # 「趋势分析 / 模型分布变化」在页面上始终是空的。
            try:
                from analyzers.trend_analyzer import TrendAnalyzer
                trends = TrendAnalyzer().analyze_trends(aggregated, days_back=7)
                trend_cards = _format_trend_cards(trends, start_idx=len(market_insights) + 1)
                market_insights.extend(trend_cards)
                history_status = trends.get("history_status", "unknown")
                history_count = trends.get("history_count", 0)
                compared_with = trends.get("compared_with", "") or "无"
                print(f"     ✓ 趋势分析：{len(trend_cards)} 条；"
                      f"历史状态={history_status}，快照={history_count}，最近对比={compared_with}"
                      + (f"（{trends.get('note')}）" if trends.get('note') else ""))
            except Exception as e:
                print(f"     [WARN] 趋势分析失败，跳过：{e}")

        except Exception as e:
            print(f"     [WARN] 市场数据采集失败：{e}")
            # 添加降级显示卡片
            market_insights.append({
                "idx": 1,
                "title": "市场数据暂不可用",
                "summary": "OpenRouter 或 Artificial Analysis API 暂时无法访问。如需查看行业动态，请稍后刷新本页面或访问官方网站。",
                "link": "#",
                "source": "System",
                "pubDate": datetime.now(timezone.utc).isoformat(),
                "error": str(e)
            })
    else:
        print("[1.5/4] 市场数据模块未安装，跳过")
        # 模块缺失时也添加提示
        market_insights.append({
            "idx": 1,
            "title": "市场数据模块未安装",
            "summary": "当前环境未安装 analyzers 模块，无法采集 OpenRouter 和 Artificial Analysis 数据。",
            "link": "#",
            "source": "System",
            "pubDate": datetime.now(timezone.utc).isoformat()
        })

    # 从新闻中提取关键指标
    print("[1.6/4] 从新闻提取关键指标（ARR/Token/用户数等）...")
    try:
        from news_metrics_extractor import extract_metrics_from_news
        from llm_helpers import call_llm_json

        # 准备新闻数据（合并所有新闻）
        all_news_items = []
        for section in combined_report.get('sections', []):
            all_news_items.extend(section.get('items', []))

        if all_news_items:
            # LLM 调用包装器
            def metrics_llm_caller(system_prompt, user_prompt, model=None):
                from llm_helpers import _llm_config
                analysis_model = _llm_config()[3]
                return call_llm_json(system_prompt, user_prompt, model=model or analysis_model)

            # 提取指标
            metrics_result = extract_metrics_from_news(all_news_items, metrics_llm_caller)
            news_metrics = metrics_result.get('grouped_metrics', {})

            total_metrics = metrics_result.get('high_confidence_count', 0)
            print(f"     ✓ 提取到 {total_metrics} 个高置信度指标")
        else:
            print(f"     无新闻数据，跳过指标提取")

    except Exception as e:
        print(f"     [WARN] 指标提取失败，跳过：{e}")
        news_metrics = {}

    # 全文翻译会显著放大抓取和 LLM 延迟，默认且生产环境均关闭。
    print("[1.7/4] 已关闭新闻全文翻译；标题和摘要翻译保留")

    data = shape(combined_report, market_insights=market_insights, news_metrics=news_metrics,
                token_usage=token_usage_payload)
    print(f"     成功：共 {data['meta']['total']} 条，版块 {[s['label'] for s in data['sections']]}")

    print("[2/4] 生成 HTML 仪表盘 ...")
    out_html = os.path.join(HERE, "ai_daily_dashboard.html")
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(build_html(data))
    print(f"     已写入 {out_html}")
    # 推送专用无导航落地页：Pages 版保留导航，企业微信卡片/正文链接用无导航版。
    out_push_html = os.path.join(HERE, "ai_push_standalone.html")
    with open(out_push_html, "w", encoding="utf-8") as f:
        f.write(build_html(data, standalone=True))
    print(f"     已写入 {out_push_html}")
    push_url = derive_push_dashboard_url(dashboard_url) or dashboard_url

    print("[3/4] 渲染 Markdown 摘要 ...")
    md = build_markdown(data, push_url)
    print(f"     长度 {len(md.encode('utf-8'))} 字节")

    if args.no_push:
        print("[4/4] --no-push：跳过推送。")
        print("—— Markdown 预览 ——")
        print(md[:600])
        return

    # 渠道优先级：企业微信群机器人 > 飞书群机器人 > 企业微信应用消息 > pushplus
    webhook = (os.environ.get("WECOM_WEBHOOK") or cfg.get("wecom_webhook", "")).strip()
    feishu_webhook = (os.environ.get("FEISHU_WEBHOOK") or cfg.get("feishu_webhook", "")).strip()
    delivery_status_path = os.environ.get("DELIVERY_STATUS_FILE", "").strip()
    wecom_channel = "wecom_webhook" if webhook else (
        "wecom_application" if corpid and corpsecret and agentid else "none"
    )
    delivery_succeeded = False
    delivery_attempted = False
    delivery_failure = "not_configured"

    if webhook:
        delivery_attempted = True
        print("[4/4] 推送到企业微信群机器人（-> 个人微信）...")
        title = f"AI 日报 · {fmt_cst(data['meta']['date'] + 'T00:00:00+08:00', '%m月%d日 {wd}')}"
        try:
            resp = push_wecom_webhook(webhook, md, push_url, title_prefix=title)
            print("     企业微信返回：", resp)
            failed = [r for r in resp if not isinstance(r, dict) or r.get("errcode", 0) != 0]
            delivery_succeeded = bool(resp) and not failed
            delivery_failure = "" if delivery_succeeded else "api_rejected"
            if failed:
                print("     ⚠️ 推送失败：", failed)
        except Exception as e:
            delivery_failure = f"exception:{type(e).__name__}"
            print("     ⚠️ 企业微信群机器人推送异常：", repr(e))

    elif feishu_webhook:
        print("[4/4] 推送到飞书群机器人（-> 飞书个人）...")
        title = f"AI 日报 · {fmt_cst(data['meta']['date'] + 'T00:00:00+08:00', '%m月%d日 {wd}')}"
        try:
            resp = push_feishu(feishu_webhook, title, md, push_url)
            print("     飞书返回：", resp)
            if isinstance(resp, dict) and resp.get("StatusCode") != 0:
                print("     ⚠️ 推送失败：", resp.get("msg"), resp)
        except Exception as e:
            print("     ⚠️ 飞书推送异常：", repr(e))

    elif corpid and corpsecret and agentid:
        delivery_attempted = True
        print("[4/4] 推送到企业微信（应用消息 -> 个人微信）...")
        try:
            resp = push_wecom(corpid, corpsecret, agentid, touser, md)
            print("     企业微信返回：", resp)
            delivery_succeeded = isinstance(resp, dict) and resp.get("errcode", 0) == 0
            delivery_failure = "" if delivery_succeeded else "api_rejected"
            if not delivery_succeeded:
                print("     ⚠️ 推送失败：", resp.get("errmsg") if isinstance(resp, dict) else "invalid response", resp)
        except Exception as e:
            delivery_failure = f"exception:{type(e).__name__}"
            print("     ⚠️ 企业微信推送异常：", repr(e))

    elif token:
        print("[4/4] 推送到 pushplus（个人微信）...")
        title = f"AI 日报 · {fmt_cst(data['meta']['date'] + 'T00:00:00+08:00', '%Y年%m月%d日 {wd}')}"
        resp = push_pushplus(token, md, title, api, topic or None)
        print("     pushplus 返回：", resp)
        if isinstance(resp, dict) and resp.get("code") != 200:
            print("     ⚠️ 推送可能失败，请检查返回信息。")
    else:
        print("[4/4] 未配置任何推送渠道（企业微信 WECOM_CORPID/SECRET/AGENTID 或 pushplus PUSHPLUS_TOKEN），跳过推送。")

    if delivery_status_path:
        from delivery_status import write_delivery_status
        write_delivery_status(
            delivery_status_path, "ai", wecom_channel,
            wecom_channel != "none", delivery_attempted, delivery_succeeded,
            completed_at=datetime.now(timezone.utc) if delivery_succeeded else None,
            reason=delivery_failure,
        )
        if not delivery_succeeded:
            raise RuntimeError(f"企业微信日报推送未成功: {delivery_failure}")

    # 微信公众号发布（独立于推送渠道）
    wechat_cfg = cfg.get("wechat_official", {}) or {}
    wechat_appid = (os.environ.get("WECHAT_APPID") or wechat_cfg.get("appid", "")).strip()
    wechat_appsecret = (os.environ.get("WECHAT_APPSECRET") or wechat_cfg.get("appsecret", "")).strip()
    # 如果设置了 appid 和 appsecret（无论是环境变量还是配置文件），则自动启用
    wechat_enabled = bool(wechat_appid and wechat_appsecret) or wechat_cfg.get("enabled", False)

    if wechat_enabled and wechat_appid and wechat_appsecret:
        print("\n[额外] 发布到微信公众号...")
        try:
            from wechat_official import publish_to_wechat
            from wechat_content_formatter import format_ai_daily_for_wechat
            from cover_generator import get_or_create_cover, create_default_cover

            # 格式化内容
            article_title, article_content, article_digest = format_ai_daily_for_wechat(data)

            # 获取或生成封面图
            date_str = data['meta']['date']
            cover_path = get_or_create_cover(date_str, cover_type="ai")

            # 如果封面生成失败，使用默认封面
            if not cover_path or not os.path.exists(cover_path):
                print("     使用默认封面...")
                cover_path = create_default_cover(cover_type="ai")

            if cover_path and os.path.exists(cover_path):
                # 发布到公众号
                publish_id = publish_to_wechat(
                    appid=wechat_appid,
                    appsecret=wechat_appsecret,
                    title=article_title,
                    content=article_content,
                    author="AI Daily Push",
                    digest=article_digest,
                    content_source_url=push_url,
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

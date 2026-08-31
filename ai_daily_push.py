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
import json, sys, os, re, html, time, urllib.parse, urllib.request, urllib.error
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
    from analyzers.market_data_aggregator import MarketDataAggregator
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
                    return re.sub(r"<[^>]+>", " ", node.text).strip()
            return ""
        link = text("link", "{http://www.w3.org/2005/Atom}link")
        atom_link = entry.find("{http://www.w3.org/2005/Atom}link")
        if atom_link is not None:
            link = atom_link.get("href", link)
        result.append({
            "title": text("title", "{http://www.w3.org/2005/Atom}title"),
            "summary": text("description", "summary", "{http://www.w3.org/2005/Atom}summary"),
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
    """智能分类：按关键词匹配将条目分到对应板块。

    items: AI HOT + RSS 聚合后的所有条目（扁平列表）
    返回：按新分类规则组织的 sections
    """
    buckets = {label: [] for label, _ in SECTION_RULES}
    buckets[DEFAULT_SECTION] = []

    for item in items:
        text = f"{item.get('title', '')} {item.get('summary', '')} {item.get('originalTitle', '')}".lower()
        placed = False

        for label, keywords in SECTION_RULES:
            if any(kw.lower() in text for kw in keywords):
                buckets[label].append(item)
                placed = True
                break

        if not placed:
            buckets[DEFAULT_SECTION].append(item)

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

    # 从 RSS 源收集
    for source_name, url in RSS_FEEDS:
        try:
            source_items = fetch_rss(source_name, url)
            for item in source_items:
                key = re.sub(r"\W+", "", item["title"].lower())
                if item["title"] and key and key not in seen:
                    seen.add(key)
                    all_items.append({
                        "title": item["title"],
                        "summary": item["summary"],
                        "source": {"name": item["source"]},
                        "links": {"original": item["link"], "aihot": item["link"]}
                    })
            print(f"     {source_name}：抓取 {len(source_items)} 条")
        except Exception as exc:
            print(f"     来源跳过：{source_name}（{exc}）")

    # 统一智能分类
    sections = classify_ai_items(all_items)

    return {
        "date": primary.get("date", ""),
        "windowStart": primary.get("windowStart", ""),
        "windowEnd": primary.get("windowEnd", ""),
        "generatedAt": primary.get("generatedAt", ""),
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


def translate_items(report, give_up_after=6):
    """英文条目译中文并保留原文；失败回退原文，不中断整体流程。

    连续 give_up_after 条都失败就放弃剩余翻译：MyMemory 按 IP 限流，被限流后
    每条都要重试到超时（实测单条约 17s），几十条能拖十几分钟。保留原文即可，
    网页和推送本来就同时展示原文。
    """
    translated, failed, consecutive_fail = 0, 0, 0
    gave_up = False
    for section in report.get("sections", []):
        for item in section.get("items", []):
            item["originalTitle"] = item.get("title", "")
            item["originalSummary"] = item.get("summary", "")
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


def pick_highlights(flat_items, top_n=5):
    """flat_items: [(entry_dict, section_label), ...]。按打分+原始序号排序取前 N 条。"""
    ranked = sorted(
        flat_items,
        key=lambda pair: (-_score_importance(pair[0]["title"] + " " + pair[0].get("originalTitle", ""), pair[1]), pair[0]["idx"]),
    )
    return [entry for entry, _label in ranked[:top_n]]

# ----------------------------- 数据整形 -----------------------------
def translate_page_url(original_url):
    """用 Google 翻译的网页代理把英文原文整页翻译成中文；只在原文确实是英文时生成。"""
    if not original_url or not re.match(r"^https?://", original_url):
        return ""
    return "https://translate.google.com/translate?sl=auto&tl=zh-CN&u=" + urllib.parse.quote(original_url, safe="")


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


def shape(report, market_insights=None, news_metrics=None):
    sections, gi = [], 0
    flat_for_ranking = []

    for s in report.get("sections", []):
        label = s.get("label", "")
        its = []
        for it in s.get("items", []):
            gi += 1
            title = it.get("title", "")
            original_title = it.get("originalTitle", title)
            original_link = it.get("links", {}).get("original", "")
            is_translated = bool(original_title) and original_title != title

            # 对所有有效的链接都生成翻译选项（不仅仅是已翻译的内容）
            # 判断是否需要翻译：有原文链接，且标题中包含英文或已被翻译
            needs_translation = bool(original_link) and (
                is_translated or
                bool(re.search(r'[a-zA-Z]{3,}', original_title))  # 包含3个以上连续英文字母
            )

            entry = {
                "idx": gi,
                "title": title,
                "originalTitle": original_title,
                "summary": it.get("summary", ""),
                "originalSummary": it.get("originalSummary", it.get("summary", "")),
                "source": it.get("source", {}).get("name", ""),
                "original": original_link,
                "aihot": it.get("links", {}).get("aihot", ""),
                "translatedPage": translate_page_url(original_link) if needs_translation else "",
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
        sections.append({"label": "📊 行业数据洞察", "items": market_items})

    meta = {
        "date": report.get("date", ""),
        "windowStart": report.get("windowStart", ""),
        "windowEnd": report.get("windowEnd", ""),
        "generatedAt": report.get("generatedAt", ""),
        "total": gi,
        "source": report.get("attribution", {}),
        "dailyUrl": report.get("links", {}).get("aihot", ""),
    }
    highlights = pick_highlights(flat_for_ranking, top_n=min(5, gi)) if gi else []
    return {
        "meta": meta,
        "sections": sections,
        "highlights": highlights,
        "newsMetrics": news_metrics or {}
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
  body{background:radial-gradient(1200px 600px at 80% -10%, #1a2233 0%, var(--bg) 55%) fixed;color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;line-height:1.6;-webkit-font-smoothing:antialiased}
  a{color:inherit;text-decoration:none}
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
  .card h3{font-size:16.5px;font-weight:700;line-height:1.45;margin-bottom:9px;text-align:justify}
  .card h3 a:hover{color:var(--accent)}
  .card .summary{font-size:14px;color:#c4ccd8;flex:1;margin-bottom:10px;text-align:justify}
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

    // Token 使用量
    if(newsMetrics.Token使用量&&newsMetrics.Token使用量.length>0){
      main+='<div class="block"><h2>🔢 Token 使用量</h2><ul style="list-style:none;padding:0">';
      newsMetrics.Token使用量.forEach(m=>{
        const company=esc(m.company||'');
        const name=esc(m.metric_name||'');
        const val=m.value||0;
        const unit=m.unit||'';
        let valStr='';
        if(unit.toLowerCase().includes('tokens')){
          valStr=val>=1e12?(val/1e12).toFixed(1)+'T tokens':val>=1e9?(val/1e9).toFixed(1)+'B tokens':val.toLocaleString()+' tokens';
        }else{
          valStr=val.toLocaleString()+' '+unit;
        }
        const ctx=m.context?'（'+esc(m.context)+'）':'';
        main+='<li style="padding:10px;border-bottom:1px solid var(--border)"><span style="color:var(--accent2);font-weight:600">'+company+'</span> '+name+' <span style="color:var(--accent);font-size:18px;font-weight:700">'+valStr+'</span> '+ctx+'</li>';
      });
      main+='</ul></div>';
    }

    // 市场份额
    if(newsMetrics.市场份额&&newsMetrics.市场份额.length>0){
      main+='<div class="block"><h2>📈 市场份额</h2><ul style="list-style:none;padding:0">';
      newsMetrics.市场份额.forEach(m=>{
        const company=esc(m.company||'');
        const name=esc(m.metric_name||'');
        const val=m.value||0;
        const valStr=(val*100).toFixed(1)+'%';
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
      main+='<p class="summary">'+esc(truncate(it.summary,120))+'</p>';
      if(it.originalTitle!==it.title||it.originalSummary!==it.summary) main+='<p class="original-text"><b>原文</b><br>'+esc(truncate(it.originalTitle,120))+'<br>'+esc(truncate(it.originalSummary,260))+'</p>';
      main+='<div class="foot"><span class="src">'+esc(it.source)+'</span><span class="linkgroup">'+(tp&&tp!=='#'?'<a class="orig" href="'+esc(tp)+'" target="_blank" rel="noopener noreferrer">翻译全文 ↗</a>':'')+'<a class="orig" href="'+esc(orig)+'" target="_blank" rel="noopener noreferrer">阅读原文 ↗</a></span></div></article>';});
    main+='</div></section>';});
  document.getElementById('main').innerHTML=main;
  const sn=(meta.source&&meta.source.name)||'AI HOT', su=(meta.source&&meta.source.url)||meta.dailyUrl||'https://aihot.virxact.com';
  document.getElementById('footerMeta').innerHTML='本期共 <b style="color:var(--accent2)">'+meta.total+'</b> 条 · 数据来源：AI HOT、VentureBeat AI、Hugging Face Blog、arXiv cs.AI、TechCrunch AI · 日报主页：<a href="'+esc(safeUrl(meta.dailyUrl))+'" target="_blank" rel="noopener noreferrer">'+esc(meta.dailyUrl)+'</a>';
})();
</script>
</body></html>"""

def build_html(data):
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return HTML_TMPL.replace("__DATA__", payload)

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
    raw, used_date, fell_back = fetch_daily(date_str)
    if fell_back:
        print(f"     当日未生成，已回退到最近一期：{used_date}")
    combined_report = aggregate_sources(raw["report"])
    combined_report = translate_items(combined_report)

    # 提取市场数据洞察
    market_insights = []
    news_metrics = []  # 新增：新闻指标数据

    if MARKET_DATA_AVAILABLE:
        try:
            print("[1.5/4] 采集市场数据洞察 ...")
            aggregator = MarketDataAggregator()
            formatter = MarketReportFormatter()

            # 聚合数据（暂不传入新闻项）
            aggregated = aggregator.aggregate(news_items=None)

            # 格式化为卡片
            market_cards = formatter.format_for_html(aggregated)

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

            print(f"     ✓ 市场数据：{len(market_insights)} 个指标卡片")

        except Exception as e:
            print(f"     [WARN] 市场数据采集失败，跳过该板块：{e}")
            market_insights = []
    else:
        print("[1.5/4] 市场数据模块未安装，跳过")

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
                return call_llm_json(system_prompt, user_prompt, model=model)

            # 提取指标
            metrics_result = extract_metrics_from_news(all_news_items, metrics_llm_caller)
            news_metrics = metrics_result.get('grouped_metrics', {})

            total_metrics = metrics_result.get('high_confidence_count', 0)
            print(f"     ✓ 提取到 {total_metrics} 个高置信度指标")
        else:
            print(f"     无新闻数据，跳过指标提取")

    except Exception as e:
        print(f"     [WARN] 指标提取失败，跳过：{e}")
        news_metrics = []

    data = shape(combined_report, market_insights=market_insights, news_metrics=news_metrics)
    print(f"     成功：共 {data['meta']['total']} 条，版块 {[s['label'] for s in data['sections']]}")

    print("[2/4] 生成 HTML 仪表盘 ...")
    out_html = os.path.join(HERE, "ai_daily_dashboard.html")
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(build_html(data))
    print(f"     已写入 {out_html}")

    print("[3/4] 渲染 Markdown 摘要 ...")
    md = build_markdown(data, dashboard_url)
    print(f"     长度 {len(md.encode('utf-8'))} 字节")

    if args.no_push:
        print("[4/4] --no-push：跳过推送。")
        print("—— Markdown 预览 ——")
        print(md[:600])
        return

    # 渠道优先级：企业微信群机器人 > 飞书群机器人 > 企业微信应用消息 > pushplus
    webhook = (os.environ.get("WECOM_WEBHOOK") or cfg.get("wecom_webhook", "")).strip()
    feishu_webhook = (os.environ.get("FEISHU_WEBHOOK") or cfg.get("feishu_webhook", "")).strip()

    if webhook:
        print("[4/4] 推送到企业微信群机器人（-> 个人微信）...")
        title = f"AI 日报 · {fmt_cst(data['meta']['date'] + 'T00:00:00+08:00', '%m月%d日 {wd}')}"
        try:
            resp = push_wecom_webhook(webhook, md, dashboard_url, title_prefix=title)
            print("     企业微信返回：", resp)
            failed = [r for r in resp if isinstance(r, dict) and r.get("errcode", 0) != 0]
            if failed:
                print("     ⚠️ 推送失败：", failed)
        except Exception as e:
            print("     ⚠️ 企业微信群机器人推送异常：", repr(e))
        return

    if feishu_webhook:
        print("[4/4] 推送到飞书群机器人（-> 飞书个人）...")
        title = f"AI 日报 · {fmt_cst(data['meta']['date'] + 'T00:00:00+08:00', '%m月%d日 {wd}')}"
        try:
            resp = push_feishu(feishu_webhook, title, md, dashboard_url)
            print("     飞书返回：", resp)
            if isinstance(resp, dict) and resp.get("StatusCode") != 0:
                print("     ⚠️ 推送失败：", resp.get("msg"), resp)
        except Exception as e:
            print("     ⚠️ 飞书推送异常：", repr(e))
        return

    if corpid and corpsecret and agentid:
        print("[4/4] 推送到企业微信（应用消息 -> 个人微信）...")
        try:
            resp = push_wecom(corpid, corpsecret, agentid, touser, md)
            print("     企业微信返回：", resp)
            if isinstance(resp, dict) and resp.get("errcode", 0) != 0:
                print("     ⚠️ 推送失败：", resp.get("errmsg"), resp)
        except Exception as e:
            print("     ⚠️ 企业微信推送异常：", repr(e))
        return

    if token:
        print("[4/4] 推送到 pushplus（个人微信）...")
        title = f"AI 日报 · {fmt_cst(data['meta']['date'] + 'T00:00:00+08:00', '%Y年%m月%d日 {wd}')}"
        resp = push_pushplus(token, md, title, api, topic or None)
        print("     pushplus 返回：", resp)
        if isinstance(resp, dict) and resp.get("code") != 200:
            print("     ⚠️ 推送可能失败，请检查返回信息。")
    else:
        print("[4/4] 未配置任何推送渠道（企业微信 WECOM_CORPID/SECRET/AGENTID 或 pushplus PUSHPLUS_TOKEN），跳过推送。")

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

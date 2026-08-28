# -*- coding: utf-8 -*-
"""
AI 日报 -> pushplus(个人微信) 每日推送管线（单文件，可独立运行）

流程：
  1. 拉取 AI HOT 当日日报；若当日未生成则回退到最近一期（按官方 skill 规则）。
  2. 同步抓取多个 AI 资讯 RSS 来源，去重后合并到仪表盘。
  3. 生成单文件 HTML 仪表盘（内联 CSS/JS，五版块，全局连续编号，≤60 字摘要，北京时间）。
  4. 渲染 Markdown 摘要（五版块要点 + 原文链接）。
  5. 推送 markdown 消息到 pushplus，再由 pushplus 转发到你的个人微信；
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

BASE = "https://aihot.virxact.com/api/v1"
UA = "aihot-skill/1.2.1 (+https://aihot.virxact.com/aihot-skill/)"
# 中国标准时间 = UTC+8（无夏令时），无需 tzdata 依赖
CST_OFFSET = timedelta(hours=8)
HERE = __import__("os").path.dirname(__import__("os").path.abspath(__file__))

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
        result.append({"title": text("title", "{http://www.w3.org/2005/Atom}title"), "summary": text("description", "summary", "{http://www.w3.org/2005/Atom}summary"), "link": link, "source": source_name})
    return result


def aggregate_sources(primary):
    sections = [{"label": s.get("label", ""), "items": list(s.get("items", []))} for s in primary.get("sections", [])]
    extra_items = []
    for source_name, url in RSS_FEEDS:
        try:
            source_items = fetch_rss(source_name, url)
            extra_items.extend(source_items)
            print(f"     {source_name}：抓取 {len(source_items)} 条")
        except Exception as exc:
            print(f"     来源跳过：{source_name}（{exc}）")
    if extra_items:
        sections.append({"label": "全网 AI 资讯", "items": []})
    if not sections:
        sections = [{"label": "全网 AI 资讯", "items": []}]
    seen = {re.sub(r"\W+", "", item.get("title", "").lower()) for section in sections for item in section["items"]}
    target = sections[-1]["items"]
    for item in extra_items:
        key = re.sub(r"\W+", "", item["title"].lower())
        if item["title"] and key and key not in seen:
            seen.add(key)
            target.append({"title": item["title"], "summary": item["summary"], "source": {"name": item["source"]}, "links": {"original": item["link"], "aihot": item["link"]}})
    return {"date": primary.get("date", ""), "windowStart": primary.get("windowStart", ""), "windowEnd": primary.get("windowEnd", ""), "generatedAt": primary.get("generatedAt", ""), "attribution": primary.get("attribution", {}), "links": primary.get("links", {}), "sections": sections}

TRANSLATE_API = "https://api.mymemory.translated.net/get"


def translate_text(text, target="zh-CN", retries=3):
    if not text or not re.search(r"[A-Za-z]", text):
        return text
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()[:490]
    query = urllib.parse.urlencode({"q": text, "langpair": f"en|{target}"})
    req = urllib.request.Request(f"{TRANSLATE_API}?{query}", headers={"User-Agent": "Mozilla/5.0"})
    last_exc = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
            translated = payload.get("responseData", {}).get("translatedText", "")
            if not translated or payload.get("responseStatus") not in (200, "200"):
                raise ValueError(f"响应异常：{payload.get('responseStatus')}")
            return html.unescape(translated).strip()
        except (urllib.error.HTTPError, urllib.error.URLError, ValueError) as exc:
            last_exc = exc
            time.sleep(2 * (attempt + 1))
            continue
    raise last_exc


def translate_items(report):
    translated, failed = 0, 0
    for section in report.get("sections", []):
        for item in section.get("items", []):
            item["originalTitle"] = item.get("title", "")
            item["originalSummary"] = item.get("summary", "")
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
            else:
                failed += 1
    print(f"     翻译完成：{translated} 条，失败：{failed} 条")
    return report

# ----------------------------- 数据整形 -----------------------------
def shape(report):
    sections, gi = [], 0
    for s in report.get("sections", []):
        its = []
        for it in s.get("items", []):
            gi += 1
            its.append({
                "idx": gi,
                "title": it.get("title", ""),
                "originalTitle": it.get("originalTitle", it.get("title", "")),
                "summary": it.get("summary", ""),
                "originalSummary": it.get("originalSummary", it.get("summary", "")),
                "source": it.get("source", {}).get("name", ""),
                "original": it.get("links", {}).get("original", ""),
                "aihot": it.get("links", {}).get("aihot", ""),
            })
        sections.append({"label": s.get("label", ""), "items": its})
    meta = {
        "date": report.get("date", ""),
        "windowStart": report.get("windowStart", ""),
        "windowEnd": report.get("windowEnd", ""),
        "generatedAt": report.get("generatedAt", ""),
        "total": gi,
        "source": report.get("attribution", {}),
        "dailyUrl": report.get("links", {}).get("aihot", ""),
    }
    return {"meta": meta, "sections": sections}

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
  .hero{padding:54px 0 30px}
  .kicker{display:inline-flex;align-items:center;gap:8px;font-size:13px;letter-spacing:.18em;color:var(--accent2);text-transform:uppercase;border:1px solid var(--border);padding:5px 12px;border-radius:999px;background:var(--bg2)}
  .hero h1{font-size:clamp(30px,5vw,52px);font-weight:800;margin:16px 0 6px;letter-spacing:-.5px}
  .hero h1 .sub{color:var(--accent)}
  .hero .date{font-size:18px;color:var(--text);font-weight:600}
  .hero .window{font-size:14px;color:var(--muted);margin-top:4px}
  .stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin-top:26px}
  .stat{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:16px 18px}
  .stat .num{font-size:30px;font-weight:800;color:var(--accent)}
  .stat .lbl{font-size:13px;color:var(--muted);margin-top:2px}
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
  .card h3{font-size:16.5px;font-weight:700;line-height:1.45;margin-bottom:9px}
  .card h3 a:hover{color:var(--accent)}
  .card .summary{font-size:14px;color:#c4ccd8;flex:1;margin-bottom:10px}
  .card .original-text{font-size:12.5px;color:var(--muted);border-top:1px solid var(--border);padding-top:10px;margin-bottom:14px}
  .card .foot{display:flex;align-items:center;justify-content:space-between;gap:10px}
  .src{font-size:12.5px;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .orig{font-size:13px;font-weight:600;color:var(--accent);border:1px solid var(--border);padding:6px 12px;border-radius:10px;background:var(--bg2);white-space:nowrap;transition:.15s}
  .orig:hover{background:var(--accent);color:#0c1320;border-color:var(--accent)}
  footer{border-top:1px solid var(--border);margin-top:18px;padding:26px 0 50px;color:var(--muted);font-size:13.5px}
  footer .wrap{display:flex;flex-wrap:wrap;gap:8px 18px;align-items:center;justify-content:space-between}
  footer a{color:var(--accent);border-bottom:1px dotted var(--accent)}
  .note{font-size:12.5px;color:#6f7a8a;margin-top:10px;width:100%}
  @media (max-width:560px){.hero{padding:38px 0 22px}.grid{grid-template-columns:1fr}}
</style>
</head>
<body>
<header class="hero"><div class="wrap">
  <span class="kicker">● AI 日报 · 多来源聚合</span>
  <h1>AI 日报 <span class="sub">晨报仪表盘</span></h1>
  <div class="date" id="heroDate">—</div>
  <div class="window" id="heroWindow">—</div>
  <div class="stats" id="heroStats"></div>
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
(function render(){
  const meta=DATA.meta, sections=DATA.sections;
  document.getElementById('heroDate').textContent=fmtBeijing(meta.date+'T00:00:00+08:00',{year:'numeric',month:'long',day:'numeric',weekday:'long'})+'（北京时间）';
  document.getElementById('heroWindow').textContent='收录窗口：'+fmtBeijing(meta.windowStart,{month:'long',day:'numeric',hour:'2-digit',minute:'2-digit'})+' — '+fmtBeijing(meta.windowEnd,{month:'long',day:'numeric',hour:'2-digit',minute:'2-digit'})+'（北京时间）';
  let st='<div class="stat total"><div class="num">'+meta.total+'</div><div class="lbl">总条数</div></div>';
  sections.forEach(s=>{st+='<div class="stat"><div class="num">'+s.items.length+'</div><div class="lbl">'+esc(s.label)+'</div></div>';});
  document.getElementById('heroStats').innerHTML=st;
  let nav='';sections.forEach((s,i)=>{nav+='<a href="#sec-'+i+'">'+esc(s.label)+'<b>'+s.items.length+'</b></a>';});
  document.getElementById('navLinks').innerHTML=nav;
  let main='';sections.forEach((s,i)=>{main+='<section class="section" id="sec-'+i+'"><div class="section-head"><h2>'+esc(s.label)+'</h2><span class="count">'+s.items.length+' 条</span></div><div class="grid">';
    s.items.forEach(it=>{const orig=it.original||it.aihot||'#';const tl=it.aihot||it.original||'#';
      main+='<article class="card"><div class="top"><span class="idx">'+it.idx+'</span><span class="chip" title="'+esc(it.source)+'">'+esc(it.source)+'</span></div>';
      main+='<h3><a href="'+esc(tl)+'" target="_blank" rel="noopener noreferrer">'+esc(it.title)+'</a></h3>';
      main+='<p class="summary">'+esc(truncate(it.summary,120))+'</p>';
      if(it.originalTitle!==it.title||it.originalSummary!==it.summary) main+='<p class="original-text"><b>原文</b><br>'+esc(truncate(it.originalTitle,120))+'<br>'+esc(truncate(it.originalSummary,260))+'</p>';
      main+='<div class="foot"><span class="src">'+esc(it.source)+'</span><a class="orig" href="'+esc(orig)+'" target="_blank" rel="noopener noreferrer">阅读原文 ↗</a></div></article>';});
    main+='</div></section>';});
  document.getElementById('main').innerHTML=main;
  const sn=(meta.source&&meta.source.name)||'AI HOT', su=(meta.source&&meta.source.url)||meta.dailyUrl||'https://aihot.virxact.com';
  document.getElementById('footerMeta').innerHTML='本期共 <b style="color:var(--accent2)">'+meta.total+'</b> 条 · 数据来源：AI HOT、VentureBeat AI、Hugging Face Blog、arXiv cs.AI、TechCrunch AI · 日报主页：<a href="'+esc(meta.dailyUrl)+'" target="_blank" rel="noopener noreferrer">'+esc(meta.dailyUrl)+'</a>';
})();
</script>
</body></html>"""

def build_html(data):
    return HTML_TMPL.replace("__DATA__", json.dumps(data, ensure_ascii=False))

# ----------------------------- Markdown 摘要 -----------------------------
def build_markdown(data, dashboard_url):
    meta, sections = data["meta"], data["sections"]
    date_human = fmt_cst(meta["date"] + "T00:00:00+08:00", "%Y年%m月%d日 {wd}")
    ws = fmt_cst(meta["windowStart"], "%m/%d %H:%M")
    we = fmt_cst(meta["windowEnd"], "%m/%d %H:%M")
    lines = []
    lines.append(f"# AI 日报 · {date_human}")
    lines.append(f"> 总条数 **{meta['total']}** · 收录窗口 {ws}–{we}（北京时间）")
    for s in sections:
        lines.append(f"## {s['label']}（{len(s['items'])}）")
        for it in s["items"]:
            link = it["original"] or it["aihot"] or "#"
            title = it["title"].replace("[", "【").replace("]", "】")
            lines.append(f"> **{it['idx']}.** [{title}]({link})　*— {it['source']}*")
            if it.get("originalTitle") and it["originalTitle"] != it["title"]:
                lines.append(f"> English: {it['originalTitle']}")
    if dashboard_url:
        lines.append(f"\n[📊 查看完整仪表盘]({dashboard_url})")
    else:
        lines.append(f"\n[📊 AI HOT 日报主页]({meta['dailyUrl']})")
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

def truncate_bytes(s, max_bytes):
    """按字符截断，保证 UTF-8 字节数 <= max_bytes，避免截断半个中文字。"""
    if len(s.encode("utf-8")) <= max_bytes:
        return s
    out, total = [], 0
    for ch in s:
        b = len(ch.encode("utf-8"))
        if total + b > max_bytes:
            break
        out.append(ch); total += b
    return "".join(out) + "\n…（完整版见仪表盘链接）"

def push_wecom_webhook(webhook, markdown, dashboard_url=None):
    """企业微信群机器人 -> 个人微信。无需 access_token、无需 IP 白名单。
    发两条：① news 图文卡片（按钮卡片，点击打开完整仪表盘网页）② markdown 摘要。"""
    results = []
    if dashboard_url:
        news = {
            "msgtype": "news",
            "news": {
                "articles": [{
                    "title": "📊 查看完整仪表盘（网页版）",
                    "description": "AI 日报 · 全部版块 · 卡片式网页，点击打开",
                    "url": dashboard_url,
                    "picurl": "https://picsum.photos/id/1015/600/400",
                }]
            },
        }
        results.append(http_post_json(webhook, news))
    content = truncate_bytes(markdown, 3900)  # 群机器人 markdown 上限 4096 字节
    results.append(http_post_json(webhook, {"msgtype": "markdown", "markdown": {"content": content}}))
    return results


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
        cfg = json.load(open(cfg_path, encoding="utf-8"))
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
    data = shape(combined_report)
    print(f"     成功：共 {data['meta']['total']} 条，版块 {[s['label'] for s in data['sections']]}")

    print("[2/4] 生成 HTML 仪表盘 ...")
    out_html = os.path.join(HERE, "ai_daily_dashboard.html")
    open(out_html, "w", encoding="utf-8").write(build_html(data))
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
        try:
            resp = push_wecom_webhook(webhook, md, dashboard_url)
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
        return

    print("[4/4] 未配置任何推送渠道（企业微信 WECOM_CORPID/SECRET/AGENTID 或 pushplus PUSHPLUS_TOKEN），跳过推送。")

if __name__ == "__main__":
    main()

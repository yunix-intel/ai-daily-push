#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
博主博客抓取器 - 抓取指定博主近 N 小时内的博文

目前支持新浪博客（blog.sina.com.cn）。新浪博客是少数还保留纯静态 HTML
列表页的平台：文章列表、标题、时间戳、正文全部在服务端渲染好，
不需要登录、不需要执行 JS、也没有反爬。

刻意不支持微博：微博的 m.weibo.cn API 对未登录客户端返回 HTTP 432，
游客系统（visitor.passport.weibo.cn）拿到的 cookie 只对 .weibo.com 域有效，
换不到 m.weibo.cn 的内容。要抓微博必须上无头浏览器执行 JS 挑战，
那是另一个量级的依赖，不放在这个模块里。
"""
import re
import time
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

from .base_scraper import BaseScraper


# 新浪博客列表页：uid 是纯数字，_0_1 表示「全部分类第 1 页」。
# 一页 50 条，对 24 小时窗口来说远远够用（最高产的博主一天也就几篇）。
SINA_LIST_URL = "https://blog.sina.com.cn/s/articlelist_{uid}_0_1.html"

# 正文容器。新浪博客模板换过几版，两个 id/class 都可能出现。
BODY_SELECTORS = ("#sina_keyword_ad_area2", ".articalContent", "#articlebody")

# 每篇博文都重复的样板段落，占 LLM 上下文又没有信息量。
# 按行匹配后整行丢弃，不做模糊替换——避免误伤正文里正常提到的「微信」等词。
BOILERPLATE_PATTERNS = (
    r"^\s*点击进入\s*$",
    r"骗子|冒充|诈骗|上当受骗",
    r"本人没有\s*QQ|不代客理财|不提供指导",
    r"^\s*微信(公众号|号)[:：]",
    r"^\s*(声明|提示|风险提示)[:：]?\s*$",
    r"股市有风险.{0,12}入市需谨慎",
    r"^\s*(转载|分享|阅读|收藏|喜欢|赠金笔)\s*$",
)
_BOILERPLATE_RE = re.compile("|".join(BOILERPLATE_PATTERNS))


# 盘中直播贴的标题形如「徐小明：9月1日盘中即时直播」。
# 这类帖子的发布时间和内容时间对不上——前一交易日收盘后先发一个空壳，
# 次日开盘后把播报逐条追加进正文。按发布时间过滤会永远漏掉正文，
# 所以单独识别，用标题里的日期当作内容日期。
LIVE_TITLE_RE = re.compile(r"(\d{1,2})月(\d{1,2})日.*?(?:盘中|即时|直播)")


class BloggerScraper(BaseScraper):
    """按博主抓取近期博文"""

    def __init__(self, cache_dir="data/market_data", timeout=25,
                 min_interval=1.5):
        super().__init__(cache_dir=cache_dir, timeout=timeout)
        # 新浪对连续请求会返回 HTTP 418（它拿这个码当限流用，不是标准语义）。
        # 实测密集抓取几次就会触发，所以请求之间强制留间隔。
        self.min_interval = min_interval
        self._last_request = 0.0

    # ---------- 内部工具 ----------

    def _throttle(self):
        """两次请求之间至少间隔 min_interval 秒。"""
        wait = self.min_interval - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def _get_soup(self, url, retries=2):
        """取回页面并解析。新浪博客的 charset 声明不总是可信，用探测编码。

        418 是新浪的限流响应，退避后重试往往就过了；其余状态码直接抛。
        """
        last_exc = None
        for attempt in range(retries + 1):
            self._throttle()
            try:
                resp = requests.get(url, headers={"User-Agent": self.user_agent},
                                    timeout=self.timeout)
                if resp.status_code == 418:
                    raise requests.HTTPError("418 限流", response=resp)
                resp.raise_for_status()
                # apparent_encoding 基于内容探测，比 headers 里声明的准；
                # 直接信 headers 会把 GBK 页面解成乱码，正文里全是 U+FFFD。
                resp.encoding = resp.apparent_encoding or resp.encoding
                return BeautifulSoup(resp.text, "html.parser")
            except requests.HTTPError as exc:
                last_exc = exc
                code = getattr(exc.response, "status_code", None)
                if code != 418 or attempt == retries:
                    raise
                backoff = 5 * (attempt + 1)
                print(f"     [WARN] 新浪限流(418)，{backoff}s 后重试 "
                      f"{attempt + 1}/{retries}")
                time.sleep(backoff)
        raise last_exc

    @staticmethod
    def _abs_url(href):
        """列表页里的链接是协议相对的（//blog.sina.com.cn/...）。"""
        if href.startswith("//"):
            return "https:" + href
        if href.startswith("/"):
            return "https://blog.sina.com.cn" + href
        return href

    @staticmethod
    def _clean_body(text):
        """去掉每篇都重复的样板行，并压掉多余空行。"""
        kept = [line.strip() for line in text.split("\n")
                if line.strip() and not _BOILERPLATE_RE.search(line)]
        return "\n".join(kept)

    @staticmethod
    def _effective_time(title, published):
        """内容时间：正常博文就是发布时间，盘中直播贴取标题里的日期。

        直播贴在前一交易日收盘后就发出来了（空壳），次日盘中才把播报追加进正文。
        用发布时间判断新鲜度会得出「这篇是昨天的」，把当天写满的直播整篇滤掉。

        标题只有月日没有年份，跨年时（12月发出、标题写「1月2日」）直接套发布年
        会算成一年前。所以在发布年的前后各试一次，取离发布时间最近的那个。
        """
        match = LIVE_TITLE_RE.search(title or "")
        if not match:
            return published, False

        month, day = int(match.group(1)), int(match.group(2))
        best = None
        for year in (published.year - 1, published.year, published.year + 1):
            try:
                candidate = datetime(year, month, day, 15, 0)
            except ValueError:
                continue  # 2月30日之类的脏标题
            if best is None or abs(candidate - published) < abs(best - published):
                best = candidate
        if best is None:
            return published, False
        # 直播当天的内容按收盘时刻计；若解析出的日期比发布时间还早，
        # 说明标题日期不是「下一个交易日」，退回发布时间更保险。
        return (best, True) if best >= published else (published, False)

    # ---------- 对外接口 ----------

    def fetch_article_list(self, uid):
        """
        抓取博主的文章列表（第 1 页，最多 50 条）。

        Returns:
            list[dict]: [{title, url, published(datetime)}, ...] 按时间倒序
        """
        soup = self._get_soup(SINA_LIST_URL.format(uid=uid))

        articles = []
        for cell in soup.select("div.articleCell"):
            link = cell.select_one("span.atc_title a")
            stamp = cell.select_one("span.atc_tm")
            if not (link and stamp):
                continue

            # 列表页的时间戳没有秒：2026-08-31 16:28
            try:
                published = datetime.strptime(stamp.get_text(strip=True),
                                              "%Y-%m-%d %H:%M")
            except ValueError:
                continue

            title = link.get_text(strip=True)
            href = link.get("href") or ""
            if not (title and href):
                continue

            effective, is_live = self._effective_time(title, published)
            articles.append({
                "title": title,
                "url": self._abs_url(href),
                "published": published,
                "effective": effective,
                "is_live": is_live,
            })

        return articles

    def fetch_article_body(self, url):
        """抓取单篇正文。失败返回空字符串，让调用方保留标题继续走。"""
        try:
            soup = self._get_soup(url)
        except Exception as exc:
            print(f"     [WARN] 正文抓取失败 {url}：{exc!r}")
            return ""

        for selector in BODY_SELECTORS:
            node = soup.select_one(selector)
            if node:
                return self._clean_body(node.get_text("\n", strip=True))
        return ""

    def fetch_recent(self, uid, name="", hours=24, max_articles=6,
                     with_body=True):
        """
        抓取博主近 N 小时内的博文。

        Args:
            uid: 新浪博客数字 uid
            name: 博主显示名（仅用于日志和输出）
            hours: 时间窗口
            max_articles: 最多取几篇（防止某天刷屏把上下文占满）
            with_body: 是否抓正文

        Returns:
            dict: {name, uid, articles: [...], available: bool}
        """
        label = name or uid
        result = {"name": name, "uid": str(uid), "articles": [], "available": False}

        try:
            listing = self.fetch_article_list(uid)
        except Exception as exc:
            print(f"     [!] {label} 列表抓取失败：{exc!r}")
            return result

        if not listing:
            # 能打开但一条都解析不出来，通常意味着新浪换了模板
            print(f"     [!] {label} 列表页解析不出文章，可能是模板变更")
            return result

        cutoff = datetime.now() - timedelta(hours=hours)
        # 按内容时间过滤，不按发布时间——见 _effective_time 的说明。
        # 上界卡在「现在」：直播贴的 effective 是当天 15:00，早盘推送时
        # 那个时刻还没到，不排除的话会把今天尚未写入内容的空壳也算进来。
        now = datetime.now()
        fresh = [a for a in listing
                 if cutoff <= a["effective"] and a["published"] <= now][:max_articles]

        # 区分「源正常但今天没发」和「源已停更」：后者值得提醒，
        # 前者是常态（周末、休市日博主本来就不发）。
        newest = max(a["published"] for a in listing)
        stale_days = (datetime.now() - newest).days
        if not fresh and stale_days >= 30:
            print(f"     [!] {label} 最新一篇是 {newest:%Y-%m-%d}，"
                  f"已停更 {stale_days} 天，建议确认该源是否还有效")
            return result

        result["available"] = True
        if not fresh:
            print(f"     {label}：{hours}h 内无更新（最新 {newest:%m-%d %H:%M}）")
            return result

        for art in fresh:
            body = self.fetch_article_body(art["url"]) if with_body else ""
            # 直播贴的空壳（还没开盘）没有信息量，别送去占 LLM 上下文
            if art["is_live"] and len(body) < 60:
                continue
            result["articles"].append({
                "title": art["title"],
                "url": art["url"],
                "published": art["published"].strftime("%Y-%m-%d %H:%M"),
                "isLive": art["is_live"],
                "content": body,
            })

        if not result["articles"]:
            print(f"     {label}：{hours}h 内 {len(fresh)} 篇均无有效正文")
            return result

        total_chars = sum(len(a["content"]) for a in result["articles"])
        print(f"     {label}：{hours}h 内 {len(result['articles'])} 篇，"
              f"正文合计 {total_chars} 字")
        return result

    def fetch_all(self, bloggers, hours=24, max_articles=6):
        """
        批量抓取多个博主。单个博主失败不影响其他人。

        Args:
            bloggers: [{"name": "徐小明", "uid": "1300871220"}, ...]

        Returns:
            list[dict]: 只包含 available 且有文章的博主
        """
        collected = []
        for blogger in bloggers:
            uid = blogger.get("uid")
            if not uid:
                continue
            data = self.fetch_recent(uid, name=blogger.get("name", ""),
                                     hours=hours, max_articles=max_articles)
            if data["articles"]:
                collected.append(data)
        return collected


def test_scraper():
    """本地自测：抓徐小明近 24 小时的博文"""
    scraper = BloggerScraper()
    data = scraper.fetch_recent("1300871220", name="徐小明", hours=24)
    print(f"\navailable={data['available']}  文章数={len(data['articles'])}")
    for art in data["articles"]:
        print(f"\n  [{art['published']}] {art['title']}")
        print(f"  {art['url']}")
        preview = art["content"][:120].replace("\n", " ")
        print(f"  {preview}...")


if __name__ == "__main__":
    test_scraper()

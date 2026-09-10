#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Twitter/X 财经传言抓取模块
通过 RSSHub 获取重要财经账号的推文，用 LLM 过滤噪音并提取核心观点
"""
import os
import json
import time
from typing import List, Dict, Optional
import xml.etree.ElementTree as ET
import requests
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta


class TwitterScraper:
    """Twitter 财经传言抓取器"""

    # 小道消息/爆料型账号（先于公开公布）
    RUMOR_ACCOUNTS = [
        "unusual_whales",      # 🐋 期权异动监测（大单追踪）
        "HindenburgRes",       # 🔍 兴登堡研究（做空机构爆料）
        "muddywatersre",       # 💧 浑水研究（做空机构）
        "CitronResearch",      # 🍋 香橼研究（做空机构）
        "zerohedge",           # ⚡ Zero Hedge（快速市场消息）
        "DeItaone",            # 📊 实时新闻爆料
        "Fxhedgers",           # 💱 外汇市场传言
    ]

    # 正规媒体账号（权威报道）
    MEDIA_ACCOUNTS = [
        "WSJ",                 # 📰 华尔街日报
        "Bloomberg",           # 📈 彭博社
        "FinancialTimes",      # 💼 金融时报
        "Reuters",             # 🌐 路透社
        "business",            # 📊 Bloomberg Business
        "markets",             # 💹 Bloomberg Markets
    ]

    # 默认使用小道消息账号
    DEFAULT_ACCOUNTS = RUMOR_ACCOUNTS

    # 默认 RSSHub 镜像列表（按优先级排序）
    DEFAULT_MIRRORS = [
        "https://rsshub.app",
        "https://rsshub.rssforever.com",
        "https://rsshub.ktachibana.party",
    ]

    def __init__(self, rsshub_base=None, timeout=None):
        """
        初始化 Twitter 抓取器

        Args:
            rsshub_base: RSSHub 服务地址（可选，默认使用镜像列表）
            timeout: 请求超时时间（秒）
        """
        # 如果指定了单一地址，只用它；否则从镜像列表依次尝试
        self.rsshub_mirrors = [rsshub_base.rstrip("/")] if rsshub_base else self.DEFAULT_MIRRORS
        self.timeout = timeout if timeout is not None else float(os.getenv("RSSHUB_TIMEOUT", "5"))
        self.max_mirrors = max(1, int(os.getenv("RSSHUB_MAX_MIRRORS", "2")))
        self.user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )

    def fetch_tweets(self, username: str, limit: int = 10) -> Dict:
        """
        抓取指定用户的最新推文

        Args:
            username: Twitter 用户名
            limit: 最多返回多少条推文

        Returns:
            dict: {
                "tweets": 推文列表，每条包含 title, content, link, pub_date, username
                "available": bool,
                "error": str (失败时),
                "source_url": str (使用的镜像地址)
            }
        """
        last_error = None

        for mirror in self.rsshub_mirrors[:self.max_mirrors]:
            url = f"{mirror}/twitter/user/{username}"

            try:
                headers = {"User-Agent": self.user_agent}
                response = requests.get(url, headers=headers, timeout=self.timeout)
                response.raise_for_status()

                # 解析 RSS XML
                root = ET.fromstring(response.content)

                tweets = []
                for item in root.findall(".//item")[:limit]:
                    title = item.findtext("title", "").strip()
                    link = item.findtext("link", "").strip()
                    pub_date_str = item.findtext("pubDate", "")
                    description = item.findtext("description", "").strip()

                    # 解析发布时间
                    pub_date = None
                    if pub_date_str:
                        try:
                            from dateutil.parser import parse
                            pub_date = parse(pub_date_str)
                        except Exception:
                            pass

                    tweets.append({
                        "title": title,
                        "content": description,
                        "link": link,
                        "pub_date": pub_date,
                        "username": username
                    })

                state = "rsshub" if tweets else "no_content"
                return {
                    "tweets": tweets,
                    "available": bool(tweets),
                    "source": "rsshub",
                    "source_url": "rsshub",
                    "provenance": state,
                    "attempted_sources": ["rsshub"],
                    **({"error": "RSSHub 返回空内容"} if not tweets else {}),
                }

            except Exception as e:
                last_error = repr(e)
                continue

        # 所有镜像都失败
        attempted = min(len(self.rsshub_mirrors), self.max_mirrors)
        print(f"     [WARN] 抓取 @{username} 失败，已尝试 {attempted} 个镜像")
        return {
            "tweets": [],
            "available": False,
            "error": last_error or "所有 RSSHub 镜像均不可用",
            "source": "rsshub",
            "source_url": "",
            "provenance": "source_failed",
            "attempted_sources": ["rsshub"],
        }

    def fetch_multiple_accounts(self, accounts: Optional[List[str]] = None,
                               limit_per_account: int = 5,
                               hours: int = 24) -> Dict:
        """
        批量抓取多个账号的推文，并按时间窗口过滤

        Args:
            accounts: Twitter 账号列表，None 时使用默认列表
            limit_per_account: 每个账号最多抓取多少条
            hours: 时间窗口（小时）

        Returns:
            dict: {
                "tweets": 所有推文的合并列表（已按时间过滤）,
                "available": bool,
                "failed_accounts": [失败的账号列表],
                "error": str (全部失败时)
            }
        """
        if accounts is None:
            accounts = self.DEFAULT_ACCOUNTS

        all_tweets = []
        failed_accounts = []

        from datetime import datetime, timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        def fetch_one(username):
            return username, self.fetch_tweets(username, limit=limit_per_account)

        with ThreadPoolExecutor(max_workers=min(3, max(1, len(accounts)))) as executor:
            fetched = list(executor.map(fetch_one, accounts))

        for username, fetch_result in fetched:
            if fetch_result["available"]:
                fresh_tweets = [
                    t for t in fetch_result["tweets"]
                    if t.get("pub_date") and t["pub_date"] >= cutoff
                ]
                all_tweets.extend(fresh_tweets)
            else:
                failed_accounts.append(username)

        if not all_tweets:
            state = "source_failed" if len(failed_accounts) == len(accounts) else "no_content"
            error_msg = "所有账号均抓取失败" if state == "source_failed" else f"{hours}小时内无新推文"
            return {
                "tweets": [],
                "available": False,
                "failed_accounts": failed_accounts,
                "error": error_msg,
                "source": "rsshub",
                "provenance": state,
                "attempted_sources": ["rsshub"],
            }

        return {
            "tweets": all_tweets,
            "available": True,
            "failed_accounts": failed_accounts,
            "source": "rsshub",
            "provenance": "rsshub",
            "attempted_sources": ["rsshub"],
        }

    def filter_and_summarize(self, tweets: List[Dict], llm_caller,
                            max_rumors: int = 5, category: str = "rumors",
                            analysis_model: Optional[str] = None) -> List[Dict]:
        """
        使用 LLM 过滤噪音并提取核心观点

        Args:
            tweets: 推文列表
            llm_caller: LLM 调用函数 (system_prompt, user_prompt, model) -> str
            max_rumors: 最多返回多少条传言
            category: "rumors" 或 "media"，用于调整 LLM 提示词

        Returns:
            过滤后的传言列表，包含 title, summary, source, link, impact, verification
        """
        if not tweets:
            return []

        # 构建 LLM 提示词
        tweet_list = []
        for i, tweet in enumerate(tweets[:20], 1):  # 最多分析20条
            content = tweet.get("content", "")[:200]  # 限制长度
            username = tweet.get("username", "")
            pub_date = tweet.get("pub_date")
            time_str = pub_date.strftime("%m-%d %H:%M") if pub_date else ""
            tweet_list.append(f"{i}. @{username} [{time_str}]: {content}")

        if category == "media":
            system_prompt = """你是财经新闻分析专家。
从正规媒体推文中提取重要财经报道，过滤广告和无关内容。
只返回 JSON 数组，不要其他文字。"""
            impact_field = "报道重要性分析（30字内）"
        elif category == "comments":
            system_prompt = """你是财经市场讨论分析专家。
从公开推文中提取有信息量的市场讨论，过滤广告、纯情绪和无依据喊单。
所有内容均标记为“未经证实”，不得当作事实或正规媒体报道。
只返回 JSON 数组，不要其他文字。"""
            impact_field = "讨论焦点（30字内）"
        else:
            system_prompt = """你是财经市场传言分析专家。
从推文中识别有价值的市场传言，过滤噪音（广告、无关内容）。
传言标记为"未经证实"，需谨慎对待。
只返回 JSON 数组，不要其他文字。"""
            impact_field = "市场影响分析（30字内）"

        if category == "media":
            content_type = "财经报道"
        elif category == "comments":
            content_type = "公开市场讨论"
        else:
            content_type = "市场传言"
        user_prompt = f"""分析以下 Twitter 推文，提取有价值的{content_type}。

筛选标准：
- ✅ 保留：市场动向、重大交易、公司并购、监管变化、重要人物观点
- ❌ 过滤：广告、无关话题、纯转发、情绪化评论

推文列表：
{chr(10).join(tweet_list)}

返回 JSON 数组（最多{max_rumors}条），每条包含：
{{
  "title": "标题（简短）",
  "summary": "核心内容摘要",
  "source": "@用户名",
  "impact": "{impact_field}",
  "verification": "{'confirmed' if category == 'media' else 'unverified'}",
  "idx": 原推文编号
}}

示例：
[
  {{
    "title": "特斯拉考虑收购某供应商",
    "summary": "据知情人士透露，特斯拉正在洽谈收购其电池供应商...",
    "source": "@zerohedge",
    "impact": "可能影响电动车供应链格局",
    "verification": "unverified",
    "idx": 3
  }}
]
"""

        try:
            result = llm_caller(system_prompt, user_prompt, model=analysis_model)

            # 解析 JSON
            if isinstance(result, str):
                result = json.loads(result)

            # 提取数组
            if isinstance(result, dict):
                for value in result.values():
                    if isinstance(value, list):
                        result = value
                        break

            # 添加链接和分类标记
            rumors = []
            for item in result[:max_rumors]:
                idx = item.get("idx", 0) - 1
                if 0 <= idx < len(tweets):
                    item["link"] = tweets[idx].get("link", "#")
                    item["pub_date"] = tweets[idx].get("pub_date")
                    for field in ("username", "author_id", "id", "conversation_id",
                                  "in_reply_to_user_id", "public_metrics", "content", "source"):
                        if field not in item and field in tweets[idx]:
                            item[field] = tweets[idx][field]
                else:
                    item["link"] = "#"
                    item["pub_date"] = None

                # 确保 verification 字段存在
                if "verification" not in item:
                    item["verification"] = "confirmed" if category == "media" else "unverified"

                item["category"] = category
                rumors.append(item)

            return rumors

        except Exception as e:
            print(f"     [WARN] LLM 过滤失败：{e}")
            return []


def fetch_twitter_rumors(llm_caller, accounts: Optional[List[str]] = None,
                        max_rumors: int = 5) -> List[Dict]:
    """便捷函数：抓取并过滤 Twitter 财经传言。"""
    scraper = TwitterScraper()

    # 抓取推文
    print(f"     抓取 {len(accounts or scraper.DEFAULT_ACCOUNTS)} 个账号的推文...")
    fetch_result = scraper.fetch_multiple_accounts(accounts=accounts, limit_per_account=5)
    tweets = fetch_result["tweets"]
    print(f"     获取到 {len(tweets)} 条推文")

    if not fetch_result["available"]:
        print(f"     [WARN] Twitter 数据源不可用：{fetch_result.get('error', '未知错误')}")
        return []

    # 过滤并提取传言
    print(f"     使用 LLM 过滤噪音...")
    rumors = scraper.filter_and_summarize(tweets, llm_caller, max_rumors=max_rumors,
                                          analysis_model=None)
    print(f"     提取到 {len(rumors)} 条有价值传言")

    return rumors


def _fetch_official_accounts(scraper, accounts, limit_per_account, hours):
    """Fetch configured accounts through the optional official X API."""
    from .x_api_scraper import XApiScraper

    api = XApiScraper()
    if not api.configured:
        return api._unavailable("X_BEARER_TOKEN 未配置", "not_configured")
    fetched = []
    failed = []
    failure_states = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    for username in accounts:
        result = api.fetch_username_tweets(username, limit=limit_per_account)
        if not result.get("available"):
            failed.append(username)
            failure_states.append(result.get("provenance", "source_failed"))
            continue
        fetched.extend(t for t in result.get("tweets", [])
                       if t.get("pub_date") and t["pub_date"] >= cutoff)
    if not fetched:
        if failure_states and all(state == "auth_failed" for state in failure_states):
            state = "auth_failed"
        elif failure_states and all(state == "quota_limited" for state in failure_states):
            state = "quota_limited"
        elif failure_states and all(state == "not_configured" for state in failure_states):
            state = "not_configured"
        elif failed and len(failed) == len(accounts):
            state = "source_failed"
        else:
            state = "no_content"
        return api._unavailable(
            "官方 X API 没有可用内容", state, failed_accounts=failed,
        )
    return {
        "tweets": fetched,
        "available": True,
        "failed_accounts": failed,
        "source": "official_x_api",
        "provenance": "official_x_api",
        "attempted_sources": ["official_x_api"],
    }


def _fetch_official_comments(terms, limit=20):
    """Fetch public finance discussion through Recent Search when configured."""
    from .x_api_scraper import XApiScraper

    api = XApiScraper()
    if not api.configured:
        return api._unavailable("X_BEARER_TOKEN 未配置", "not_configured")
    return api.fetch_finance_comments(terms, limit=limit)


def fetch_twitter_categorized(llm_caller, max_per_category: int = 5, hours: int = 24,
                              analysis_model: Optional[str] = None) -> Dict[str, List[Dict]]:
    """
    分类抓取 Twitter 内容：小道消息 + 正规媒体

    Args:
        llm_caller: LLM 调用函数
        max_per_category: 每个类别最多返回多少条
        hours: 时间窗口（小时）

    Returns:
        dict: {
            "rumors": [...],
            "media": [...],
            "available": bool,
            "errors": {"rumors": str, "media": str}
        }
    """
    scraper = TwitterScraper()
    result = {
        "rumors": [],
        "media": [],
        "comments": [],
        "available": False,
        "errors": {},
        "provenance": {},
    }

    def provenance_for(fetch_result, official_result=None):
        fetch_result = fetch_result or {}
        official_result = official_result or {}
        attempted = []
        fetch_source = fetch_result.get("source")
        official_source = official_result.get("source")
        for source in (
            official_result.get("attempted_sources", [])
            + ([official_source] if official_source else [])
            + fetch_result.get("attempted_sources", [])
            + ([fetch_source] if fetch_source else [])
        ):
            if source in ("official_x_api", "rsshub") and source not in attempted:
                attempted.append(source)
        state = fetch_result.get("provenance") or fetch_source
        if not state and fetch_result.get("available"):
            state = "official_x_api" if "official_x_api" in attempted else "rsshub"
        state = state or "source_failed"
        details = {
            "state": state,
            "attempted_sources": attempted,
        }
        official_state = official_result.get("provenance") or official_source
        if state == "rsshub" and official_state not in (None, "official_x_api"):
            details["degraded_from"] = official_state
        error = fetch_result.get("error")
        if error:
            details["reason"] = str(error)
        return details

    def summarize_one(args):
        category, fetch_result = args
        if not fetch_result["available"]:
            return category, [], fetch_result.get("error", "抓取失败")
        print(f"     使用 LLM 过滤 {category} 噪音...")
        return category, scraper.filter_and_summarize(
            fetch_result["tweets"], llm_caller,
            max_rumors=max_per_category, category=category,
            analysis_model=analysis_model
        ), ""

    print("\n[Twitter 小道消息]")
    print(f"     抓取 {len(scraper.RUMOR_ACCOUNTS)} 个爆料型账号...")
    print("\n[Twitter 正规媒体]")
    print(f"     抓取 {len(scraper.MEDIA_ACCOUNTS)} 个媒体账号...")
    print("\n[Twitter 公开讨论]")
    comment_terms = [
        "$SPY", "$QQQ", "$AAPL", "$TSLA", "$NVDA",
        "Federal Reserve", "earnings", "merger",
    ]
    with ThreadPoolExecutor(max_workers=3, thread_name_prefix="twitter-category") as executor:
        rumor_future = executor.submit(
            _fetch_official_accounts, scraper, scraper.RUMOR_ACCOUNTS, 5, hours
        )
        media_future = executor.submit(
            _fetch_official_accounts, scraper, scraper.MEDIA_ACCOUNTS, 5, hours
        )
        comments_future = executor.submit(
            _fetch_official_comments, comment_terms, max(20, max_per_category * 4)
        )
        rumor_result = rumor_future.result()
        media_result = media_future.result()
        comments_result = comments_future.result()

    official_rumor_result = rumor_result
    official_media_result = media_result

    # Official X API is opt-in. A category that is unavailable or empty falls
    # back independently so rumor accounts are never lost because media worked.
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="twitter-category") as executor:
        rumor_future = (executor.submit(scraper.fetch_multiple_accounts,
                                        scraper.RUMOR_ACCOUNTS, 5, hours)
                        if not rumor_result or not rumor_result.get("available") else None)
        media_future = (executor.submit(scraper.fetch_multiple_accounts,
                                        scraper.MEDIA_ACCOUNTS, 5, hours)
                        if not media_result or not media_result.get("available") else None)
        if rumor_future:
            rumor_result = rumor_future.result()
        if media_future:
            media_result = media_future.result()

    result["provenance"]["rumors"] = provenance_for(
        rumor_result, official_rumor_result,
    )
    result["provenance"]["media"] = provenance_for(
        media_result, official_media_result,
    )
    result["provenance"]["comments"] = provenance_for(comments_result)

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="twitter-category") as executor:
        summary_results = list(executor.map(
            summarize_one,
            (("rumors", rumor_result), ("media", media_result))
        ))

    for category, entries, error in summary_results:
        if error:
            result["errors"][category] = error
            print(f"     [!] {category} 抓取失败：{error}")
            continue
        result[category] = entries
        print(f"     提取到 {len(entries)} 条内容")
        result["available"] = True

    def summarize_comments(fetch_result):
        if not fetch_result or not fetch_result.get("available"):
            return [], (fetch_result or {}).get("error", "抓取失败")
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        fresh_tweets = [
            tweet for tweet in fetch_result.get("tweets", [])
            if tweet.get("pub_date") and tweet["pub_date"] >= cutoff
        ]
        if not fresh_tweets:
            return [], f"{hours}小时内无新讨论"
        print("     使用 LLM 过滤 comments 噪音...")
        return scraper.filter_and_summarize(
            fresh_tweets, llm_caller,
            max_rumors=max_per_category, category="comments",
            analysis_model=analysis_model,
        ), ""

    comments_entries, comments_error = summarize_comments(comments_result)
    if comments_error:
        result["errors"]["comments"] = comments_error
        print(f"     [!] comments 抓取失败：{comments_error}")
    else:
        result["comments"] = comments_entries
        print(f"     提取到 {len(comments_entries)} 条公开讨论")
        result["available"] = bool(result["comments"] or result["available"])

    if not result["rumors"] and not result["media"] and not result["comments"]:
        result["available"] = False
    return result

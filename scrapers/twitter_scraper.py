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
from datetime import datetime, timezone


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

                return {
                    "tweets": tweets,
                    "available": True,
                    "source_url": mirror
                }

            except Exception as e:
                last_error = f"{mirror}: {e!r}"
                continue

        # 所有镜像都失败
        print(f"     [WARN] 抓取 @{username} 失败，已尝试 {len(self.rsshub_mirrors)} 个镜像")
        return {
            "tweets": [],
            "available": False,
            "error": last_error or "所有 RSSHub 镜像均不可用",
            "source_url": ""
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
        successful_mirrors = set()

        from datetime import datetime, timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        for username in accounts:
            fetch_result = self.fetch_tweets(username, limit=limit_per_account)

            if fetch_result["available"]:
                # 只保留时间窗口内的推文
                fresh_tweets = [
                    t for t in fetch_result["tweets"]
                    if t.get("pub_date") and t["pub_date"] >= cutoff
                ]
                all_tweets.extend(fresh_tweets)
                if fetch_result["source_url"]:
                    successful_mirrors.add(fetch_result["source_url"])
            else:
                failed_accounts.append(username)

            time.sleep(1)  # 避免请求过快

        if not all_tweets:
            error_msg = "所有账号均抓取失败" if len(failed_accounts) == len(accounts) else f"{hours}小时内无新推文"
            return {
                "tweets": [],
                "available": False,
                "failed_accounts": failed_accounts,
                "error": error_msg
            }

        return {
            "tweets": all_tweets,
            "available": True,
            "failed_accounts": failed_accounts,
            "successful_mirrors": list(successful_mirrors)
        }

    def filter_and_summarize(self, tweets: List[Dict], llm_caller,
                            max_rumors: int = 5, category: str = "rumors") -> List[Dict]:
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
        else:
            system_prompt = """你是财经市场传言分析专家。
从推文中识别有价值的市场传言，过滤噪音（广告、无关内容）。
传言标记为"未经证实"，需谨慎对待。
只返回 JSON 数组，不要其他文字。"""
            impact_field = "市场影响分析（30字内）"

        user_prompt = f"""分析以下 Twitter 推文，提取有价值的{'财经报道' if category == 'media' else '市场传言'}。

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
            result = llm_caller(system_prompt, user_prompt, model=None)

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
    rumors = scraper.filter_and_summarize(tweets, llm_caller, max_rumors=max_rumors)
    print(f"     提取到 {len(rumors)} 条有价值传言")

    return rumors


def fetch_twitter_categorized(llm_caller, max_per_category: int = 5, hours: int = 24) -> Dict[str, List[Dict]]:
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
        "available": False,
        "errors": {}
    }

    # 1. 抓取小道消息
    print("\n[Twitter 小道消息]")
    print(f"     抓取 {len(scraper.RUMOR_ACCOUNTS)} 个爆料型账号...")
    rumor_result = scraper.fetch_multiple_accounts(
        accounts=scraper.RUMOR_ACCOUNTS,
        limit_per_account=5,
        hours=hours
    )

    if rumor_result["available"]:
        print(f"     获取到 {len(rumor_result['tweets'])} 条推文（{hours}小时内）")
        if rumor_result.get("failed_accounts"):
            print(f"     [!] {len(rumor_result['failed_accounts'])} 个账号抓取失败")

        print(f"     使用 LLM 过滤噪音...")
        result["rumors"] = scraper.filter_and_summarize(
            rumor_result["tweets"], llm_caller,
            max_rumors=max_per_category, category="rumors"
        )
        print(f"     提取到 {len(result['rumors'])} 条小道消息")
        result["available"] = True
    else:
        result["errors"]["rumors"] = rumor_result.get("error", "抓取失败")
        print(f"     [!] 小道消息抓取失败：{result['errors']['rumors']}")

    # 2. 抓取正规媒体
    print("\n[Twitter 正规媒体]")
    print(f"     抓取 {len(scraper.MEDIA_ACCOUNTS)} 个媒体账号...")
    media_result = scraper.fetch_multiple_accounts(
        accounts=scraper.MEDIA_ACCOUNTS,
        limit_per_account=5,
        hours=hours
    )

    if media_result["available"]:
        print(f"     获取到 {len(media_result['tweets'])} 条推文（{hours}小时内）")
        if media_result.get("failed_accounts"):
            print(f"     [!] {len(media_result['failed_accounts'])} 个账号抓取失败")

        print(f"     使用 LLM 过滤噪音...")
        result["media"] = scraper.filter_and_summarize(
            media_result["tweets"], llm_caller,
            max_rumors=max_per_category, category="media"
        )
        print(f"     提取到 {len(result['media'])} 条正规媒体报道")
        result["available"] = True
    else:
        result["errors"]["media"] = media_result.get("error", "抓取失败")
        print(f"     [!] 正规媒体抓取失败：{result['errors']['media']}")

    # 如果两个都失败才标记为整体不可用
    if not result["rumors"] and not result["media"]:
        result["available"] = False

    return result


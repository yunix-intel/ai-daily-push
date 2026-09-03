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

    # 重要财经传言账号列表（爆料型/内幕型）
    DEFAULT_ACCOUNTS = [
        "unusual_whales",      # 🐋 期权异动监测（大单追踪）
        "HindenburgRes",       # 🔍 兴登堡研究（做空机构，重磅爆料）
        "muddywatersre",       # 💧 浑水研究（做空机构）
        "CitronResearch",      # 🍋 香橼研究（做空机构）
        "zerohedge",           # ⚡ Zero Hedge（快速市场消息）
        "DeItaone",            # 📊 实时新闻爆料
        "Fxhedgers",           # 💱 外汇市场传言
    ]

    def __init__(self, rsshub_base="https://rsshub.app", timeout=30):
        """
        初始化 Twitter 抓取器

        Args:
            rsshub_base: RSSHub 服务地址
            timeout: 请求超时时间（秒）
        """
        self.rsshub_base = rsshub_base.rstrip("/")
        self.timeout = timeout
        self.user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )

    def fetch_tweets(self, username: str, limit: int = 10) -> List[Dict]:
        """
        抓取指定用户的最新推文

        Args:
            username: Twitter 用户名
            limit: 最多返回多少条推文

        Returns:
            推文列表，每条包含 title, content, link, pub_date
        """
        url = f"{self.rsshub_base}/twitter/user/{username}"

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

            return tweets

        except Exception as e:
            print(f"     [WARN] 抓取 @{username} 失败：{e}")
            return []

    def fetch_multiple_accounts(self, accounts: Optional[List[str]] = None,
                               limit_per_account: int = 5) -> List[Dict]:
        """
        批量抓取多个账号的推文

        Args:
            accounts: Twitter 账号列表，None 时使用默认列表
            limit_per_account: 每个账号最多抓取多少条

        Returns:
            所有推文的合并列表
        """
        if accounts is None:
            accounts = self.DEFAULT_ACCOUNTS

        all_tweets = []
        for username in accounts:
            tweets = self.fetch_tweets(username, limit=limit_per_account)
            all_tweets.extend(tweets)
            time.sleep(1)  # 避免请求过快

        return all_tweets

    def filter_and_summarize(self, tweets: List[Dict], llm_caller,
                            max_rumors: int = 5) -> List[Dict]:
        """
        使用 LLM 过滤噪音并提取核心观点

        Args:
            tweets: 推文列表
            llm_caller: LLM 调用函数 (system_prompt, user_prompt, model) -> str
            max_rumors: 最多返回多少条传言

        Returns:
            过滤后的传言列表，包含 title, summary, source, link, impact
        """
        if not tweets:
            return []

        # 构建 LLM 提示词
        tweet_list = []
        for i, tweet in enumerate(tweets[:20], 1):  # 最多分析20条
            content = tweet.get("content", "")[:200]  # 限制长度
            username = tweet.get("username", "")
            tweet_list.append(f"{i}. @{username}: {content}")

        system_prompt = """你是财经市场传言分析专家。
从推文中识别有价值的市场传言，过滤噪音（广告、无关内容）。
只返回 JSON 数组，不要其他文字。"""

        user_prompt = f"""分析以下 Twitter 推文，提取有价值的市场传言。

筛选标准：
- ✅ 保留：市场动向、重大交易、公司并购、监管变化、重要人物观点
- ❌ 过滤：广告、无关话题、纯转发、情绪化评论

推文列表：
{chr(10).join(tweet_list)}

返回 JSON 数组（最多{max_rumors}条），每条包含：
{{
  "title": "传言标题（简短）",
  "summary": "核心内容摘要",
  "source": "@用户名",
  "impact": "市场影响分析（30字内）",
  "idx": 原推文编号
}}

示例：
[
  {{
    "title": "特斯拉考虑收购某供应商",
    "summary": "据知情人士透露，特斯拉正在洽谈收购其电池供应商...",
    "source": "@zerohedge",
    "impact": "可能影响电动车供应链格局",
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

            # 添加链接
            rumors = []
            for item in result[:max_rumors]:
                idx = item.get("idx", 0) - 1
                if 0 <= idx < len(tweets):
                    item["link"] = tweets[idx].get("link", "#")
                else:
                    item["link"] = "#"
                rumors.append(item)

            return rumors

        except Exception as e:
            print(f"     [WARN] LLM 过滤失败：{e}")
            return []


def fetch_twitter_rumors(llm_caller, accounts: Optional[List[str]] = None,
                        max_rumors: int = 5) -> List[Dict]:
    """
    便捷函数：抓取并过滤 Twitter 财经传言

    Args:
        llm_caller: LLM 调用函数
        accounts: Twitter 账号列表
        max_rumors: 最多返回多少条传言

    Returns:
        传言列表
    """
    scraper = TwitterScraper()

    # 抓取推文
    print(f"     抓取 {len(accounts or scraper.DEFAULT_ACCOUNTS)} 个账号的推文...")
    tweets = scraper.fetch_multiple_accounts(accounts=accounts, limit_per_account=5)
    print(f"     获取到 {len(tweets)} 条推文")

    if not tweets:
        return []

    # 过滤并提取传言
    print(f"     使用 LLM 过滤噪音...")
    rumors = scraper.filter_and_summarize(tweets, llm_caller, max_rumors=max_rumors)
    print(f"     提取到 {len(rumors)} 条有价值传言")

    return rumors


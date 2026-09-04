#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
微博抓取器 - 通过 RSSHub 获取微博内容
因为微博需要登录且有反爬机制，直接抓取困难，所以使用 RSSHub 服务
"""
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import requests


class WeiboScraper:
    """微博抓取器（通过 RSSHub）"""

    # RSSHub 公共镜像列表（按优先级排序）
    DEFAULT_MIRRORS = [
        "https://rsshub.app",
        "https://rsshub.rssforever.com",
        "https://rsshub.ktachibana.party",
    ]

    def __init__(self, rsshub_base=None, timeout=None):
        """
        初始化微博抓取器

        Args:
            rsshub_base: RSSHub 服务地址（可选，默认使用镜像列表）
            timeout: 请求超时时间（秒）
        """
        # 如果指定了单一地址，只用它；否则从镜像列表依次尝试
        self.rsshub_mirrors = [rsshub_base.rstrip("/")] if rsshub_base else self.DEFAULT_MIRRORS
        self.timeout = timeout if timeout is not None else float(os.getenv("RSSHUB_TIMEOUT", "10"))
        self.user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )

    def fetch_weibo_user(self, uid: str, limit: int = 10) -> Dict:
        """
        抓取指定用户的微博

        Args:
            uid: 微博用户ID
            limit: 最多返回多少条

        Returns:
            dict: {
                "weibos": 微博列表，每条包含 title, content, link, pub_date
                "available": bool,
                "error": str (失败时),
                "source_url": str (使用的镜像地址)
            }
        """
        last_error = None

        for mirror in self.rsshub_mirrors:
            url = f"{mirror}/weibo/user/{uid}"

            try:
                headers = {"User-Agent": self.user_agent}
                response = requests.get(url, headers=headers, timeout=self.timeout)
                response.raise_for_status()

                # 解析 RSS XML
                root = ET.fromstring(response.content)

                weibos = []
                for item in root.findall(".//item")[:limit]:
                    title = item.findtext("title", "").strip()
                    link = item.findtext("link", "").strip()
                    pub_date_str = item.findtext("pubDate", "")
                    description = item.findtext("description", "").strip()

                    # 清理 HTML 标签
                    import re
                    from html import unescape
                    clean_content = re.sub(r'<[^>]+>', '', description)
                    clean_content = unescape(clean_content).strip()

                    # 解析发布时间
                    pub_date = None
                    if pub_date_str:
                        try:
                            from dateutil.parser import parse
                            pub_date = parse(pub_date_str)
                        except Exception:
                            pass

                    weibos.append({
                        "title": title,
                        "content": clean_content,
                        "link": link,
                        "pub_date": pub_date,
                        "uid": uid
                    })

                return {
                    "weibos": weibos,
                    "available": True,
                    "source_url": mirror
                }

            except Exception as e:
                last_error = f"{mirror}: {e!r}"
                continue

        # 所有镜像都失败
        print(f"     [WARN] 抓取微博用户 {uid} 失败，已尝试 {len(self.rsshub_mirrors)} 个镜像")
        return {
            "weibos": [],
            "available": False,
            "error": last_error or "所有 RSSHub 镜像均不可用",
            "source_url": ""
        }

    def fetch_recent(self, uid: str, name: str = "", hours: int = 24,
                    max_articles: int = 6) -> Dict:
        """
        抓取用户近 N 小时内的微博

        Args:
            uid: 微博用户ID
            name: 用户显示名（仅用于日志和输出）
            hours: 时间窗口
            max_articles: 最多取几条

        Returns:
            dict: {name, uid, articles: [...], available: bool, error: str (失败时)}
        """
        label = name or uid
        result = {"name": name, "uid": str(uid), "articles": [], "available": False}

        fetch_result = self.fetch_weibo_user(uid, limit=20)

        if not fetch_result["available"]:
            result["error"] = fetch_result.get("error", "RSSHub 服务不可用")
            print(f"     [!] {label} 微博抓取失败：{result['error']}")
            return result

        weibos = fetch_result["weibos"]
        if not weibos:
            result["error"] = "解析不出内容"
            print(f"     [!] {label} 微博解析不出内容")
            return result

        # 按时间过滤
        cutoff = datetime.now(weibos[0]["pub_date"].tzinfo if weibos[0]["pub_date"] else None) - timedelta(hours=hours)
        now = datetime.now(weibos[0]["pub_date"].tzinfo if weibos[0]["pub_date"] else None)

        fresh = [w for w in weibos
                if w["pub_date"] and cutoff <= w["pub_date"] <= now][:max_articles]

        result["available"] = True
        if not fresh:
            print(f"     {label} 近 {hours} 小时内无更新")
            return result

        # 转换为标准格式
        for weibo in fresh:
            result["articles"].append({
                "title": weibo["title"][:50] + "..." if len(weibo["title"]) > 50 else weibo["title"],
                "url": weibo["link"],
                "published": weibo["pub_date"].strftime("%Y-%m-%d %H:%M") if weibo["pub_date"] else "",
                "body": weibo["content"][:500]  # 限制长度
            })

        print(f"     {label} 收录 {len(result['articles'])} 条微博（来源：{fetch_result['source_url']}）")
        return result


def fetch_weibo_blogger(uid: str, name: str, hours: int = 24) -> Dict:
    """
    便捷函数：抓取单个微博博主

    Args:
        uid: 微博用户ID
        name: 博主名称
        hours: 时间窗口

    Returns:
        博主数据字典
    """
    scraper = WeiboScraper()
    return scraper.fetch_recent(uid, name, hours=hours)

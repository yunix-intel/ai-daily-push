#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文章正文提取模块
支持多种提取方案，自动回退
"""

import requests
from bs4 import BeautifulSoup
import re


def extract_article(url, timeout=15):
    """
    提取文章正文

    Args:
        url: 文章URL
        timeout: 请求超时时间

    Returns:
        {
            'title': str,
            'text': str,  # 纯文本
            'html': str,  # HTML格式（保留段落）
            'author': str,
            'publish_date': str
        }
        失败返回 None
    """
    # 方案 A: newspaper3k
    try:
        from newspaper import Article

        article = Article(url)
        article.download()
        article.parse()

        if not article.text or len(article.text) < 100:
            raise ValueError("正文过短，可能提取失败")

        return {
            'title': article.title,
            'text': article.text,
            'html': article.html or '',
            'author': ', '.join(article.authors) if article.authors else '',
            'publish_date': str(article.publish_date) if article.publish_date else ''
        }
    except ImportError:
        print(f"     newspaper3k 未安装，使用 readability")
    except Exception as e:
        print(f"     newspaper3k 提取失败，尝试 readability：{e}")

    # 方案 B: readability-lxml
    try:
        from readability import Document

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()

        doc = Document(response.content)
        html_content = doc.summary()

        # 提取纯文本
        soup = BeautifulSoup(html_content, 'html.parser')
        text = soup.get_text(separator='\n', strip=True)

        if len(text) < 100:
            raise ValueError("正文过短")

        return {
            'title': doc.title(),
            'text': text,
            'html': html_content,
            'author': '',
            'publish_date': ''
        }
    except ImportError:
        print(f"     readability-lxml 未安装")
    except Exception as e:
        print(f"     readability 提取失败：{e}")

    # 方案 C: 简单 BeautifulSoup 回退
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')

        # 移除脚本和样式
        for script in soup(["script", "style"]):
            script.decompose()

        # 尝试找到主要内容区域
        article_tag = (
            soup.find('article') or
            soup.find('div', class_=re.compile(r'article|content|post|entry', re.I)) or
            soup.find('main') or
            soup.body
        )

        if not article_tag:
            raise ValueError("无法找到文章内容区域")

        # 提取文本
        text = article_tag.get_text(separator='\n', strip=True)

        # 简单清洗
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        text = '\n'.join(lines)

        if len(text) < 100:
            raise ValueError("正文过短")

        # 尝试提取标题
        title_tag = soup.find('h1') or soup.find('title')
        title = title_tag.get_text(strip=True) if title_tag else ''

        return {
            'title': title,
            'text': text,
            'html': str(article_tag),
            'author': '',
            'publish_date': ''
        }
    except Exception as e:
        print(f"     BeautifulSoup 提取失败：{e}")
        return None


if __name__ == '__main__':
    # 测试
    test_urls = [
        'https://www.bloomberg.com/news/articles/2024-01-01/test',
        'https://seekingalpha.com/article/test'
    ]

    for url in test_urls:
        print(f"\n测试: {url}")
        result = extract_article(url)
        if result:
            print(f"  标题: {result['title'][:50]}")
            print(f"  正文长度: {len(result['text'])} 字符")
        else:
            print("  提取失败")

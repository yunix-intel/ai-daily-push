#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文章翻译模块 - 为国际要闻提供全文翻译
"""
import os
import json
import hashlib
import time
from datetime import datetime, timedelta
from pathlib import Path
import requests
from bs4 import BeautifulSoup


class ArticleTranslator:
    """文章全文翻译器"""

    def __init__(self, cache_dir="translations", llm_caller=None):
        """
        初始化翻译器

        Args:
            cache_dir: 翻译缓存目录
            llm_caller: LLM 调用函数 (system_prompt, user_prompt, model) -> str
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.llm_caller = llm_caller
        self.timeout = 30
        self.user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )

    # 抓不到正文的链接：Bloomberg 视频页/直播页返回 403，
    # 播客与视频本身也没有可翻译的正文，提前排除避免浪费一次抓取配额。
    SKIP_URL_PATTERNS = ("/videos/", "/video/", "/audio/", "/podcast", "/live-blog", "/livestream")

    # 硬付费墙 / 强反爬域名：正文抓取必然 403，换 UA 也没用。
    # 不排除的话，这些条目会把每天 5 篇的全文翻译配额全部占掉
    # （实测一次 3 个候选全是 bloomberg.com，最终 0 篇成功），
    # 真正能翻的文章反而排不进来。
    SKIP_DOMAINS = ("bloomberg.com", "wsj.com", "ft.com", "economist.com",
                    "barrons.com", "nytimes.com", "seekingalpha.com")

    def is_worth_translating(self, item):
        """
        判断文章是否值得翻译

        Args:
            item: 新闻条目

        Returns:
            bool: 是否值得翻译
        """
        # 必须是国际要闻
        if item.get("region") != "international":
            return False

        # 重要性评分 >= 7
        importance = item.get("importance_score", 0)
        if importance < 7:
            return False

        # 必须有原文链接
        link = item.get("link")
        if not link:
            return False

        # 视频/音频页没有正文，且常被反爬拦截
        if any(p in link.lower() for p in self.SKIP_URL_PATTERNS):
            return False

        if any(dom in link.lower() for dom in self.SKIP_DOMAINS):
            return False

        # 标题包含"快讯"等关键词的跳过
        title = item.get("title", "")
        skip_keywords = ["快讯", "简讯", "速递", "Breaking:", "Quick Update"]
        if any(kw in title for kw in skip_keywords):
            return False

        # 中文源不需要「全文翻译」。isEnglish 是抓取时按源打的标，
        # 但格隆汇/第一财经这类中文源也会走到这里；再按原文内容兜一层，
        # 否则中文正文会被送去做「英译中」，白占 5 篇配额还生成一份废译文。
        original_title = item.get("originalTitle") or item.get("title", "")
        original_summary = item.get("originalSummary") or item.get("summary", "")
        probe = f"{original_title} {original_summary}"
        if any('一' <= c <= '鿿' for c in probe):
            return False

        # 摘要够长才说明不是简短快讯。
        # 必须量原文：这一步跑在标题摘要翻译之后，同一条英文摘要翻成中文后
        # 字符数会缩到三分之一左右，拿中文长度卡 100 会把绝大多数正常长文误杀。
        summary = original_summary
        if len(summary) < 100:
            return False

        return True

    def get_cache_path(self, url):
        """获取翻译缓存路径"""
        url_hash = hashlib.md5(url.encode()).hexdigest()
        return self.cache_dir / f"{url_hash}.json"

    def load_translation_cache(self, url):
        """
        加载翻译缓存

        Returns:
            dict or None: 缓存数据
        """
        cache_path = self.get_cache_path(url)
        if not cache_path.exists():
            return None

        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                cache = json.load(f)

            # 检查缓存是否过期（7天）
            cached_time = datetime.fromisoformat(cache.get("timestamp", ""))
            if datetime.now() - cached_time > timedelta(days=7):
                return None

            return cache

        except Exception as e:
            print(f"     [WARN] 翻译缓存读取失败: {e}")
            return None

    def save_translation_cache(self, url, original_content, translated_content):
        """保存翻译缓存"""
        cache_path = self.get_cache_path(url)

        cache = {
            "url": url,
            "timestamp": datetime.now().isoformat(),
            "original_content": original_content,
            "translated_content": translated_content
        }

        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
            print(f"     [OK] 翻译已缓存: {cache_path.name}")
        except Exception as e:
            print(f"     [WARN] 翻译缓存保存失败: {e}")

    def fetch_article_content(self, url):
        """
        获取文章正文内容

        Args:
            url: 文章链接

        Returns:
            str: 正文内容，失败返回 None
        """
        try:
            headers = {"User-Agent": self.user_agent}
            response = requests.get(url, headers=headers, timeout=self.timeout)
            response.raise_for_status()

            # 尝试检测编码
            if response.encoding.lower() in ['iso-8859-1', 'windows-1252']:
                response.encoding = response.apparent_encoding

            soup = BeautifulSoup(response.content, 'html.parser')

            # 移除脚本、样式、导航等无关元素
            for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'aside', 'iframe']):
                tag.decompose()

            # 尝试多种常见的正文选择器
            content_selectors = [
                'article',
                '.article-content',
                '.post-content',
                '.entry-content',
                '#article-body',
                '.story-body',
                'main'
            ]

            content = None
            for selector in content_selectors:
                element = soup.select_one(selector)
                if element:
                    content = element.get_text(separator='\n', strip=True)
                    break

            # 如果没找到，使用 body
            if not content:
                body = soup.find('body')
                if body:
                    content = body.get_text(separator='\n', strip=True)

            # 清理多余空行
            if content:
                lines = [line.strip() for line in content.split('\n') if line.strip()]
                content = '\n\n'.join(lines)

            # 长度检查（至少 200 字符）
            if content and len(content) >= 200:
                return content

            return None

        except Exception as e:
            print(f"     [WARN] 文章内容获取失败 ({url}): {e}")
            return None

    def translate_article(self, content, title=""):
        """
        翻译文章内容

        Args:
            content: 原文内容
            title: 文章标题（可选）

        Returns:
            str: 译文，失败返回 None
        """
        if not self.llm_caller:
            print("     [WARN] 未配置 LLM，跳过翻译")
            return None

        # 分段翻译（每段最多 3000 字符）
        max_chunk_size = 3000
        paragraphs = content.split('\n\n')
        chunks = []
        current_chunk = []
        current_size = 0

        for para in paragraphs:
            para_size = len(para)
            if current_size + para_size > max_chunk_size and current_chunk:
                chunks.append('\n\n'.join(current_chunk))
                current_chunk = []
                current_size = 0

            current_chunk.append(para)
            current_size += para_size

        if current_chunk:
            chunks.append('\n\n'.join(current_chunk))

        # 翻译每个分段
        translated_chunks = []
        failed_chunks = 0
        failed_chars = 0
        total_chars = sum(len(c) for c in chunks)
        for i, chunk in enumerate(chunks):
            print(f"     翻译分段 {i+1}/{len(chunks)} ({len(chunk)} 字符)...")

            system_prompt = "你是专业的财经新闻翻译，擅长将英文财经文章翻译成流畅的中文。"

            user_prompt = f"""请将以下英文财经文章翻译成中文：

标题：{title}

正文：
{chunk}

要求：
1. 准确传达原文意思
2. 使用专业财经术语
3. 保持段落结构
4. 翻译要流畅自然

直接返回译文，不要添加任何说明或标注。"""

            # 单段最多再试一次。实测失败多是 SSL EOF / 504 这类瞬时错误，
            # 隔几秒重来通常就成了；不重试的话整篇里会夹着一大段英文。
            translated = None
            for attempt in range(2):
                try:
                    translated = self.llm_caller(system_prompt, user_prompt)
                    if translated:
                        break
                    print(f"     [WARN] 分段 {i+1} 返回空内容")
                except Exception as e:
                    print(f"     [WARN] 分段 {i+1} 翻译异常: {e}")
                    translated = None
                if attempt == 0:
                    time.sleep(5)

            if translated:
                translated_chunks.append(translated.strip())
            else:
                print(f"     [WARN] 分段 {i+1} 重试后仍失败，使用原文")
                translated_chunks.append(chunk)
                failed_chunks += 1
                failed_chars += len(chunk)

        # 失败占比按字符算，不按段数算：分段长度差很多，
        # 3 段里失败 1 段可能是失败了近一半正文。夹着大段英文的「译文」
        # 一旦存进 7 天缓存会反复复用，宁可判定失败、不显示按钮。
        if failed_chunks and failed_chars / max(total_chars, 1) > 0.3:
            print(f"     [WARN] {failed_chars}/{total_chars} 字符未翻成，判定为翻译失败")
            return None

        # 合并翻译结果
        translated_content = '\n\n'.join(translated_chunks)
        return translated_content

    def translate_news_item(self, item):
        """
        翻译新闻条目的全文

        Args:
            item: 新闻条目 dict

        Returns:
            bool: 是否翻译成功
        """
        url = item.get("link", "")
        if not url:
            return False

        # 检查缓存
        cache = self.load_translation_cache(url)
        if cache:
            item["translated_content"] = cache.get("translated_content")
            item["original_content"] = cache.get("original_content")
            print(f"     [OK] 使用翻译缓存: {item.get('title', '')[:50]}")
            return True

        # 获取原文
        print(f"     [>>] 获取原文: {item.get('title', '')[:50]}...")
        original_content = self.fetch_article_content(url)
        if not original_content:
            return False

        # 翻译
        print(f"     [>>] 翻译全文...")
        translated_content = self.translate_article(
            original_content,
            title=item.get("title", "")
        )

        if translated_content:
            # 保存到 item
            item["translated_content"] = translated_content
            item["original_content"] = original_content

            # 缓存
            self.save_translation_cache(url, original_content, translated_content)

            print(f"     [OK] 全文翻译完成: {len(translated_content)} 字符")
            return True

        return False


def batch_translate_articles(items, llm_caller, max_count=5):
    """
    批量翻译文章

    Args:
        items: 新闻条目列表
        llm_caller: LLM 调用函数
        max_count: 最多翻译几篇

    Returns:
        int: 实际翻译数量
    """
    translator = ArticleTranslator(llm_caller=llm_caller)

    # 筛选值得翻译的文章
    candidates = [item for item in items if translator.is_worth_translating(item)]

    if not candidates:
        print("     无值得翻译的文章")
        return 0

    print(f"     找到 {len(candidates)} 篇值得翻译的文章，最多翻译 {max_count} 篇")

    # 按重要性排序
    candidates.sort(key=lambda x: x.get("importance_score", 0), reverse=True)

    # 翻译：抓取失败（付费墙/反爬）不占用配额，继续往后顺延，
    # 否则前几条恰好抓不到时，页面上一个「查看中文全文」按钮都不会出现。
    translated_count = 0
    attempted = 0
    for item in candidates:
        if translated_count >= max_count:
            break
        attempted += 1
        if translator.translate_news_item(item):
            translated_count += 1
        # 兜底上限：最多尝试 max_count 的三倍，避免整批都抓不到时一直重试
        if attempted >= max_count * 3:
            break

    if translated_count < min(max_count, len(candidates)):
        print(f"     全文翻译：{translated_count} 篇成功 / 尝试 {attempted} 篇")

    return translated_count


# 测试函数
if __name__ == "__main__":
    # 模拟 LLM 调用
    def mock_llm(system_prompt, user_prompt, model=None):
        return "[模拟翻译] " + user_prompt[:100]

    translator = ArticleTranslator(llm_caller=mock_llm)

    # 测试文章
    test_item = {
        "title": "OpenAI Launches New Model",
        "summary": "OpenAI has announced the release of their latest AI model...",
        "link": "https://example.com/article",
        "region": "international",
        "importance_score": 8
    }

    print("测试文章翻译系统...")
    print(f"是否值得翻译: {translator.is_worth_translating(test_item)}")

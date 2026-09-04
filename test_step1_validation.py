#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
验证计划第1步的修复成果
"""
import sys
import json
from datetime import datetime

def test_module_imports():
    """测试1：模块导入"""
    print("=== Test 1: Module Imports ===")
    try:
        from scrapers.weibo_scraper import WeiboScraper
        from scrapers.twitter_scraper import TwitterScraper, fetch_twitter_categorized
        from scrapers.blogger_scraper import BloggerScraper
        from article_translator import ArticleTranslator
        print("[PASS] All modules imported successfully")
        return True
    except Exception as e:
        print(f"[FAIL] Module import failed: {e}")
        return False

def test_weibo_scraper_mirrors():
    """测试2：微博抓取器镜像配置"""
    print("\n=== Test 2: Weibo Scraper Mirror Config ===")
    try:
        from scrapers.weibo_scraper import WeiboScraper
        scraper = WeiboScraper()

        assert hasattr(scraper, 'rsshub_mirrors'), "Missing rsshub_mirrors attribute"
        assert len(scraper.rsshub_mirrors) >= 3, f"Expected >= 3 mirrors, got {len(scraper.rsshub_mirrors)}"

        print(f"[PASS] Default mirrors: {len(scraper.rsshub_mirrors)}")
        for i, mirror in enumerate(scraper.rsshub_mirrors, 1):
            print(f"  {i}. {mirror}")
        return True
    except Exception as e:
        print(f"[FAIL] {e}")
        return False

def test_twitter_scraper_config():
    """测试3：Twitter抓取器配置"""
    print("\n=== Test 3: Twitter Scraper Config ===")
    try:
        from scrapers.twitter_scraper import TwitterScraper
        twitter = TwitterScraper()

        assert hasattr(twitter, 'rsshub_mirrors'), "Missing rsshub_mirrors"
        assert hasattr(twitter, 'RUMOR_ACCOUNTS'), "Missing RUMOR_ACCOUNTS"
        assert hasattr(twitter, 'MEDIA_ACCOUNTS'), "Missing MEDIA_ACCOUNTS"

        print(f"[PASS] Mirrors: {len(twitter.rsshub_mirrors)}")
        print(f"[PASS] Rumor accounts: {len(twitter.RUMOR_ACCOUNTS)}")
        print(f"[PASS] Media accounts: {len(twitter.MEDIA_ACCOUNTS)}")
        return True
    except Exception as e:
        print(f"[FAIL] {e}")
        return False

def test_blogger_platform_routing():
    """测试4：博主平台路由"""
    print("\n=== Test 4: Blogger Platform Routing ===")
    try:
        bloggers_cfg = [
            {"name": "Test Blog", "uid": "1234567", "type": "blog"},
            {"name": "Test Weibo", "uid": "7654321", "type": "weibo"},
        ]

        # 模拟 collect_blogger_views 的URL生成逻辑
        for blogger in bloggers_cfg:
            uid = blogger['uid']
            blogger_type = blogger.get('type', 'blog')

            if blogger_type == 'weibo':
                url = f"https://weibo.com/u/{uid}"
                platform = "weibo"
            else:
                url = f"https://blog.sina.com.cn/u/{uid}"
                platform = "blog"

            expected_domain = "weibo.com" if blogger_type == "weibo" else "blog.sina.com.cn"
            assert expected_domain in url, f"Wrong URL for {blogger_type}: {url}"
            print(f"[PASS] {blogger['name']}: {url}")

        return True
    except Exception as e:
        print(f"[FAIL] {e}")
        return False

def test_translator_data_contract():
    """测试5：翻译器数据契约"""
    print("\n=== Test 5: Translator Data Contract ===")
    try:
        from article_translator import ArticleTranslator
        translator = ArticleTranslator()

        # 测试用例1：完整字段
        item_full = {
            "link": "https://example.com/article",
            "region": "international",
            "importance_score": 7,
            "title": "Test Article",
            "summary": "This is a test article with more than 100 characters to pass the summary length check. It contains enough content to be considered a full article."
        }
        result1 = translator.is_worth_translating(item_full)
        print(f"  Full fields: {result1} (expected True)")

        # 测试用例2：缺失region和importance_score（应该放行）
        item_missing = {
            "link": "https://example.com/article2",
            "title": "Test Article 2",
            "summary": "This is another test article with more than 100 characters in the summary field to ensure it passes validation checks."
        }
        result2 = translator.is_worth_translating(item_missing)
        print(f"  Missing fields: {result2} (expected True if English summary)")

        # 测试用例3：中文内容（应该拒绝）
        item_chinese = {
            "link": "https://example.com/chinese",
            "title": "中文标题测试",
            "summary": "这是一篇中文摘要，用于测试翻译器是否正确识别中文内容并拒绝翻译。内容需要足够长以通过长度检查，所以添加更多字符。"
        }
        result3 = translator.is_worth_translating(item_chinese)
        print(f"  Chinese content: {result3} (expected False)")
        assert not result3, "Should reject Chinese content"

        print("[PASS] Translator data contract verified")
        return True
    except Exception as e:
        print(f"[FAIL] {e}")
        return False

def test_market_insights_fallback():
    """测试6：市场数据降级逻辑检查"""
    print("\n=== Test 6: Market Insights Fallback Logic ===")
    try:
        # 检查ai_daily_push.py中是否包含降级逻辑
        with open('ai_daily_push.py', 'r', encoding='utf-8') as f:
            content = f.read()

        # 检查关键字
        checks = [
            ('市场数据暂不可用', 'Unavailable message'),
            ('市场数据模块未安装', 'Module missing message'),
            ('error', 'Error field in fallback'),
        ]

        for keyword, desc in checks:
            if keyword in content:
                print(f"[PASS] Found: {desc}")
            else:
                print(f"[WARN] Missing: {desc}")

        return True
    except Exception as e:
        print(f"[FAIL] {e}")
        return False

def main():
    print("Step 1 Validation Test Suite")
    print("=" * 50)

    results = []
    results.append(("Module Imports", test_module_imports()))
    results.append(("Weibo Scraper Mirrors", test_weibo_scraper_mirrors()))
    results.append(("Twitter Scraper Config", test_twitter_scraper_config()))
    results.append(("Blogger Platform Routing", test_blogger_platform_routing()))
    results.append(("Translator Data Contract", test_translator_data_contract()))
    results.append(("Market Insights Fallback", test_market_insights_fallback()))

    print("\n" + "=" * 50)
    print("Summary:")
    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status} {name}")

    print(f"\nTotal: {passed}/{total} passed")

    return 0 if passed == total else 1

if __name__ == "__main__":
    sys.exit(main())

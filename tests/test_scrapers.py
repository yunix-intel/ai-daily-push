#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
爬虫单元测试
"""
import unittest
import json
from pathlib import Path
from scrapers.openrouter_scraper import fetch_openrouter_data
from scrapers.artificial_analysis_scraper import fetch_aa_data


class TestScrapers(unittest.TestCase):
    """爬虫测试套件"""

    def test_openrouter_fetch(self):
        """测试 OpenRouter 数据抓取"""
        data = fetch_openrouter_data()

        # 基础字段验证
        self.assertIn('source', data)
        self.assertEqual(data['source'], 'openrouter')
        self.assertIn('top_models', data)
        self.assertIsInstance(data['top_models'], list)

        # 描述字段验证
        self.assertIn('description', data)

        # 增强字段验证（Phase A2）
        self.assertIn('date', data)
        self.assertIn('total_models', data)
        self.assertIn('pricing', data)
        self.assertIn('rankings', data)

        # 验证数据质量
        if data.get('total_models', 0) > 0:
            self.assertGreater(data['total_models'], 0)

        if len(data.get('pricing', [])) > 0:
            pricing = data['pricing'][0]
            self.assertIn('model', pricing)
            self.assertIn('price_per_1m_tokens', pricing)
            self.assertIn('context_length', pricing)

        print(f"[OK] OpenRouter data fetch test passed")
        print(f"  - Total models: {data.get('total_models', 0)}")
        print(f"  - Pricing entries: {len(data.get('pricing', []))}")
        print(f"  - Rankings entries: {len(data.get('rankings', []))}")
        print(f"  - Detected models: {len(data.get('detected_models', []))}")

    def test_aa_fetch(self):
        """测试 Artificial Analysis 数据抓取"""
        data = fetch_aa_data()

        # 基础字段验证
        self.assertIn('source', data)
        self.assertEqual(data['source'], 'artificial_analysis')

        # 数据结构验证
        self.assertIn('intelligence', data)
        self.assertIn('speed', data)
        self.assertIn('cost', data)

        self.assertIsInstance(data['intelligence'], list)
        self.assertIsInstance(data['speed'], list)
        self.assertIsInstance(data['cost'], list)

        # Phase A3 增强字段验证
        self.assertIn('date', data)

        # 数据质量验证
        if len(data.get('intelligence', [])) > 0:
            intel = data['intelligence'][0]
            self.assertIn('model', intel)
            self.assertIn('score', intel)
            self.assertIsInstance(intel['score'], int)

        print(f"[OK] Artificial Analysis data fetch test passed")
        print(f"  - Date: {data.get('date', 'N/A')}")
        print(f"  - Intelligence: {len(data['intelligence'])} items")
        print(f"  - Speed: {len(data['speed'])} items")
        print(f"  - Cost: {len(data['cost'])} items")

    def test_cache_mechanism(self):
        """测试缓存机制"""
        # 第一次调用（可能从网络或缓存加载）
        data1 = fetch_openrouter_data()

        # 第二次调用（应该从缓存加载）
        data2 = fetch_openrouter_data()

        # 验证两次数据一致
        self.assertEqual(data1['source'], data2['source'])

        print(f"[OK] Cache mechanism test passed")

    def test_data_structure(self):
        """测试数据结构完整性"""
        openrouter_data = fetch_openrouter_data()
        aa_data = fetch_aa_data()

        # 验证 OpenRouter 数据可序列化
        try:
            json.dumps(openrouter_data)
        except Exception as e:
            self.fail(f"OpenRouter 数据无法序列化: {e}")

        # 验证 AA 数据可序列化
        try:
            json.dumps(aa_data)
        except Exception as e:
            self.fail(f"AA 数据无法序列化: {e}")

        print(f"[OK] Data structure integrity test passed")


class TestCacheFiles(unittest.TestCase):
    """缓存文件测试"""

    def test_cache_directory_exists(self):
        """测试缓存目录存在"""
        cache_dir = Path("data/market_data")
        self.assertTrue(cache_dir.exists())
        self.assertTrue(cache_dir.is_dir())

        print(f"[OK] Cache directory exists: {cache_dir}")

    def test_cache_files_valid_json(self):
        """测试缓存文件是有效的 JSON"""
        cache_dir = Path("data/market_data")
        cache_files = list(cache_dir.glob("*.json"))

        self.assertGreater(len(cache_files), 0, "缓存目录为空")

        for cache_file in cache_files:
            with open(cache_file, 'r', encoding='utf-8') as f:
                try:
                    data = json.load(f)
                    self.assertIsInstance(data, dict)
                except json.JSONDecodeError as e:
                    self.fail(f"{cache_file.name} 不是有效的 JSON: {e}")

        print(f"[OK] Cache files JSON validation passed ({len(cache_files)} files)")


if __name__ == '__main__':
    # 运行测试
    unittest.main(verbosity=2)

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""新闻分类器单元测试"""

import unittest
from news_classifier import classify_by_keywords

class TestNewsClassifier(unittest.TestCase):

    def test_china_bonds_bloomberg(self):
        """中国债券（Bloomberg来源）应该归为国内"""
        item = {
            'title': 'China Bond Issuance Hits Record',
            'summary': 'Chinese companies issued $50B in bonds',
            'source': {'name': 'Bloomberg'}
        }
        result = classify_by_keywords(item)
        self.assertEqual(result, 'domestic', f"中国债券应该归国内，实际: {result}")

    def test_fed_meeting(self):
        """美联储会议应该归为国际"""
        item = {
            'title': 'Fed Raises Rates',
            'summary': 'Federal Reserve increases rates by 25bps',
            'source': {'name': 'Reuters'}
        }
        result = classify_by_keywords(item)
        self.assertEqual(result, 'international', f"美联储应该归国际，实际: {result}")

    def test_a_share_market(self):
        """A股市场应该归为国内"""
        item = {
            'title': 'A股大涨',
            'summary': '上证指数上涨2%',
            'source': {'name': '财联社'}
        }
        result = classify_by_keywords(item)
        self.assertEqual(result, 'domestic', f"A股应该归国内，实际: {result}")

    def test_huawei_english_title(self):
        """华为新闻（英文标题）应该归为国内"""
        item = {
            'title': 'Huawei Reports Strong Earnings',
            'summary': 'The Chinese tech giant beat expectations',
            'source': {'name': 'CNBC'}
        }
        result = classify_by_keywords(item)
        self.assertEqual(result, 'domestic', f"华为应该归国内，实际: {result}")

    def test_us_military_iran(self):
        """美军袭击伊朗应该归为国际"""
        item = {
            'title': 'US Military Strikes Iran',
            'summary': 'American forces launched attacks on Iranian targets',
            'source': {'name': 'Bloomberg'}
        }
        result = classify_by_keywords(item)
        self.assertEqual(result, 'international', f"美军袭击应该归国际，实际: {result}")

    def test_pboc_policy(self):
        """央行政策应该归为国内"""
        item = {
            'title': 'PBOC Cuts Reserve Ratio',
            'summary': 'People\'s Bank of China reduces RRR by 50bp',
            'source': {'name': 'Reuters'}
        }
        result = classify_by_keywords(item)
        self.assertEqual(result, 'domestic', f"央行政策应该归国内，实际: {result}")

    def test_hong_kong_stocks(self):
        """港股应该归为国内"""
        item = {
            'title': 'Hong Kong Stocks Rally',
            'summary': 'Hang Seng Index gains 3% on tech strength',
            'source': {'name': 'Bloomberg'}
        }
        result = classify_by_keywords(item)
        self.assertEqual(result, 'domestic', f"港股应该归国内，实际: {result}")

if __name__ == '__main__':
    print("="*60)
    print("新闻分类器单元测试")
    print("="*60)
    unittest.main(verbosity=2)

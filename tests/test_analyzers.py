#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分析器模块单元测试
"""
import unittest
from analyzers.market_data_aggregator import MarketDataAggregator
from analyzers.trend_analyzer import TrendAnalyzer


class TestAnalyzers(unittest.TestCase):
    """分析器测试"""

    def test_market_data_aggregator(self):
        """测试市场数据聚合器"""
        aggregator = MarketDataAggregator()
        result = aggregator.aggregate()

        # 验证基本结构
        self.assertIn('date', result)
        self.assertIn('market_trends', result)
        self.assertIn('intelligence_rankings', result)
        self.assertIn('sources', result)
        self.assertIn('cross_validation', result)

        # 验证市场趋势数据
        market_trends = result['market_trends']
        self.assertIn('total_models', market_trends)
        self.assertIn('top_models_by_price', market_trends)
        self.assertIn('pricing_summary', market_trends)

        print(f"[OK] Market data aggregator test passed")
        print(f"  - Date: {result.get('date')}")
        print(f"  - Total models: {market_trends.get('total_models')}")
        print(f"  - Intelligence rankings: {len(result.get('intelligence_rankings', []))}")

    def test_trend_analyzer(self):
        """测试趋势分析器"""
        analyzer = TrendAnalyzer()
        aggregator = MarketDataAggregator()
        current_data = aggregator.aggregate()

        trends = analyzer.analyze_trends(current_data, days_back=3)

        # 验证结构（处理无历史数据的情况）
        if 'note' in trends:
            # 无历史数据
            self.assertIn('trends', trends)
            self.assertIn('note', trends)
            print(f"[OK] Trend analyzer test passed (no historical data)")
            print(f"  - Note: {trends.get('note')}")
        else:
            # 有历史数据
            self.assertIn('period', trends)
            self.assertIn('price_trends', trends)
            self.assertIn('ranking_trends', trends)
            print(f"[OK] Trend analyzer test passed")
            print(f"  - Period: {trends.get('period')}")
            print(f"  - Price trends: {len(trends.get('price_trends', []))}")
            print(f"  - Ranking trends: {len(trends.get('ranking_trends', []))}")


if __name__ == '__main__':
    unittest.main()

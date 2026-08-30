#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
趋势分析器 - 对比历史数据
"""
import glob
import json
from pathlib import Path
from datetime import datetime, timedelta


class TrendAnalyzer:
    """趋势分析器"""

    def __init__(self, data_dir="data/market_data"):
        self.data_dir = Path(data_dir)

    def analyze_trends(self, current_data, days_back=7):
        """
        分析趋势（对比历史数据）

        Args:
            current_data: 当前数据
            days_back: 回溯天数

        Returns:
            dict: 趋势分析结果
        """
        # 加载历史数据
        historical = self._load_historical_data(days_back)

        if not historical:
            return {"trends": [], "note": "无足够历史数据"}

        # 分析价格趋势
        price_trends = self._analyze_price_trends(current_data, historical)

        # 分析排名变化
        ranking_trends = self._analyze_ranking_trends(current_data, historical)

        return {
            "period": f"past_{days_back}_days",
            "price_trends": price_trends,
            "ranking_trends": ranking_trends
        }

    def _load_historical_data(self, days_back):
        """加载历史数据"""
        historical = []

        # 查找过去 N 天的缓存文件
        for i in range(1, days_back + 1):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            cache_file = self.data_dir / f"openrouter_{date}.json"

            if cache_file.exists():
                try:
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        historical.append({"date": date, "data": data})
                except:
                    continue

        return historical

    def _analyze_price_trends(self, current, historical):
        """分析价格趋势"""
        trends = []

        # 获取当前价格
        current_prices = {
            r.get("model"): r.get("price_per_1m_tokens", 0)
            for r in current.get("market_trends", {}).get("top_models_by_price", [])
        }

        # 对比历史价格
        for hist in historical:
            hist_prices = {
                r.get("model"): r.get("price_per_1m_tokens", 0)
                for r in hist.get("data", {}).get("rankings", [])
            }

            for model, current_price in current_prices.items():
                if model in hist_prices:
                    hist_price = hist_prices[model]
                    if hist_price > 0 and current_price != hist_price:
                        change_pct = ((current_price - hist_price) / hist_price) * 100

                        trends.append({
                            "model": model,
                            "from_date": hist.get("date"),
                            "old_price": hist_price,
                            "new_price": current_price,
                            "change_percent": round(change_pct, 2)
                        })

        return trends

    def _analyze_ranking_trends(self, current, historical):
        """分析排名变化"""
        # 简化版：只返回当前排名
        rankings = current.get("intelligence_rankings", [])
        return [
            {"model": r.get("model"), "score": r.get("score")}
            for r in rankings[:5]
        ]


# 测试函数
def test_trend_analyzer():
    """测试趋势分析"""
    analyzer = TrendAnalyzer()

    # 需要先有聚合数据
    from .market_data_aggregator import MarketDataAggregator
    aggregator = MarketDataAggregator()
    current_data = aggregator.aggregate()

    trends = analyzer.analyze_trends(current_data)

    print("趋势分析：")
    import json
    print(json.dumps(trends, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    test_trend_analyzer()

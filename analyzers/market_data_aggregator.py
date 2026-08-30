#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
市场数据聚合器 - 整合多个数据源
"""
from datetime import datetime
from scrapers import fetch_openrouter_data, fetch_aa_data
from .news_metrics_extractor import NewsMetricsExtractor


class MarketDataAggregator:
    """市场数据聚合器"""

    def __init__(self):
        self.metrics_extractor = NewsMetricsExtractor()

    def aggregate(self, news_items=None):
        """
        聚合所有数据源

        Args:
            news_items: 新闻列表（可选）

        Returns:
            dict: 聚合后的市场数据
        """
        print("\n=== 市场数据聚合 ===")

        # 1. 获取 OpenRouter 数据
        print("1. 获取 OpenRouter 数据...")
        openrouter_data = fetch_openrouter_data()

        # 2. 获取 Artificial Analysis 数据
        print("2. 获取 Artificial Analysis 数据...")
        aa_data = fetch_aa_data()

        # 3. 提取新闻指标（如果提供了新闻）
        news_metrics = {}
        if news_items:
            print("3. 从新闻中提取指标...")
            news_metrics = self.metrics_extractor.extract_metrics(news_items)
        else:
            print("3. 跳过新闻指标提取（无新闻数据）")
            news_metrics = self.metrics_extractor._empty_metrics()

        # 4. 整合数据
        print("4. 整合数据...")
        aggregated = self._merge_data(openrouter_data, aa_data, news_metrics)

        # 5. 交叉验证
        print("5. 交叉验证...")
        aggregated['cross_validation'] = self._cross_validate(
            openrouter_data, news_metrics
        )

        print("=== 聚合完成 ===\n")
        return aggregated

    def _merge_data(self, openrouter, aa, news_metrics):
        """合并数据"""
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "timestamp": datetime.now().isoformat(),

            # OpenRouter 数据
            "market_trends": {
                "total_models": openrouter.get("total_models", 0),
                "top_models_by_price": self._extract_top_models(openrouter),
                "pricing_summary": self._summarize_pricing(openrouter)
            },

            # Artificial Analysis 数据
            "intelligence_rankings": aa.get("intelligence", [])[:10],
            "speed_rankings": aa.get("speed", [])[:10],
            "cost_rankings": aa.get("cost", [])[:10],

            # 新闻指标
            "news_metrics": news_metrics,

            # 元数据
            "sources": {
                "openrouter": openrouter.get("date"),
                "artificial_analysis": aa.get("date"),
                "news_count": len(news_metrics.get("revenue", [])) +
                             len(news_metrics.get("funding", [])) +
                             len(news_metrics.get("users", [])) +
                             len(news_metrics.get("token_usage", [])) +
                             len(news_metrics.get("price_changes", []))
            }
        }

    def _extract_top_models(self, openrouter):
        """提取 Top 模型"""
        rankings = openrouter.get("rankings", [])
        return [
            {
                "model": r.get("model"),
                "price_per_1m_tokens": r.get("price_per_1m_tokens")
            }
            for r in rankings[:10]
        ]

    def _summarize_pricing(self, openrouter):
        """价格摘要统计"""
        pricing = openrouter.get("pricing", [])
        if not pricing:
            return {}

        prices = [p.get("price_per_1m_tokens", 0) for p in pricing if p.get("price_per_1m_tokens", 0) > 0]

        if not prices:
            return {}

        return {
            "min_price": round(min(prices), 4),
            "max_price": round(max(prices), 4),
            "avg_price": round(sum(prices) / len(prices), 4),
            "count": len(prices)
        }

    def _cross_validate(self, openrouter, news_metrics):
        """交叉验证 - 多源印证"""
        validated = {
            "confirmed": [],
            "unconfirmed": []
        }

        # 检查价格变化是否在两个数据源中都有
        price_changes = news_metrics.get("price_changes", [])
        openrouter_models = {
            r.get("model"): r.get("price_per_1m_tokens")
            for r in openrouter.get("rankings", [])
        }

        for change in price_changes:
            model_name = change.get("model", "")
            # 简单匹配（可以改进为模糊匹配）
            found_in_or = any(model_name.lower() in or_model.lower()
                            for or_model in openrouter_models.keys())

            if found_in_or:
                validated["confirmed"].append({
                    "type": "price_change",
                    "model": model_name,
                    "sources": ["news", "openrouter"]
                })
            else:
                validated["unconfirmed"].append({
                    "type": "price_change",
                    "model": model_name,
                    "sources": ["news"]
                })

        return validated


# 测试函数
def test_aggregator():
    """测试市场数据聚合"""
    aggregator = MarketDataAggregator()

    # 不使用新闻数据测试
    result = aggregator.aggregate()

    print("聚合结果：")
    import json
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    test_aggregator()

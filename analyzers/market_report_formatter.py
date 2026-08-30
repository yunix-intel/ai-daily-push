#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
市场数据报告格式化器 - 将聚合数据格式化为 HTML
"""


class MarketReportFormatter:
    """市场数据报告格式化器"""

    def format_for_html(self, aggregated_data):
        """
        格式化为 HTML 卡片数据

        Args:
            aggregated_data: 聚合后的市场数据

        Returns:
            list: HTML 卡片数据列表
        """
        cards = []

        # 卡片 1: 官方公布数据（来自新闻）
        news_card = self._format_news_metrics(aggregated_data.get("news_metrics", {}))
        if news_card:
            cards.append(news_card)

        # 卡片 2: 市场使用趋势（OpenRouter）
        market_card = self._format_market_trends(aggregated_data.get("market_trends", {}))
        if market_card:
            cards.append(market_card)

        # 卡片 3: 性能基准（Artificial Analysis）
        performance_card = self._format_performance(aggregated_data)
        if performance_card:
            cards.append(performance_card)

        # 卡片 4: 交叉验证
        validation_card = self._format_cross_validation(
            aggregated_data.get("cross_validation", {})
        )
        if validation_card:
            cards.append(validation_card)

        return cards

    def _format_news_metrics(self, news_metrics):
        """格式化新闻指标"""
        items = []

        # 营收数据
        for revenue in news_metrics.get("revenue", []):
            company = revenue.get("company", "未知")
            value = revenue.get("value", "")
            items.append(f"• {company} ARR {value} ↗")

        # 融资数据
        for funding in news_metrics.get("funding", []):
            company = funding.get("company", "未知")
            amount = funding.get("amount", "")
            items.append(f"• {company} 融资 {amount}")

        # 用户增长
        for user in news_metrics.get("users", []):
            company = user.get("company", "未知")
            metric = user.get("metric", "用户数")
            value = user.get("value", "")
            items.append(f"• {company} {metric} {value} ↗")

        # 价格变化
        for price in news_metrics.get("price_changes", []):
            model = price.get("model", "未知")
            change = price.get("change", "")
            items.append(f"• {model} 价格 {change}")

        if not items:
            return None

        return {
            "title": "💡 官方公布数据",
            "subtitle": "来自新闻",
            "content": "\n".join(items),
            "source": "LLM 提取自行业新闻"
        }

    def _format_market_trends(self, market_trends):
        """格式化市场趋势"""
        items = []

        total = market_trends.get("total_models", 0)
        if total > 0:
            items.append(f"• 总模型数：{total} 个")

        pricing = market_trends.get("pricing_summary", {})
        if pricing:
            min_price = pricing.get("min_price", 0)
            max_price = pricing.get("max_price", 0)
            avg_price = pricing.get("avg_price", 0)
            items.append(f"• 价格范围：${min_price:.3f} - ${max_price:.2f} / 1M tokens")
            items.append(f"• 平均价格：${avg_price:.3f} / 1M tokens")

        top_models = market_trends.get("top_models_by_price", [])
        if top_models:
            items.append(f"\n热门模型 Top 3：")
            for i, model in enumerate(top_models[:3], 1):
                name = model.get("model", "未知")
                price = model.get("price_per_1m_tokens", 0)
                items.append(f"  {i}. {name} - ${price:.3f}/1M")

        if not items:
            return None

        return {
            "title": "📈 市场使用趋势",
            "subtitle": "来自 OpenRouter",
            "content": "\n".join(items),
            "source": "OpenRouter API"
        }

    def _format_performance(self, aggregated_data):
        """格式化性能基准"""
        items = []

        intelligence = aggregated_data.get("intelligence_rankings", [])
        if intelligence:
            items.append("智能排名 Top 5：")
            for i, rank in enumerate(intelligence[:5], 1):
                model = rank.get("model", "未知")
                score = rank.get("score", 0)
                items.append(f"  {i}. {model} - 分数 {score}")

        speed = aggregated_data.get("speed_rankings", [])
        if speed:
            items.append("\n速度排名 Top 3：")
            for i, rank in enumerate(speed[:3], 1):
                model = rank.get("model", "未知")
                tps = rank.get("tokens_per_sec", 0)
                items.append(f"  {i}. {model} - {tps} tok/s")

        if not items:
            return None

        return {
            "title": "⚡ 性能基准",
            "subtitle": "来自 Artificial Analysis",
            "content": "\n".join(items),
            "source": "Artificial Analysis"
        }

    def _format_cross_validation(self, cross_validation):
        """格式化交叉验证"""
        confirmed = cross_validation.get("confirmed", [])
        unconfirmed = cross_validation.get("unconfirmed", [])

        items = []
        items.append(f"• 已确认：{len(confirmed)} 项")
        items.append(f"• 待确认：{len(unconfirmed)} 项")

        if confirmed:
            items.append("\n已确认项：")
            for item in confirmed[:3]:
                model = item.get("model", "未知")
                sources = ", ".join(item.get("sources", []))
                items.append(f"  • {model} ✓ ({sources})")

        return {
            "title": "🔍 交叉验证",
            "subtitle": "多源印证",
            "content": "\n".join(items),
            "source": "数据交叉验证"
        }


# 测试函数
def test_formatter():
    """测试格式化器"""
    import sys
    # 确保输出使用 UTF-8
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    from analyzers.market_data_aggregator import MarketDataAggregator

    aggregator = MarketDataAggregator()
    aggregated = aggregator.aggregate()

    formatter = MarketReportFormatter()
    cards = formatter.format_for_html(aggregated)

    print(f"生成了 {len(cards)} 个卡片：")
    for i, card in enumerate(cards, 1):
        print(f"\n--- 卡片 {i}: {card['title']} ---")
        print(card['content'])


if __name__ == "__main__":
    test_formatter()

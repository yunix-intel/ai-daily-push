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
        try:
            openrouter_data = fetch_openrouter_data()
        except Exception as e:
            self._log_error("OpenRouter 数据获取", e)
            openrouter_data = {"total_models": 0, "rankings": [], "pricing": []}

        # 2. 获取 Artificial Analysis 数据
        print("2. 获取 Artificial Analysis 数据...")
        try:
            aa_data = fetch_aa_data()
        except Exception as e:
            self._log_error("Artificial Analysis 数据获取", e)
            aa_data = {"intelligence": [], "speed": [], "cost": []}

        # 3. 提取新闻指标（如果提供了新闻）
        news_metrics = {}
        if news_items:
            print("3. 从新闻中提取指标...")
            try:
                news_metrics = self.metrics_extractor.extract_metrics(news_items)
            except Exception as e:
                self._log_error("新闻指标提取", e)
                news_metrics = self.metrics_extractor._empty_metrics()
        else:
            print("3. 跳过新闻指标提取（无新闻数据）")
            news_metrics = self.metrics_extractor._empty_metrics()

        # 4. 整合数据
        print("4. 整合数据...")
        try:
            aggregated = self._merge_data(openrouter_data, aa_data, news_metrics)
        except Exception as e:
            self._log_error("数据整合", e)
            return self._empty_aggregated()

        # 5. 交叉验证
        print("5. 交叉验证...")
        try:
            aggregated['cross_validation'] = self._cross_validate(
                openrouter_data, news_metrics
            )
        except Exception as e:
            self._log_error("交叉验证", e)
            aggregated['cross_validation'] = {"confirmed": [], "unconfirmed": []}

        print("=== 聚合完成 ===\n")
        return aggregated

    def _log_error(self, context, error):
        """统一的错误日志格式"""
        error_type = type(error).__name__
        print(f"     [ERROR] {context}失败 - {error_type}: {error}")

    def _empty_aggregated(self):
        """返回空的聚合数据结构"""
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "timestamp": datetime.now().isoformat(),
            "market_trends": {
                "total_models": 0,
                "top_models_by_price": [],
                "pricing_summary": {}
            },
            "intelligence_rankings": [],
            "speed_rankings": [],
            "cost_rankings": [],
            "news_metrics": self.metrics_extractor._empty_metrics(),
            "cross_validation": {"confirmed": [], "unconfirmed": []},
            "sources": {
                "openrouter": None,
                "artificial_analysis": None,
                "news_count": 0
            }
        }

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

            # Artificial Analysis 数据（去重）
            "intelligence_rankings": self._deduplicate_rankings(aa.get("intelligence", []))[:10],
            "speed_rankings": self._deduplicate_rankings(aa.get("speed", []))[:10],
            "cost_rankings": self._deduplicate_rankings(aa.get("cost", []))[:10],

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

    def _deduplicate_rankings(self, rankings):
        """去重排名数据（基于模型名称和分数）"""
        if not rankings:
            return []

        seen = set()
        unique = []

        for rank in rankings:
            model = rank.get("model", "")
            score = rank.get("score", 0)

            # 创建唯一键（标准化模型名称 + 分数）
            normalized_model = self._normalize_model_name(model)
            key = (normalized_model, score)

            if key not in seen and model:  # 确保模型名称不为空
                seen.add(key)
                unique.append(rank)

        return unique

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
            # 使用模糊匹配
            found_in_or = False
            matched_model = None

            for or_model in openrouter_models.keys():
                if self._fuzzy_match_model(model_name, or_model):
                    found_in_or = True
                    matched_model = or_model
                    break

            if found_in_or:
                validated["confirmed"].append({
                    "type": "price_change",
                    "model": model_name,
                    "matched_with": matched_model,
                    "sources": ["news", "openrouter"]
                })
            else:
                validated["unconfirmed"].append({
                    "type": "price_change",
                    "model": model_name,
                    "sources": ["news"]
                })

        return validated

    def _normalize_model_name(self, name):
        """标准化模型名称用于匹配"""
        import re
        if not name:
            return ""

        # 移除常见前缀
        name = re.sub(r'^(OpenAI|Anthropic|Google|Meta|DeepSeek|Qwen|Alibaba|Tencent|Z\.ai):\s*', '', name, flags=re.I)
        # 统一大小写
        name = name.lower()
        # 移除特殊字符和空格
        name = re.sub(r'[-_\s\.]+', '', name)
        return name

    def _fuzzy_match_model(self, name1, name2, threshold=0.75):
        """模糊匹配两个模型名称"""
        from difflib import SequenceMatcher

        n1 = self._normalize_model_name(name1)
        n2 = self._normalize_model_name(name2)

        if not n1 or not n2:
            return False

        # 检查是否有一个是另一个的子串
        if n1 in n2 or n2 in n1:
            return True

        # 使用序列匹配器计算相似度
        ratio = SequenceMatcher(None, n1, n2).ratio()
        return ratio >= threshold


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

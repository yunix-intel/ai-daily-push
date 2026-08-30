#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从新闻中提取数值指标
"""
import json
from llm.openai_client import OpenAIClient


class NewsMetricsExtractor:
    """新闻指标提取器"""

    def __init__(self):
        try:
            self.llm = OpenAIClient()
        except Exception as e:
            print(f"     [WARN] OpenAI 客户端初始化失败：{e}")
            self.llm = None

    def extract_metrics(self, news_items):
        """
        从新闻列表中提取关键指标

        Args:
            news_items: 新闻列表 [{"title": ..., "summary": ...}, ...]

        Returns:
            dict: 提取的指标
        """
        if not self.llm:
            print("     [WARN] LLM 未初始化，跳过新闻指标提取")
            return self._empty_metrics()

        if not news_items:
            return self._empty_metrics()

        # 构建提示词
        news_text = self._format_news_for_llm(news_items)

        system_prompt = """你是一个专业的 AI 市场数据分析师。
从新闻中提取以下数值指标：
1. 营收/ARR（年度经常性收入）
2. 融资金额
3. 用户数（日活/月活/总用户）
4. Token 调用量
5. 价格变化

返回 JSON 格式：
{
  "revenue": [{"company": "...", "value": "...", "source": "..."}],
  "funding": [{"company": "...", "amount": "...", "round": "..."}],
  "users": [{"company": "...", "metric": "...", "value": "..."}],
  "token_usage": [{"platform": "...", "volume": "..."}],
  "price_changes": [{"model": "...", "change": "...", "new_price": "..."}]
}

如果没有找到某类指标，返回空数组 []。"""

        user_prompt = f"""请从以下 AI 行业新闻中提取数值指标：

{news_text}

请严格按照 JSON 格式返回结果。"""

        # 调用 LLM
        result = self.llm.extract_structured_data(user_prompt, system_prompt)

        return self._normalize_metrics(result)

    def _format_news_for_llm(self, news_items):
        """格式化新闻为 LLM 输入"""
        formatted = []
        for i, item in enumerate(news_items[:20], 1):  # 最多20条
            title = item.get('title', '')
            summary = item.get('summary', '')
            formatted.append(f"{i}. {title}\n{summary}\n")

        return "\n".join(formatted)

    def _normalize_metrics(self, raw_metrics):
        """标准化指标数据"""
        normalized = {
            "revenue": raw_metrics.get("revenue", []),
            "funding": raw_metrics.get("funding", []),
            "users": raw_metrics.get("users", []),
            "token_usage": raw_metrics.get("token_usage", []),
            "price_changes": raw_metrics.get("price_changes", [])
        }

        return normalized

    def _empty_metrics(self):
        """返回空指标"""
        return {
            "revenue": [],
            "funding": [],
            "users": [],
            "token_usage": [],
            "price_changes": []
        }


# 测试函数
def test_extractor():
    """测试新闻指标提取"""
    sample_news = [
        {
            "title": "Anthropic ARR 突破 10 亿美元",
            "summary": "Anthropic 宣布年度经常性收入（ARR）已达到 10 亿美元，同比增长 300%。"
        },
        {
            "title": "OpenAI 宣布 GPT-4o 降价 50%",
            "summary": "OpenAI 今日宣布 GPT-4o 价格下调 50%，新价格为每百万 token $2.5。"
        }
    ]

    extractor = NewsMetricsExtractor()
    metrics = extractor.extract_metrics(sample_news)

    print("提取的指标：")
    print(json.dumps(metrics, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    test_extractor()

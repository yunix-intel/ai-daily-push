#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
新闻指标提取模块 - 从 AI 新闻中提取关键数值指标
"""
import json
import re


class NewsMetricsExtractor:
    """新闻指标提取器"""

    # 单次请求最多塞多少条新闻。一次性把 30+ 条丢给模型，
    # 网关等不到上游响应就返回 504，整批指标全丢；
    # 分批还能做到「单批失败只丢这一批」。
    BATCH_SIZE = 12

    def __init__(self, llm_caller=None):
        """
        初始化提取器

        Args:
            llm_caller: LLM 调用函数 (system_prompt, user_prompt, model) -> dict
        """
        self.llm_caller = llm_caller

    def extract_metrics(self, news_items):
        """
        从新闻列表中提取关键指标（自动分批）

        Args:
            news_items: 新闻列表，每个包含 title, summary, content

        Returns:
            list: 提取的指标列表
        """
        if not self.llm_caller or not news_items:
            return []

        print(f"     提取 {len(news_items)} 条新闻的关键指标...")

        collected = []
        failed = 0
        total_batches = (len(news_items) + self.BATCH_SIZE - 1) // self.BATCH_SIZE
        for bi, start in enumerate(range(0, len(news_items), self.BATCH_SIZE), 1):
            chunk = news_items[start:start + self.BATCH_SIZE]
            got = self._extract_chunk(chunk, offset=start)
            if got is None:
                failed += 1
                print(f"     [!] 指标提取第 {bi}/{total_batches} 批失败，跳过该批")
                continue
            collected.extend(got)

        print(f"     提取到 {len(collected)} 个指标"
              + (f"（{failed}/{total_batches} 批失败）" if failed else ""))
        return collected

    def _extract_chunk(self, news_items, offset=0):
        """提取单批。成功返回列表（可能为空），失败返回 None 以便调用方区分。"""
        # 准备新闻文本
        news_texts = []
        for i, item in enumerate(news_items):
            text = f"[{offset + i + 1}] {item.get('title', '')} - {item.get('summary', '')}"
            news_texts.append(text)

        news_combined = "\n".join(news_texts)

        system_prompt = """你是专业的 AI 行业数据分析师，擅长从新闻中提取关键数值指标。"""

        user_prompt = f"""请从以下 AI 行业新闻中提取关键数值指标：

{news_combined}

请提取以下类型的指标：
1. **ARR/营收**：年度经常性收入、季度营收、年度营收
2. **融资/估值**：融资金额、公司估值、投资轮次
3. **用户数据**：总用户数、日活跃用户(DAU)、月活跃用户(MAU)、周活跃用户(WAU)
4. **Token 使用量**：日/周/月 Token 调用量、API 调用次数
5. **定价变化**：价格调整、折扣、免费额度
6. **市场份额**：市场占有率、使用率百分比

返回 JSON 数组格式：
[
  {{
    "company": "公司名称",
    "metric_type": "ARR|融资|用户数|Token使用量|定价|市场份额",
    "metric_name": "具体指标名称（如：年度ARR、月活用户、周Token调用量）",
    "value": 数值（纯数字，如果是百分比则转为小数，如 28% -> 0.28）,
    "unit": "单位（USD|CNY|亿美元|万|亿|tokens|calls|%）",
    "period": "时间期间（如：2024-Q3、2024年、本周、本月）",
    "source_index": 新闻序号（1-based）,
    "confidence": 置信度（0.5-1.0，官方公告0.9+，媒体报道0.7-0.8，分析师估计0.5-0.6）,
    "context": "简短上下文（20字内，如：Anthropic CEO宣布、OpenAI财报显示）"
  }}
]

要求：
- 只提取明确的数值指标，不要猜测
- 单位统一：美元用 USD，人民币用 CNY，大数用"亿"
- Token 使用量保留原始单位（如 15.2T tokens）
- 置信度基于信息来源的可靠性
- 如果没有找到指标，返回空数组 []

只返回 JSON，格式为 {{"metrics": [ ...上述对象... ]}}，不要添加其他内容。"""

        try:
            result = self.llm_caller(system_prompt, user_prompt)

            # response_format=json_object 会强制模型把数组包成
            # {"metrics": [...]} 这种对象，直接 isinstance(list) 判定必然失败，
            # 提取到的指标会被整批丢掉（页面上 ARR/Token/定价 全是空的）。
            if isinstance(result, dict):
                for value in result.values():
                    if isinstance(value, list):
                        result = value
                        break

            if isinstance(result, list):
                return result
            print(f"     [WARN] 指标提取结果格式错误：{type(result).__name__}")
            return []

        except Exception as e:
            print(f"     [WARN] 指标提取失败: {e}")
            return None

    def group_metrics_by_type(self, metrics):
        """
        按类型分组指标

        Args:
            metrics: 指标列表

        Returns:
            dict: 按 metric_type 分组的指标
        """
        grouped = {
            "ARR": [],
            "融资": [],
            "用户数": [],
            "Token使用量": [],
            "定价": [],
            "市场份额": []
        }

        for metric in metrics:
            metric_type = metric.get("metric_type", "")
            if metric_type in grouped:
                grouped[metric_type].append(metric)

        return grouped

    def filter_high_confidence_metrics(self, metrics, min_confidence=0.7):
        """
        过滤高置信度指标

        Args:
            metrics: 指标列表
            min_confidence: 最小置信度阈值

        Returns:
            list: 高置信度指标列表
        """
        return [
            m for m in metrics
            if m.get("confidence", 0) >= min_confidence
        ]

    def format_metric_display(self, metric):
        """
        格式化指标显示

        Args:
            metric: 单个指标 dict

        Returns:
            str: 格式化的显示文本
        """
        company = metric.get("company", "")
        metric_name = metric.get("metric_name", "")
        value = metric.get("value", 0)
        unit = metric.get("unit", "")
        context = metric.get("context", "")

        # 格式化数值
        if unit == "%":
            value_str = f"{value * 100:.1f}%"
        elif unit in ["USD", "CNY"]:
            if value >= 1_000_000_000:
                value_str = f"${value / 1_000_000_000:.1f}B"
            elif value >= 1_000_000:
                value_str = f"${value / 1_000_000:.1f}M"
            else:
                value_str = f"${value:,.0f}"
        elif unit == "亿美元":
            value_str = f"{value} 亿美元"
        elif "tokens" in unit.lower():
            # Token 单位保留原样
            if value >= 1_000_000_000_000:  # T tokens
                value_str = f"{value / 1_000_000_000_000:.1f}T tokens"
            elif value >= 1_000_000_000:  # B tokens
                value_str = f"{value / 1_000_000_000:.1f}B tokens"
            else:
                value_str = f"{value:,.0f} tokens"
        else:
            value_str = f"{value:,.0f} {unit}"

        # 组合显示
        if context:
            return f"{company} {metric_name} {value_str} ({context})"
        else:
            return f"{company} {metric_name} {value_str}"


def extract_metrics_from_news(news_items, llm_caller):
    """
    从新闻中提取指标的便捷函数

    Args:
        news_items: 新闻列表
        llm_caller: LLM 调用函数

    Returns:
        dict: 分组的指标数据
    """
    extractor = NewsMetricsExtractor(llm_caller=llm_caller)

    # 提取指标
    metrics = extractor.extract_metrics(news_items)

    # 过滤高置信度指标
    high_confidence_metrics = extractor.filter_high_confidence_metrics(metrics, min_confidence=0.7)

    # 按类型分组
    grouped_metrics = extractor.group_metrics_by_type(high_confidence_metrics)

    return {
        "all_metrics": metrics,
        "high_confidence_metrics": high_confidence_metrics,
        "grouped_metrics": grouped_metrics,
        "total_count": len(metrics),
        "high_confidence_count": len(high_confidence_metrics)
    }


# 测试函数
if __name__ == "__main__":
    # 模拟 LLM 调用
    def mock_llm(system_prompt, user_prompt, model=None):
        return [
            {
                "company": "Anthropic",
                "metric_type": "ARR",
                "metric_name": "年度ARR",
                "value": 1000000000,
                "unit": "USD",
                "period": "2024-Q3",
                "source_index": 1,
                "confidence": 0.9,
                "context": "CEO 公开宣布"
            },
            {
                "company": "OpenAI",
                "metric_type": "用户数",
                "metric_name": "周活跃用户",
                "value": 300000000,
                "unit": "人",
                "period": "本周",
                "source_index": 2,
                "confidence": 0.85,
                "context": "官方博客披露"
            }
        ]

    extractor = NewsMetricsExtractor(llm_caller=mock_llm)

    # 测试新闻
    test_news = [
        {
            "title": "Anthropic ARR 突破 10 亿美元",
            "summary": "Anthropic CEO 宣布公司年度经常性收入突破 10 亿美元..."
        },
        {
            "title": "ChatGPT 周活用户达 3 亿",
            "summary": "OpenAI 官方博客披露 ChatGPT 周活跃用户数达到 3 亿..."
        }
    ]

    print("测试新闻指标提取...")
    result = extract_metrics_from_news(test_news, mock_llm)
    print(json.dumps(result, ensure_ascii=False, indent=2))

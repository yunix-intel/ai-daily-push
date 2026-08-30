# Phase A4: LLM 数据分析 - 实施计划

## 📊 当前状态分析

### 已完成的基础设施
✅ **爬虫模块**（Phase A1-A3）
- OpenRouter 爬虫：396个模型数据 + 价格信息
- Artificial Analysis 爬虫：Intelligence 数据
- 缓存机制：按日期缓存，历史降级
- 单元测试：6个测试全部通过

### 现有数据结构
**OpenRouter 数据**：
```json
{
  "date": "2026-08-30",
  "total_models": 396,
  "pricing": [...],  // 50个模型价格
  "rankings": [...]  // 20个模型排名
}
```

**Artificial Analysis 数据**：
```json
{
  "date": "2026-08-30",
  "intelligence": [...],  // 9个模型分数
  "speed": [],
  "cost": []
}
```

**AI 日报新闻数据**（已有）：
```json
{
  "title": "Anthropic ARR 突破 10 亿美元",
  "link": "...",
  "summary": "...",
  "source": "TechCrunch",
  "pubDate": "..."
}
```

---

## 🎯 Phase A4 目标

### 核心功能
1. **数据整合模块** - 合并多个数据源
2. **LLM 数据提取** - 从新闻中提取数值指标
3. **趋势分析** - 对比历史数据
4. **交叉验证** - 多源印证
5. **统一数据结构** - 生成标准化输出

### 目标输出结构
```json
{
  "date": "2026-08-30",
  "summary": "本周 AI 市场动态摘要...",
  "market_trends": {
    "top_models_by_usage": [...],
    "pricing_changes": [...],
    "intelligence_rankings": [...]
  },
  "news_metrics": {
    "revenue": [...],
    "funding": [...],
    "user_growth": [...],
    "price_changes": [...]
  },
  "cross_validation": {
    "confirmed": [...],
    "unconfirmed": [...]
  },
  "insights": [
    "GPT-4o 降价 50%（OpenAI 公告 + OpenRouter 确认）",
    "Claude Sonnet 3.5 使用量增长 12%"
  ]
}
```

---

## 🔧 实施方案

### 模块架构
```
scrapers/
  ├── base_scraper.py         # 基础爬虫类（已有）
  ├── openrouter_scraper.py   # OpenRouter（已完成）
  └── artificial_analysis_scraper.py  # AA（已完成）

analyzers/                    # 新增模块
  ├── __init__.py
  ├── market_data_aggregator.py   # 数据整合器
  ├── news_metrics_extractor.py   # 新闻指标提取
  └── trend_analyzer.py            # 趋势分析

llm/                          # 新增模块
  ├── __init__.py
  └── openai_client.py        # OpenAI API 封装
```

---

## 📋 实施步骤

### 步骤 1: 创建 LLM 客户端封装（30分钟）

**文件**：`llm/openai_client.py`

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenAI API 客户端封装
"""
import os
import json
from openai import OpenAI


class OpenAIClient:
    """OpenAI API 客户端"""
    
    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not found")
        
        self.client = OpenAI(api_key=self.api_key)
        self.model = "gpt-4o-mini"  # 使用性价比高的模型
    
    def extract_structured_data(self, prompt, system_prompt=None):
        """
        提取结构化数据（JSON）
        
        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词（可选）
        
        Returns:
            dict: 解析后的 JSON 数据
        """
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.1,  # 低温度，更确定性
                response_format={"type": "json_object"}  # 强制 JSON 输出
            )
            
            content = response.choices[0].message.content
            return json.loads(content)
        
        except Exception as e:
            print(f"[ERROR] OpenAI API 调用失败：{e}")
            return {}
    
    def summarize(self, text, max_length=200):
        """
        文本摘要
        
        Args:
            text: 输入文本
            max_length: 最大长度
        
        Returns:
            str: 摘要文本
        """
        try:
            prompt = f"请用不超过 {max_length} 字总结以下内容：\n\n{text}"
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=max_length * 2
            )
            
            return response.choices[0].message.content.strip()
        
        except Exception as e:
            print(f"[ERROR] 摘要生成失败：{e}")
            return ""
```

### 步骤 2: 新闻指标提取器（60分钟）

**文件**：`analyzers/news_metrics_extractor.py`

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从新闻中提取数值指标
"""
import re
from llm.openai_client import OpenAIClient


class NewsMetricsExtractor:
    """新闻指标提取器"""
    
    def __init__(self):
        self.llm = OpenAIClient()
    
    def extract_metrics(self, news_items):
        """
        从新闻列表中提取关键指标
        
        Args:
            news_items: 新闻列表 [{"title": ..., "summary": ...}, ...]
        
        Returns:
            dict: 提取的指标
        """
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

如果没有找到某类指标，返回空数组 []。
"""
        
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
```

### 步骤 3: 市场数据聚合器（60分钟）

**文件**：`analyzers/market_data_aggregator.py`

```python
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
                "news_count": len(news_metrics) if news_metrics else 0
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
            "min_price": min(prices),
            "max_price": max(prices),
            "avg_price": sum(prices) / len(prices),
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
            found_in_or = any(model_name in or_model for or_model in openrouter_models.keys())
            
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
```

### 步骤 4: 趋势分析器（30分钟）

**文件**：`analyzers/trend_analyzer.py`

```python
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
```

### 步骤 5: 集成测试（30分钟）

**文件**：`tests/test_analyzers.py`

```python
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
        
        print(f"[OK] Market data aggregator test passed")
        print(f"  - Date: {result.get('date')}")
        print(f"  - Total models: {result['market_trends'].get('total_models')}")
    
    def test_trend_analyzer(self):
        """测试趋势分析器"""
        analyzer = TrendAnalyzer()
        aggregator = MarketDataAggregator()
        current_data = aggregator.aggregate()
        
        trends = analyzer.analyze_trends(current_data, days_back=3)
        
        # 验证结构
        self.assertIn('period', trends)
        self.assertIn('price_trends', trends)
        self.assertIn('ranking_trends', trends)
        
        print(f"[OK] Trend analyzer test passed")
        print(f"  - Period: {trends.get('period')}")
        print(f"  - Price trends: {len(trends.get('price_trends', []))}")


if __name__ == '__main__':
    unittest.main()
```

---

## 🧪 测试计划

### 测试场景
1. **LLM 客户端测试**
   - API 连接正常
   - JSON 输出格式正确
   - 异常处理（超时、格式错误）

2. **新闻指标提取测试**
   - 提取营收数据
   - 提取融资信息
   - 提取价格变化
   - 空新闻处理

3. **数据聚合测试**
   - 三个数据源整合
   - 交叉验证逻辑
   - 数据结构完整性

4. **趋势分析测试**
   - 历史数据加载
   - 价格趋势计算
   - 排名变化追踪

---

## 📝 待办清单

- [ ] 1. 创建 llm/ 和 analyzers/ 目录
- [ ] 2. 实现 OpenAI 客户端封装
- [ ] 3. 实现新闻指标提取器
- [ ] 4. 实现市场数据聚合器
- [ ] 5. 实现趋势分析器
- [ ] 6. 编写单元测试
- [ ] 7. 本地测试（需要 OPENAI_API_KEY）
- [ ] 8. 更新 requirements.txt
- [ ] 9. 提交代码

---

## ⚠️ 注意事项

### API Key 管理
- 本地测试：使用 `.env` 文件
- GitHub Actions：使用 Secrets
- 错误处理：API Key 缺失时的降级策略

### 成本控制
- 使用 `gpt-4o-mini` 模型（性价比高）
- 限制新闻数量（最多20条）
- 温度设置低（0.1-0.3）减少随机性

### 错误处理
- API 超时：设置超时时间
- JSON 解析失败：返回空对象
- 无历史数据：返回提示信息

---

## 🚀 准备退出计划模式

等待用户批准后开始实施。

# Phase A5: HTML 报告生成 - 实施计划

## 📊 当前状态分析

### 已完成的模块（Phase A1-A4）
✅ **数据采集**
- OpenRouter 爬虫：396个模型数据
- Artificial Analysis 爬虫：Intelligence 数据
- 缓存机制完善

✅ **数据分析**
- 市场数据聚合器
- 新闻指标提取器（LLM）
- 趋势分析器
- 交叉验证逻辑

### 现有 AI 日报架构
**流程**：
1. 拉取 AI HOT 日报
2. 抓取多个 RSS 来源
3. 生成单文件 HTML 仪表盘
4. 渲染 Markdown 摘要
5. 推送到微信（PushPlus）

**HTML 板块**（当前5个）：
- 📰 AI HOT 日报
- 🔥 AI 要闻速递
- 📝 博客深度
- 🎓 学术前沿
- 💼 创业动态

---

## 🎯 Phase A5 目标

### 核心任务
1. **新增第6个板块**："📊 行业数据洞察"
2. **集成市场数据聚合器**到主流程
3. **设计数据可视化展示**
4. **更新 HTML 模板**
5. **错误处理和降级**

### 目标展示效果

```
📊 行业数据洞察

【💡 官方公布数据】（来自新闻）
• Anthropic ARR 突破 10 亿美元 ↗
• ChatGPT 周活用户 3 亿 ↗

【📈 市场使用趋势】（OpenRouter）
• 总模型数：396 个
• 价格范围：$0.042 - $30.0 / 1M tokens
• 平均价格：$2.39 / 1M tokens

【⚡ 性能基准】（Artificial Analysis）
• 智能排名 Top 3：
  1. Qwen - 分数 3
  2. DeepSeek - 分数 4
  3. Llama - 分数 29

【🔍 交叉验证】
• 已确认：0 项
• 待确认：0 项
```

---

## 🔧 实施方案

### 方案选择：集成到现有流程

**优势**：
- ✅ 复用现有 HTML 模板和样式
- ✅ 统一的用户体验
- ✅ 单文件仪表盘，易于托管

**架构**：
```
ai_daily_push.py (主流程)
  ├── 1. 拉取 AI HOT 日报
  ├── 2. 抓取 RSS 来源
  ├── 3. 调用市场数据聚合器 ← 新增
  ├── 4. 生成 HTML 仪表盘（6个板块）
  └── 5. 推送
```

---

## 📋 实施步骤

### 步骤 1: 创建市场数据格式化器（45分钟）

**文件**：`analyzers/market_report_formatter.py`

```python
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
            items.append("智能排名 Top 3：")
            for i, rank in enumerate(intelligence[:3], 1):
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
```

### 步骤 2: 修改 ai_daily_push.py 主流程（60分钟）

**修改位置 1**：导入新模块

```python
# 在文件顶部添加
from analyzers.market_data_aggregator import MarketDataAggregator
from analyzers.market_report_formatter import MarketReportFormatter
```

**修改位置 2**：添加市场数据采集步骤

```python
def main():
    # ... 现有代码 ...
    
    # [新增] 步骤 2.5: 采集市场数据
    print("[2.5/5] 采集市场数据...")
    market_data = []
    try:
        aggregator = MarketDataAggregator()
        formatter = MarketReportFormatter()
        
        # 聚合数据（可以传入新闻项用于指标提取）
        aggregated = aggregator.aggregate(news_items=None)  # 暂不传新闻
        
        # 格式化为卡片
        market_cards = formatter.format_for_html(aggregated)
        
        # 转换为统一格式
        for i, card in enumerate(market_cards):
            market_data.append({
                "idx": i + 1,
                "title": card["title"],
                "summary": card["content"],
                "link": "#",
                "source": card["source"],
                "pubDate": datetime.now().isoformat()
            })
        
        print(f"  ✓ 市场数据：{len(market_data)} 个指标卡片")
    
    except Exception as e:
        print(f"  [WARN] 市场数据采集失败：{e}")
        market_data = []
    
    # ... 继续现有代码 ...
```

**修改位置 3**：更新数据结构（添加第6个板块）

```python
# 构建数据结构
data = {
    "meta": {
        "date": bjnow.strftime("%Y-%m-%d"),
        "time": bjnow.strftime("%H:%M"),
        "window": window_text,
        "total": len(aihot_items) + len(rss_items) + len(blog_items) + len(arxiv_items) + len(startup_items) + len(market_data),  # 新增
        "dailyUrl": daily_url
    },
    "sections": [
        {"id": "aihot", "name": "📰 AI HOT 日报", "items": aihot_items},
        {"id": "news", "name": "🔥 AI 要闻速递", "items": rss_items},
        {"id": "blog", "name": "📝 博客深度", "items": blog_items},
        {"id": "arxiv", "name": "🎓 学术前沿", "items": arxiv_items},
        {"id": "startup", "name": "💼 创业动态", "items": startup_items},
        {"id": "market", "name": "📊 行业数据洞察", "items": market_data}  # 新增
    ]
}
```

### 步骤 3: 更新 HTML 模板样式（可选，30分钟）

由于现有模板已经很完善，新板块会自动使用现有样式。如需特殊样式，可以添加：

```css
/* 市场数据特殊样式 */
.section#market .card .summary {
  font-family: 'Consolas', 'Monaco', monospace;
  white-space: pre-wrap;
}
```

### 步骤 4: 测试集成（30分钟）

```bash
# 本地测试
python ai_daily_push.py --no-push

# 检查生成的 HTML
ls -lh ai_daily_dashboard.html

# 在浏览器中打开
start ai_daily_dashboard.html  # Windows
```

### 步骤 5: 错误处理和降级（15分钟）

确保市场数据采集失败不影响整体流程：

```python
try:
    # 市场数据采集
    market_data = collect_market_data()
except Exception as e:
    print(f"  [WARN] 市场数据采集失败，跳过此板块：{e}")
    market_data = []
    # 继续执行后续流程
```

---

## 🧪 测试计划

### 测试场景
1. **完整数据** - 所有数据源正常
2. **部分数据** - 某些数据源失败
3. **无市场数据** - 市场数据采集全部失败
4. **无 API Key** - OpenAI API Key 未配置

### 验收标准
- [ ] 第6个板块正确显示
- [ ] 市场数据卡片格式正确
- [ ] 数据采集失败时优雅降级
- [ ] HTML 仪表盘完整渲染
- [ ] 总条数统计正确
- [ ] 导航链接包含市场数据板块

---

## 📝 待办清单

- [ ] 1. 创建 market_report_formatter.py
- [ ] 2. 修改 ai_daily_push.py 导入
- [ ] 3. 添加市场数据采集步骤
- [ ] 4. 更新数据结构（第6个板块）
- [ ] 5. 本地测试（--no-push）
- [ ] 6. 验证 HTML 输出
- [ ] 7. 错误处理测试
- [ ] 8. 提交代码

---

## ⚠️ 注意事项

### 性能影响
- 市场数据采集增加 2-5 秒执行时间
- OpenAI API 调用增加成本（如果启用）
- 建议在 GitHub Actions 中配置 API Key

### 降级策略
1. **API Key 未配置** - 跳过新闻指标提取
2. **OpenRouter 失败** - 使用缓存数据
3. **AA 失败** - 使用缓存数据
4. **全部失败** - 市场数据板块显示空

### 用户体验
- 市场数据板块放在最后（第6个）
- 不影响现有5个板块
- 采集失败时不阻塞整体流程

---

## 🚀 准备退出计划模式

等待用户批准后开始实施。

# AI 日报数据分析系统实施计划

## 目标
为 AI 日报添加全面的行业数据分析功能，融合三个数据源：
1. **现有 RSS 新闻**：提取 ARR、融资、用户数等官方公布数据
2. **OpenRouter**：实时模型使用量、市场份额、价格趋势
3. **Artificial Analysis**：模型性能基准、速度、成本对比

## 架构设计

### 数据流
```
┌─────────────────────────────────────────────┐
│  数据采集层                                  │
├─────────────────────────────────────────────┤
│  • openrouter_scraper.py                   │
│    - /rankings (使用量趋势)                 │
│    - /rankings?tab=leaderboard (排行榜)    │
│    - /models (价格数据)                     │
│  • artificial_analysis_scraper.py          │
│    - / (Intelligence/Speed/Cost)           │
│    - /leaderboards                         │
│  • LLM 从新闻提取数值指标                   │
├─────────────────────────────────────────────┤
│  数据整合层                                  │
├─────────────────────────────────────────────┤
│  • market_data_aggregator.py              │
│    - 合并三个数据源                         │
│    - 交叉验证                               │
│    - 趋势分析                               │
│    - 生成结构化 JSON                        │
├─────────────────────────────────────────────┤
│  展示层                                     │
├─────────────────────────────────────────────┤
│  • ai_daily_push.py (修改)                │
│    - 新增"📊 行业数据洞察"板块              │
│  • ai_daily_dashboard_template.html (修改) │
│    - 数据可视化图表                         │
│  • Markdown 推送优化                        │
└─────────────────────────────────────────────┘
```

## 文件结构

### 新增文件
```
ai-daily-push/
├── scrapers/
│   ├── __init__.py
│   ├── openrouter_scraper.py          # OpenRouter 数据爬虫
│   ├── artificial_analysis_scraper.py # AA 数据爬虫
│   └── base_scraper.py                # 基础爬虫类
├── data/
│   ├── market_data/                   # 每日数据快照
│   │   └── YYYY-MM-DD.json
│   └── market_data_aggregator.py      # 数据整合器
└── tests/
    ├── test_openrouter_scraper.py
    └── test_aa_scraper.py
```

### 修改文件
```
ai_daily_push.py                       # 集成市场数据
ai_daily_dashboard_template.html       # 新增数据展示区块
.github/workflows/daily.yml            # 添加依赖安装
```

## 技术方案

### 1. OpenRouter 爬虫 (openrouter_scraper.py)

**技术选择：Playwright**
- 原因：页面使用 Next.js SSR，数据通过客户端 hydration 加载
- 需要渲染 JavaScript 才能获取完整数据

**抓取内容：**
```python
{
  "rankings": {
    "date": "2026-08-28",
    "models": [
      {
        "name": "Claude Sonnet 3.5",
        "tokens_weekly": "15.2T",
        "market_share": 0.28,
        "trend": "+12%"
      }
    ]
  },
  "pricing": {
    "updates": [
      {
        "model": "GPT-4o",
        "old_price": 0.03,
        "new_price": 0.015,
        "change_date": "2026-08-15"
      }
    ]
  }
}
```

### 2. Artificial Analysis 爬虫 (artificial_analysis_scraper.py)

**抓取内容：**
```python
{
  "intelligence": [
    {"model": "Claude Opus 5", "score": 63},
    {"model": "GPT-4", "score": 62}
  ],
  "speed": [
    {"model": "Gemini 2.5 Flash", "tokens_per_sec": 324}
  ],
  "cost": [
    {"model": "Llama 3.3 70B", "cost_per_task": 0.05}
  ]
}
```

### 3. 新闻数据提取 (修改 ai_daily_push.py)

**使用现有 LLM 集成，新增提取函数：**
```python
def extract_market_metrics(news_items):
    """从新闻标题和摘要中提取数值指标"""
    prompt = """
    从以下新闻中提取关键数值指标：
    - ARR/营收（单位：美元）
    - 融资金额（单位：美元）
    - 用户数/日活/月活
    - Token 调用量
    - 价格变化
    
    返回 JSON 格式...
    """
    # 调用 LLM 提取
```

### 4. 数据整合 (market_data_aggregator.py)

**核心功能：**
1. 合并三个数据源
2. 交叉验证（例如：新闻报道的价格变化 vs OpenRouter 实际价格）
3. 趋势分析（对比历史数据）
4. 生成统一的数据结构

**输出格式：**
```python
{
  "date": "2026-08-28",
  "highlights": {
    "official_announcements": [
      {"text": "Anthropic ARR 突破 10 亿美元", "source": "新闻", "verified": true}
    ],
    "market_usage": [
      {"text": "Claude Sonnet 3.5 本周 15.2T tokens ↗ +12%", "source": "OpenRouter"}
    ],
    "performance_benchmarks": [
      {"text": "智能排名：Claude Opus 5 (63) > GPT-4 (62)", "source": "AA"}
    ],
    "price_wars": [
      {"text": "GPT-4o Token 价格 ↘ -50%", "source": "新闻+OpenRouter", "verified": true}
    ]
  },
  "raw_data": {
    "openrouter": {...},
    "artificial_analysis": {...},
    "news_metrics": {...}
  }
}
```

### 5. 展示层修改

**HTML Dashboard 新增区块：**
```html
<section class="market-insights">
  <h2>📊 行业数据洞察</h2>
  
  <div class="metrics-grid">
    <div class="metric-card official">
      <h3>💡 官方公布数据</h3>
      <ul><!-- 来自新闻提取 --></ul>
    </div>
    
    <div class="metric-card usage">
      <h3>📈 市场使用趋势</h3>
      <ul><!-- 来自 OpenRouter --></ul>
    </div>
    
    <div class="metric-card benchmarks">
      <h3>⚡ 性能基准</h3>
      <ul><!-- 来自 AA --></ul>
    </div>
    
    <div class="metric-card verified">
      <h3>🔍 交叉验证</h3>
      <ul><!-- 多源印证的数据 --></ul>
    </div>
  </div>
  
  <div class="charts">
    <canvas id="usageTrendChart"></canvas>
    <canvas id="performanceChart"></canvas>
  </div>
</section>
```

**Markdown 推送格式：**
```markdown
# AI 日报 · 2026年8月28日

## 📊 行业数据洞察

**💡 官方公布数据**
• Anthropic ARR 突破 10 亿美元 ↗
• ChatGPT 周活用户 3 亿 ↗

**📈 市场使用趋势（OpenRouter）**
• Claude Sonnet 3.5 本周 15.2T tokens ↗ +12%
• GPT-4o 市场份额 28% ↘ -3%

**⚡ 性能基准（Artificial Analysis）**
• 智能排名：Claude Opus 5 (63) > GPT-4 (62)
• 速度冠军：Gemini 2.5 Flash (324 tok/s)

**🔍 交叉验证**
• GPT-4o 降价 50% ✓（OpenAI 公告 + OpenRouter 确认）

---

【然后是原有的各板块内容】
```

## 实施步骤

### Phase 1: 爬虫开发 (2-3 小时)
1. ✅ 安装依赖：`playwright`, `beautifulsoup4`
2. ✅ 开发 `base_scraper.py`（通用爬虫基类）
3. ✅ 开发 `openrouter_scraper.py`
4. ✅ 开发 `artificial_analysis_scraper.py`
5. ✅ 单元测试

### Phase 2: 数据整合 (1-2 小时)
1. ✅ 开发 `market_data_aggregator.py`
2. ✅ 实现交叉验证逻辑
3. ✅ 实现趋势分析（对比历史数据）
4. ✅ 测试数据输出格式

### Phase 3: 新闻提取增强 (1 小时)
1. ✅ 修改 `ai_daily_push.py`
2. ✅ 添加 `extract_market_metrics()` 函数
3. ✅ 集成到现有 LLM 调用流程
4. ✅ 测试提取准确性

### Phase 4: 集成到 AI 日报 (1-2 小时)
1. ✅ 修改 `ai_daily_push.py` 主流程
2. ✅ 调用市场数据聚合器
3. ✅ 生成新的数据结构
4. ✅ 修改 HTML 模板
5. ✅ 修改 Markdown 生成逻辑

### Phase 5: 测试与调优 (1-2 小时)
1. ✅ 本地完整测试
2. ✅ GitHub Actions 配置更新
3. ✅ 错误处理和降级策略
4. ✅ 性能优化

## 依赖管理

### 新增依赖 (requirements.txt)
```
playwright==1.48.0
beautifulsoup4==4.12.3
```

### GitHub Actions 更新
```yaml
- name: 安装浏览器依赖
  run: |
    pip install playwright beautifulsoup4
    playwright install chromium
    playwright install-deps
```

## 错误处理策略

### 降级方案
如果爬虫失败，不影响原有功能：
```python
try:
    market_data = aggregate_market_data()
except Exception as e:
    print(f"⚠️ 市场数据获取失败，跳过该板块：{e}")
    market_data = None

# 只在有数据时添加板块
if market_data:
    sections.insert(0, create_market_insights_section(market_data))
```

### 超时控制
- 每个爬虫最多 30 秒
- 总体数据采集最多 2 分钟
- 超时则跳过，不阻塞日报生成

### 缓存机制
- 如果当天爬取失败，使用昨天的数据
- 在展示时标注"数据截至 XX 日"

## 性能考虑

### 并行爬取
```python
import asyncio

async def fetch_all_market_data():
    tasks = [
        fetch_openrouter_data(),
        fetch_aa_data(),
        extract_news_metrics(news_items)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return process_results(results)
```

### 缓存策略
- 每天只爬取一次，存储到 `data/market_data/YYYY-MM-DD.json`
- GitHub Actions 中缓存 Playwright 浏览器

## 测试计划

### 单元测试
```bash
# 测试 OpenRouter 爬虫
python -m pytest tests/test_openrouter_scraper.py

# 测试 AA 爬虫
python -m pytest tests/test_aa_scraper.py

# 测试数据整合
python -m pytest tests/test_aggregator.py
```

### 集成测试
```bash
# 本地完整运行
python ai_daily_push.py --no-push

# 检查生成的 HTML
open ai_daily_dashboard.html
```

### 边界测试
- [ ] 爬虫失败时的降级
- [ ] 数据格式异常时的处理
- [ ] 空数据的展示
- [ ] 网络超时

## 交付物

1. ✅ 完整可运行的爬虫代码
2. ✅ 集成到 AI 日报的完整流程
3. ✅ 更新的 HTML Dashboard（含数据可视化）
4. ✅ 更新的 Markdown 推送格式
5. ✅ 单元测试和集成测试
6. ✅ 文档和配置说明

## 时间估算
- **开发时间**：6-9 小时
- **测试调优**：2-3 小时
- **总计**：8-12 小时

## 风险与缓解

### 风险 1：网站反爬
- **缓解**：添加 User-Agent、延时、使用 Playwright 模拟真实浏览器

### 风险 2：数据格式变化
- **缓解**：健壮的解析逻辑 + 异常处理 + 降级策略

### 风险 3：性能问题
- **缓解**：并行爬取 + 超时控制 + 缓存

### 风险 4：LLM 调用成本
- **缓解**：新闻提取只处理最新 20 条，使用 mini 模型

## 成功标准

✅ 每天成功抓取 OpenRouter 和 AA 数据
✅ 从新闻中提取至少 3 个关键指标
✅ 数据交叉验证准确率 > 90%
✅ Dashboard 展示清晰美观
✅ 爬虫失败不影响原有功能
✅ 总执行时间增加 < 3 分钟

# AI 日报市场数据分析系统

## 功能概述

为 AI 日报添加了全面的行业数据分析功能，融合三个数据源：

1. **RSS 新闻提取**：从现有新闻中自动提取 ARR、融资、用户数、价格变化等关键指标
2. **OpenRouter 数据**：实时模型使用量、市场份额趋势（基础文本提取）
3. **Artificial Analysis**：模型性能基准数据（基础文本提取）

## 新增功能

### 📊 行业数据洞察板块

在 AI 日报最前面新增"📊 行业数据洞察"板块，展示：

- **官方公告数据**：从新闻中提取的 ARR、营收、融资、用户数等
- **市场使用趋势**：OpenRouter 平台的模型使用数据（带原站链接）
- **性能基准**：Artificial Analysis 的性能测试结果（带原站链接）

### 数据提取能力

自动从新闻标题和摘要中提取：
- ARR/营收数据（支持"亿美元"、"billion"等单位）
- 融资金额
- 用户数/日活/月活
- Token 调用量
- 价格变化（百分比）

## 文件结构

```
ai-daily-push/
├── scrapers/                          # 新增：爬虫模块
│   ├── __init__.py
│   ├── base_scraper.py               # 基础爬虫类（缓存、重试）
│   ├── openrouter_scraper.py         # OpenRouter 数据爬虫
│   └── artificial_analysis_scraper.py # AA 数据爬虫
├── data/
│   ├── market_data/                  # 新增：每日数据快照
│   │   └── YYYY-MM-DD.json
│   └── market_data_aggregator.py     # 新增：数据整合器
├── tests/
│   └── test_market_data.py           # 新增：功能测试
├── ai_daily_push.py                  # 修改：集成市场数据
└── README_MARKET_DATA.md             # 本文档
```

## 使用方法

### 本地测试

```bash
# 测试市场数据功能
cd ai-daily-push
python -c "
import sys
sys.path.insert(0, '.')
from data.market_data_aggregator import aggregate_market_data
from scrapers import fetch_openrouter_data, fetch_aa_data

# 模拟新闻数据
mock_sections = [{
    'label': '📊 行业趋势',
    'items': [{
        'title': 'Anthropic ARR 突破 10 亿美元',
        'summary': 'Anthropic 的年度经常性收入达到 10 亿美元',
        'source': {'name': 'TechCrunch'}
    }]
}]

# 获取市场数据
or_data = fetch_openrouter_data()
aa_data = fetch_aa_data()
insights = aggregate_market_data(mock_sections, or_data, aa_data)

print(f'成功提取 {len(insights[\"highlights\"][\"official_announcements\"])} 条官方公告')
"
```

### 完整运行

```bash
# 生成 AI 日报（包含市场数据）
python ai_daily_push.py --no-push

# 查看生成的 HTML
open ai_daily_dashboard.html
```

## 数据来源

### 1. 新闻提取（主要数据源）
- **优势**：数据来自官方公告和权威媒体，准确可靠
- **提取方式**：正则表达式匹配关键词和数值
- **支持指标**：ARR、融资、用户数、Token、价格

### 2. OpenRouter Rankings
- **网址**：https://openrouter.ai/rankings
- **数据类型**：模型实际使用量排名
- **提取方式**：HTML 文本解析（基础版）
- **限制**：数据通过 JS 动态加载，当前仅提取页面描述和部分模型名称

### 3. Artificial Analysis
- **网址**：https://artificialanalysis.ai
- **数据类型**：Intelligence、Speed、Cost 基准测试
- **提取方式**：HTML 文本解析（基础版）
- **限制**：数据通过 JS 渲染，当前提取准确度有限

## 技术实现

### 缓存机制
- 每天的数据缓存在 `data/market_data/` 目录
- 文件名格式：`{source}_{YYYY-MM-DD}.json`
- 如果当天爬取失败，自动使用最近 3 天的历史缓存

### 错误处理
- **降级策略**：任何爬虫或数据整合失败都不会影响原有的 AI 日报功能
- **超时控制**：每个爬虫最多 30 秒超时
- **编码兼容**：所有输出信息使用纯文本标记（避免 Windows GBK 编码问题）

### 数据整合流程

```
新闻条目 ──→ extract_news_metrics() ──→ 提取数值指标
                                           ↓
OpenRouter ──→ fetch_openrouter_data() ──→ 爬取使用量
                                           ↓
AA ──────────→ fetch_aa_data() ────────→ 爬取性能数据
                                           ↓
                                    aggregate_market_data()
                                           ↓
                                    统一的洞察数据
                                           ↓
                            create_market_insights_section()
                                           ↓
                                    新闻条目格式
                                           ↓
                                 插入到日报最前面
```

## 示例输出

### 市场数据板块示例

```
📊 行业数据洞察

1. Anthropic ARR 突破 10 亿美元
   数据来源：TechCrunch | 类型：revenue
   
2. ChatGPT 周活跃用户达到 3 亿
   数据来源：OpenAI | 类型：users

3. 📈 Claude Sonnet 3.5 本周 15.2T tokens
   数据来源：OpenRouter 实时统计
   查看详情：https://openrouter.ai/rankings

4. ⚡ Claude Opus 5 - 智能指数 63
   数据来源：Artificial Analysis 性能测试
   查看详情：https://artificialanalysis.ai
```

## 未来优化方向

### 短期（1-2 周）
1. **Playwright 集成**：使用真实浏览器渲染 OpenRouter 和 AA 页面，获取完整数据
2. **数据可视化**：在 HTML 中添加图表展示趋势
3. **LLM 分析增强**：使用 LLM 分析提取的数据，生成洞察摘要

### 中期（1 个月）
1. **历史趋势分析**：对比多天的数据，生成趋势报告
2. **交叉验证**：自动匹配新闻报道和实际数据的一致性
3. **异常检测**：识别数据中的显著变化并高亮

### 长期（3 个月+）
1. **API 集成**：如果 OpenRouter/AA 提供 API，直接对接
2. **更多数据源**：集成 GitHub Trending、Hugging Face 等
3. **智能推荐**：基于数据趋势提供投资或关注建议

## 测试覆盖

✅ 新闻数据提取（ARR、用户数、价格）
✅ OpenRouter 爬虫（基础文本提取）
✅ Artificial Analysis 爬虫（基础文本提取）
✅ 数据整合与格式化
✅ 市场数据板块生成
✅ 集成到 AI 日报主流程
✅ 降级策略（爬虫失败不影响原功能）
✅ 缓存机制
✅ HTML 输出验证

## 已知限制

1. **OpenRouter 数据不完整**：由于页面使用 JS 动态加载，当前只能提取页面描述和部分信息
2. **AA 数据准确度有限**：同样受 JS 渲染限制
3. **需要安装依赖**：`beautifulsoup4`（已在项目中使用，无需额外安装）
4. **Playwright 未集成**：完整数据提取需要后续添加 Playwright 支持

## 贡献者

- 初版实现：2026-08-30
- 测试验证：通过

## 许可证

与 AI 日报主项目保持一致

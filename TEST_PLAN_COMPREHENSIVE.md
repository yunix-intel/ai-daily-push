# 100% 功能覆盖测试计划

## 测试范围

### A. 核心推送流程
1. **AI 日报推送** (`ai_daily_push.py`)
   - [ ] 数据抓取（AI HOT）
   - [ ] 内容去重
   - [ ] 封面图生成
   - [ ] HTML 生成
   - [ ] 企业微信推送
   - [ ] 飞书推送
   - [ ] 微信公众号发布

2. **财经日报推送** (`finance_daily_push.py`)
   - [ ] 6 源抓取（3 中文 + 3 英文）
   - [ ] RSShub 镜像故障转移
   - [ ] 行情数据获取（5 指数）
   - [ ] 北向资金数据
   - [ ] LLM 批量翻译
   - [ ] LLM 市场分析
   - [ ] LLM 策略建议
   - [ ] 博主观点追踪（新功能）
   - [ ] HTML 生成
   - [ ] 推送

### B. 辅助模块
3. **翻译服务** (`article_translator.py`, `translation_service.py`)
   - [ ] DeepSeek 批量翻译
   - [ ] 标题翻译
   - [ ] 摘要翻译
   - [ ] 全文翻译

4. **内容提取与分类** 
   - [ ] 文章正文提取 (`article_extractor.py`)
   - [ ] 新闻分类 (`news_classifier.py`)
   - [ ] 指标提取 (`news_metrics_extractor.py`)
   - [ ] 事件影响分析 (`event_impact_analyzer.py`)

5. **数据抓取器**
   - [ ] 新浪博客抓取 (`scrapers/blogger_scraper.py`)
   - [ ] 资金流向抓取 (`scrapers/money_flow_scraper.py`)
   - [ ] Artificial Analysis 抓取 (`scrapers/artificial_analysis_scraper.py`)
   - [ ] OpenRouter 抓取 (`scrapers/openrouter_scraper.py`)

6. **配置与工具**
   - [ ] 配置管理 (`config_manager.py`)
   - [ ] 配置验证 (`config_validator.py`)
   - [ ] 交易日历 (`trading_calendar.py`)
   - [ ] 节假日更新 (`fetch_official_holidays.py`)

7. **监控告警**
   - [ ] GitHub Actions 监控 (`github_monitor.py`)
   - [ ] 本地监控 (`local_monitor.py`)
   - [ ] 云函数处理器 (`cloudfunction_handler.py`)
   - [ ] 告警发送 (`alerting.py`)

8. **微信生态**
   - [ ] 企业微信推送 (`wechat_content_builder.py`)
   - [ ] 微信公众号发布 (`wechat_official_publisher.py`)
   - [ ] 内容格式化 (`wechat_content_formatter.py`)

9. **性能与并发**
   - [ ] 并发抓取 (`concurrent_fetcher.py`)
   - [ ] 性能监控 (`monitoring.py`)

### C. 边界场景
10. **异常处理**
    - [ ] 网络超时
    - [ ] API 限流
    - [ ] LLM 调用失败
    - [ ] 空数据处理
    - [ ] 无效配置

11. **数据质量**
    - [ ] 重复内容去重
    - [ ] 脏数据清洗
    - [ ] 时区转换正确性
    - [ ] 编码问题（U+FFFD）

## 测试执行策略

### Phase 1: 单元测试（模块级）
每个模块独立测试，mock 外部依赖

### Phase 2: 集成测试（流程级）
端到端测试完整推送流程

### Phase 3: 边界测试（异常场景）
模拟各种失败情况

### Phase 4: 回归测试
验证新功能（博主追踪）不影响现有功能

## 预计耗时
- Phase 1: 2-3 小时
- Phase 2: 1-2 小时  
- Phase 3: 1 小时
- Phase 4: 30 分钟

总计: 4.5-6.5 小时

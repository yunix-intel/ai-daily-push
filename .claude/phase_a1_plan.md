# Phase A1: 爬虫基础设施 - 实施计划

## 📊 当前状态分析

### 已完成（从之前的会话）
✅ 目录结构已创建：
```
ai-daily-push/
├── scrapers/
│   ├── __init__.py                    ✅ 存在
│   ├── base_scraper.py                ✅ 存在（64行）
│   ├── openrouter_scraper.py          ✅ 存在（174行）
│   └── artificial_analysis_scraper.py ✅ 存在（172行）
└── data/
    └── market_data/                   ✅ 存在
        ├── openrouter_2026-08-30.json
        └── artificial_analysis_2026-08-30.json
```

### 已有功能
1. **BaseScraper** - 通用爬虫基类
   - 缓存管理（按日期）
   - 重试机制
   - 超时控制

2. **OpenRouterScraper** - OpenRouter 数据爬虫
   - 抓取 rankings 页面
   - 提取 top 模型数据
   - 解析 JavaScript 嵌入的 JSON

3. **ArtificialAnalysisScraper** - Artificial Analysis 数据爬虫
   - 抓取性能基准数据
   - Intelligence/Speed/Cost 三个维度
   - 表格数据解析

### 缺失部分
❌ **Playwright 依赖未安装** - 当前爬虫使用 urllib + BeautifulSoup
❌ **测试文件** - 无 tests/ 目录和单元测试
❌ **集成到主流程** - 未集成到 AI 日报生成流程

---

## 🎯 Phase A1 目标

### 原计划任务
- [x] 安装依赖（playwright, beautifulsoup4）
- [x] 创建项目结构（scrapers/, data/market_data/, tests/）
- [x] 开发 base_scraper.py（通用爬虫基类）
- [ ] 配置 Playwright（chromium）
- [ ] 创建测试文件

### 实际需求
由于爬虫已经实现并且**不使用 Playwright**（使用 urllib + BeautifulSoup），Phase A1 的重点调整为：

1. **验证现有爬虫功能** - 测试 OpenRouter 和 Artificial Analysis 爬虫
2. **创建测试套件** - 单元测试和集成测试
3. **依赖管理** - 更新 requirements.txt
4. **文档完善** - 添加使用说明

---

## 🔧 实施方案

### 方案 A: 保持现有实现（推荐）
**优势**：
- ✅ 现有爬虫已实现且可用
- ✅ 无需安装 Playwright（轻量级）
- ✅ urllib + BeautifulSoup 足够应对静态页面
- ✅ 有缓存和降级机制

**劣势**：
- ⚠️ 无法处理动态渲染（JS）页面
- ⚠️ 如果目标网站改为 SPA，需重写

**适用场景**：OpenRouter 和 Artificial Analysis 当前是服务端渲染

### 方案 B: 添加 Playwright 支持
**优势**：
- ✅ 支持动态页面
- ✅ 更健壮（模拟真实浏览器）

**劣势**：
- ❌ 需安装 Chromium（~300MB）
- ❌ 增加 GitHub Actions 执行时间
- ❌ 增加复杂度

---

## 📋 实施步骤（方案 A）

### 步骤 1: 验证现有爬虫（15分钟）
```bash
# 测试 OpenRouter 爬虫
cd D:/c/ai-daily-push
python -m scrapers.openrouter_scraper

# 测试 Artificial Analysis 爬虫
python -m scrapers.artificial_analysis_scraper

# 检查生成的缓存文件
ls -lh data/market_data/
```

### 步骤 2: 创建测试套件（30分钟）
创建 `tests/test_scrapers.py`：
```python
import unittest
from scrapers.openrouter_scraper import fetch_openrouter_data
from scrapers.artificial_analysis_scraper import fetch_aa_data

class TestScrapers(unittest.TestCase):
    def test_openrouter_fetch(self):
        """测试 OpenRouter 数据抓取"""
        data = fetch_openrouter_data()
        self.assertIn('source', data)
        self.assertEqual(data['source'], 'openrouter')
        self.assertIn('top_models', data)
        
    def test_aa_fetch(self):
        """测试 Artificial Analysis 数据抓取"""
        data = fetch_aa_data()
        self.assertIn('source', data)
        self.assertEqual(data['source'], 'artificial_analysis')
        self.assertIn('intelligence', data)
```

### 步骤 3: 更新依赖（10分钟）
检查并更新 `requirements.txt`：
```txt
beautifulsoup4>=4.12.0
# playwright 可选（如需动态页面支持）
```

### 步骤 4: 集成到主流程（45分钟）
创建 `ai_market_analysis.py`：
```python
def generate_market_report():
    """生成 AI 市场数据分析报告"""
    # 1. 抓取数据
    openrouter_data = fetch_openrouter_data()
    aa_data = fetch_aa_data()
    
    # 2. LLM 分析
    analysis = analyze_with_llm(openrouter_data, aa_data)
    
    # 3. 生成 HTML
    html = generate_html(openrouter_data, aa_data, analysis)
    
    # 4. 保存
    save_report(html)
```

### 步骤 5: GitHub Actions 集成（20分钟）
更新 `.github/workflows/daily-push.yml`：
```yaml
- name: Generate AI Market Report
  run: python ai_market_analysis.py
```

---

## 🧪 测试计划

### 测试场景
1. **正常流程** - 数据抓取成功
2. **缓存命中** - 当日已抓取，直接读缓存
3. **网络失败** - 使用历史缓存降级
4. **数据解析失败** - 返回错误标记

### 验收标准
- [x] OpenRouter 爬虫返回 top_models
- [x] Artificial Analysis 爬虫返回 intelligence/speed/cost
- [ ] 缓存机制生效
- [ ] 降级机制生效
- [ ] 单元测试通过

---

## ⚠️ 风险与缓解

### 风险 1: 网站结构变化
- **风险**: OpenRouter/AA 改版导致爬虫失效
- **缓解**: 
  - 使用历史缓存降级
  - 添加结构变化检测（字段缺失）
  - 定期人工验证

### 风险 2: 反爬虫机制
- **风险**: IP 被封或需要验证码
- **缓解**:
  - 添加 User-Agent
  - 增加请求间隔
  - 使用缓存减少请求频率

### 风险 3: 数据格式不一致
- **风险**: 不同日期数据格式不同
- **缓解**:
  - 容错解析（try-except）
  - 返回标准化数据结构
  - 记录解析失败日志

---

## 🎯 下一步（Phase A2-A6）

完成 Phase A1 后：
- **Phase A2**: OpenRouter 爬虫增强（已完成 80%）
- **Phase A3**: Artificial Analysis 爬虫增强（已完成 80%）
- **Phase A4**: LLM 数据分析（待开发）
- **Phase A5**: HTML 报告生成（待开发）
- **Phase A6**: GitHub Actions 集成（待开发）

---

## 📝 待办清单

- [ ] 1. 验证 OpenRouter 爬虫
- [ ] 2. 验证 Artificial Analysis 爬虫
- [ ] 3. 创建测试文件
- [ ] 4. 运行单元测试
- [ ] 5. 更新 requirements.txt
- [ ] 6. 提交代码
- [ ] 7. 更新完整计划文档

---

## 🚀 准备退出计划模式

等待用户批准后开始实施。

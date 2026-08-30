# Phase A2: OpenRouter 爬虫增强 - 实施计划

## 📊 当前状态分析

### 已有实现（173行）
✅ **OpenRouterScraper 类**
- 基础 URL：https://openrouter.ai
- 主方法：`fetch_rankings()`
- 数据解析：`_parse_next_data()` + `_parse_html_fallback()`
- 缓存机制：日期缓存 + 历史降级

### 当前数据结构（实际输出）
```json
{
  "source": "openrouter",
  "date": null,
  "top_models": [],
  "description": "Live LLM rankings...",
  "detected_models": ["Gemini", "Flash", "Pro"]
}
```

### 目标数据结构（完整计划要求）
```json
{
  "date": "2026-08-30",
  "rankings": [
    {
      "model": "Claude Sonnet 3.5",
      "tokens_weekly": "15.2T",
      "market_share": 0.28,
      "trend": "+12%"
    }
  ],
  "pricing": [
    {
      "model": "GPT-4o",
      "price_per_1m_tokens": 0.015,
      "change": "-50%"
    }
  ]
}
```

---

## 🎯 Phase A2 目标

### 任务清单
- [x] 开发 openrouter_scraper.py（已存在，需增强）
- [ ] 增强 /rankings 页面抓取（提取完整排行榜数据）
- [ ] 抓取 /rankings?tab=leaderboard（如果与主页不同）
- [ ] 抓取 /models（价格数据）
- [ ] 数据解析增强（从图表中提取 JSON）
- [ ] 单元测试更新

---

## 🔍 问题分析

### 问题 1: 当前爬虫数据不完整
**现象**：
- `top_models` 为空数组
- 只有 `detected_models`（3个模型名片段）
- 缺少 tokens_weekly、market_share、trend

**原因**：
- OpenRouter 使用 Next.js 动态渲染
- 数据在客户端 JavaScript 中加载
- `_parse_next_data()` 未找到正确的数据路径
- `_parse_html_fallback()` 只提取了文本片段

### 问题 2: 缺少价格数据
**现象**：无 pricing 字段

**原因**：未实现 /models 页面抓取

### 问题 3: 缺少趋势数据
**现象**：无 trend 字段

**原因**：趋势图数据可能在 JavaScript 变量中

---

## 🔧 实施方案

### 方案 A: 增强当前爬虫（推荐）
**策略**：
1. 手动访问 https://openrouter.ai/rankings
2. 检查页面源码，找到嵌入的 JSON 数据
3. 定位 Next.js 数据结构（`__NEXT_DATA__` script）
4. 更新 `_parse_next_data()` 解析逻辑
5. 添加 `fetch_pricing()` 方法抓取 /models

**优势**：
- ✅ 保持轻量级（无需 Playwright）
- ✅ 快速执行
- ✅ 符合现有架构

**劣势**：
- ⚠️ 依赖页面结构稳定性
- ⚠️ 如果数据完全客户端渲染，无法获取

### 方案 B: 使用 Playwright（备选）
**策略**：
1. 安装 Playwright + chromium
2. 启动无头浏览器
3. 等待 JavaScript 渲染完成
4. 提取 DOM 数据

**优势**：
- ✅ 支持完全动态页面
- ✅ 更健壮

**劣势**：
- ❌ 需安装 ~300MB chromium
- ❌ 增加 GitHub Actions 执行时间（+30s）
- ❌ 增加复杂度

---

## 📋 实施步骤（方案 A）

### 步骤 1: 手动检查 OpenRouter 页面（30分钟）
```bash
# 下载页面源码
curl -A "Mozilla/5.0" https://openrouter.ai/rankings > openrouter_rankings.html

# 查找 Next.js 数据
grep -o "__NEXT_DATA__.*" openrouter_rankings.html | head -1

# 查找其他 JSON 数据
grep -o "window\.__.*" openrouter_rankings.html
```

**目标**：
- 找到嵌入的 JSON 数据
- 确认数据结构路径
- 提取示例数据

### 步骤 2: 增强 _parse_next_data() 方法（60分钟）
根据步骤 1 的发现，更新解析逻辑：

```python
def _parse_next_data(self, data):
    """解析 Next.js 页面数据（增强版）"""
    result = {
        "source": "openrouter",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "rankings": [],
        "top_models": []  # 保持兼容性
    }
    
    try:
        # 尝试多个可能的数据路径
        paths = [
            ["props", "pageProps", "rankings"],
            ["props", "pageProps", "data", "models"],
            ["props", "pageProps", "models"]
        ]
        
        for path in paths:
            models = data
            for key in path:
                models = models.get(key, {})
            
            if models and isinstance(models, list):
                # 解析模型数据
                for model in models[:10]:  # Top 10
                    result["rankings"].append({
                        "model": model.get("name", "Unknown"),
                        "tokens_weekly": model.get("tokens", "N/A"),
                        "market_share": model.get("share", 0),
                        "trend": model.get("trend", "0%")
                    })
                break
        
        # 兼容旧字段
        result["top_models"] = [r["model"] for r in result["rankings"]]
        
    except Exception as e:
        print(f"     [WARN] 解析 Next.js 数据失败：{e}")
    
    return result
```

### 步骤 3: 添加价格数据抓取（60分钟）
新增 `fetch_pricing()` 方法：

```python
def fetch_pricing(self):
    """抓取模型价格数据"""
    print("  抓取 OpenRouter 价格数据...")
    
    try:
        url = f"{self.base_url}/models"
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        
        with urllib.request.urlopen(req, timeout=self.timeout) as response:
            html = response.read().decode('utf-8')
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # 查找 __NEXT_DATA__
        script = soup.find('script', id='__NEXT_DATA__')
        if script:
            data = json.loads(script.string)
            return self._parse_pricing_data(data)
        
        return []
    
    except Exception as e:
        print(f"     [WARN] 价格数据抓取失败：{e}")
        return []

def _parse_pricing_data(self, data):
    """解析价格数据"""
    pricing = []
    
    try:
        # 遍历可能的数据路径
        models = data.get("props", {}).get("pageProps", {}).get("models", [])
        
        for model in models:
            pricing.append({
                "model": model.get("name", "Unknown"),
                "price_per_1m_tokens": model.get("pricing", {}).get("prompt", 0),
                "change": model.get("priceChange", "N/A")
            })
    
    except Exception as e:
        print(f"     [WARN] 价格数据解析失败：{e}")
    
    return pricing
```

### 步骤 4: 整合数据（30分钟）
修改 `fetch_rankings()` 整合价格数据：

```python
def fetch_rankings(self):
    """抓取完整的 OpenRouter 数据"""
    print("  抓取 OpenRouter 数据...")
    
    cached = self.load_cache("openrouter")
    if cached:
        return cached
    
    try:
        # 1. 抓取排行榜
        rankings_data = self._fetch_rankings_page()
        
        # 2. 抓取价格（可选，如果失败不影响主数据）
        try:
            pricing_data = self.fetch_pricing()
            rankings_data["pricing"] = pricing_data
        except:
            rankings_data["pricing"] = []
        
        # 保存缓存
        self.save_cache("openrouter", rankings_data)
        return rankings_data
    
    except Exception as e:
        print(f"     [WARN] OpenRouter 抓取失败：{e}")
        return self._load_fallback_cache()
```

### 步骤 5: 更新单元测试（20分钟）
更新 `tests/test_scrapers.py`：

```python
def test_openrouter_enhanced(self):
    """测试增强后的 OpenRouter 数据"""
    data = fetch_openrouter_data()
    
    # 验证新字段
    self.assertIn('rankings', data)
    self.assertIsInstance(data['rankings'], list)
    
    if len(data['rankings']) > 0:
        ranking = data['rankings'][0]
        self.assertIn('model', ranking)
        self.assertIn('tokens_weekly', ranking)
        # market_share 和 trend 可选
    
    # 验证价格数据（可选）
    if 'pricing' in data:
        self.assertIsInstance(data['pricing'], list)
```

### 步骤 6: 本地测试（20分钟）
```bash
# 清除旧缓存
rm data/market_data/openrouter_*.json

# 测试爬虫
python -m scrapers.openrouter_scraper

# 检查输出
cat data/market_data/openrouter_2026-08-30.json | python -m json.tool

# 运行单元测试
python -m unittest tests.test_scrapers.TestScrapers.test_openrouter_enhanced
```

---

## 🧪 测试计划

### 测试场景
1. **完整数据** - rankings + pricing 都成功
2. **部分数据** - rankings 成功，pricing 失败
3. **缓存命中** - 第二次调用读缓存
4. **降级机制** - 网络失败，使用历史缓存

### 验收标准
- [ ] rankings 字段非空（至少 5 个模型）
- [ ] 每个 ranking 包含 model 和 tokens_weekly
- [ ] pricing 字段存在（可以为空）
- [ ] date 字段正确（当前日期）
- [ ] 单元测试通过
- [ ] 缓存机制生效

---

## ⚠️ 风险与缓解

### 风险 1: OpenRouter 数据完全客户端渲染
- **可能性**: 中
- **影响**: 无法获取数据
- **缓解**: 
  - 先手动检查页面源码
  - 如果确认无服务端数据，升级到方案 B（Playwright）
  - 或者使用 API（如果有公开 API）

### 风险 2: 页面结构频繁变化
- **可能性**: 低-中
- **影响**: 解析失败
- **缓解**:
  - 多路径尝试（paths 列表）
  - 降级到历史缓存
  - 记录详细错误日志

### 风险 3: 反爬虫限制
- **可能性**: 低
- **影响**: IP 被封
- **缓解**:
  - 使用缓存减少请求
  - 添加 User-Agent
  - 请求间隔控制

---

## 📝 待办清单

- [ ] 1. 手动检查 OpenRouter 页面源码
- [ ] 2. 定位 JSON 数据路径
- [ ] 3. 增强 _parse_next_data() 方法
- [ ] 4. 添加 fetch_pricing() 方法
- [ ] 5. 整合数据流程
- [ ] 6. 更新单元测试
- [ ] 7. 本地测试验证
- [ ] 8. 提交代码
- [ ] 9. 更新完整计划文档

---

## 🚀 准备退出计划模式

等待用户批准后开始实施。

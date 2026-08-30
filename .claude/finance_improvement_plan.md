# 财经日报改进详细计划

## 问题清单与解决方案

### 问题 1：非交易日的策略建议处理
**现状**：非交易日没有"今日策略建议"
**解决方案**：
- 增加交易日历判断（A股、港股）
- 非交易日显示"休市提示"替代策略建议
- 提供"下一交易日展望"

**技术实现**：
```python
def is_trading_day(date, market='A'):
    """判断是否为交易日
    market: 'A' (A股), 'HK' (港股)
    """
    # 使用 exchange_calendars 或自建节假日数据
    # 返回 True/False
```

---

### 问题 2：前一日非交易日的数据有效性
**现状**：前一日非交易日，当日指数和策略无意义
**解决方案**：
- 指数数据标注"截至上一交易日 YYYY-MM-DD"
- 策略建议基于最新交易日数据
- 明确说明"等待开盘"

**展示示例**：
```
📊 市场行情（截至上一交易日 2026-08-27）
沪深300: 3850.25 ↗ +0.85%
```

---

### 问题 3：节后首个交易日的特殊处理
**现状**：节后首日仍按常规格式
**解决方案**：

#### 3.1 全文描述调整
- 将"今日"改为"上一交易日（X月X日）"
- 指数备注"截至上一交易日收盘"

#### 3.2 新增"假期要闻综述"
替代常规"今日策略建议"的内容（名称保持不变）：

**新内容结构**：
```
## 📈 今日策略建议

### 假期期间要闻回顾（8月24日-8月27日）
【重要事件】
• 美联储主席鹰派讲话，美股大跌
• 中东局势升级，原油价格飙升
• ...

### 假期影响分析与策略
【市场预判】
• 外围市场大幅波动，A股今日开盘料承压
• 关注方向：...
• 风险提示：...

【操作建议】
• 谨慎观望，等待市场企稳
• 重点关注：...
```

#### 3.3 技术实现
```python
def get_last_trading_day(date, market='A'):
    """获取上一交易日"""
    
def count_non_trading_days(start_date, end_date, market='A'):
    """计算连续休市天数"""
    
def is_post_holiday_first_day(date, market='A'):
    """判断是否为节后首个交易日（连续休市≥3天）"""
    if count_non_trading_days(...) >= 3:
        return True
```

---

### 问题 4：国内/国际要闻分类错误
**现状**：按新闻来源分类，导致格隆汇的国外新闻被归为国内
**解决方案**：

#### 4.1 使用 LLM 智能分类
```python
def classify_news_region(title, summary):
    """使用 LLM 判断新闻涉及的地区
    返回: 'domestic' 或 'international'
    """
    prompt = f"""
    判断以下财经新闻主要涉及的市场区域：
    - domestic: 中国大陆、A股、港股相关
    - international: 美股、欧洲、其他海外市场
    
    标题：{title}
    摘要：{summary}
    
    只返回 domestic 或 international
    """
    # 调用 deepseek-v4-flash
```

#### 4.2 关键词辅助判断
作为 LLM 的备选方案：
```python
DOMESTIC_KEYWORDS = ['A股', '沪深', '上证', '深证', '港股', '恒生', '人民币', '央行', '中国', ...]
INTERNATIONAL_KEYWORDS = ['美股', '纳指', '标普', '道琼斯', '美联储', '欧洲', '日本', ...]
```

---

### 问题 5：突发事件分类错误且缺乏判断
**现状**：大量事件分类错误，无影响分析
**解决方案**：

#### 5.1 强化突发事件识别
```python
def is_breaking_news(item, publish_time):
    """判断是否为突发事件
    标准：
    1. 发布时间在过去24小时内
    2. 标题包含突发性关键词
    3. 内容具有重大影响
    """
    # 时间判断
    if not within_24_hours(publish_time):
        return False
    
    # 关键词判断
    urgent_keywords = [
        '突发', '紧急', '重磅', '爆发', '暴跌', '暴涨',
        '停牌', '调查', '事故', '危机', '崩盘'
    ]
    
    # LLM 判断重要性（1-10分）
    importance = llm_judge_importance(item)
    return importance >= 7
```

#### 5.2 增加影响分析
```python
def analyze_breaking_event(event):
    """LLM 分析突发事件的市场影响
    返回：
    - 影响方向：利好/利空/中性
    - 影响板块：[...]
    - 影响程度：重大/一般/轻微
    - 简要分析：100字以内
    """
```

**展示格式**：
```
🔥 突发事件

1. 【利空 | 重大】美联储意外加息50BP
   影响板块：全市场、科技股
   简析：超预期紧缩，短期承压明显，关注企稳信号

2. 【利好 | 一般】某龙头公司获重大订单
   影响板块：新能源汽车
   简析：业绩确定性增强，关注产业链机会
```

---

### 问题 6：要闻筛选优化
**现状**：国内/国际要闻数量过多，未分优先级
**解决方案**：

#### 6.1 三级分类
1. **📌 核心必读**（5-10条）：最重要的要闻
2. **📰 重要要闻**（其余）：次要但值得关注的新闻
3. **隐藏/折叠**：可选的补充信息

#### 6.2 LLM 重要性评分
```python
def score_news_importance(item, market_context):
    """
    评分标准（0-10分）：
    - 对市场影响程度
    - 信息时效性
    - 与当前热点相关度
    - 数据权威性
    """
    prompt = f"""
    评估以下财经新闻的重要性（0-10分）：
    
    标题：{item['title']}
    摘要：{item['summary']}
    来源：{item['source']}
    
    当前市场背景：{market_context}
    
    评分标准：
    - 10分：重大政策、重要数据、市场剧烈波动
    - 7-9分：行业重要动态、龙头公司重大事件
    - 4-6分：一般性新闻、常规数据发布
    - 0-3分：次要信息、重复报道
    
    只返回数字分数。
    """
    return llm_call(prompt)
```

#### 6.3 展示结构
```html
<section class="news-domestic">
  <h2>🇨🇳 国内要闻</h2>
  
  <div class="must-read">
    <h3>📌 核心必读 <span>(5条)</span></h3>
    <div class="grid">
      <!-- 8-10分的要闻 -->
    </div>
  </div>
  
  <div class="important-news collapsible">
    <h3>📰 重要要闻 <span>(15条)</span> 
      <button class="toggle">展开 ▼</button>
    </h3>
    <div class="grid" style="display:none">
      <!-- 5-7分的要闻 -->
    </div>
  </div>
</section>
```

---

### 问题 7：缺少快速跳转导航
**现状**：必须逐个浏览分类和要闻，效率低
**解决方案**：

#### 7.1 顶部浮动导航栏
```html
<nav class="quick-nav sticky">
  <div class="nav-section">
    <span class="nav-title">快速跳转</span>
    <a href="#market-overview">📊 行情</a>
    <a href="#breaking">🔥 突发</a>
    <a href="#domestic">🇨🇳 国内</a>
    <a href="#international">🌏 国际</a>
    <a href="#strategy">📈 策略</a>
  </div>
  
  <div class="nav-section domestic-nav">
    <span class="nav-title">国内分类</span>
    <a href="#domestic-macro">宏观政策</a>
    <a href="#domestic-market">市场动态</a>
    <a href="#domestic-company">公司新闻</a>
  </div>
  
  <div class="nav-section intl-nav">
    <span class="nav-title">国际分类</span>
    <a href="#intl-macro">宏观政策</a>
    <a href="#intl-market">市场动态</a>
  </div>
</nav>
```

#### 7.2 锚点定位 + 平滑滚动
```css
html {
  scroll-behavior: smooth;
  scroll-padding-top: 80px; /* 避免被导航栏遮挡 */
}

.quick-nav {
  position: sticky;
  top: 0;
  z-index: 1000;
  background: var(--bg);
  border-bottom: 1px solid var(--border);
  padding: 12px 20px;
  display: flex;
  gap: 30px;
  overflow-x: auto;
}

.quick-nav a {
  padding: 6px 12px;
  border-radius: 6px;
  transition: 0.2s;
}

.quick-nav a:hover {
  background: var(--accent);
  color: white;
}
```

#### 7.3 "返回顶部"按钮
```html
<button class="back-to-top" onclick="window.scrollTo({top:0})">
  ↑ 顶部
</button>
```

---

### 问题 8：国际要闻未翻译
**现状**：国际要闻全部是英文标题和摘要
**解决方案**：

#### 8.1 统一翻译流程
```python
def process_international_news(items):
    """处理国际要闻：翻译 + 保留原文"""
    for item in items:
        if is_english(item['title']):
            item['originalTitle'] = item['title']
            item['originalSummary'] = item['summary']
            
            # 翻译
            item['title'] = translate_text(item['title'])
            item['summary'] = translate_text(item['summary'])
            
            # 生成 Google 翻译全文链接
            item['translatedPage'] = translate_page_url(item['link'])
```

#### 8.2 展示格式（与 AI 日报一致）
```html
<article class="card">
  <h3>美联储宣布加息50BP</h3>
  <p class="summary">美联储在本次会议上意外宣布加息50个基点...</p>
  
  <!-- 原文区块 -->
  <div class="original-text">
    <b>原文</b><br>
    Fed Announces 50BP Rate Hike<br>
    The Federal Reserve unexpectedly announced...
  </div>
  
  <div class="foot">
    <span class="src">Bloomberg</span>
    <span class="linkgroup">
      <a href="..." target="_blank">翻译全文 ↗</a>
      <a href="..." target="_blank">阅读原文 ↗</a>
    </span>
  </div>
</article>
```

---

### 问题 9：全文翻译机制优化
**现状**：Google 翻译链接经常打不开
**解决方案**：

#### 9.1 改用 LLM 预翻译（推荐方案）
```python
def pre_translate_full_article(url, use_cache=True):
    """
    在推送前使用 deepseek-v4-flash 翻译完整文章
    
    流程：
    1. 爬取原文HTML
    2. 提取正文内容
    3. LLM 翻译（保留格式）
    4. 生成静态 HTML 页面
    5. 存储到 GitHub Pages
    
    优势：
    - 不依赖 Google 翻译（国内可访问）
    - 翻译质量更高
    - 可离线阅读
    """
    # 缓存机制
    cache_key = hashlib.md5(url.encode()).hexdigest()
    cache_file = f"translations/{cache_key}.html"
    
    if use_cache and os.path.exists(cache_file):
        return f"https://your-github-pages.io/{cache_file}"
    
    # 1. 爬取原文
    article_html = fetch_article(url)
    article_text = extract_main_content(article_html)
    
    # 2. LLM 翻译（分段处理，避免超长）
    translated_text = translate_with_llm(article_text, model='deepseek-v4-flash')
    
    # 3. 生成HTML
    translated_html = generate_article_html(
        title=translated_title,
        content=translated_text,
        original_url=url
    )
    
    # 4. 保存到 translations/
    save_file(cache_file, translated_html)
    
    return f"https://your-github-pages.io/{cache_file}"
```

#### 9.2 降级方案：多翻译源
```python
TRANSLATION_SOURCES = [
    ('DeepSeek LLM', pre_translate_full_article),
    ('Google Translate', lambda url: f'https://translate.google.com/...'),
    ('Bing Translator', lambda url: f'https://www.bing.com/translator?...'),
]

def get_translation_links(url):
    """生成多个翻译源链接"""
    links = []
    for name, func in TRANSLATION_SOURCES:
        try:
            link = func(url)
            links.append({'name': name, 'url': link})
        except:
            continue
    return links
```

**展示效果**：
```html
<span class="linkgroup">
  <a href="..." target="_blank">翻译全文(LLM) ↗</a>
  <a href="..." target="_blank">阅读原文 ↗</a>
</span>
```

#### 9.3 实施建议
- **第一阶段**：只翻译"核心必读"的 5-10 条（控制成本）
- **第二阶段**：全部要闻翻译（按需扩展）
- **成本控制**：deepseek-v4-flash 很便宜，每篇文章约 $0.001

---

### 问题 10：资金流向数据
**现状**：缺少资金流向、板块热点等数据
**解决方案**：

#### 10.1 数据源选择
**免费公开数据源**：
- 东方财富网资金流向：http://data.eastmoney.com/zjlx/
- 同花顺资金流向：http://data.10jqka.com.cn/funds/
- 新浪财经板块资金：http://finance.sina.com.cn/stock/marketresearch/

**API 数据源**（可能需要注册）：
- Tushare：https://tushare.pro/（免费额度）
- AKShare：https://akshare.akfamily.xyz/（开源）

#### 10.2 数据内容
```python
def fetch_capital_flow_data():
    """
    抓取资金流向数据
    
    返回结构：
    {
      'market_overview': {
        'north_bound': {  # 北向资金（港股通）
          'net_inflow': 52.3,  # 亿元
          'trend': 'inflow',    # inflow/outflow
          'change': '+15.2%'
        },
        'main_force': {  # 主力资金
          'net_inflow': -23.5,
          'trend': 'outflow'
        }
      },
      'sector_ranking': [  # 板块资金流向排名
        {
          'name': '人工智能',
          'net_inflow': 125.6,
          'change_pct': '+3.2%',
          'top_stocks': ['科大讯飞', '海康威视']
        },
        ...
      ],
      'hot_stocks': [  # 个股资金流向Top10
        {
          'code': '600519',
          'name': '贵州茅台',
          'net_inflow': 8.5,
          'change_pct': '+1.2%'
        },
        ...
      ]
    }
    """
```

#### 10.3 展示板块
```html
<section class="capital-flow">
  <h2>💰 资金流向</h2>
  
  <div class="market-funds">
    <h3>市场资金概览</h3>
    <div class="fund-cards">
      <div class="fund-card inflow">
        <div class="fund-label">北向资金</div>
        <div class="fund-value">+52.3亿</div>
        <div class="fund-change">↗ +15.2%</div>
      </div>
      
      <div class="fund-card outflow">
        <div class="fund-label">主力资金</div>
        <div class="fund-value">-23.5亿</div>
        <div class="fund-change">↘ -8.3%</div>
      </div>
    </div>
  </div>
  
  <div class="sector-funds">
    <h3>板块资金流向 Top 10</h3>
    <table class="fund-table">
      <thead>
        <tr>
          <th>板块</th>
          <th>净流入(亿)</th>
          <th>涨跌幅</th>
          <th>龙头股</th>
        </tr>
      </thead>
      <tbody>
        <tr class="inflow">
          <td>人工智能</td>
          <td class="positive">+125.6</td>
          <td class="positive">+3.2%</td>
          <td>科大讯飞、海康威视</td>
        </tr>
        ...
      </tbody>
    </table>
  </div>
  
  <div class="hot-stocks">
    <h3>个股资金流向 Top 10</h3>
    <div class="stock-grid">
      <!-- 类似要闻卡片的展示 -->
    </div>
  </div>
</section>
```

#### 10.4 LLM 分析
```python
def analyze_capital_flow(flow_data, market_data):
    """
    LLM 分析资金流向含义
    
    输出：
    - 市场情绪判断
    - 热点板块解读
    - 资金风向变化
    """
    prompt = f"""
    根据以下资金流向数据，分析当前市场资金动向：
    
    北向资金：{flow_data['north_bound']}
    主力资金：{flow_data['main_force']}
    热门板块：{flow_data['sector_ranking'][:5]}
    
    结合市场行情：
    {market_data}
    
    请分析：
    1. 市场情绪（积极/谨慎/恐慌）
    2. 资金流向特征（题材炒作/价值回归/防御布局）
    3. 重点关注板块及原因
    4. 风险提示
    
    简洁输出，每点50字以内。
    """
    return llm_call(prompt, model='deepseek-v4-flash')
```

---

## 总体实施计划

### Phase 1: 交易日历与节假日处理（核心功能）
**预计时间**：4-6 小时

#### 任务清单
1. ✅ 实现交易日历判断
   - A股交易日历（使用 `exchange_calendars` 或自建）
   - 港股交易日历
   - 缓存机制（避免重复计算）

2. ✅ 获取上一交易日
   - 向前查找最近交易日
   - 计算连续休市天数

3. ✅ 节后首日判断
   - 识别节后首个交易日（连续休市≥3天）
   - 生成"假期要闻综述"

4. ✅ 修改策略建议生成逻辑
   - 常规交易日：正常的"今日策略建议"
   - 非交易日：显示"休市提示"
   - 节后首日：替换为"假期影响分析与策略"

5. ✅ 时间标注优化
   - 所有指数标注"截至 YYYY-MM-DD"
   - 全文"今日"→"上一交易日"（节后首日）

**文件修改**：
- `finance_daily_push.py`
- 新增 `trading_calendar.py`

---

### Phase 2: 新闻分类优化（智能化）
**预计时间**：3-4 小时

#### 任务清单
1. ✅ LLM 区域分类
   - 实现 `classify_news_region()` 函数
   - 批量处理（一次请求多条）
   - 异常处理和降级

2. ✅ LLM 重要性评分
   - 实现 `score_news_importance()` 函数
   - 分数阈值设置（核心必读≥8分，重要要闻≥5分）

3. ✅ 突发事件识别增强
   - 时间判断（24小时内）
   - 关键词判断
   - LLM 重要性判断（≥7分）

4. ✅ 突发事件影响分析
   - 实现 `analyze_breaking_event()` 函数
   - 输出：影响方向、影响板块、简要分析

**文件修改**：
- `finance_daily_push.py`
- 可能新增 `news_classifier.py`

---

### Phase 3: 国际要闻翻译（与AI日报统一）
**预计时间**：2-3 小时

#### 任务清单
1. ✅ 统一翻译流程
   - 复用 AI 日报的翻译逻辑
   - 保留原文
   - 生成翻译链接

2. ✅ 展示格式统一
   - 标题、摘要、原文、链接
   - CSS 样式保持一致

**文件修改**：
- `finance_daily_push.py`（复用已有 `translate_items()` 函数）

---

### Phase 4: 全文翻译优化（LLM预翻译）
**预计时间**：4-5 小时

#### 任务清单
1. ✅ 文章爬取器
   - 通用 HTML 解析
   - 正文提取（去广告、导航等）
   - 支持常见财经网站

2. ✅ LLM 翻译服务
   - 长文本分段处理
   - 保留格式（段落、标题）
   - 错误处理

3. ✅ 静态页面生成
   - 翻译后生成 HTML
   - 存储到 `translations/` 目录
   - Git 提交到 GitHub Pages

4. ✅ 缓存机制
   - 已翻译文章不重复处理
   - 缓存有效期设置

5. ✅ 选择性翻译
   - 优先翻译"核心必读"
   - 成本控制

**文件修改**：
- `finance_daily_push.py`
- 新增 `article_translator.py`
- 新增 `translations/` 目录

---

### Phase 5: UI/UX 优化（快速导航）
**预计时间**：3-4 小时

#### 任务清单
1. ✅ 顶部浮动导航栏
   - 主导航：行情、突发、国内、国际、策略
   - 子导航：国内/国际分类
   - 响应式设计（移动端）

2. ✅ 锚点链接
   - 每个板块设置 ID
   - 平滑滚动
   - 滚动偏移（避免被导航栏遮挡）

3. ✅ 要闻折叠展开
   - "核心必读"默认展开
   - "重要要闻"可折叠
   - 展开/收起按钮

4. ✅ 返回顶部按钮
   - 滚动超过一屏后显示
   - 平滑动画

**文件修改**：
- `finance_daily_push.py`（HTML 模板）
- CSS 和 JavaScript 增强

---

### Phase 6: 资金流向数据（新功能）
**预计时间**：5-6 小时

#### 任务清单
1. ✅ 选择数据源
   - 调研：东方财富/同花顺/Tushare/AKShare
   - 测试可用性
   - 确定最终方案

2. ✅ 数据爬取器
   - 市场资金概览（北向资金、主力资金）
   - 板块资金流向排名
   - 个股资金流向 Top 10

3. ✅ LLM 资金流向分析
   - 市场情绪判断
   - 资金流向特征
   - 重点板块解读

4. ✅ UI 展示
   - 资金流向卡片
   - 板块排名表格
   - 个股网格展示

**文件修改**：
- `finance_daily_push.py`
- 新增 `capital_flow_scraper.py`

---

### Phase 7: 测试与优化
**预计时间**：3-4 小时

#### 任务清单
1. ✅ 单元测试
   - 交易日历判断
   - 新闻分类
   - 数据爬取

2. ✅ 集成测试
   - 常规交易日
   - 非交易日
   - 节后首日

3. ✅ 边界测试
   - LLM 调用失败
   - 数据源不可用
   - 网络超时

4. ✅ 性能优化
   - 并发爬取
   - 缓存策略
   - 超时控制

5. ✅ 文档更新
   - README
   - 配置说明
   - 部署指南

---

## 总时间估算

| Phase | 任务 | 预计时间 |
|-------|------|----------|
| 1 | 交易日历与节假日处理 | 4-6 小时 |
| 2 | 新闻分类优化 | 3-4 小时 |
| 3 | 国际要闻翻译 | 2-3 小时 |
| 4 | 全文翻译优化 | 4-5 小时 |
| 5 | UI/UX 优化 | 3-4 小时 |
| 6 | 资金流向数据 | 5-6 小时 |
| 7 | 测试与优化 | 3-4 小时 |
| **总计** | | **24-32 小时** |

---

## 实施优先级

### 🔴 高优先级（必须完成）
1. **Phase 1** - 交易日历（解决问题 1、2、3）
2. **Phase 2** - 新闻分类（解决问题 4、5、6）
3. **Phase 3** - 国际要闻翻译（解决问题 8）

### 🟡 中优先级（重要但可后续迭代）
4. **Phase 5** - UI/UX 优化（解决问题 7）
5. **Phase 4** - 全文翻译优化（解决问题 9）

### 🟢 低优先级（增值功能）
6. **Phase 6** - 资金流向数据（解决问题 10）

---

## 依赖管理

### 新增依赖
```txt
# requirements.txt
exchange-calendars==4.5.4  # 交易日历
pandas-market-calendars==4.3.3  # 备选交易日历
akshare==1.13.52  # 金融数据（如果使用）
beautifulsoup4==4.12.3  # HTML 解析
lxml==5.1.0  # XML 解析
```

### GitHub Actions 更新
```yaml
- name: 安装依赖
  run: |
    pip install exchange-calendars pandas-market-calendars akshare beautifulsoup4 lxml
```

---

## 风险与缓解

### 风险 1：LLM 调用成本
- **缓解**：使用 deepseek-v4-flash（最便宜）
- **控制**：批量处理、缓存结果、设置每日上限

### 风险 2：数据源不稳定
- **缓解**：多数据源备选、异常处理、降级策略

### 风险 3：开发时间超预期
- **缓解**：按优先级分阶段实施，高优先级先上线

### 风险 4：交易日历数据不准确
- **缓解**：使用成熟的 `exchange-calendars` 库，定期更新

---

## 成功标准

### Phase 1 成功标准
- ✅ 正确识别交易日/非交易日
- ✅ 节后首日生成"假期要闻综述"
- ✅ 时间标注准确

### Phase 2 成功标准
- ✅ 国内/国际分类准确率 > 90%
- ✅ 核心必读筛选合理（5-10条）
- ✅ 突发事件识别准确，包含影响分析

### Phase 3 成功标准
- ✅ 国际要闻全部翻译
- ✅ 展示格式与 AI 日报一致

### Phase 4 成功标准
- ✅ 核心必读的全文翻译成功率 > 90%
- ✅ 翻译质量可读
- ✅ 链接可访问

### Phase 5 成功标准
- ✅ 快速导航功能正常
- ✅ 移动端体验良好
- ✅ 折叠展开交互流畅

### Phase 6 成功标准
- ✅ 资金数据每日更新
- ✅ LLM 分析有价值
- ✅ UI 展示清晰

---

## 下一步行动

1. **用户确认优先级**
2. **开始 Phase 1 开发**（交易日历）
3. **逐个 Phase 完成并测试**
4. **最后整体测试和上线**

---

## 附录：代码结构预览

```
finance-daily-push/
├── finance_daily_push.py          # 主程序（修改）
├── trading_calendar.py            # 新增：交易日历
├── news_classifier.py             # 新增：新闻分类
├── article_translator.py          # 新增：文章翻译
├── capital_flow_scraper.py        # 新增：资金流向
├── translations/                  # 新增：翻译文章存储
│   └── {hash}.html
├── tests/
│   ├── test_trading_calendar.py
│   ├── test_news_classifier.py
│   └── test_capital_flow.py
└── requirements.txt               # 更新依赖
```

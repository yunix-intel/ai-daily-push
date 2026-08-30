# Phase F4: 全文翻译优化（LLM预翻译）实施计划

## 📋 问题分析

### 当前状态
- **问题**：Google 翻译链接经常打不开（国内网络限制）
- **现状**：`translate_page_url()` 函数已禁用，返回空字符串
- **影响**：国际要闻只有标题+摘要翻译，用户无法阅读完整译文

### 用户需求
1. **核心需求**：国际要闻全文翻译，国内可访问
2. **质量要求**：翻译准确，保留格式
3. **成本控制**：优先翻译核心必读（5-10条）
4. **访问方式**：静态页面，托管在 GitHub Pages

---

## 🎯 设计方案

### 方案概述：LLM 预翻译 + 静态页面生成

**核心流程**：
```
1. 抓取原文HTML → 提取正文 → LLM翻译 → 生成静态HTML → 部署到 GitHub Pages
```

**优势**：
- ✅ 不依赖外部翻译服务（国内可访问）
- ✅ 翻译质量高（LLM 理解上下文）
- ✅ 可离线阅读（静态页面）
- ✅ 缓存机制（避免重复翻译）

**成本控制**：
- 优先翻译"核心必读"（importance_score >= 8）
- 回退翻译"重要要闻"前 5 条
- 使用快速模型（gpt-4o-mini）

---

## 🔧 技术实现

### 1. 文章正文提取

#### 1.1 方案选择

**方案 A：newspaper3k**（推荐）
```python
from newspaper import Article

def extract_article_text(url):
    article = Article(url)
    article.download()
    article.parse()
    return {
        'title': article.title,
        'text': article.text,
        'authors': article.authors,
        'publish_date': article.publish_date
    }
```
- ✅ 轻量级，无需浏览器
- ✅ 支持多语言
- ✅ 自动提取正文
- ⚠️ 部分网站可能失败（反爬）

**方案 B：BeautifulSoup + readability-lxml**
```python
from readability import Document
import requests

def extract_article_text(url):
    response = requests.get(url, headers={'User-Agent': '...'})
    doc = Document(response.content)
    return {
        'title': doc.title(),
        'html': doc.summary(),  # 提取的正文HTML
    }
```
- ✅ 基于 Mozilla Readability 算法
- ✅ 提取准确度高
- ⚠️ 需要额外处理HTML

**推荐**：方案 A（newspaper3k），失败时回退到方案 B

#### 1.2 实现代码

```python
# article_extractor.py

import requests
from newspaper import Article
from readability import Document
import re

def extract_article(url, timeout=15):
    """
    提取文章正文
    
    Args:
        url: 文章URL
        timeout: 请求超时时间
        
    Returns:
        {
            'title': str,
            'text': str,  # 纯文本
            'html': str,  # HTML格式（保留段落）
            'author': str,
            'publish_date': str
        }
        失败返回 None
    """
    try:
        # 方案 A: newspaper3k
        article = Article(url)
        article.download()
        article.parse()
        
        if not article.text or len(article.text) < 100:
            raise ValueError("正文过短，可能提取失败")
            
        return {
            'title': article.title,
            'text': article.text,
            'html': article.html,  # 保留原始HTML
            'author': ', '.join(article.authors) if article.authors else '',
            'publish_date': str(article.publish_date) if article.publish_date else ''
        }
    except Exception as e:
        print(f"     newspaper3k 提取失败，尝试 readability：{e}")
        
    try:
        # 方案 B: readability-lxml
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        
        doc = Document(response.content)
        html_content = doc.summary()
        
        # 提取纯文本
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')
        text = soup.get_text(separator='\n', strip=True)
        
        if len(text) < 100:
            raise ValueError("正文过短")
            
        return {
            'title': doc.title(),
            'text': text,
            'html': html_content,
            'author': '',
            'publish_date': ''
        }
    except Exception as e:
        print(f"     readability 提取失败：{e}")
        return None
```

---

### 2. LLM 翻译服务

#### 2.1 分段翻译策略

**问题**：文章过长会超出 token 限制
**解决**：按段落分批翻译，保留格式

```python
# translation_service.py

def translate_article_llm(article_text, max_chars_per_batch=3000):
    """
    使用 LLM 翻译文章，分段处理
    
    Args:
        article_text: 原文文本
        max_chars_per_batch: 每批最大字符数
        
    Returns:
        翻译后的文本
    """
    paragraphs = article_text.split('\n\n')
    
    translated_paragraphs = []
    batch = []
    batch_chars = 0
    
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
            
        para_len = len(para)
        
        # 如果当前批次 + 新段落超限，先翻译当前批次
        if batch and batch_chars + para_len > max_chars_per_batch:
            batch_text = '\n\n'.join(batch)
            translated = _translate_batch(batch_text)
            translated_paragraphs.append(translated)
            batch = []
            batch_chars = 0
        
        batch.append(para)
        batch_chars += para_len
    
    # 翻译最后一批
    if batch:
        batch_text = '\n\n'.join(batch)
        translated = _translate_batch(batch_text)
        translated_paragraphs.append(translated)
    
    return '\n\n'.join(translated_paragraphs)


def _translate_batch(text):
    """翻译一批文本"""
    system_prompt = (
        "你是专业的财经翻译。把用户给出的英文财经文章翻译成简体中文，"
        "保持段落结构和格式，财经术语准确，公司名、人名保留通用译名。"
    )
    
    user_prompt = f"翻译以下英文财经文章为简体中文，保持段落结构：\n\n{text}"
    
    try:
        # 使用 gpt-4o-mini（快速且便宜）
        result = call_llm_json(
            system_prompt, 
            user_prompt, 
            model='gpt-4o-mini',
            retries=2
        )
        
        # LLM 可能返回 JSON，也可能直接返回文本
        if isinstance(result, dict):
            return result.get('translation', '') or result.get('text', '')
        return str(result)
        
    except Exception as e:
        print(f"     批次翻译失败：{e}")
        return text  # 失败时返回原文
```

---

### 3. 静态页面生成

#### 3.1 HTML 模板

```html
<!-- translation_template.html -->
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{title}} - 财经日报全文翻译</title>
    <style>
        :root {
            --bg: #0e1014;
            --card: #171c26;
            --text: #e8ecf3;
            --muted: #9aa4b2;
            --accent: #5b9eff;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background: var(--bg);
            color: var(--text);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            line-height: 1.8;
            padding: 20px;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
            background: var(--card);
            border-radius: 12px;
            padding: 40px;
        }
        .header {
            border-bottom: 1px solid rgba(255,255,255,0.1);
            padding-bottom: 20px;
            margin-bottom: 30px;
        }
        h1 {
            font-size: 28px;
            margin-bottom: 12px;
            color: var(--accent);
        }
        .meta {
            font-size: 14px;
            color: var(--muted);
        }
        .meta a {
            color: var(--accent);
            text-decoration: none;
        }
        .meta a:hover {
            text-decoration: underline;
        }
        .content {
            font-size: 16px;
            line-height: 1.8;
        }
        .content p {
            margin-bottom: 16px;
        }
        .footer {
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid rgba(255,255,255,0.1);
            font-size: 13px;
            color: var(--muted);
            text-align: center;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{{title}}</h1>
            <div class="meta">
                <span>来源：{{source}}</span>
                {{#author}}<span> | 作者：{{author}}</span>{{/author}}
                {{#date}}<span> | {{date}}</span>{{/date}}
                <br>
                <a href="{{original_url}}" target="_blank">📄 阅读英文原文 ↗</a>
            </div>
        </div>
        <div class="content">
            {{content}}
        </div>
        <div class="footer">
            本文由 LLM 自动翻译 | <a href="https://yunix-intel.github.io/ai-daily-push/finance.html">返回财经日报</a>
        </div>
    </div>
</body>
</html>
```

#### 3.2 页面生成代码

```python
# static_page_generator.py

import os
import hashlib
from datetime import datetime

def generate_translation_page(article_data, translated_text, output_dir='translations'):
    """
    生成静态翻译页面
    
    Args:
        article_data: 原文数据 {title, url, source, author, date}
        translated_text: 翻译后的文本
        output_dir: 输出目录
        
    Returns:
        生成的HTML文件路径（相对路径）
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # 使用 URL hash 作为文件名（去重）
    url_hash = hashlib.md5(article_data['url'].encode()).hexdigest()[:12]
    filename = f"{url_hash}.html"
    filepath = os.path.join(output_dir, filename)
    
    # 如果已存在，直接返回（缓存）
    if os.path.exists(filepath):
        print(f"     翻译页面已缓存：{filename}")
        return f"{output_dir}/{filename}"
    
    # 将纯文本转换为HTML段落
    paragraphs = translated_text.split('\n\n')
    content_html = '\n'.join(f'<p>{para}</p>' for para in paragraphs if para.strip())
    
    # 填充模板
    html = TRANSLATION_TEMPLATE.replace('{{title}}', article_data.get('title', ''))
    html = html.replace('{{source}}', article_data.get('source', ''))
    html = html.replace('{{original_url}}', article_data.get('url', ''))
    
    # 可选字段
    author = article_data.get('author', '')
    if author:
        html = html.replace('{{#author}}', '').replace('{{/author}}', '')
        html = html.replace('{{author}}', author)
    else:
        html = re.sub(r'{{#author}}.*?{{/author}}', '', html, flags=re.DOTALL)
    
    date = article_data.get('date', '')
    if date:
        html = html.replace('{{#date}}', '').replace('{{/date}}', '')
        html = html.replace('{{date}}', date)
    else:
        html = re.sub(r'{{#date}}.*?{{/date}}', '', html, flags=re.DOTALL)
    
    html = html.replace('{{content}}', content_html)
    
    # 写入文件
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"     翻译页面生成：{filename}")
    return f"{output_dir}/{filename}"


TRANSLATION_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{title}} - 财经日报全文翻译</title>
    <style>
        :root {
            --bg: #0e1014;
            --card: #171c26;
            --text: #e8ecf3;
            --muted: #9aa4b2;
            --accent: #5b9eff;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background: var(--bg);
            color: var(--text);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", sans-serif;
            line-height: 1.8;
            padding: 20px;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
            background: var(--card);
            border-radius: 12px;
            padding: 40px;
            box-shadow: 0 4px 24px rgba(0,0,0,0.3);
        }
        .header {
            border-bottom: 1px solid rgba(255,255,255,0.1);
            padding-bottom: 20px;
            margin-bottom: 30px;
        }
        h1 {
            font-size: 28px;
            margin-bottom: 12px;
            color: var(--accent);
            line-height: 1.3;
        }
        .meta {
            font-size: 14px;
            color: var(--muted);
        }
        .meta a {
            color: var(--accent);
            text-decoration: none;
        }
        .meta a:hover {
            text-decoration: underline;
        }
        .content {
            font-size: 16px;
            line-height: 1.8;
        }
        .content p {
            margin-bottom: 16px;
        }
        .footer {
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid rgba(255,255,255,0.1);
            font-size: 13px;
            color: var(--muted);
            text-align: center;
        }
        .footer a {
            color: var(--accent);
            text-decoration: none;
        }
        @media (max-width: 768px) {
            .container { padding: 24px; }
            h1 { font-size: 22px; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{{title}}</h1>
            <div class="meta">
                <span>来源：{{source}}</span>
                {{#author}}<span> | 作者：{{author}}</span>{{/author}}
                {{#date}}<span> | {{date}}</span>{{/date}}
                <br>
                <a href="{{original_url}}" target="_blank">📄 阅读英文原文 ↗</a>
            </div>
        </div>
        <div class="content">
            {{content}}
        </div>
        <div class="footer">
            本文由 LLM 自动翻译 | <a href="https://yunix-intel.github.io/ai-daily-push/finance.html">返回财经日报</a>
        </div>
    </div>
</body>
</html>
"""
```

---

### 4. 主流程集成

#### 4.1 选择性翻译逻辑

```python
# finance_daily_push.py

def pre_translate_articles(items_international):
    """
    预翻译国际要闻全文
    
    优先级：
    1. 核心必读（importance_score >= 8）
    2. 重要要闻前 5 条（5 <= importance_score < 8）
    
    Args:
        items_international: 国际要闻列表
        
    Returns:
        无返回值，直接修改 items 添加 translatedPage 字段
    """
    from article_extractor import extract_article
    from translation_service import translate_article_llm
    from static_page_generator import generate_translation_page
    
    # 筛选需要翻译的文章
    candidates = []
    
    # 1. 核心必读
    must_read = [item for item in items_international if item.get('importance_score', 0) >= 8]
    candidates.extend(must_read)
    
    # 2. 重要要闻前 5 条
    important = [item for item in items_international if 5 <= item.get('importance_score', 0) < 8]
    candidates.extend(important[:5])
    
    if not candidates:
        print("     无需翻译的核心文章")
        return
    
    print(f"     准备翻译 {len(candidates)} 篇文章全文 ...")
    
    success_count = 0
    for item in candidates:
        url = item.get('link', '')
        if not url:
            continue
        
        try:
            # 1. 提取原文
            article = extract_article(url)
            if not article:
                print(f"     [!] 文章提取失败：{url[:50]}")
                continue
            
            # 2. LLM 翻译
            translated_text = translate_article_llm(article['text'])
            if not translated_text or len(translated_text) < 100:
                print(f"     [!] 翻译失败：{url[:50]}")
                continue
            
            # 3. 生成静态页面
            article_data = {
                'title': item.get('title', ''),
                'url': url,
                'source': item.get('source', ''),
                'author': article.get('author', ''),
                'date': article.get('publish_date', '')
            }
            page_path = generate_translation_page(article_data, translated_text)
            
            # 4. 更新 item
            item['translatedPage'] = f"https://yunix-intel.github.io/ai-daily-push/{page_path}"
            success_count += 1
            
        except Exception as e:
            print(f"     [!] 全文翻译失败：{e}")
            continue
    
    print(f"     全文翻译完成：{success_count}/{len(candidates)} 篇")
```

#### 4.2 集成到主流程

```python
# 在 main() 函数中，翻译国际新闻标题摘要后：

# [2.2] 翻译国际要闻标题摘要
if items_international:
    print("     [2.2] 翻译国际要闻 ...")
    translate_finance_items(items_international)

# [2.3] 预翻译核心文章全文（新增）
if items_international:
    print("     [2.3] 预翻译核心文章全文 ...")
    try:
        pre_translate_articles(items_international)
    except Exception as exc:
        print(f"     [!] 全文翻译失败，跳过：{exc}")
```

---

## 📦 依赖安装

```bash
pip install newspaper3k
pip install readability-lxml
pip install lxml_html_clean  # newspaper3k 需要
```

---

## 🧪 测试计划

### 测试场景

1. **正常流程**
   - ✅ 提取英文文章正文
   - ✅ LLM 翻译成功
   - ✅ 生成静态页面
   - ✅ 链接可访问

2. **边界情况**
   - ✅ 文章提取失败（反爬、404）
   - ✅ 翻译失败（LLM 错误）
   - ✅ 无核心文章（跳过翻译）

3. **性能测试**
   - ✅ 5 篇文章翻译时间 < 2 分钟
   - ✅ 缓存命中率

4. **成本估算**
   - 每篇文章平均 3000 tokens
   - 5 篇 = 15K tokens ≈ $0.003（gpt-4o-mini）
   - 可接受

---

## 📊 实施步骤

1. **安装依赖** (5分钟)
   ```bash
   pip install newspaper3k readability-lxml lxml_html_clean
   ```

2. **创建 article_extractor.py** (30分钟)
   - 实现 newspaper3k + readability 双方案
   - 测试主流财经网站

3. **创建 translation_service.py** (30分钟)
   - 实现分段翻译逻辑
   - 测试长文章翻译

4. **创建 static_page_generator.py** (20分钟)
   - 实现 HTML 模板渲染
   - 测试样式

5. **集成到 finance_daily_push.py** (30分钟)
   - 添加 pre_translate_articles()
   - 修改主流程

6. **本地测试** (30分钟)
   - 完整流程测试
   - 生成翻译页面

7. **GitHub Actions 部署** (20分钟)
   - 确认 translations/ 目录部署
   - 验证线上访问

**总计**：约 3-3.5 小时

---

## ⚠️ 风险与缓解

### 风险 1：文章提取失败率高
- **风险**：部分网站反爬，提取失败
- **缓解**：双方案回退（newspaper3k → readability）
- **监控**：记录失败率，优化提取策略

### 风险 2：翻译成本过高
- **风险**：文章过长，token 消耗大
- **缓解**：只翻译核心必读（5-10篇）
- **优化**：使用 gpt-4o-mini（便宜 10x）

### 风险 3：GitHub Pages 部署延迟
- **风险**：translations/ 目录未部署
- **缓解**：确认 .github/workflows 配置正确
- **验证**：手动触发一次 Actions

---

## 🎯 预期收益

1. **用户体验**：国际要闻全文可读，不依赖外部服务
2. **访问性**：国内网络可访问
3. **翻译质量**：LLM 理解上下文，质量优于机器翻译
4. **成本控制**：每天 < $0.01（5篇文章）

---

## 📝 待办清单

- [ ] 1. 安装依赖（newspaper3k, readability-lxml）
- [ ] 2. 创建 article_extractor.py
- [ ] 3. 创建 translation_service.py
- [ ] 4. 创建 static_page_generator.py
- [ ] 5. 集成到 finance_daily_push.py
- [ ] 6. 本地测试（完整流程）
- [ ] 7. 提交代码并推送
- [ ] 8. GitHub Actions 验证
- [ ] 9. 更新完整计划文档

---

## 🚀 下一步

等待用户批准后开始实施。

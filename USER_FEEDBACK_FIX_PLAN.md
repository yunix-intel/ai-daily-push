# 用户反馈问题修复方案

**反馈时间**: 2026-08-31  
**问题数量**: 3个

---

## 问题1: 今日重要新闻有重复（索尼起诉Anthropic）⭐

**现象**: 
- 同一新闻出现2次
- 来自不同网站但内容基本相同

**根本原因**:
缺少**去重机制**。当前逻辑按打分排序选Top 5，但不检查内容相似度。

**修复方案**:

```python
# ai_daily_push.py - 在pick_highlights函数中添加去重

def calculate_similarity(title1, title2):
    """计算标题相似度"""
    # 方案A: 简单关键词匹配
    words1 = set(re.findall(r'\w+', title1.lower()))
    words2 = set(re.findall(r'\w+', title2.lower()))
    
    if not words1 or not words2:
        return 0.0
    
    intersection = words1 & words2
    union = words1 | words2
    
    return len(intersection) / len(union)  # Jaccard相似度

def pick_highlights(flat_items, top_n=5):
    """选择重要新闻，自动去重"""
    ranked = sorted(
        flat_items,
        key=lambda pair: (-_score_importance(pair[0]["title"] + " " + pair[0].get("originalTitle", ""), pair[1]), pair[0]["idx"]),
    )
    
    selected = []
    for item, sec in ranked:
        if len(selected) >= top_n:
            break
        
        # 检查是否与已选新闻重复
        is_duplicate = False
        for existing_item, _ in selected:
            similarity = calculate_similarity(
                item.get("title", ""),
                existing_item.get("title", "")
            )
            if similarity > 0.6:  # 相似度阈值60%
                is_duplicate = True
                break
        
        if not is_duplicate:
            selected.append((item, sec))
    
    return selected
```

**验收标准**:
- ✅ 同一主题新闻只出现1次
- ✅ 保留分数最高的那条
- ✅ Top 5数量不变

---

## 问题2: 今日重要新闻内容没有两端对齐 ⚠️

**现象**:
- 卡片内的文字左对齐
- 用户期望两端对齐（justify）

**当前CSS**:
```css
/* ai_daily_push.py Line 571, 573 */
.card h3{...; text-align:justify}        /* 标题已两端对齐 */
.card .summary{...; text-align:justify}   /* 摘要已两端对齐 */
```

**问题分析**:
- ✅ 代码中**已经设置**了 `text-align:justify`
- ❓ 可能是浏览器渲染问题或内容太短

**两端对齐不生效的原因**:
1. 文本只有一行时，justify不起作用
2. 最后一行文本不会两端对齐（CSS标准行为）
3. 需要添加 `text-align-last: justify`（但会让最后一行拉得很开，不美观）

**改进方案**:

```python
# 方案A: 保持当前justify，接受CSS标准行为
# 解释：最后一行不对齐是正常的，避免单词间距过大

# 方案B: 强制最后一行也对齐（不推荐）
.card h3{...; text-align:justify; text-align-last:justify}
.card .summary{...; text-align:justify; text-align-last:justify}

# 方案C: 增加文字间距，让对齐更明显
.card h3{...; text-align:justify; word-spacing:0.05em}
.card .summary{...; text-align:justify; word-spacing:0.05em}
```

**建议**: 
保持当前设置。`text-align:justify`已生效，最后一行不对齐是CSS标准行为，强制对齐会让排版更差。

如果用户仍觉得不够对齐，可能是因为：
- 标题/摘要太短，只有1-2行
- 浏览器缩放导致

---

## 问题3: 全文翻译在两个日报里面仍然不能用 🔗

**现象**:
- "翻译全文 ↗" 链接存在
- 但无法使用（点击无效或体验差）

**当前实现**:

```python
# ai_daily_push.py Line 751
const tp=safeUrl(it.translatedPage||'');
'<a class="orig" href="'+esc(tp)+'" target="_blank">翻译全文 ↗</a>'
```

**链接格式**:
```
https://translate.google.com/translate?sl=auto&tl=zh-CN&u=https%3A%2F%2F原文URL
```

**问题原因**:
1. ✅ Google Translate在国内**无法访问**（需要VPN）
2. ✅ 翻译质量一般
3. ✅ 用户期望的可能是"直接看中文全文"而非Google翻译页面

**解决方案**:

### 方案A: 移除翻译全文链接（推荐）

```python
# ai_daily_push.py Line 756 - 修改为
main+='<div class="foot"><span class="src">'+esc(it.source)+'</span><span class="linkgroup">'
# 移除：+(tp&&tp!=='#'?'<a class="orig" href="'+esc(tp)+'">翻译全文 ↗</a>':'')
main+='<a class="orig" href="'+esc(orig)+'" target="_blank">阅读原文 ↗</a></span></div>'
```

**理由**:
- Google Translate国内不可用
- 原文链接+已翻译的标题/摘要已经足够
- 简化界面

### 方案B: 替换为国内翻译服务

```python
# 使用百度翻译、有道翻译或DeepL
def get_translation_url(original_url):
    """生成翻译链接"""
    encoded_url = urllib.parse.quote(original_url)
    
    # 百度翻译
    # return f"https://fanyi.baidu.com/translate?url={encoded_url}"
    
    # 有道翻译
    # return f"https://fanyi.youdao.com/translate?url={encoded_url}"
    
    # 或者移除此功能
    return ""
```

### 方案C: 显示"已翻译"标签而非链接

```python
# 如果title已翻译，显示标签而非链接
if(it.originalTitle!==it.title){
  main+='<span class="badge">已翻译</span>';
}
```

**推荐**: **方案A - 移除翻译全文链接**

原因：
1. 功能在国内不可用
2. 已有翻译的标题和摘要
3. 原文链接可直接阅读

---

## 财经日报的翻译全文问题

财经日报默认是**中文内容**，不需要翻译功能。

如果有英文新闻源，应该：
1. 在数据采集时翻译
2. 不显示"翻译全文"链接

---

## 实施优先级

| 问题 | 优先级 | 预计时间 | 实施难度 |
|------|--------|---------|---------|
| 重要新闻去重 | P1 | 2小时 | 中 |
| 移除翻译全文链接 | P1 | 0.5小时 | 低 |
| 文本对齐优化 | P2 | 已完成 | - |

---

## 实施步骤

### Step 1: 添加去重功能（2小时）

1. 在 `ai_daily_push.py` 添加 `calculate_similarity` 函数
2. 修改 `pick_highlights` 函数添加去重逻辑
3. 测试验证

```bash
# 测试
python ai_daily_push.py --no-push
grep "索尼\|Sony" ai_daily_dashboard.html | wc -l
# 应该只有1条
```

### Step 2: 移除翻译全文链接（0.5小时）

```python
# ai_daily_push.py Line 756
# 修改前
main+='<span class="linkgroup">'+(tp&&tp!=='#'?'<a href="'+esc(tp)+'">翻译全文 ↗</a>':'')+'<a href="'+esc(orig)+'">阅读原文 ↗</a></span>'

# 修改后
main+='<span class="linkgroup"><a href="'+esc(orig)+'" target="_blank">阅读原文 ↗</a></span>'
```

同样修改markdown生成部分（如果有）。

### Step 3: 验证

```bash
# 本地测试
python ai_daily_push.py --no-push

# 检查去重
grep "重要新闻" ai_daily_dashboard.html -A 20

# 检查翻译链接
grep "翻译全文" ai_daily_dashboard.html
# 应该无输出

# 检查对齐
grep "text-align:justify" ai_daily_dashboard.html
# 应该有2处
```

---

## 验收标准

**问题1 - 去重**:
- [ ] 同一主题新闻只出现1次
- [ ] Top 5仍然是5条（如果有足够新闻）
- [ ] 保留分数最高的

**问题2 - 对齐**:
- [x] CSS已设置justify（无需修改）
- [x] 标题和摘要都使用两端对齐

**问题3 - 翻译链接**:
- [ ] AI日报移除"翻译全文"链接
- [ ] 财经日报无"翻译全文"链接
- [ ] 保留"阅读原文"链接

---

**预计总时间**: 2.5小时
**建议实施**: 下次更新时一起修复

# AI 日报优化计划

## 📊 当前状态分析

### 已完成的功能
✅ 6个板块的 AI 日报
✅ 市场数据采集（OpenRouter + AA）
✅ LLM 新闻指标提取
✅ HTML 报告生成
✅ GitHub Actions 自动化

### 发现的问题

1. **交叉验证准确性低**
   - 当前使用简单的字符串包含匹配
   - 模型名称格式不统一（"GPT-4o" vs "gpt-4o" vs "OpenAI GPT-4o"）
   - 导致很多应该确认的项被标记为"待确认"

2. **Artificial Analysis 数据质量问题**
   - Intelligence 排名中出现重复的 "Qwen" 条目（分数相同）
   - 缺少模型完整名称（只有 "Qwen", "DeepSeek"）
   - Speed 排名为空

3. **缓存策略可优化**
   - 缓存文件按日期，但没有过期清理机制
   - 历史数据累积可能占用过多空间

4. **报告格式可改进**
   - 市场数据卡片的 summary 使用 \n 换行，HTML 渲染可能不理想
   - 缺少数据时间戳显示

5. **错误信息不够友好**
   - 编码问题导致中文乱码（Windows GBK）
   - 错误日志缺少上下文信息

---

## 🎯 优化方案

### 优化 1: 改进交叉验证算法（30分钟）

**问题**：简单字符串匹配导致准确率低

**方案**：实现模糊匹配算法
```python
def normalize_model_name(name):
    """标准化模型名称"""
    # 移除常见前缀
    name = re.sub(r'^(OpenAI|Anthropic|Google|Meta|DeepSeek|Qwen):\s*', '', name, flags=re.I)
    # 统一大小写
    name = name.lower()
    # 移除版本号和特殊字符
    name = re.sub(r'[-_\s]+', '', name)
    return name

def fuzzy_match(name1, name2, threshold=0.8):
    """模糊匹配两个模型名称"""
    from difflib import SequenceMatcher
    n1 = normalize_model_name(name1)
    n2 = normalize_model_name(name2)
    ratio = SequenceMatcher(None, n1, n2).ratio()
    return ratio >= threshold
```

### 优化 2: 改进 Artificial Analysis 数据解析（45分钟）

**问题**：数据重复、不完整

**方案**：
1. 去重逻辑：使用 model + score 组合去重
2. 完整名称提取：尝试从多个字段提取
3. Speed 排名解析增强

```python
def _deduplicate_rankings(self, rankings):
    """去重排名数据"""
    seen = set()
    unique = []
    for rank in rankings:
        key = (rank.get('model'), rank.get('score'))
        if key not in seen:
            seen.add(key)
            unique.append(rank)
    return unique
```

### 优化 3: 优化报告格式（30分钟）

**问题**：换行符在 HTML 中不显示

**方案**：使用 `<br>` 标签或 `white-space: pre-wrap`

```python
def _format_for_html(self, text):
    """格式化文本为 HTML"""
    # 将换行符转换为 <br>
    return text.replace('\n', '<br>')
```

### 优化 4: 添加缓存清理机制（20分钟）

**问题**：缓存文件累积

**方案**：保留最近 30 天的缓存

```python
def cleanup_old_cache(self, days=30):
    """清理超过 N 天的缓存文件"""
    cutoff = datetime.now() - timedelta(days=days)
    for cache_file in self.data_dir.glob("*.json"):
        # 从文件名提取日期
        match = re.search(r'(\d{4}-\d{2}-\d{2})', cache_file.name)
        if match:
            file_date = datetime.strptime(match.group(1), '%Y-%m-%d')
            if file_date < cutoff:
                cache_file.unlink()
                print(f"删除过期缓存：{cache_file.name}")
```

### 优化 5: 改进错误处理和日志（15分钟）

**问题**：错误信息不够友好

**方案**：
1. 统一日志格式
2. 添加更多上下文信息
3. 修复编码问题

```python
def log_error(self, context, error):
    """统一的错误日志"""
    print(f"     [ERROR] {context}: {type(error).__name__}: {error}")
```

---

## 📋 优化优先级

### 高优先级（必做）
1. ✅ **优化 1**: 改进交叉验证算法（30分钟）
2. ✅ **优化 2**: 改进 AA 数据解析（45分钟）
3. ✅ **优化 3**: 优化报告格式（30分钟）

### 中优先级（推荐）
4. **优化 4**: 添加缓存清理机制（20分钟）
5. **优化 5**: 改进错误处理和日志（15分钟）

### 低优先级（可选）
6. 性能监控
7. 单元测试覆盖率提升
8. 文档完善

---

## 🧪 测试计划

### 测试场景
1. 交叉验证准确性测试
2. 去重逻辑测试
3. HTML 格式测试
4. 缓存清理测试
5. 完整流程测试

---

## 📝 待办清单

- [ ] 1. 实现模糊匹配算法
- [ ] 2. 更新交叉验证逻辑
- [ ] 3. 实现 AA 数据去重
- [ ] 4. 优化报告格式化器
- [ ] 5. 实现缓存清理机制
- [ ] 6. 改进错误日志
- [ ] 7. 运行测试
- [ ] 8. 提交代码

预计总时间：2-3 小时

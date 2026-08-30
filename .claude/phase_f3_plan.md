# Phase F3: 国际要闻翻译统一实施计划

## 📋 当前问题分析

### 现状
1. **翻译策略双轨制**
   - 优先：LLM 批量翻译（`translate_batch_llm`）
   - 回退：MyMemory API 逐条翻译（`translate_text`）

2. **实际运行问题**
   - 本地测试：LLM 未配置 → 回退 MyMemory → 429 限流 → 连续 4 条失败 → 放弃翻译
   - GitHub Actions：LLM 已配置，理论上应该正常工作

3. **MyMemory API 限制**
   - 免费接口按 IP 限流
   - 逐条调用必然被打成 429
   - 单条失败重试约 17 秒
   - 连续 4 条失败后熔断机制触发

### 代码位置
- `finance_daily_push.py:231-301` - `translate_finance_items()` 主函数
- `finance_daily_push.py:416-447` - `translate_batch_llm()` LLM 批量翻译
- `ai_daily_push.py:259-286` - `translate_text()` MyMemory 翻译

---

## 🎯 优化目标

### Phase F3 核心任务
1. **统一翻译策略**：完全移除 MyMemory API 依赖
2. **提升翻译质量**：标题+摘要一起翻译，保留上下文
3. **优化错误处理**：更细粒度的降级策略
4. **保留原文查看**：双语对照，透明度更高

---

## 🔧 实施方案

### 方案 A：完全移除 MyMemory（推荐）

**理由**：
- LLM 翻译质量更好（有上下文）
- 无限流问题
- 批量处理更快
- 已有完整实现（`translate_batch_llm`）

**变更**：
1. 移除 `translate_finance_items()` 中的 MyMemory 回退逻辑（272-301 行）
2. LLM 失败时直接保留英文原文，不再尝试 MyMemory
3. 优化错误提示信息

**优点**：
- ✅ 简化代码逻辑
- ✅ 无外部 API 依赖
- ✅ 失败时立即降级，不浪费时间

**缺点**：
- ⚠️ LLM 未配置时完全无翻译（但这是预期行为）

### 方案 B：保留 MyMemory 作为最后兜底

**理由**：
- 在完全无 LLM 的环境中提供基础翻译能力

**变更**：
1. 保持当前双轨制
2. 优化 MyMemory 熔断参数（give_up_after=2）
3. 添加更清晰的日志提示

**优点**：
- ✅ 最大兼容性

**缺点**：
- ❌ 限流问题依然存在
- ❌ 代码复杂度高
- ❌ 失败时浪费大量时间（单条 17s * 重试）

---

## 📝 推荐实施：方案 A

### 代码变更

#### 1. 简化 `translate_finance_items()`

**修改前**（231-301 行）：
```python
def translate_finance_items(items, give_up_after=4):
    """英文条目译为中文，保留原文；失败则回退英文原文，不中断整体流程。
    
    优先走 LLM 批量翻译（一次请求翻多条）：MyMemory 是按 IP 限流的免费接口，
    逐条调用几十条必然被打成 429，且每次失败要重试到超时（实测单条约 17s）。
    LLM 不可用（未配置 key 等）时退回 MyMemory 逐条翻译，并保留熔断：
    连续 give_up_after 条失败就放弃剩余翻译，避免把 CI 拖死。
    
    items: 列表，直接修改每个 item 的 title/summary，并添加 originalTitle/originalSummary
    """
    # ... 当前实现：LLM → MyMemory 回退 → 熔断
```

**修改后**：
```python
def translate_finance_items(items):
    """用 LLM 批量翻译英文条目为中文，保留原文；失败则保留英文原文。
    
    使用 LLM 批量翻译（一次请求翻多条），避免 MyMemory API 的限流问题。
    LLM 不可用时直接保留英文原文，不再尝试其他翻译接口。
    
    items: 列表，直接修改每个 item 的 title/summary，并添加 originalTitle/originalSummary
    """
    # 1. 保存原文
    for item in items:
        item["originalTitle"] = item["title"]
        item["originalSummary"] = item["summary"]
    
    # 2. 找出英文条目
    en_indexes = [i for i, item in enumerate(items) if item.get("isEnglish")]
    if not en_indexes:
        print("     无英文条目，跳过翻译")
        return items
    
    print(f"     检测到 {len(en_indexes)} 条英文新闻，准备批量翻译 ...")
    
    # 3. LLM 批量翻译
    try:
        pairs = [(i, items[i]["title"], items[i]["summary"]) for i in en_indexes]
        mapping = translate_batch_llm(pairs)
        done = 0
        for i in en_indexes:
            got = mapping.get(i)
            if not got:
                continue
            title_zh, summary_zh = got
            if title_zh:
                items[i]["title"] = title_zh
            if summary_zh:
                items[i]["summary"] = summary_zh
            if title_zh:
                done += 1
        
        if done > 0:
            print(f"     LLM 翻译完成：{done}/{len(en_indexes)} 条")
        else:
            print(f"     LLM 翻译未产出结果，保留英文原文")
        
        return items
        
    except Exception as exc:
        print(f"     [!] LLM 翻译失败，保留英文原文：{exc}")
        return items
```

#### 2. 优化 `translate_batch_llm()`

**当前问题**：
- batch_size=12 可能过大，某些 LLM 可能处理不好
- 错误处理可以更细致

**优化建议**：
```python
def translate_batch_llm(pairs, batch_size=10):
    """用 LLM 批量翻译英文条目：pairs 为 [(idx, title, summary)]。
    
    返回 {idx: (title_zh, summary_zh)}。批量翻译避免 MyMemory 的限流问题。
    单批失败只影响该批，其余批次照常。
    """
    result = {}
    total_batches = (len(pairs) + batch_size - 1) // batch_size
    
    for start in range(0, len(pairs), batch_size):
        batch = pairs[start:start + batch_size]
        batch_num = start // batch_size + 1
        
        listing = []
        for idx, title, summary in batch:
            listing.append(json.dumps(
                {"id": idx, "title": title, "summary": summary[:300]}, 
                ensure_ascii=False
            ))
        
        user_prompt = (
            "把下面每条英文财经资讯的 title 和 summary 翻译成简体中文。\n"
            "输入（每行一个 JSON 对象）：\n" + "\n".join(listing) + "\n\n"
            '输出 JSON：{"items":[{"id":原样返回的id,"title":"中文标题","summary":"中文摘要"}]}\n'
            "summary 为空则中文 summary 也返回空字符串。必须覆盖全部输入条目。"
        )
        
        try:
            data = call_llm_json(TRANSLATE_SYSTEM, user_prompt, retries=1)
            items_translated = data.get("items") or []
            
            for row in items_translated:
                rid = row.get("id")
                if isinstance(rid, str) and rid.isdigit():
                    rid = int(rid)
                if rid is None:
                    continue
                
                title_zh = (row.get("title") or "").strip()
                summary_zh = (row.get("summary") or "").strip()
                
                result[rid] = (title_zh, summary_zh)
            
            print(f"     批次 {batch_num}/{total_batches}：{len(items_translated)}/{len(batch)} 条翻译成功")
            
        except Exception as exc:
            print(f"     批次 {batch_num}/{total_batches} 失败（该批保留英文）：{exc!r}")
    
    return result
```

#### 3. 更新文档字符串

**修改**：
- `finance_daily_push.py:13` - 更新模块文档，说明翻译策略变更
- 移除 MyMemory 相关描述

---

## 🧪 测试计划

### 测试场景

1. **LLM 已配置**（GitHub Actions 环境）
   - ✅ 批量翻译成功
   - ✅ 部分批次失败，其他批次成功
   - ✅ 翻译质量验证

2. **LLM 未配置**（本地无 API Key）
   - ✅ 直接保留英文原文
   - ✅ 不尝试 MyMemory
   - ✅ 程序正常完成

3. **边界情况**
   - ✅ 无英文条目
   - ✅ 全部英文条目
   - ✅ 标题/摘要为空

### 验证步骤

```bash
# 本地测试（无 LLM）
python finance_daily_push.py --no-push --hours 24

# 预期输出：
# [2.2] 翻译国际要闻 ...
#      检测到 26 条英文新闻，准备批量翻译 ...
#      [!] LLM 翻译失败，保留英文原文：未配置 OPENAI_API_KEY
```

---

## 📊 影响评估

### 代码变更
- 删除：约 30 行（MyMemory 回退逻辑）
- 修改：约 20 行（简化主函数）
- 优化：约 10 行（改进日志）
- **总计**：净减少约 20 行代码

### 依赖变更
- ✅ 移除对 MyMemory API 的依赖
- ✅ 统一为 LLM 翻译
- ⚠️ 完全依赖 `OPENAI_API_KEY` 配置

### 性能影响
- **本地测试**（无 LLM）：翻译时间从 ~68s（4×17s 重试）降至 <1s（立即跳过）
- **GitHub Actions**（有 LLM）：无变化，本来就用 LLM

### 向后兼容
- ✅ 函数签名兼容（移除未使用的 `give_up_after` 参数）
- ✅ 返回值兼容
- ✅ 数据结构兼容（originalTitle/originalSummary 保留）

---

## ✅ 待办清单

- [ ] 1. 简化 `translate_finance_items()` 函数
- [ ] 2. 优化 `translate_batch_llm()` 日志输出
- [ ] 3. 更新模块文档字符串
- [ ] 4. 本地测试（无 LLM）
- [ ] 5. 提交代码并推送
- [ ] 6. GitHub Actions 验证（有 LLM）
- [ ] 7. 查看翻译质量
- [ ] 8. 更新完整计划文档

---

## 🚀 预期收益

1. **代码质量**：逻辑更简单，易维护
2. **用户体验**：翻译质量更好（有上下文）
3. **性能优化**：失败时不浪费时间
4. **成本优化**：避免无效的 API 调用
5. **可靠性**：无限流风险

---

## 📌 风险与缓解

### 风险 1：完全依赖 LLM
- **风险**：LLM 未配置时无翻译
- **缓解**：这是预期行为，英文原文依然可读
- **备选**：用户可以配置 LLM 或直接阅读英文

### 风险 2：翻译质量问题
- **风险**：LLM 翻译可能不准确
- **缓解**：保留 originalTitle/originalSummary，用户可对照
- **备选**：后续可添加翻译质量评分机制

---

## 📝 实施时间估算

- 代码修改：30 分钟
- 本地测试：15 分钟
- GitHub Actions 验证：10 分钟
- 文档更新：15 分钟
- **总计**：约 1-1.5 小时

---

## 🎯 下一步

等待用户批准后开始实施。

# Phase A6: GitHub Actions 集成 - 实施计划

## 📊 当前状态分析

### 已完成的功能（Phase A1-A5）
✅ **数据采集**
- OpenRouter 爬虫：396个模型数据
- Artificial Analysis 爬虫：Intelligence + Speed 数据
- 缓存机制：按日期缓存

✅ **数据分析**
- 市场数据聚合器
- 新闻指标提取器（LLM）
- 趋势分析器

✅ **HTML 报告生成**
- 第6个板块：📊 行业数据洞察
- 3个市场数据卡片
- 集成到 ai_daily_push.py

### 现有 GitHub Actions 配置
**文件**：`.github/workflows/daily.yml`

**已配置的环境变量**：
```yaml
OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
OPENAI_BASE_URL: ${{ secrets.OPENAI_BASE_URL }}
```

**运行时间**：
- UTC 00:00（北京时间 08:00）
- 支持手动触发（workflow_dispatch）

**依赖安装**：
```yaml
pip install -r requirements.txt
```

---

## 🎯 Phase A6 目标

### 核心任务
1. ✅ **requirements.txt 已完善**（包含 openai>=1.0.0）
2. ✅ **GitHub Actions 已配置 OPENAI_API_KEY**
3. **验证本地测试**
4. **创建 GitHub Secret**（OPENAI_API_KEY）
5. **手动触发测试**
6. **验证 Pages 部署**

---

## 📋 实施步骤

### 步骤 1: 本地完整测试（已完成 ✅）
- ✅ 市场数据聚合器测试通过
- ✅ HTML 生成测试通过（32条，包含3个市场数据卡片）
- ✅ 错误处理正常（无 API Key 时降级）

### 步骤 2: 更新文档（15分钟）

需要更新 README.md 说明新功能和配置要求。

**新增内容**：
```markdown
## 🆕 市场数据分析功能

AI 日报现在包含「📊 行业数据洞察」板块：

- **市场使用趋势**（OpenRouter API）
  - 396+ 个 AI 模型价格数据
  - 价格范围、平均价格统计
  - 热门模型 Top 3

- **性能基准**（Artificial Analysis）
  - 智能排名 Top 5
  - 速度排名 Top 3

- **交叉验证**
  - 多源数据印证
  - 确认/待确认项统计

### 可选配置

如需启用 LLM 新闻指标提取（从新闻中提取营收、融资等数据），需配置：

```bash
# GitHub Actions Secrets
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1  # 可选
```

### 成本说明

- **OpenRouter API**：免费（公开数据）
- **Artificial Analysis**：免费（网页抓取）
- **OpenAI API**（可选）：
  - 使用 gpt-4o-mini 模型
  - 每次运行约 $0.001-0.005
  - 未配置时自动跳过
```

### 步骤 3: 配置 GitHub Secret（用户操作）

用户需要在 GitHub 仓库中配置：

1. 进入 GitHub 仓库 Settings → Secrets and variables → Actions
2. 添加 Secret：
   - Name: `OPENAI_API_KEY`
   - Value: `sk-...`（OpenAI API Key）

### 步骤 4: 手动触发测试（用户操作）

1. 进入 GitHub Actions 页面
2. 选择 "每日推送：AI 日报 + 财经日报" workflow
3. 点击 "Run workflow"
4. 查看日志验证：
   - 市场数据采集成功
   - HTML 生成包含市场数据板块
   - Pages 部署成功

### 步骤 5: 验证部署结果（用户操作）

访问 GitHub Pages 地址，检查：
- ✅ 第6个板块显示正常
- ✅ 市场数据卡片格式正确
- ✅ 数据内容完整

---

## 🧪 测试清单

### 本地测试（已完成 ✅）
- [x] 市场数据聚合器单元测试
- [x] 趋势分析器单元测试
- [x] HTML 生成集成测试
- [x] 无 API Key 降级测试

### GitHub Actions 测试（待用户执行）
- [ ] 手动触发 workflow
- [ ] 检查市场数据采集日志
- [ ] 验证 HTML 文件包含市场数据
- [ ] 确认 Pages 部署成功
- [ ] 检查 Pages 页面显示正常

---

## ⚠️ 注意事项

### 环境变量
- **OPENAI_API_KEY**：可选，未配置时跳过新闻指标提取
- **OPENAI_BASE_URL**：可选，默认 https://api.openai.com/v1

### 错误处理
- OpenRouter API 失败 → 使用缓存数据
- Artificial Analysis 失败 → 使用缓存数据
- OpenAI API 失败 → 跳过新闻指标提取
- 全部失败 → 市场数据板块为空，不影响其他板块

### 成本控制
- OpenRouter：免费公开 API
- Artificial Analysis：免费网页抓取
- OpenAI（可选）：每次约 $0.001-0.005
- 建议：生产环境配置 API Key，测试环境可跳过

### 缓存策略
- 数据按日期缓存到 `data/market_data/`
- 当日数据优先使用缓存
- 历史数据自动降级到最近可用日期

---

## 📝 待办清单

- [x] 1. 本地完整测试
- [x] 2. requirements.txt 已包含依赖
- [x] 3. GitHub Actions 已配置环境变量
- [ ] 4. 更新 README.md 文档
- [ ] 5. 创建使用指南
- [ ] 6. 提交代码
- [ ] 7. 用户配置 GitHub Secret
- [ ] 8. 手动触发测试
- [ ] 9. 验证部署结果

---

## 🚀 部署检查清单

### 部署前
- [x] 代码已提交到 main 分支
- [x] requirements.txt 包含所有依赖
- [x] GitHub Actions 配置正确
- [ ] README.md 已更新

### 部署时
- [ ] 配置 OPENAI_API_KEY（可选）
- [ ] 手动触发 workflow
- [ ] 检查 Actions 日志
- [ ] 确认无错误

### 部署后
- [ ] 访问 GitHub Pages
- [ ] 验证市场数据板块显示
- [ ] 检查数据完整性
- [ ] 确认自动定时运行

---

## 📖 使用指南（待创建）

### 对于维护者

**1. 查看市场数据**
- 访问 GitHub Pages 查看 HTML 仪表盘
- 滚动到「📊 行业数据洞察」板块

**2. 调试市场数据**
```bash
# 本地测试市场数据聚合
python -m analyzers.market_data_aggregator

# 本地测试完整流程
python ai_daily_push.py --no-push

# 查看生成的 HTML
open ai_daily_dashboard.html  # macOS
start ai_daily_dashboard.html  # Windows
```

**3. 配置 OpenAI API（可选）**
```bash
# 本地测试
export OPENAI_API_KEY=sk-...
python ai_daily_push.py --no-push

# GitHub Actions
# Settings → Secrets → OPENAI_API_KEY
```

**4. 查看缓存数据**
```bash
# 查看缓存的市场数据
ls -lh data/market_data/

# 查看特定日期的数据
cat data/market_data/openrouter_2026-08-30.json | jq .
```

### 对于用户

**查看 AI 日报**
- 访问 GitHub Pages 地址
- 查看「📊 行业数据洞察」板块
- 获取最新的市场数据和趋势

**理解数据来源**
- OpenRouter：实时模型价格数据
- Artificial Analysis：性能基准测试
- 新闻提取：官方公布的营收、融资数据（需 API Key）

---

## ✅ Phase A6 完成标准

- [x] requirements.txt 包含所有依赖
- [x] GitHub Actions 配置正确
- [x] 本地测试全部通过
- [ ] README.md 已更新
- [ ] 用户配置指南已创建
- [ ] 提交所有代码
- [ ] （用户操作）GitHub Secret 已配置
- [ ] （用户操作）手动测试成功
- [ ] （用户操作）Pages 部署正常

---

## 🎉 项目完成总结

### AI 日报市场数据分析系统（6个阶段）

✅ **Phase A1**: 爬虫基础设施验证
✅ **Phase A2**: OpenRouter 爬虫增强
✅ **Phase A3**: Artificial Analysis 爬虫增强
✅ **Phase A4**: LLM 数据分析
✅ **Phase A5**: HTML 报告生成
🔄 **Phase A6**: GitHub Actions 集成（进行中）

### 成果
- 6 个板块的 AI 日报仪表盘
- 396+ 个 AI 模型价格数据
- 性能基准测试数据
- LLM 驱动的新闻指标提取
- 完整的错误处理和降级策略
- 自动化 GitHub Actions 部署

### 技术栈
- Python 3.11
- OpenRouter API
- Artificial Analysis（网页抓取）
- OpenAI API（可选）
- BeautifulSoup4
- GitHub Actions
- GitHub Pages

---

准备退出计划模式，开始实施剩余任务。

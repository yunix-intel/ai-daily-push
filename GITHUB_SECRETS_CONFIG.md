# GitHub Secrets 配置指南

## 必需配置（财经日报相关）

### LLM API 配置

在 GitHub 仓库的 `Settings > Secrets and variables > Actions > Repository secrets` 中添加：

#### 1. OPENAI_API_KEY (必需)
- **说明**: OpenAI 兼容 API 的密钥
- **值示例**: `sk-xxxxxxxxxxxxxxxxxxxxx`
- **用途**: 调用 LLM 进行翻译、分析、总结
- **状态**: ⚠️ **当前未配置** - 导致所有 LLM 功能失败

#### 2. OPENAI_BASE_URL (必需)
- **说明**: OpenAI 兼容 API 的基础 URL
- **实际值**: `https://aiapi.hk.oliga.top/v1`
- **用途**: API 请求的目标地址
- **状态**: ✓ 已配置

#### 3. OPENAI_MODEL_TRANSLATE (可选，推荐配置)
- **说明**: 翻译模型名称
- **默认值**: `deepseek-v4-flash`
- **推荐值**: `deepseek-v4-flash` (快速、便宜)
- **用途**: 翻译国际新闻标题和摘要
- **状态**: ⚠️ 未配置（将使用默认值）

#### 4. OPENAI_MODEL_ANALYSIS (可选，推荐配置)
- **说明**: 分析模型名称
- **默认值**: `gpt-5.6-sol`
- **推荐值**: `gpt-5.6-sol` (高级推理能力)
- **用途**: 
  - 市场总结
  - 市场分析（宏观、板块）
  - 策略建议（A股、港股）
  - 假期新闻总结
  - 突发事件影响分析
- **状态**: ⚠️ 未配置（将使用默认值）

---

## 为什么需要分开配置两个模型？

### 成本优化
- **翻译任务**: 高频、简单，用 `deepseek-v4-flash` 省钱
  - 每天约 100+ 条新闻需要翻译
  - 成本约为 GPT-4 的 1/50
  
- **分析任务**: 低频、复杂，用 `gpt-5.6-sol` 保证质量
  - 每天仅 5-10 次调用
  - 需要深度推理和准确判断

### 示例对比

| 任务 | 模型 | 调用次数/天 | 单次Token | 总成本/月 |
|------|------|------------|----------|----------|
| 翻译 | deepseek-v4-flash | ~100 | ~200 | $1 |
| 翻译 | gpt-5.6-sol | ~100 | ~200 | $50 |
| 分析 | gpt-5.6-sol | ~10 | ~1000 | $10 |

使用双模型配置，每月可节省约 **$40**。

---

## 如何添加 Secrets

### 方法1: 通过网页界面

1. 打开仓库页面
2. 点击 `Settings` → `Secrets and variables` → `Actions`
3. 点击 `New repository secret`
4. 输入名称（如 `OPENAI_API_KEY`）
5. 输入值
6. 点击 `Add secret`

### 方法2: 使用 GitHub CLI

```bash
# 安装 gh CLI (如果还没有)
# https://cli.github.com/

# 登录
gh auth login

# 添加 secrets
gh secret set OPENAI_API_KEY
# 粘贴你的 API key，按 Ctrl+D 结束

gh secret set OPENAI_BASE_URL -b "https://api.deepseek.com/v1"
gh secret set OPENAI_MODEL_TRANSLATE -b "deepseek-v4-flash"
gh secret set OPENAI_MODEL_ANALYSIS -b "gpt-5.6-sol"
```

---

## 配置检查清单

### 立即修复（P0）
- [ ] `OPENAI_API_KEY` - **必须配置，否则财经日报完全失败**
- [ ] `OPENAI_BASE_URL` - ✓ 已配置

### 推荐配置（P1）
- [ ] `OPENAI_MODEL_TRANSLATE` - 未配置将使用默认值 `deepseek-v4-flash`
- [ ] `OPENAI_MODEL_ANALYSIS` - 未配置将使用默认值 `gpt-5.6-sol`

### 其他 Secrets（已配置）
- [x] `WECOM_WEBHOOK` - 企业微信推送
- [x] `FEISHU_WEBHOOK` - 飞书推送  
- [x] `FINANCE_DASHBOARD_URL` - 财经仪表盘 URL

---

## 验证配置

### 本地测试

```bash
# 设置环境变量
export OPENAI_API_KEY="sk-your-key"
export OPENAI_BASE_URL="https://aiapi.hk.oliga.top/v1"
export OPENAI_MODEL_TRANSLATE="deepseek-v4-flash"
export OPENAI_MODEL_ANALYSIS="gpt-5.6-sol"

# 运行财经日报（不推送，只生成HTML）
python finance_daily_push.py --no-push

# 检查输出
# 应该看到:
# ============================================================
# [LLM配置] 财经日报模型配置
# ============================================================
# ✓ API Key: 已配置 (长度: 51)
#   Base URL: https://api.deepseek.com/v1
#   翻译模型: deepseek-v4-flash (用于新闻标题/摘要翻译)
#   分析模型: gpt-5.6-sol (用于市场总结/策略建议)
# ============================================================
```

### GitHub Actions 测试

1. 配置好所有 Secrets
2. 进入 `Actions` 页面
3. 选择 `每日推送` workflow
4. 点击 `Run workflow` → `Run workflow`
5. 等待执行完成
6. 检查日志输出中的 `[LLM配置]` 部分

---

## 故障排查

### 问题1: "未配置 OPENAI_API_KEY"

**症状**:
```
市场总结: （本次未生成 AI 分析：LLM 未配置或调用失败...）
策略建议: 空白
```

**解决**:
1. 检查 GitHub Secrets 是否已添加 `OPENAI_API_KEY`
2. 检查 `.github/workflows/daily.yml` 是否引用了该 secret
3. 重新运行 workflow

### 问题2: "API Key 无效"

**症状**:
```
RuntimeError: 401 Unauthorized
```

**解决**:
1. 验证 API Key 是否正确
2. 检查 API Key 是否过期
3. 确认 Base URL 与 API Key 匹配

### 问题3: "模型不存在"

**症状**:
```
RuntimeError: 404 Model not found: gpt-5.6-sol
```

**解决**:
1. 确认你的 API 提供商支持该模型
2. 更新 `OPENAI_MODEL_ANALYSIS` 为支持的模型名称
3. 或者删除该 Secret，使用代码中的默认值

---

## 当前状态总结

### ✓ 已配置
- `OPENAI_BASE_URL`
- `WECOM_WEBHOOK`
- `FEISHU_WEBHOOK`

### ⚠️ 缺失（紧急）
- `OPENAI_API_KEY` ← **立即配置**

### 📝 建议配置
- `OPENAI_MODEL_TRANSLATE` (可选，有默认值)
- `OPENAI_MODEL_ANALYSIS` (可选，有默认值)

---

## 下一步

1. **立即**: 添加 `OPENAI_API_KEY` 到 GitHub Secrets
2. **推荐**: 添加 `OPENAI_MODEL_TRANSLATE` 和 `OPENAI_MODEL_ANALYSIS`
3. **测试**: 手动触发 workflow 验证配置
4. **监控**: 检查明天的自动运行结果

# 每日推送：AI 日报 + 财经日报（企业微信 + GitHub Pages）

每天北京时间 08:00 自动运行，向企业微信群机器人推送**两条**消息，并部署**两个独立网页**：

| | 推送形式 | 网页 |
|---|---|---|
| 第一条 · AI 日报 | 图文卡片（点击进网页） | `index.html` |
| 第二条 · 财经日报 | 图文卡片（点击进网页） | `finance.html` |

两个网页各自独立 URL，内容不混排。

## 工作原理

- `ai_daily_push.py`：拉取 AI HOT 日报 + 4 个 AI 资讯 RSS → 英文条目译中文（保留原文）→ **[新增]** 采集市场数据（OpenRouter + Artificial Analysis）→ 生成 `ai_daily_dashboard.html`（6个板块）→ 推送图文卡片。
- `finance_daily_push.py`：抓指数行情 + 6 个财经源（3 中文 / 3 英文，过去 24 小时）→ LLM 批量翻译 → LLM 生成突发事件/今日总结/市场分析 → LLM 生成 A股/港股策略建议 → 生成 `finance_dashboard.html` → 推送 markdown。
- `.github/workflows/daily.yml`：定时（`cron 0 0 * * *` = 北京 08:00）+ 手动触发，两步依次执行后一起部署到 Pages。财经日报那步带 `continue-on-error`，它失败不会影响已成功的 AI 日报。

## 财经日报的数据与分析

- **行情锚点**：腾讯行情接口取上证/深证/创业板/恒生/恒生科技 5 个指数，作为「唯一可引用的数字来源」注入 LLM prompt，避免模型编造点位。
- **来源**：格隆汇快讯、同花顺快讯、金十数据、Seeking Alpha、MarketWatch、CNBC Finance。只保留过去 24 小时条目（发布时间无法解析的一律保留，宁多不漏）。
- **rsshub 镜像故障转移**：中文源（格隆汇、同花顺、金十数据）通过 rsshub 聚合服务抓取。主镜像（`rsshub.rssforever.com`）失败时自动依次尝试备用镜像（`rsshub.liumingye.cn`、`rsshub.ktachibana.party`），提升稳定性。英文源直连官方 RSS。已验证：当主镜像超时，系统自动从备用镜像成功抓取。
- **突发事件**：由 LLM 从全部条目中挑「真突发」（地缘冲突、监管黑天鹅、重大事故、系统性风险、超预期政策转向），排除例行业绩公告和数据发布。
- **免责声明**：由代码强制拼接，不依赖模型输出（实测模型会漏字），且推送截断时优先保留。

## 部署步骤

1. 仓库 **Settings → Secrets and variables → Actions**，添加：

   | Secret | 用途 |
   |---|---|
   | `WECOM_WEBHOOK` | 企业微信群机器人 webhook（两条推送共用，无需 IP 白名单） |
   | `DASHBOARD_URL` | AI 日报网页地址，如 `https://<用户名>.github.io/<仓库名>/` |
   | `FINANCE_DASHBOARD_URL` | 财经日报网页地址，如 `https://<用户名>.github.io/<仓库名>/finance.html` |
   | `OPENAI_API_KEY` | 财经日报的翻译与分析（缺失时网页仍生成，分析区块标注未生成） |
   | `OPENAI_BASE_URL` | 可选，自建 OpenAI 兼容网关，如 `https://your-gateway/v1` |
   | `FEISHU_WEBHOOK` | 可选，配了就走飞书；企业微信 webhook 优先 |

2. 仓库 **Settings → Pages → Source** 选 **GitHub Actions**。
3. **Actions** 标签页 → 选工作流 → **Run workflow** 手动跑一次。

### LLM 模型分工

翻译和分析用不同模型，可用 Secret 覆盖：

- `OPENAI_MODEL_TRANSLATE`：默认 `deepseek-v4-flash`（批量翻译，量大要求低）
- `OPENAI_MODEL_ANALYSIS`：默认 `gpt-5.6-sol`（总结/分析/策略，需要推理）

分开是因为实测 `deepseek-v4-flash` 在 57 条的分析 prompt 上会 504 超时（273s 无响应），而 gpt 系列 26s 返回。

## 本地调试

```bash
python ai_daily_push.py --no-push        # 只生成 AI 日报网页
python finance_daily_push.py --no-push   # 只生成财经网页，打印实际会发送的 markdown
```

### 市场数据分析模块测试

```bash
# 测试市场数据聚合器
python -m analyzers.market_data_aggregator

# 测试趋势分析器
python -m analyzers.trend_analyzer

# 查看缓存的市场数据
ls -lh data/market_data/
cat data/market_data/openrouter_2026-08-30.json | jq .
```

---

## 🆕 AI 日报市场数据分析功能

AI 日报现已集成「📊 行业数据洞察」板块，自动采集和分析 AI 市场数据。

### 数据来源

| 数据源 | 内容 | 更新频率 | API 费用 |
|---|---|---|---|
| **OpenRouter API** | 396+ 个 AI 模型价格数据 | 实时 | 免费 |
| **Artificial Analysis** | 性能基准测试（智能、速度、成本） | 每周 | 免费（网页抓取） |
| **新闻指标提取**（可选） | 从新闻中提取营收、融资、用户数等 | 每日 | 需 OpenAI API Key |

### 展示内容

**📈 市场使用趋势**（OpenRouter）
- 总模型数：396+ 个
- 价格范围：$0.042 - $30.00 / 1M tokens
- 平均价格统计
- 热门模型 Top 3

**⚡ 性能基准**（Artificial Analysis）
- 智能排名 Top 5
- 速度排名 Top 3
- 成本排名 Top 3

**💡 官方公布数据**（可选，需 API Key）
- 从新闻中提取的营收/ARR
- 融资金额和轮次
- 用户增长数据
- 价格变化信息

**🔍 交叉验证**
- 多源数据印证
- 确认/待确认项统计

### 可选配置

新闻指标提取功能需要配置 OpenAI API Key（可选）：

```bash
# GitHub Actions Secrets（推荐）
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1  # 可选，默认官方 API

# 或本地测试
export OPENAI_API_KEY=sk-...
python ai_daily_push.py --no-push
```

**成本说明**：
- OpenRouter API：免费（公开数据）
- Artificial Analysis：免费（网页抓取）
- OpenAI API（可选）：
  - 使用 `gpt-4o-mini` 模型
  - 每次运行约 $0.001-0.005
  - 未配置时自动跳过，不影响其他数据

### 错误处理

所有市场数据采集失败均不影响主流程：

- OpenRouter 失败 → 使用缓存数据
- Artificial Analysis 失败 → 使用缓存数据
- OpenAI API 失败 → 跳过新闻指标提取
- 全部失败 → 市场数据板块为空，其他板块正常显示

### 缓存机制

- 数据按日期缓存到 `data/market_data/`
- 当日数据优先使用 API
- 历史数据自动降级到最近可用缓存
- 缓存文件示例：
  - `openrouter_2026-08-30.json`
  - `artificial_analysis_2026-08-30.json`

---

## 隐私说明

所有密钥仅存于 GitHub Secrets / 本地 `push_config.json`（不提交真实密钥），不写入公开仓库。

# AI 日报每日推送（企业微信 + GitHub Pages）

每天北京时间 08:00 自动拉取 AI HOT 日报，生成单文件 HTML 仪表盘，并通过**企业微信自建应用**把摘要推送到你的**个人微信**（免认证、免身份证、可显示全文）。

## 工作原理

- `ai_daily_push.py`：拉取 AI HOT 日报 → 生成 `ai_daily_dashboard.html` → 调用企业微信 `message/send` 推送 markdown 摘要。
- `.github/workflows/daily.yml`：GitHub Actions 定时（`cron 0 0 * * *` = 北京 08:00）+ 手动触发；同时把仪表盘部署到 GitHub Pages（固定链接，每天自动更新）。
- `push_config.json`：本地/备用配置（密钥建议用 GitHub Secrets，不要写进仓库）。

## 部署步骤（一次性）

1. 在 GitHub 新建一个**私有**仓库（如 `ai-daily-push`）。
2. 把本目录全部内容推上去（`git push`）。
3. 仓库 **Settings → Secrets and variables → Actions → New repository secret**，添加：
   - `WECOM_CORPID`：企业微信「我的企业 → 企业信息 → 企业 ID」
   - `WECOM_CORPSECRET`：自建应用详情里的 Secret
   - `WECOM_AGENTID`：自建应用的 AgentId
   - `WECOM_TOUSER`：填 `@all`（单人企业直接全员）
   - `DASHBOARD_URL`（可选）：Pages 部署后的链接，如 `https://<用户名>.github.io/<仓库名>/`，用于推送里附「查看完整仪表盘」
4. 仓库 **Settings → Pages → Source** 选 **GitHub Actions**。
5. **Actions** 标签页 → 选工作流 → **Run workflow** 手动跑一次测试。

## 验证

- 个人微信（已关注「微信插件」）应收到一条 markdown 格式的 AI 日报。
- 浏览器打开 Pages 链接，能看到当天仪表盘。

## 隐私说明

所有密钥仅存于 GitHub Secrets / 本地 `push_config.json`，不写入公开仓库，不提交任何身份证或实名信息。

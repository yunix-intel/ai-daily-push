# 快速配置监控告警 - 复用现有webhook

**目标**: 让监控告警功能立即可用，无需创建新的webhook

---

## 📋 操作步骤（2分钟）

### 方案：复用现有的 WECOM_WEBHOOK

由于告警频率很低（只在异常时触发），与日报推送使用同一个webhook完全可行。

### 步骤：

1. **打开GitHub仓库设置**
   ```
   https://github.com/yunix-intel/ai-daily-push/settings/secrets/actions
   ```

2. **添加新Secret**
   - 点击 "New repository secret"
   - Name: `ALERT_WECOM_WEBHOOK`
   - Value: **复制 `WECOM_WEBHOOK` 的值**（相同的webhook地址）

3. **完成**
   - 点击 "Add secret"
   - 监控告警功能立即生效

---

## ✅ 为什么复用webhook合理？

| 考虑因素 | 说明 |
|---------|------|
| **告警频率** | 很低，只在系统异常时触发（推送失败、延迟超过5分钟等） |
| **消息区分** | 告警消息有明显的标记（`[ALERT] ERROR/WARNING`） |
| **管理成本** | 无需维护多个webhook，配置简单 |
| **推送及时性** | 同一个群，不会遗漏告警消息 |

**正常情况下**：每天只收到2条日报推送（AI日报+财经日报）
**异常情况下**：额外收到1-2条告警消息

---

## 🧪 测试验证

配置完成后，测试告警功能：

```bash
# 本地测试
export ALERT_WECOM_WEBHOOK="你的webhook地址"
python -c "
from alerting import send_alert
send_alert('INFO', '测试告警', '监控系统配置成功！')
"
```

或者在GitHub Actions中手动触发monitor workflow：
1. 进入 Actions → Monitor Push Status
2. 点击 "Run workflow"
3. 检查企业微信群是否收到消息

---

## 📊 预期效果

配置后的推送情况：

**每日正常情况**（08:00-08:05）：
```
[企业微信群]
├─ 08:00 AI日报（图文卡片）
└─ 08:05 财经日报（Markdown）
```

**异常情况示例**：
```
[企业微信群]
├─ 08:00 AI日报（图文卡片）
├─ 08:05 财经日报（Markdown）
└─ 08:15 [ALERT] ERROR: GitHub Actions 推送延迟
         实际推送时间: 08:12
         预期推送时间: 08:00
         延迟: 12分钟
```

---

## 🔄 后续优化（可选）

如果未来告警频率确实过高（每天>5条），再考虑分离：
1. 创建独立的"系统告警"群
2. 添加新的webhook作为 `ALERT_WECOM_WEBHOOK`

但根据当前的告警规则，这种情况不太可能发生。

---

**结论**：复用现有webhook是最实用的方案 ✅

**下一步**：添加 `ALERT_WECOM_WEBHOOK` Secret（值与 `WECOM_WEBHOOK` 相同）

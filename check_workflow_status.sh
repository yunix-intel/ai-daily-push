#!/bin/bash
# 检查 GitHub Actions workflow 状态的脚本

echo "=== 方法 1: 检查 workflow 是否被禁用 ==="
echo "访问 GitHub Actions 页面查看："
echo "https://github.com/yunix-intel/ai-daily-push/actions"
echo ""
echo "如果看到以下任一情况，说明 cron 被禁用了："
echo "  - 黄色横幅提示：'This scheduled workflow is disabled'"
echo "  - workflow 名称旁边有灰色的 'Disabled' 标签"
echo "  - 需要点击 'Enable workflow' 按钮重新启用"
echo ""

echo "=== 方法 2: 使用 GitHub CLI 检查 ==="
gh workflow view "每日推送：AI 日报 + 财经日报（企业微信 + GitHub Pages）" --json state,name 2>&1 || echo "需要安装 gh CLI"
echo ""

echo "=== 方法 3: 查看最近的 schedule 事件 ==="
echo "检查最近 10 天内 schedule 触发的运行记录："
gh run list \
  --workflow "每日推送：AI 日报 + 财经日报（企业微信 + GitHub Pages）" \
  --limit 50 \
  --json event,createdAt,conclusion \
  --jq '.[] | select(.event == "schedule") | {date: (.createdAt | split("T")[0]), time: (.createdAt | split("T")[1] | split(".")[0]), conclusion}' \
  2>&1 | head -20

echo ""
echo "=== 判断标准 ==="
echo "🔴 被禁用的特征："
echo "  1. 网页上有明确的 'This scheduled workflow is disabled' 提示"
echo "  2. 连续多天没有 event='schedule' 的运行记录"
echo "  3. 最近一次 schedule 运行是失败的，之后就再无 schedule 记录"
echo ""
echo "🟡 高峰延迟的特征："
echo "  1. 每天都有 schedule 事件触发（即使延迟）"
echo "  2. 创建时间晚于 00:00 UTC，但每天都在触发"
echo "  3. 延迟时间不规律，但不会完全缺失某一天"
echo ""
echo "📊 当前情况分析："
echo "最近 3 次 schedule 运行："
gh run list \
  --workflow "每日推送：AI 日报 + 财经日报（企业微信 + GitHub Pages）" \
  --limit 50 \
  --json event,createdAt,conclusion \
  --jq '.[] | select(.event == "schedule") | "\(.createdAt) - \(.conclusion)"' \
  2>&1 | head -3


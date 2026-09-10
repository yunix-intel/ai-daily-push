#!/bin/bash
# 集成测试脚本 - 完整验证项目输出

set -euo pipefail
export PYTHONIOENCODING="utf-8"
export PYTHONUTF8="1"
export OPENAI_API_KEY="sk-REDACTED"
export OPENAI_BASE_URL="https://api.example.com/v1"

echo "============================================================"
echo "AI Daily Push - 集成测试"
echo "============================================================"
echo "测试时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "环境变量:"
echo "  OPENAI_API_KEY: ${OPENAI_API_KEY:0:20}..."
echo "  OPENAI_BASE_URL: $OPENAI_BASE_URL"
echo "============================================================"
echo

echo "[1/2] 测试财经日报（含 LLM 功能）..."
python finance_daily_push.py --no-push --hours 24

echo
echo "[2/2] 验证输出..."
python - <<'PY'
import json
import re
from pathlib import Path

html = Path("finance_dashboard.html").read_text(encoding="utf-8")
match = re.search(r"const DATA\s*=\s*({.*?});", html, re.DOTALL)
if not match:
    raise SystemExit("未找到 dashboard DATA")
data = json.loads(match.group(1))

print("=" * 60)
print("财经日报输出验证")
print("=" * 60)
print(f"日期: {data['meta']['date']}")
print(f"新闻总数: {data['meta']['total']}")
print(f"行情数据: {len(data['quotes'])} 个指数")
print()

analysis = data["domestic"]["analysis"]
strategy = data["strategy"]
summary_len = len(analysis["summary"])
a_share_len = len(strategy["aShare"])
hk_share_len = len(strategy["hkShare"])
print("LLM 生成内容:")
print(f"  市场总结: {summary_len} 字")
print(f"  A股策略: {a_share_len} 字")
print(f"  港股策略: {hk_share_len} 字")
print()
print("=" * 60)
if summary_len > 100 and a_share_len > 50 and hk_share_len > 50:
    print("测试通过: LLM 功能正常")
else:
    print("测试阻断: LLM 功能未生成完整内容")
    print("该次运行使用了 LLM 降级结果，不能作为 LLM PASS 证据")
    print("集成门禁返回非零；日报主流程仍已完成并写出降级产物")
    print("=" * 60)
    raise SystemExit(2)
print("=" * 60)
PY

echo
echo "测试完成"

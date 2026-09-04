#!/bin/bash
# 集成测试脚本 - 完整验证项目输出

export OPENAI_API_KEY="sk-W3WD48qw6NatwMTVg3nEXGGMZEWWHVdSy50ApetdL042v5YK"
export OPENAI_BASE_URL="https://aiapi.hk.oliga.top/v1"

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
python -c "
import re, json

with open('finance_dashboard.html', 'r', encoding='utf-8') as f:
    html = f.read()

match = re.search(r'const DATA\s*=\s*({.*?});', html, re.DOTALL)
data = json.loads(match.group(1))

print('='*60)
print('财经日报输出验证')
print('='*60)
print(f'日期: {data[\"meta\"][\"date\"]}')
print(f'新闻总数: {data[\"meta\"][\"total\"]}')
print(f'行情数据: {len(data[\"quotes\"])} 个指数')
print()

analysis = data['domestic']['analysis']
strategy = data['strategy']

print('LLM 生成内容:')
summary_len = len(analysis['summary'])
if summary_len > 100:
    print(f'  ✓ 市场总结: {summary_len} 字')
else:
    print(f'  ✗ 市场总结: {summary_len} 字 (疑似失败)')
    print(f'    内容: {analysis[\"summary\"]}')

aShare_len = len(strategy['aShare'])
if aShare_len > 50:
    print(f'  ✓ A股策略: {aShare_len} 字')
else:
    print(f'  ✗ A股策略: {aShare_len} 字 (未生成)')

hkShare_len = len(strategy['hkShare'])
if hkShare_len > 50:
    print(f'  ✓ 港股策略: {hkShare_len} 字')
else:
    print(f'  ✗ 港股策略: {hkShare_len} 字 (未生成)')

print()
print('='*60)
if summary_len > 100 and aShare_len > 50:
    print('测试通过: LLM 功能正常')
else:
    print('测试失败: LLM 功能未生成完整内容')
print('='*60)
"

echo
echo "测试完成"

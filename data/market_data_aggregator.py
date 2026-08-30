#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
市场数据整合器 - 合并多个数据源并生成统一的分析结果
"""
import json
import re
from datetime import datetime
from pathlib import Path


def extract_news_metrics(news_sections):
    """
    从新闻条目中提取数值指标

    Args:
        news_sections: AI 日报的 sections 数据结构

    Returns:
        提取的关键指标列表
    """
    metrics = {
        "arr_revenue": [],      # ARR/营收数据
        "funding": [],          # 融资数据
        "users": [],            # 用户数/活跃度
        "tokens": [],           # Token 调用量
        "price_changes": []     # 价格变化
    }

    # 遍历所有新闻条目
    for section in news_sections:
        for item in section.get('items', []):
            title = item.get('title', '')
            summary = item.get('summary', '')
            text = f"{title} {summary}".lower()

            # 提取 ARR/营收
            arr_match = re.search(r'arr.*?(\d+(?:\.\d+)?)\s*(?:亿|亿美元|billion)', text, re.IGNORECASE)
            if arr_match:
                metrics['arr_revenue'].append({
                    'value': arr_match.group(1),
                    'unit': 'billion USD' if 'billion' in text else '亿美元',
                    'source': item.get('source', {}).get('name', ''),
                    'title': title
                })

            # 提取融资
            funding_match = re.search(r'融资.*?(\d+(?:\.\d+)?)\s*(?:亿美元|亿|million|billion)', text)
            if funding_match:
                metrics['funding'].append({
                    'value': funding_match.group(1),
                    'context': title,
                    'source': item.get('source', {}).get('name', '')
                })

            # 提取用户数
            user_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:亿|万|million|billion).*?(?:用户|活跃|日活|月活)', text)
            if user_match:
                metrics['users'].append({
                    'value': user_match.group(0),
                    'title': title,
                    'source': item.get('source', {}).get('name', '')
                })

            # 提取 Token 相关
            token_match = re.search(r'token.*?(\d+(?:\.\d+)?)\s*(?:%|倍|T|trillion)', text, re.IGNORECASE)
            if token_match:
                metrics['tokens'].append({
                    'value': token_match.group(0),
                    'title': title
                })

            # 提取价格变化
            price_match = re.search(r'(?:降价|下调|price.*?(?:cut|drop|reduce)).*?(\d+)%', text, re.IGNORECASE)
            if price_match:
                metrics['price_changes'].append({
                    'change': f"-{price_match.group(1)}%",
                    'title': title,
                    'source': item.get('source', {}).get('name', '')
                })

    return metrics


def cross_validate(news_metrics, openrouter_data, aa_data):
    """
    交叉验证数据

    找出在多个数据源中都能印证的信息
    """
    validated = []

    # 验证价格变化
    news_prices = news_metrics.get('price_changes', [])
    if news_prices and openrouter_data.get('top_models'):
        for price_change in news_prices:
            # 简化：如果新闻中提到价格变化，标记为"待验证"
            validated.append({
                'type': 'price_change',
                'text': price_change['title'],
                'sources': ['news'],
                'verified': False  # 实际验证需要对比 OpenRouter 历史价格
            })

    return validated


def aggregate_market_data(news_sections, openrouter_data=None, aa_data=None):
    """
    整合所有市场数据源

    Args:
        news_sections: AI 日报新闻板块
        openrouter_data: OpenRouter 爬虫数据（可选）
        aa_data: Artificial Analysis 数据（可选）

    Returns:
        整合后的市场洞察数据
    """
    print("  整合市场数据...")

    # 从新闻中提取指标
    news_metrics = extract_news_metrics(news_sections)

    # 构建洞察数据
    insights = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "highlights": {
            "official_announcements": [],
            "market_usage": [],
            "performance_benchmarks": [],
            "cross_validated": []
        },
        "raw_data": {
            "news_metrics": news_metrics,
            "openrouter": openrouter_data,
            "artificial_analysis": aa_data
        }
    }

    # 处理新闻中的官方公告
    for arr in news_metrics.get('arr_revenue', [])[:3]:
        insights['highlights']['official_announcements'].append({
            'text': f"{arr['title'][:50]}... - {arr['value']} {arr['unit']}",
            'source': arr['source'],
            'type': 'revenue'
        })

    for funding in news_metrics.get('funding', [])[:3]:
        insights['highlights']['official_announcements'].append({
            'text': funding['context'],
            'source': funding['source'],
            'type': 'funding'
        })

    for user_data in news_metrics.get('users', [])[:3]:
        insights['highlights']['official_announcements'].append({
            'text': f"{user_data['title'][:60]}...",
            'source': user_data['source'],
            'type': 'users'
        })

    # 处理 OpenRouter 数据
    if openrouter_data and openrouter_data.get('top_models'):
        for model in openrouter_data['top_models'][:5]:
            text = f"{model.get('name', 'Unknown')} "
            if model.get('tokens'):
                text += f"- {model['tokens']} tokens"
            if model.get('market_share'):
                text += f" (份额 {model['market_share']}%)"

            insights['highlights']['market_usage'].append({
                'text': text,
                'rank': model.get('rank'),
                'source': 'OpenRouter'
            })

    # 处理 AA 数据
    if aa_data:
        for intel in aa_data.get('intelligence', [])[:3]:
            insights['highlights']['performance_benchmarks'].append({
                'text': f"{intel.get('model')} - 智能指数 {intel.get('score')}",
                'type': 'intelligence',
                'source': 'Artificial Analysis'
            })

    # 交叉验证
    if openrouter_data and aa_data:
        validated = cross_validate(news_metrics, openrouter_data, aa_data)
        insights['highlights']['cross_validated'] = validated

    # 统计
    total_highlights = sum(len(v) for v in insights['highlights'].values() if isinstance(v, list))
    print(f"     [OK] 提取 {total_highlights} 条关键洞察")

    return insights


def save_market_data(data, output_dir="data/market_data"):
    """保存市场数据快照"""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    today = datetime.now().strftime("%Y-%m-%d")
    file_path = output_path / f"aggregated_{today}.json"

    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"     [OK] 市场数据已保存：{file_path.name}")
    return file_path


if __name__ == "__main__":
    # 测试
    mock_sections = [
        {
            "label": "📊 行业趋势",
            "items": [
                {
                    "title": "Anthropic ARR 突破 10 亿美元",
                    "summary": "根据 The Information 报道，Anthropic 的年度经常性收入已达到 10 亿美元。",
                    "source": {"name": "TechCrunch"}
                }
            ]
        }
    ]

    result = aggregate_market_data(mock_sections)
    print(json.dumps(result, indent=2, ensure_ascii=False))

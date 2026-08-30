# -*- coding: utf-8 -*-
"""
新闻智能分类模块
使用 LLM 进行国内/国际分类、重要性评分、突发事件识别
"""
import json
import re
from typing import List, Dict, Literal, Optional


def classify_news_region_batch(items: List[Dict], llm_call_func) -> List[str]:
    """
    批量判断新闻涉及的地区（国内/国际）

    Args:
        items: 新闻列表，每个包含 title, summary
        llm_call_func: LLM 调用函数，签名为 (system_prompt, user_prompt, model=None)

    Returns:
        分类结果列表 ['domestic', 'international', ...]
    """
    if not items:
        return []

    # 构建批量分类提示
    news_list = []
    for i, item in enumerate(items, 1):
        title = item.get('title', '')
        summary = item.get('summary', '')
        news_list.append(f"{i}. {title}\n   {summary[:100]}")

    system_prompt = "你是财经新闻分类专家。只返回 JSON 数组，不要其他文字。"

    user_prompt = f"""判断以下财经新闻主要涉及的市场区域。

分类标准：
- domestic: 中国大陆、A股、港股、人民币、中国企业相关
- international: 美股、欧洲、日本、其他海外市场、外国企业相关

新闻列表：
{chr(10).join(news_list)}

返回 JSON 数组，每个元素为 "domestic" 或 "international"，顺序对应新闻编号：
["domestic", "international", "domestic", ...]
"""

    try:
        result = llm_call_func(system_prompt, user_prompt, model='gpt-4o-mini')
        # 解析 JSON
        if isinstance(result, str):
            # 提取 JSON 数组
            match = re.search(r'\[.*?\]', result, re.DOTALL)
            if match:
                classifications = json.loads(match.group(0))
            else:
                raise ValueError("无法提取 JSON 数组")
        else:
            classifications = result

        # 验证结果
        if len(classifications) != len(items):
            raise ValueError(f"分类结果数量不匹配：{len(classifications)} vs {len(items)}")

        return classifications

    except Exception as e:
        print(f"     [!] LLM 批量分类失败，使用关键词回退：{e}")
        # 回退到关键词分类
        return [classify_by_keywords(item) for item in items]


def classify_by_keywords(item: Dict) -> Literal['domestic', 'international']:
    """关键词分类（回退方案）"""
    text = f"{item.get('title', '')} {item.get('summary', '')}".lower()

    domestic_keywords = [
        'a股', '沪深', '上证', '深证', '港股', '恒生', '人民币', '央行',
        '中国', '国内', '北京', '上海', '深圳', '香港', '内地'
    ]

    international_keywords = [
        '美股', '纳指', '标普', '道琼斯', '美联储', '美元', '欧洲', '日本',
        'nasdaq', 'dow', 's&p', 'fed', 'wall street'
    ]

    domestic_score = sum(1 for kw in domestic_keywords if kw in text)
    international_score = sum(1 for kw in international_keywords if kw in text)

    if domestic_score > international_score:
        return 'domestic'
    elif international_score > domestic_score:
        return 'international'
    else:
        # 默认根据来源判断
        source = item.get('source', '')
        # source 可能是字符串或字典
        if isinstance(source, dict):
            source_name = source.get('name', '').lower()
        else:
            source_name = str(source).lower()

        if any(s in source_name for s in ['新浪', '东方财富', '证券', '财联社', '格隆汇']):
            return 'domestic'
        else:
            return 'international'


def score_news_importance_batch(items: List[Dict], llm_call_func, market_context: str = "") -> List[int]:
    """
    批量评估新闻重要性（0-10分）

    Args:
        items: 新闻列表
        llm_call_func: LLM 调用函数，签名为 (system_prompt, user_prompt, model=None)
        market_context: 当前市场背景

    Returns:
        重要性分数列表 [8, 5, 9, ...]
    """
    if not items:
        return []

    # 构建批量评分提示
    news_list = []
    for i, item in enumerate(items, 1):
        title = item.get('title', '')
        summary = item.get('summary', '')
        source = item.get('source', '')
        # source 可能是字符串或字典
        if isinstance(source, dict):
            source_name = source.get('name', '')
        else:
            source_name = str(source)
        news_list.append(f"{i}. [{source_name}] {title}\n   {summary[:150]}")

    system_prompt = "你是财经新闻分析专家。只返回 JSON 数组，不要其他文字。"

    user_prompt = f"""评估以下财经新闻的重要性（0-10分）。

评分标准：
- 10分：重大政策发布、重要经济数据、市场剧烈波动
- 7-9分：行业重要动态、龙头公司重大事件、监管政策
- 4-6分：一般性新闻、常规数据发布、行业动态
- 0-3分：次要信息、重复报道、企业常规公告

当前市场背景：{market_context or '正常交易环境'}

新闻列表：
{chr(10).join(news_list)}

返回 JSON 数组，每个元素为 0-10 的整数，顺序对应新闻编号：
[8, 5, 9, 6, ...]
"""

    try:
        result = llm_call_func(system_prompt, user_prompt, model='gpt-4o-mini')

        # 解析 JSON
        if isinstance(result, str):
            match = re.search(r'\[.*?\]', result, re.DOTALL)
            if match:
                scores = json.loads(match.group(0))
            else:
                raise ValueError("无法提取 JSON 数组")
        else:
            scores = result

        # 验证和修正结果
        if len(scores) != len(items):
            raise ValueError(f"评分结果数量不匹配：{len(scores)} vs {len(items)}")

        # 确保分数在 0-10 范围内
        scores = [max(0, min(10, int(s))) for s in scores]

        return scores

    except Exception as e:
        print(f"     [!] LLM 批量评分失败，使用默认分数：{e}")
        # 回退：所有新闻默认 5 分
        return [5] * len(items)


def identify_breaking_news(items: List[Dict], llm_call_func, time_threshold_hours: int = 24) -> List[Dict]:
    """
    识别突发事件

    Args:
        items: 新闻列表
        llm_call_func: LLM 调用函数，签名为 (system_prompt, user_prompt, model=None)
        time_threshold_hours: 时间阈值（小时）

    Returns:
        突发事件列表，每个包含 title, desc, impact, direction, sectors
    """
    # 第一步：关键词筛选候选
    urgent_keywords = [
        '突发', '紧急', '重磅', '爆发', '暴跌', '暴涨',
        '停牌', '调查', '事故', '危机', '崩盘', '熔断',
        '破产', '违约', '制裁', '战争'
    ]

    candidates = []
    for item in items:
        text = f"{item.get('title', '')} {item.get('summary', '')}".lower()
        if any(kw in text for kw in urgent_keywords):
            candidates.append(item)

    if not candidates:
        return []

    # 第二步：LLM 判断重要性和影响
    news_list = []
    for i, item in enumerate(candidates, 1):
        title = item.get('title', '')
        summary = item.get('summary', '')
        news_list.append(f"{i}. {title}\n   {summary[:200]}")

    system_prompt = "你是突发事件分析专家。只返回 JSON 数组，不要其他文字。"

    user_prompt = f"""分析以下候选突发事件，判断是否为真正的突发重大事件（影响市场的紧急新闻）。

新闻列表：
{chr(10).join(news_list)}

对每条新闻返回：
{{
  "is_breaking": true/false,  // 是否为突发事件
  "importance": 0-10,  // 重要性评分
  "impact_direction": "利空" | "利好" | "中性",  // 影响方向
  "impact_level": "重大" | "一般" | "轻微",  // 影响程度
  "affected_sectors": ["板块1", "板块2"],  // 影响的板块
  "brief_analysis": "简要分析（50字以内）"  // 市场影响分析
}}

返回 JSON 数组：
[{{"is_breaking": true, ...}}, {{"is_breaking": false, ...}}, ...]
"""

    try:
        result = llm_call_func(system_prompt, user_prompt, model='gpt-4o-mini')

        # 解析 JSON
        if isinstance(result, str):
            match = re.search(r'\[.*?\]', result, re.DOTALL)
            if match:
                analyses = json.loads(match.group(0))
            else:
                raise ValueError("无法提取 JSON 数组")
        else:
            analyses = result

        # 筛选真正的突发事件
        breaking_events = []
        for i, analysis in enumerate(analyses):
            if i >= len(candidates):
                break

            if analysis.get('is_breaking') and analysis.get('importance', 0) >= 7:
                event = {
                    'title': candidates[i].get('title', ''),
                    'desc': candidates[i].get('summary', '')[:100],
                    'impact': analysis.get('brief_analysis', ''),
                    'direction': analysis.get('impact_direction', '中性'),
                    'level': analysis.get('impact_level', '一般'),
                    'sectors': analysis.get('affected_sectors', []),
                    'original_item': candidates[i]
                }
                breaking_events.append(event)

        return breaking_events

    except Exception as e:
        print(f"     [!] 突发事件识别失败：{e}")
        # 回退：返回前3个候选
        return [{
            'title': item.get('title', ''),
            'desc': item.get('summary', '')[:100],
            'impact': '需进一步关注',
            'direction': '待确认',
            'level': '一般',
            'sectors': [],
            'original_item': item
        } for item in candidates[:3]]


if __name__ == '__main__':
    # 测试代码
    print("新闻分类模块测试")
    print("=" * 60)

    # 模拟 LLM 调用
    def mock_llm(system, user, model='deepseek-v4-flash'):
        if "市场区域" in user:
            return '["domestic", "international", "domestic"]'
        elif "重要性" in user:
            return '[8, 5, 9]'
        elif "突发事件" in user:
            return '[{"is_breaking": true, "importance": 8, "impact_direction": "利空", "impact_level": "重大", "affected_sectors": ["科技"], "brief_analysis": "市场承压"}]'
        return ""

    # 测试数据
    test_items = [
        {'title': 'A股大涨3%', 'summary': '上证指数大涨', 'source': {'name': '新浪财经'}},
        {'title': 'Fed raises rates', 'summary': 'Federal Reserve hikes', 'source': {'name': 'Bloomberg'}},
        {'title': '突发：某公司暴雷', 'summary': '重大违约事件', 'source': {'name': '财联社'}},
    ]

    # 测试分类
    print("\n测试 1: 区域分类")
    regions = classify_news_region_batch(test_items, mock_llm)
    print(f"结果: {regions}")

    # 测试评分
    print("\n测试 2: 重要性评分")
    scores = score_news_importance_batch(test_items, mock_llm)
    print(f"结果: {scores}")

    # 测试突发事件
    print("\n测试 3: 突发事件识别")
    breaking = identify_breaking_news(test_items, mock_llm)
    print(f"结果: {len(breaking)} 个突发事件")

    print("\n=" * 60)
    print("新闻分类模块测试完成")

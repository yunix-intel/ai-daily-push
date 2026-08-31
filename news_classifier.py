# -*- coding: utf-8 -*-
"""
新闻智能分类模块
使用 LLM 进行国内/国际分类、重要性评分、突发事件识别
"""
import json
import os
import re
from typing import List, Dict, Literal, Optional

# 分类/评分是「机械打标」任务，不是推理任务：条目多、单条判断简单。
# 用快模型（翻译模型）而不是推理模型——推理模型处理上百条要跑好几分钟，
# 网关等不到上游响应就返回 503，整条链路静默回退到关键词兜底
# （国内要闻混进美国新闻、重要新闻不排序）。
# 也不能硬编码模型名：自建网关只挂了自己那几个模型，写死 gpt-4o-mini 必然 503。
CLASSIFY_MODEL_DEFAULT = "deepseek-v4-flash"

# 单次请求最多塞多少条。一次性把 100 条丢给模型会超时，
# 分批还能做到「单批失败只丢这一批」而不是整体回退。
CLASSIFY_BATCH_SIZE = 20


def _classify_model():
    """分类/评分使用的模型：优先专用变量，其次翻译模型（快、便宜）。"""
    return (os.environ.get("OPENAI_MODEL_CLASSIFY")
            or os.environ.get("OPENAI_MODEL_TRANSLATE")
            or CLASSIFY_MODEL_DEFAULT).strip()


def _extract_json_array(result):
    """从 LLM 返回值里取出 JSON 数组。

    调用方可能拿到三种形态：已解析好的 list、裸数组字符串、
    或被 response_format=json_object 包了一层的 {"result": [...]}。
    贪婪匹配是必须的——突发事件那种「数组里套数组」的结构，
    非贪婪会只截到最内层的 affected_sectors。
    """
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        for value in result.values():
            if isinstance(value, list):
                return value
        raise ValueError("返回的 JSON 对象里没有数组字段")
    match = re.search(r'\[.*\]', str(result), re.DOTALL)
    if not match:
        raise ValueError("无法提取 JSON 数组")
    return json.loads(match.group(0))


def _chunked(items, size):
    for start in range(0, len(items), size):
        yield start, items[start:start + size]


def classify_news_region_batch(items: List[Dict], llm_call_func) -> List[str]:
    """
    批量判断新闻涉及的地区（国内/国际）

    分批送模型，单批失败只让该批回退到关键词，不拖垮整体分类。

    Args:
        items: 新闻列表，每个包含 title, summary
        llm_call_func: LLM 调用函数，签名为 (system_prompt, user_prompt, model=None)

    Returns:
        分类结果列表 ['domestic', 'international', ...]
    """
    if not items:
        return []

    results: List[str] = []
    failed_batches = 0
    for _, chunk in _chunked(items, CLASSIFY_BATCH_SIZE):
        try:
            results.extend(_classify_region_chunk(chunk, llm_call_func))
        except Exception as exc:
            failed_batches += 1
            print(f"     [!] 区域分类单批失败（{len(chunk)} 条），该批走关键词回退：{exc}")
            results.extend(classify_by_keywords(item) for item in chunk)

    if failed_batches:
        print(f"     [!] 区域分类共 {failed_batches} 批回退")
    return results


def _classify_region_chunk(items: List[Dict], llm_call_func) -> List[str]:
    """对一批（<= CLASSIFY_BATCH_SIZE 条）新闻做区域分类。失败抛异常交给调用方回退。"""
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

共 {len(items)} 条，必须返回长度为 {len(items)} 的 JSON 数组，
每个元素为 "domestic" 或 "international"，顺序对应新闻编号：
["domestic", "international", "domestic", ...]
"""

    classifications = _extract_json_array(
        llm_call_func(system_prompt, user_prompt, model=_classify_model())
    )

    if len(classifications) != len(items):
        raise ValueError(f"分类结果数量不匹配：{len(classifications)} vs {len(items)}")

    # 规范化：模型偶尔会返回 "Domestic"/"中国" 之类
    normalized = []
    for value in classifications:
        text = str(value).strip().lower()
        normalized.append('domestic' if text.startswith('dom') or '国内' in text or '中国' in text
                          else 'international')
    return normalized


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

    分批送模型，单批失败只让该批拿默认分，不会让全部新闻退化成同一分数
    （那会让「最重要 5-10 条」排序完全失效）。

    Args:
        items: 新闻列表
        llm_call_func: LLM 调用函数，签名为 (system_prompt, user_prompt, model=None)
        market_context: 当前市场背景

    Returns:
        重要性分数列表 [8, 5, 9, ...]
    """
    if not items:
        return []

    scores: List[int] = []
    failed_batches = 0
    for _, chunk in _chunked(items, CLASSIFY_BATCH_SIZE):
        try:
            scores.extend(_score_importance_chunk(chunk, llm_call_func, market_context))
        except Exception as exc:
            failed_batches += 1
            print(f"     [!] 重要性评分单批失败（{len(chunk)} 条），该批用默认分：{exc}")
            scores.extend([5] * len(chunk))

    if failed_batches:
        print(f"     [!] 重要性评分共 {failed_batches} 批回退")
    return scores


def _score_importance_chunk(items: List[Dict], llm_call_func, market_context: str = "") -> List[int]:
    """对一批新闻评分。失败抛异常交给调用方回退。"""
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

共 {len(items)} 条，必须返回长度为 {len(items)} 的 JSON 数组，
每个元素为 0-10 的整数，顺序对应新闻编号：
[8, 5, 9, 6, ...]
"""

    scores = _extract_json_array(
        llm_call_func(system_prompt, user_prompt, model=_classify_model())
    )

    if len(scores) != len(items):
        raise ValueError(f"评分结果数量不匹配：{len(scores)} vs {len(items)}")

    # 确保分数在 0-10 范围内
    return [max(0, min(10, int(s))) for s in scores]


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

    # 第二步：LLM 判断重要性和影响（分批，避免一次性请求过大超时）
    breaking_events = []
    for _, chunk in _chunked(candidates, CLASSIFY_BATCH_SIZE):
        try:
            breaking_events.extend(_analyze_breaking_chunk(chunk, llm_call_func))
        except Exception as exc:
            print(f"     [!] 突发事件识别单批失败（{len(chunk)} 条）：{exc}")
            # 回退：该批取前 2 条当待确认事件
            breaking_events.extend({
                'title': item.get('title', ''),
                'desc': item.get('summary', '')[:100],
                'impact': '需进一步关注',
                'direction': '待确认',
                'level': '一般',
                'sectors': [],
                'original_item': item
            } for item in chunk[:2])

    return breaking_events


def _analyze_breaking_chunk(candidates: List[Dict], llm_call_func) -> List[Dict]:
    """分析一批候选突发事件。失败抛异常交给调用方回退。"""
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

共 {len(candidates)} 条，返回长度为 {len(candidates)} 的 JSON 数组：
[{{"is_breaking": true, ...}}, {{"is_breaking": false, ...}}, ...]
"""

    analyses = _extract_json_array(
        llm_call_func(system_prompt, user_prompt, model=_classify_model())
    )

    # 筛选真正的突发事件
    breaking_events = []
    for i, analysis in enumerate(analyses):
        if i >= len(candidates):
            break
        if not isinstance(analysis, dict):
            continue

        if analysis.get('is_breaking') and analysis.get('importance', 0) >= 7:
            breaking_events.append({
                'title': candidates[i].get('title', ''),
                'desc': candidates[i].get('summary', '')[:100],
                'impact': analysis.get('brief_analysis', ''),
                'direction': analysis.get('impact_direction', '中性'),
                'level': analysis.get('impact_level', '一般'),
                'sectors': analysis.get('affected_sectors', []),
                'original_item': candidates[i]
            })

    return breaking_events


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

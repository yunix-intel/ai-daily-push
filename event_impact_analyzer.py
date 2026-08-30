#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
突发事件影响分析模块
"""
import json


class EventImpactAnalyzer:
    """突发事件影响分析器"""

    def __init__(self, llm_caller=None):
        """
        初始化分析器

        Args:
            llm_caller: LLM 调用函数 (system_prompt, user_prompt, model) -> dict
        """
        self.llm_caller = llm_caller

    def analyze_event_impact(self, event):
        """
        分析单个突发事件的市场影响

        Args:
            event: 突发事件 dict，包含 title, summary

        Returns:
            dict: 影响分析结果
        """
        if not self.llm_caller:
            return self._empty_impact()

        system_prompt = """你是专业的市场分析师，擅长分析突发事件对股市的影响。"""

        user_prompt = f"""请分析以下突发事件的市场影响：

【事件标题】
{event.get('title', '')}

【事件摘要】
{event.get('summary', '')}

请分析并返回 JSON 格式：
{{
  "impact_level": "重大/中等/轻微",
  "impact_direction": "利好/利空/中性",
  "beneficiary_sectors": ["受益行业1", "受益行业2", "受益行业3"],
  "damaged_sectors": ["受损行业1", "受损行业2", "受损行业3"],
  "duration": "短期/中期/长期",
  "operation_advice": "操作建议（50-100字）",
  "risk_warning": "风险提示（30-60字）"
}}

说明：
- impact_level: 重大（影响指数级别）、中等（影响板块级别）、轻微（影响个股级别）
- impact_direction: 利好（推动上涨）、利空（推动下跌）、中性（方向不明）
- beneficiary_sectors: 最多3个，优先填写直接受益的行业
- damaged_sectors: 最多3个，优先填写直接受损的行业
- duration: 短期（1-3天）、中期（1-4周）、长期（1个月以上）
- operation_advice: 具体的操作建议，如"关注XX板块""规避XX行业""持币观望"等
- risk_warning: 简洁的风险提示

只返回 JSON，不要添加其他内容。"""

        try:
            result = self.llm_caller(system_prompt, user_prompt)

            # 验证必需字段
            required_fields = ["impact_level", "impact_direction", "operation_advice"]
            if all(field in result for field in required_fields):
                return result
            else:
                print(f"     [WARN] 影响分析结果缺少必需字段")
                return self._empty_impact()

        except Exception as e:
            print(f"     [WARN] 事件影响分析失败: {e}")
            return self._empty_impact()

    def analyze_events_batch(self, events):
        """
        批量分析突发事件影响

        Args:
            events: 突发事件列表

        Returns:
            list: 带有影响分析的事件列表
        """
        if not events:
            return []

        print(f"     分析 {len(events)} 个突发事件的影响...")

        analyzed_events = []
        for i, event in enumerate(events):
            print(f"     [{i+1}/{len(events)}] 分析: {event.get('title', '')[:40]}...")

            impact = self.analyze_event_impact(event)

            # 将影响分析添加到事件对象
            event_with_impact = event.copy()
            event_with_impact['impact'] = impact

            analyzed_events.append(event_with_impact)

        return analyzed_events

    def _empty_impact(self):
        """返回空的影响分析结果"""
        return {
            "impact_level": "未知",
            "impact_direction": "中性",
            "beneficiary_sectors": [],
            "damaged_sectors": [],
            "duration": "未知",
            "operation_advice": "",
            "risk_warning": ""
        }

    def merge_impacts_for_strategy(self, analyzed_events):
        """
        合并多个事件的影响，生成策略建议的补充内容

        Args:
            analyzed_events: 带有影响分析的事件列表

        Returns:
            dict: 合并后的影响信息
        """
        if not analyzed_events:
            return None

        # 筛选重大和中等影响的事件
        major_events = [
            e for e in analyzed_events
            if e.get('impact', {}).get('impact_level') in ['重大', '中等']
        ]

        if not major_events:
            return None

        # 收集受益和受损行业
        beneficiary_sectors = []
        damaged_sectors = []
        operation_advices = []
        risk_warnings = []

        for event in major_events:
            impact = event.get('impact', {})

            beneficiary_sectors.extend(impact.get('beneficiary_sectors', []))
            damaged_sectors.extend(impact.get('damaged_sectors', []))

            if impact.get('operation_advice'):
                operation_advices.append(impact['operation_advice'])

            if impact.get('risk_warning'):
                risk_warnings.append(impact['risk_warning'])

        # 去重
        beneficiary_sectors = list(set(beneficiary_sectors))[:5]
        damaged_sectors = list(set(damaged_sectors))[:5]

        return {
            "major_events_count": len(major_events),
            "beneficiary_sectors": beneficiary_sectors,
            "damaged_sectors": damaged_sectors,
            "operation_advices": operation_advices,
            "risk_warnings": risk_warnings
        }


# 测试函数
if __name__ == "__main__":
    # 模拟 LLM 调用
    def mock_llm(system_prompt, user_prompt, model=None):
        return {
            "impact_level": "重大",
            "impact_direction": "利好",
            "beneficiary_sectors": ["芯片", "半导体", "科技"],
            "damaged_sectors": [],
            "duration": "长期",
            "operation_advice": "关注国产芯片替代概念股，中长期布局半导体产业链龙头。",
            "risk_warning": "短期可能存在炒作风险，注意仓位控制。"
        }

    analyzer = EventImpactAnalyzer(llm_caller=mock_llm)

    # 测试事件
    test_event = {
        "title": "美国宣布对华芯片出口新限制",
        "summary": "美国商务部宣布对向中国出口先进芯片实施新的限制措施..."
    }

    print("测试突发事件影响分析...")
    impact = analyzer.analyze_event_impact(test_event)
    print(json.dumps(impact, ensure_ascii=False, indent=2))

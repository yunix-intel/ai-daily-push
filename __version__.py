#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Daily Push 版本信息
"""

__version__ = "3.1.1"
__version_info__ = (3, 1, 1)

# 版本历史
VERSION_HISTORY = {
    "3.1.1": "测试修复版本：修复所有测试参数类型错误，达成100%通过率（31/31测试）",
    "3.1.0": "内容质量版本：核心必读排序、假期要闻回顾、资金流向、全文翻译、LLM 分批容错",
    "3.0.1": "修复版本：monitoring/logger 语法错误、finance_daily_push datetime 作用域",
    "3.0.0": "企业级改进版本：监控系统、并发优化、配置验证、告警通知、GitHub推送监测",
    "2.0.0": "增强版：交易日历、市场数据、新闻指标提取、微信公众号发布",
    "1.0.0": "初始版本：基础 AI 日报和财经日报推送功能"
}

def get_version():
    """获取版本号"""
    return __version__

def get_version_info():
    """获取版本信息"""
    return {
        "version": __version__,
        "version_info": __version_info__,
        "description": VERSION_HISTORY.get(__version__, "")
    }

if __name__ == "__main__":
    print(f"AI Daily Push v{__version__}")
    print(f"版本说明: {VERSION_HISTORY.get(__version__, '')}")

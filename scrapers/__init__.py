"""
AI 日报市场数据爬虫模块
"""
from .openrouter_scraper import fetch_openrouter_data
from .artificial_analysis_scraper import fetch_aa_data

__all__ = ['fetch_openrouter_data', 'fetch_aa_data']

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基础爬虫类 - 提供通用的爬虫功能
"""
import time
import json
import re
from datetime import datetime, timedelta
from pathlib import Path


class BaseScraper:
    """基础爬虫类"""

    def __init__(self, cache_dir="data/market_data", timeout=30):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )

    def get_cache_path(self, source_name):
        """获取缓存文件路径"""
        today = datetime.now().strftime("%Y-%m-%d")
        return self.cache_dir / f"{source_name}_{today}.json"

    def load_cache(self, source_name):
        """加载缓存数据"""
        cache_path = self.get_cache_path(source_name)
        if cache_path.exists():
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                print(f"     [OK] 使用缓存：{cache_path.name}")
                return data
            except Exception as e:
                print(f"     [WARN] 缓存读取失败：{e}")
        return None

    def save_cache(self, source_name, data):
        """保存缓存数据"""
        cache_path = self.get_cache_path(source_name)
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"     [OK] 缓存已保存：{cache_path.name}")
        except Exception as e:
            print(f"     [WARN] 缓存保存失败：{e}")

    def cleanup_old_cache(self, days=30):
        """
        清理超过指定天数的缓存文件

        Args:
            days: 保留天数，默认 30 天
        """
        if not self.cache_dir.exists():
            return

        cutoff = datetime.now() - timedelta(days=days)
        deleted_count = 0

        try:
            for cache_file in self.cache_dir.glob("*.json"):
                # 从文件名提取日期 (格式: source_YYYY-MM-DD.json)
                match = re.search(r'(\d{4}-\d{2}-\d{2})', cache_file.name)
                if match:
                    try:
                        file_date = datetime.strptime(match.group(1), '%Y-%m-%d')
                        if file_date < cutoff:
                            cache_file.unlink()
                            deleted_count += 1
                            print(f"     [OK] 删除过期缓存：{cache_file.name}")
                    except Exception as e:
                        print(f"     [WARN] 删除缓存失败 {cache_file.name}：{e}")

            if deleted_count > 0:
                print(f"     [OK] 共清理 {deleted_count} 个过期缓存文件")
            else:
                print(f"     [OK] 无需清理缓存（保留 {days} 天内数据）")

        except Exception as e:
            print(f"     [WARN] 缓存清理失败：{e}")

    def fetch_with_retry(self, fetch_func, retries=2):
        """带重试的数据获取"""
        for attempt in range(retries):
            try:
                return fetch_func()
            except Exception as e:
                if attempt < retries - 1:
                    print(f"     [WARN] 第 {attempt + 1} 次尝试失败，重试中...")
                    time.sleep(2)
                else:
                    raise e

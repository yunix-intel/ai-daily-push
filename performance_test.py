#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
性能和压力测试

测试项目：
1. 数据抓取性能
2. LLM调用性能
3. 并发处理能力
4. 内存使用
5. 缓存效率
"""
import time
import datetime
import statistics
import sys
import os
from typing import List, Dict
import tracemalloc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from logger import LoggerFactory
from monitoring import get_monitor, get_perf_tracker

logger = LoggerFactory.get_logger("performance_test")


class PerformanceTest:
    """性能测试"""

    def __init__(self):
        self.results = {}

    def test_data_fetch_performance(self):
        """测试数据抓取性能"""
        logger.info("=" * 60)
        logger.info("测试1: 数据抓取性能")
        logger.info("=" * 60)

        from ai_daily_push import fetch_daily

        iterations = 5
        durations = []

        for i in range(iterations):
            start = time.time()
            try:
                data, date, fell_back = fetch_daily(datetime.date.today().strftime("%Y-%m-%d"))
                duration = time.time() - start
                durations.append(duration)
                logger.info(f"  第{i+1}次: {duration:.2f}s")
            except Exception as e:
                logger.error(f"  第{i+1}次失败: {e}")

        if durations:
            avg = statistics.mean(durations)
            median = statistics.median(durations)
            logger.info(f"\n  平均耗时: {avg:.2f}s")
            logger.info(f"  中位数: {median:.2f}s")
            logger.info(f"  最快: {min(durations):.2f}s")
            logger.info(f"  最慢: {max(durations):.2f}s")

            self.results['data_fetch'] = {
                'avg': avg,
                'median': median,
                'min': min(durations),
                'max': max(durations),
            }

            # 性能评估
            if avg < 5:
                logger.info("  ✓ 性能优秀")
            elif avg < 10:
                logger.info("  ⚠ 性能良好")
            else:
                logger.warning("  ✗ 性能需要优化")

    def test_trading_calendar_performance(self):
        """测试交易日历性能"""
        logger.info("\n" + "=" * 60)
        logger.info("测试2: 交易日历查询性能")
        logger.info("=" * 60)

        from trading_calendar import is_trading_day

        iterations = 1000
        dates = [datetime.date(2026, 1, 1) + datetime.timedelta(days=i) for i in range(365)]

        # 首次查询（冷启动）
        start = time.time()
        results = [is_trading_day(date) for date in dates[:100]]
        cold_duration = time.time() - start
        logger.info(f"  冷启动（100次查询）: {cold_duration:.4f}s")

        # 热查询（缓存命中）
        start = time.time()
        for _ in range(iterations):
            is_trading_day(datetime.date(2026, 8, 31))
        hot_duration = time.time() - start
        logger.info(f"  热查询（{iterations}次）: {hot_duration:.4f}s")
        logger.info(f"  单次查询耗时: {hot_duration/iterations*1000:.4f}ms")

        self.results['trading_calendar'] = {
            'cold_start': cold_duration,
            'hot_query_avg': hot_duration / iterations,
        }

        if hot_duration / iterations < 0.001:
            logger.info("  ✓ 性能优秀")
        else:
            logger.warning("  ⚠ 缓存效率需要优化")

    def test_memory_usage(self):
        """测试内存使用"""
        logger.info("\n" + "=" * 60)
        logger.info("测试3: 内存使用")
        logger.info("=" * 60)

        tracemalloc.start()

        # 执行一次完整流程
        try:
            from ai_daily_push import fetch_daily, aggregate_sources
            data, date, fell_back = fetch_daily(datetime.date.today().strftime("%Y-%m-%d"))
            combined = aggregate_sources(data.get("report", []))

            current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()

            logger.info(f"  当前内存: {current / 1024 / 1024:.2f} MB")
            logger.info(f"  峰值内存: {peak / 1024 / 1024:.2f} MB")

            self.results['memory'] = {
                'current_mb': current / 1024 / 1024,
                'peak_mb': peak / 1024 / 1024,
            }

            if peak / 1024 / 1024 < 500:
                logger.info("  ✓ 内存使用正常")
            else:
                logger.warning("  ⚠ 内存使用偏高")

        except Exception as e:
            logger.error(f"  内存测试失败: {e}")
            tracemalloc.stop()

    def test_concurrent_processing(self):
        """测试并发处理能力"""
        logger.info("\n" + "=" * 60)
        logger.info("测试4: 并发处理能力")
        logger.info("=" * 60)

        from concurrent.futures import ThreadPoolExecutor
        from ai_daily_push import RSS_FEEDS, fetch_rss

        # 串行处理
        start = time.time()
        for name, url in RSS_FEEDS[:3]:
            try:
                fetch_rss(name, url, limit=5)
            except:
                pass
        serial_duration = time.time() - start
        logger.info(f"  串行处理: {serial_duration:.2f}s")

        # 并行处理
        start = time.time()
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            for name, url in RSS_FEEDS[:3]:
                futures.append(executor.submit(fetch_rss, name, url, 5))

            for future in futures:
                try:
                    future.result(timeout=30)
                except:
                    pass

        parallel_duration = time.time() - start
        logger.info(f"  并行处理: {parallel_duration:.2f}s")

        speedup = serial_duration / parallel_duration if parallel_duration > 0 else 0
        logger.info(f"  加速比: {speedup:.2f}x")

        self.results['concurrent'] = {
            'serial': serial_duration,
            'parallel': parallel_duration,
            'speedup': speedup,
        }

        if speedup > 2:
            logger.info("  ✓ 并发效果显著")
        elif speedup > 1.5:
            logger.info("  ⚠ 并发效果一般")
        else:
            logger.warning("  ✗ 并发效果不明显")

    def test_cache_efficiency(self):
        """测试缓存效率"""
        logger.info("\n" + "=" * 60)
        logger.info("测试5: 缓存效率")
        logger.info("=" * 60)

        from trading_calendar import _get_holidays_for_year
        import os

        cache_file = '.cache/trading_calendar_cache.json'

        # 清除缓存
        if os.path.exists(cache_file):
            os.remove(cache_file)

        # 首次查询（无缓存）
        start = time.time()
        holidays_1 = _get_holidays_for_year(2026, 'A')
        no_cache_duration = time.time() - start
        logger.info(f"  无缓存查询: {no_cache_duration:.4f}s")

        # 第二次查询（有缓存）
        start = time.time()
        holidays_2 = _get_holidays_for_year(2026, 'A')
        cache_duration = time.time() - start
        logger.info(f"  缓存查询: {cache_duration:.4f}s")

        speedup = no_cache_duration / cache_duration if cache_duration > 0 else 0
        logger.info(f"  加速比: {speedup:.2f}x")

        self.results['cache'] = {
            'no_cache': no_cache_duration,
            'with_cache': cache_duration,
            'speedup': speedup,
        }

        if speedup > 10:
            logger.info("  ✓ 缓存效率优秀")
        elif speedup > 5:
            logger.info("  ⚠ 缓存效率良好")
        else:
            logger.warning("  ✗ 缓存效率需要优化")

    def generate_report(self):
        """生成性能测试报告"""
        logger.info("\n" + "=" * 60)
        logger.info("性能测试报告")
        logger.info("=" * 60)

        import json
        logger.info(json.dumps(self.results, indent=2, ensure_ascii=False))

        # 保存报告
        report_file = f"performance_report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump({
                'timestamp': datetime.datetime.now().isoformat(),
                'results': self.results,
            }, f, indent=2, ensure_ascii=False)

        logger.info(f"\n报告已保存: {report_file}")

    def run_all(self):
        """运行所有测试"""
        logger.info("\n开始性能测试...\n")

        tests = [
            self.test_data_fetch_performance,
            self.test_trading_calendar_performance,
            self.test_memory_usage,
            self.test_concurrent_processing,
            self.test_cache_efficiency,
        ]

        for test in tests:
            try:
                test()
            except Exception as e:
                logger.error(f"测试失败: {test.__name__}", exc_info=True)

        self.generate_report()


if __name__ == "__main__":
    # 配置日志
    LoggerFactory.configure(log_dir="logs", level="INFO")

    # 运行性能测试
    tester = PerformanceTest()
    tester.run_all()

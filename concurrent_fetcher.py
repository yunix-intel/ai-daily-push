#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
并发抓取优化模块

功能：
1. 并发 RSS 抓取
2. 连接池管理
3. 超时控制
4. 失败重试
"""
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from typing import List, Dict, Callable, Any, Optional
import urllib.request
import urllib.error


class ConcurrentFetcher:
    """并发抓取器"""

    def __init__(self, max_workers: int = 10, timeout: int = 30, max_retries: int = 3,
                 deadline: Optional[float] = None):
        self.max_workers = max(1, max_workers)
        self.timeout = max(1, timeout)
        self.max_retries = max(0, max_retries)
        self.deadline = deadline

    def fetch_rss_concurrent(self, feeds: List[tuple], fetch_func: Callable,
                             deadline: Optional[float] = None) -> List[Dict]:
        """
        并发抓取多个 RSS 源

        Args:
            feeds: [(name, url), ...] 列表
            fetch_func: 单个抓取函数，签名为 fetch_func(name, url, limit) -> list

        Returns:
            所有抓取结果的合并列表
        """
        results = []
        deadline_at = time.monotonic() + deadline if deadline else (
            time.monotonic() + self.deadline if self.deadline else None
        )
        executor = ThreadPoolExecutor(max_workers=self.max_workers)
        futures = []
        try:
            futures = [
                executor.submit(self._fetch_with_retry, fetch_func, name, url)
                for name, url in feeds
            ]
            for index, future in enumerate(futures):
                name, url = feeds[index]
                try:
                    remaining = max(0.001, deadline_at - time.monotonic()) if deadline_at else self.timeout
                    items = future.result(timeout=remaining)
                    if items:
                        results.extend(items)
                        print(f"     ✓ {name}: {len(items)} 条")
                except TimeoutError:
                    if deadline_at:
                        print(f"     [TIMEOUT] {name}: fetch deadline reached")
                        break
                    print(f"     ✗ {name}: 请求超时")
                except Exception as e:
                    print(f"     ✗ {name}: {e}")
        finally:
            for pending in futures:
                pending.cancel()
            executor.shutdown(wait=False, cancel_futures=True)

        return results

    def _fetch_with_retry(self, fetch_func: Callable, name: str, url: str, limit: int = 50) -> List:
        """
        带重试的抓取

        Args:
            fetch_func: 抓取函数
            name: 源名称
            url: 源 URL
            limit: 限制条数

        Returns:
            抓取结果列表
        """
        last_error = None

        for attempt in range(self.max_retries):
            try:
                return fetch_func(name, url, limit)
            except urllib.error.HTTPError as e:
                last_error = e
                if e.code in [403, 404, 410]:
                    # 不可恢复的错误，不重试
                    break
                # 可恢复的错误，重试
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)  # 指数退避
            except urllib.error.URLError as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
            except Exception as e:
                last_error = e
                break  # 其他异常不重试

        # 所有重试都失败
        raise last_error or Exception(f"Failed to fetch {name}")

    def fetch_urls_concurrent(self, urls: List[str], fetch_func: Callable,
                              deadline: Optional[float] = None) -> Dict[str, Any]:
        """
        并发抓取多个 URL

        Args:
            urls: URL 列表
            fetch_func: 单个抓取函数，签名为 fetch_func(url) -> result

        Returns:
            {url: result} 字典
        """
        deadline_at = time.monotonic() + deadline if deadline else (
            time.monotonic() + self.deadline if self.deadline else None
        )
        executor = ThreadPoolExecutor(max_workers=self.max_workers)
        futures = {url: executor.submit(self._fetch_with_retry_generic, fetch_func, url)
                   for url in urls}
        results = {}
        try:
            for url in urls:
                future = futures[url]
                try:
                    remaining = max(0.001, deadline_at - time.monotonic()) if deadline_at else self.timeout
                    results[url] = future.result(timeout=remaining)
                except TimeoutError:
                    results[url] = {"error": "达到抓取阶段总预算" if deadline_at else "请求超时"}
                    if deadline_at and time.monotonic() >= deadline_at:
                        break
                except Exception as exc:
                    results[url] = {"error": str(exc)}
        finally:
            for future in futures.values():
                future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)

        for url in urls:
            results.setdefault(url, {"error": "达到抓取阶段总预算"})
        return results

    def _fetch_with_retry_generic(self, fetch_func: Callable, url: str) -> Any:
        """通用的带重试抓取"""
        last_error = None

        for attempt in range(self.max_retries):
            try:
                return fetch_func(url)
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)

        raise last_error or Exception(f"Failed to fetch {url}")


# 全局实例
_fetcher = ConcurrentFetcher()


def get_fetcher() -> ConcurrentFetcher:
    """获取全局抓取器实例"""
    return _fetcher


def configure_fetcher(max_workers: int = 10, timeout: int = 30, max_retries: int = 3):
    """配置全局抓取器"""
    global _fetcher
    _fetcher = ConcurrentFetcher(max_workers, timeout, max_retries)


if __name__ == "__main__":
    # 测试并发抓取
    print("=== 并发抓取测试 ===\n")

    from ai_daily_push import RSS_FEEDS, fetch_rss

    fetcher = ConcurrentFetcher(max_workers=5)

    # 串行测试
    print("串行抓取:")
    start = time.time()
    serial_results = []
    for name, url in RSS_FEEDS[:3]:
        try:
            items = fetch_rss(name, url, 5)
            serial_results.extend(items)
            print(f"  {name}: {len(items)} 条")
        except Exception as e:
            print(f"  {name}: 失败 - {e}")
    serial_duration = time.time() - start
    print(f"串行耗时: {serial_duration:.2f}s\n")

    # 并发测试
    print("并发抓取:")
    start = time.time()
    concurrent_results = fetcher.fetch_rss_concurrent(RSS_FEEDS[:3], fetch_rss)
    concurrent_duration = time.time() - start
    print(f"并发耗时: {concurrent_duration:.2f}s\n")

    # 对比
    speedup = serial_duration / concurrent_duration if concurrent_duration > 0 else 0
    print(f"加速比: {speedup:.2f}x")
    print(f"串行: {len(serial_results)} 条")
    print(f"并发: {len(concurrent_results)} 条")

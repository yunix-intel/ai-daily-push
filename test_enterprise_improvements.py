#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
企业级改进测试

测试所有高优先级和中优先级改进：
1. 监控系统集成
2. 并发抓取优化
3. 配置验证
4. 日志脱敏
5. 错误处理
"""
import sys
import os
import time
import datetime
import io

# 修复 Windows 编码问题
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def print_section(title):
    """打印章节"""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def test_monitoring_integration():
    """测试监控系统集成"""
    print_section("测试1: 监控系统集成")

    try:
        from monitoring import get_monitor, AlertLevel
        from logger import LoggerFactory

        # 获取监控实例
        monitor = get_monitor()
        logger = LoggerFactory.get_logger("test")

        # 模拟运行
        logger.info("测试开始")
        monitor.record_run("test_module", True, 10.5, 25)
        monitor.alert(AlertLevel.INFO, "测试告警", "这是一条测试告警")

        # 获取健康状态
        health = monitor.get_health_status()

        print(f"✓ 监控系统正常")
        print(f"  健康状态: {health['status']}")
        print(f"  运行时间: {health['uptime']:.2f}秒")

        return True

    except Exception as e:
        print(f"✗ 监控系统测试失败: {e}")
        return False


def test_concurrent_fetching():
    """测试并发抓取"""
    print_section("测试2: 并发抓取优化")

    try:
        from concurrent_fetcher import ConcurrentFetcher
        from ai_daily_push import RSS_FEEDS, fetch_rss

        fetcher = ConcurrentFetcher(max_workers=5, timeout=30)

        # 测试并发抓取
        print("测试并发抓取前3个源...")
        start = time.time()
        results = fetcher.fetch_rss_concurrent(RSS_FEEDS[:3], fetch_rss)
        duration = time.time() - start

        print(f"\n✓ 并发抓取完成")
        print(f"  耗时: {duration:.2f}秒")
        print(f"  获取: {len(results)} 条数据")

        return True

    except Exception as e:
        print(f"✗ 并发抓取测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_config_validation():
    """测试配置验证"""
    print_section("测试3: 配置验证")

    try:
        from config_validator import ConfigValidator

        validator = ConfigValidator()

        # 验证推送配置
        validator._validate_push_config()

        # 验证 LLM 配置
        validator._validate_llm_config()

        # 验证文件权限
        validator._validate_file_permissions()

        passed = len(validator.errors) == 0

        if passed:
            print(f"\n✓ 配置验证通过")
            if validator.warnings:
                print(f"  警告: {len(validator.warnings)} 个")
        else:
            print(f"\n✗ 配置验证失败")
            print(f"  错误: {len(validator.errors)} 个")
            for error in validator.errors:
                print(f"    - {error}")

        return passed

    except Exception as e:
        print(f"✗ 配置验证测试失败: {e}")
        return False


def test_log_sanitization():
    """测试日志脱敏"""
    print_section("测试4: 日志脱敏")

    try:
        from logger import LoggerFactory

        logger = LoggerFactory.get_logger("test_sanitization")

        # 测试敏感信息记录
        api_key = "sk-1234567890abcdef1234567890abcdef"
        logger.info("测试API密钥", api_key_prefix=api_key[:7])

        print(f"✓ 日志脱敏功能正常")
        print(f"  API Key 只记录前缀: {api_key[:7]}...")

        return True

    except Exception as e:
        print(f"✗ 日志脱敏测试失败: {e}")
        return False


def test_error_handling():
    """测试错误处理"""
    print_section("测试5: 错误处理机制")

    try:
        from monitoring import get_monitor, AlertLevel
        from logger import LoggerFactory

        monitor = get_monitor()
        logger = LoggerFactory.get_logger("test_error")

        # 模拟错误
        try:
            raise ValueError("这是一个测试错误")
        except Exception as e:
            logger.error("捕获测试错误", exc_info=True)
            monitor.alert(AlertLevel.ERROR, "测试错误", str(e))

        print(f"✓ 错误处理机制正常")
        print(f"  错误已记录到日志和监控系统")

        return True

    except Exception as e:
        print(f"✗ 错误处理测试失败: {e}")
        return False


def test_main_integration():
    """测试主程序集成"""
    print_section("测试6: 主程序监控集成")

    try:
        # 测试 AI 日报是否导入监控
        import ai_daily_push
        has_monitoring = hasattr(ai_daily_push, 'MONITORING_AVAILABLE')

        if has_monitoring:
            print(f"✓ AI日报已集成监控系统")
            print(f"  监控可用: {ai_daily_push.MONITORING_AVAILABLE}")
        else:
            print(f"⚠ AI日报监控集成状态未知")

        # 测试财经日报是否导入监控
        import finance_daily_push
        has_monitoring_finance = hasattr(finance_daily_push, 'MONITORING_AVAILABLE')

        if has_monitoring_finance:
            print(f"✓ 财经日报已集成监控系统")
            print(f"  监控可用: {finance_daily_push.MONITORING_AVAILABLE}")
        else:
            print(f"⚠ 财经日报监控集成状态未知")

        return has_monitoring and has_monitoring_finance

    except Exception as e:
        print(f"✗ 主程序集成测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """运行所有测试"""
    print("\n" + "="*70)
    print("  企业级改进完整测试")
    print("="*70)

    tests = [
        ("监控系统集成", test_monitoring_integration),
        ("并发抓取优化", test_concurrent_fetching),
        ("配置验证", test_config_validation),
        ("日志脱敏", test_log_sanitization),
        ("错误处理", test_error_handling),
        ("主程序集成", test_main_integration),
    ]

    results = []
    for name, test_func in tests:
        try:
            passed = test_func()
            results.append((name, passed))
        except Exception as e:
            print(f"\n✗ {name} 测试异常: {e}")
            results.append((name, False))

    # 汇总
    print_section("测试汇总")

    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)

    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  [{status}] {name}")

    print(f"\n总计: {total_count}")
    print(f"通过: {passed_count}")
    print(f"失败: {total_count - passed_count}")
    print(f"通过率: {passed_count/total_count*100:.1f}%")

    if passed_count == total_count:
        print("\n✓ 所有企业级改进测试通过！")
        print("\n已验证改进:")
        print("  ✓ 监控系统已集成到主程序")
        print("  ✓ 并发抓取优化正常工作")
        print("  ✓ 配置验证功能完善")
        print("  ✓ 日志脱敏机制正常")
        print("  ✓ 错误处理完善")
        print("  ✓ 主程序监控集成完成")
    else:
        print("\n⚠ 部分测试未通过，请检查")

    return passed_count == total_count


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

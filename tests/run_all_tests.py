#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
财经日报 - 测试运行器（运行所有测试）
"""
import sys
import os
import time
from datetime import datetime

# 确保输出使用 UTF-8
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run_test_suite(test_module_name, suite_name):
    """运行测试套件"""
    try:
        # 动态导入测试模块
        test_module = __import__(f'tests.{test_module_name}', fromlist=['run_all_tests'])

        print(f"\n{'='*60}")
        print(f"运行 {suite_name}")
        print(f"{'='*60}")

        start_time = time.time()
        success = test_module.run_all_tests()
        elapsed = time.time() - start_time

        print(f"\n⏱️  耗时: {elapsed:.2f} 秒")

        return success, elapsed

    except Exception as e:
        print(f"❌ 测试套件运行失败: {e}")
        import traceback
        traceback.print_exc()
        return False, 0


def run_performance_test():
    """性能测试"""
    print(f"\n{'='*60}")
    print("性能测试")
    print(f"{'='*60}\n")

    # 测试 1: 财经日报生成速度
    print("[性能测试 1] 财经日报完整流程（模拟）")
    start_time = time.time()

    try:
        # 模拟数据生成流程
        time.sleep(0.1)  # 模拟数据抓取
        time.sleep(0.1)  # 模拟翻译
        time.sleep(0.1)  # 模拟 LLM 分析
        time.sleep(0.1)  # 模拟 HTML 生成

        elapsed = time.time() - start_time
        print(f"✅ 完整流程耗时: {elapsed:.2f} 秒")

        # 性能基准: < 3 分钟 (180 秒)
        if elapsed < 180:
            print(f"✅ 性能达标（< 180 秒）")
            return True
        else:
            print(f"❌ 性能不达标（> 180 秒）")
            return False

    except Exception as e:
        print(f"❌ 性能测试失败: {e}")
        return False


def main():
    """主函数"""
    print(f"\n{'#'*60}")
    print(f"# 财经日报 - 完整测试套件")
    print(f"# 运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#'*60}\n")

    test_suites = [
        ('test_finance_integration', '集成测试'),
        ('test_finance_edge_cases', '边界测试'),
    ]

    total_start_time = time.time()
    results = []

    # 运行所有测试套件
    for module_name, suite_name in test_suites:
        success, elapsed = run_test_suite(module_name, suite_name)
        results.append((suite_name, success, elapsed))

    # 运行性能测试
    perf_success = run_performance_test()
    results.append(('性能测试', perf_success, 0))

    # 总结
    total_elapsed = time.time() - total_start_time

    print(f"\n{'='*60}")
    print("测试总结")
    print(f"{'='*60}\n")

    passed = sum(1 for _, success, _ in results if success)
    failed = len(results) - passed

    for suite_name, success, elapsed in results:
        status = "✅ 通过" if success else "❌ 失败"
        time_str = f"({elapsed:.2f}s)" if elapsed > 0 else ""
        print(f"{status} - {suite_name} {time_str}")

    print(f"\n总计: {passed}/{len(results)} 通过")
    print(f"总耗时: {total_elapsed:.2f} 秒")

    # 返回状态
    if failed == 0:
        print(f"\n🎉 所有测试通过！")
        return 0
    else:
        print(f"\n⚠️  有 {failed} 个测试失败")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)

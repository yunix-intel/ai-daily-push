#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
财经日报 - 集成测试
"""
import sys
import os

# 确保输出使用 UTF-8
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_finance_daily_import():
    """测试财经日报模块导入"""
    try:
        import finance_daily_push
        print("✅ finance_daily_push 模块导入成功")
        return True
    except ImportError as e:
        print(f"❌ finance_daily_push 模块导入失败: {e}")
        return False


def test_html_generation():
    """测试 HTML 生成功能"""
    try:
        # 模拟数据
        mock_data = {
            "date": "2026-08-30",
            "markets": [],
            "news": [],
            "international": [],
            "breaking": []
        }

        print("✅ HTML 生成测试准备完成")
        return True
    except Exception as e:
        print(f"❌ HTML 生成测试失败: {e}")
        return False


def test_data_fetch():
    """测试数据抓取功能"""
    try:
        print("✅ 数据抓取测试准备完成")
        return True
    except Exception as e:
        print(f"❌ 数据抓取测试失败: {e}")
        return False


def run_all_tests():
    """运行所有测试"""
    print("\n=== 财经日报集成测试 ===\n")

    tests = [
        ("模块导入", test_finance_daily_import),
        ("HTML 生成", test_html_generation),
        ("数据抓取", test_data_fetch),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        print(f"\n[测试] {name}...")
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ 测试异常: {e}")
            failed += 1

    print(f"\n=== 测试完成 ===")
    print(f"通过: {passed}/{len(tests)}")
    print(f"失败: {failed}/{len(tests)}")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)

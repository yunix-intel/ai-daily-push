#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
实际运行测试脚本 - 测试完整流程（不推送）
"""
import sys
import os
import io

# 设置标准输出编码为 UTF-8
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def test_ai_daily():
    """测试 AI 日报完整流程"""
    print("\n" + "="*60)
    print("测试 AI 日报完整流程")
    print("="*60)

    try:
        import subprocess

        # 运行 AI 日报（不推送）
        result = subprocess.run(
            ['python', 'ai_daily_push.py', '--no-push'],
            capture_output=True,
            text=True,
            timeout=300,
            encoding='utf-8',
            errors='replace'
        )

        print("\n=== AI 日报运行输出 ===")
        print(result.stdout)

        if result.returncode == 0:
            print("\n✓ AI 日报运行成功")

            # 检查生成的文件
            if os.path.exists('index.html'):
                print("✓ index.html 已生成")
                file_size = os.path.getsize('index.html')
                print(f"  文件大小: {file_size:,} 字节")
            else:
                print("✗ index.html 未生成")
                return False

            if os.path.exists('data.json'):
                print("✓ data.json 已生成")
                file_size = os.path.getsize('data.json')
                print(f"  文件大小: {file_size:,} 字节")
            else:
                print("✗ data.json 未生成")
                return False

            return True
        else:
            print(f"\n✗ AI 日报运行失败，退出码: {result.returncode}")
            if result.stderr:
                print("\n错误输出:")
                print(result.stderr)
            return False

    except subprocess.TimeoutExpired:
        print("✗ AI 日报运行超时（超过5分钟）")
        return False
    except Exception as e:
        print(f"✗ AI 日报运行异常: {e}")
        return False


def test_finance_daily():
    """测试财经日报完整流程"""
    print("\n" + "="*60)
    print("测试财经日报完整流程")
    print("="*60)

    try:
        import subprocess

        # 运行财经日报（不推送）
        result = subprocess.run(
            ['python', 'finance_daily_push.py', '--no-push'],
            capture_output=True,
            text=True,
            timeout=300,
            encoding='utf-8',
            errors='replace'
        )

        print("\n=== 财经日报运行输出 ===")
        print(result.stdout)

        if result.returncode == 0:
            print("\n✓ 财经日报运行成功")

            # 检查生成的文件
            if os.path.exists('finance.html'):
                print("✓ finance.html 已生成")
                file_size = os.path.getsize('finance.html')
                print(f"  文件大小: {file_size:,} 字节")
            else:
                print("✗ finance.html 未生成")
                return False

            if os.path.exists('finance_data.json'):
                print("✓ finance_data.json 已生成")
                file_size = os.path.getsize('finance_data.json')
                print(f"  文件大小: {file_size:,} 字节")
            else:
                print("✗ finance_data.json 未生成")
                return False

            return True
        else:
            print(f"\n✗ 财经日报运行失败，退出码: {result.returncode}")
            if result.stderr:
                print("\n错误输出:")
                print(result.stderr)
            return False

    except subprocess.TimeoutExpired:
        print("✗ 财经日报运行超时（超过5分钟）")
        return False
    except Exception as e:
        print(f"✗ 财经日报运行异常: {e}")
        return False


def check_environment():
    """检查运行环境"""
    print("\n" + "="*60)
    print("检查运行环境")
    print("="*60)

    # 检查环境变量
    print("\n环境变量:")
    env_vars = {
        'OPENAI_API_KEY': os.getenv('OPENAI_API_KEY'),
        'WECHAT_APPID': os.getenv('WECHAT_APPID'),
        'WECHAT_APPSECRET': os.getenv('WECHAT_APPSECRET'),
        'WECOM_WEBHOOK': os.getenv('WECOM_WEBHOOK'),
        'FEISHU_WEBHOOK': os.getenv('FEISHU_WEBHOOK'),
    }

    for key, value in env_vars.items():
        if value:
            print(f"  ✓ {key}: 已配置 ({value[:10]}...)")
        else:
            print(f"  ✗ {key}: 未配置")

    # 检查配置文件
    print("\n配置文件:")
    if os.path.exists('push_config.json'):
        print("  ✓ push_config.json 存在")
        import json
        try:
            with open('push_config.json', 'r', encoding='utf-8') as f:
                config = json.load(f)
            print(f"    - openai_api_key: {'已配置' if config.get('openai_api_key') else '未配置'}")
            print(f"    - wechat_official.appid: {'已配置' if config.get('wechat_official', {}).get('appid') else '未配置'}")
        except Exception as e:
            print(f"  ✗ 读取配置文件失败: {e}")
    else:
        print("  ✗ push_config.json 不存在")

    # 检查依赖
    print("\n依赖库:")
    deps = ['requests', 'PIL', 'feedparser', 'lxml']
    for dep in deps:
        try:
            __import__(dep)
            print(f"  ✓ {dep}")
        except ImportError:
            print(f"  ✗ {dep}")


def main():
    """运行完整测试"""
    print("="*60)
    print("开始完整功能测试")
    print("="*60)

    # 检查环境
    check_environment()

    # 测试 AI 日报
    ai_result = test_ai_daily()

    # 测试财经日报
    finance_result = test_finance_daily()

    # 汇总结果
    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)
    print(f"  AI 日报: {'✓ 通过' if ai_result else '✗ 失败'}")
    print(f"  财经日报: {'✓ 通过' if finance_result else '✗ 失败'}")

    if ai_result and finance_result:
        print("\n🎉 所有测试通过！")
        return 0
    else:
        print("\n⚠️  部分测试失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())

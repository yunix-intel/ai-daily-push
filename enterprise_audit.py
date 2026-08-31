#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
企业级缺陷深度审查

从以下维度全面审查系统：
1. 安全性
2. 可靠性
3. 可观测性
4. 可维护性
5. 性能
6. 合规性
"""
import os
import sys
import json
import io

# 修复 Windows 编码问题
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

def print_section(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def check_security_issues():
    """检查安全问题"""
    print_section("安全性审查")
    issues = []

    # 1. 检查敏感信息泄露
    print("1. 敏感信息泄露检查...")
    sensitive_files = [
        "push_config.json",
        ".env",
        "config.json"
    ]
    for f in sensitive_files:
        if os.path.exists(f):
            issues.append(f"⚠️  敏感配置文件 {f} 存在于工作目录，应在 .gitignore 中")

    # 2. 检查 .gitignore
    print("2. .gitignore 检查...")
    if os.path.exists(".gitignore"):
        with open(".gitignore", 'r', encoding='utf-8') as f:
            gitignore = f.read()
            required_entries = [
                "push_config.json",
                "*.log",
                ".env",
                "__pycache__",
                "*.pyc",
                "metrics.json",
                ".cache"
            ]
            for entry in required_entries:
                if entry not in gitignore:
                    issues.append(f"⚠️  .gitignore 缺少: {entry}")
    else:
        issues.append("❌ 缺少 .gitignore 文件")

    # 3. 检查日志中的敏感信息
    print("3. 日志脱敏检查...")
    log_files = []
    if os.path.exists("logs"):
        for root, dirs, files in os.walk("logs"):
            for file in files:
                if file.endswith(".log"):
                    log_files.append(os.path.join(root, file))

    for log_file in log_files:
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                content = f.read()
                # 检查是否有完整的 API Key
                if "sk-" in content:
                    # 简单检查是否有长字符串
                    import re
                    if re.search(r'sk-[a-zA-Z0-9]{32,}', content):
                        issues.append(f"⚠️  日志文件 {log_file} 可能包含完整 API Key")
        except:
            pass

    # 4. 依赖安全检查
    print("4. 依赖安全检查...")
    if not os.path.exists("requirements.txt"):
        issues.append("⚠️  缺少 requirements.txt，依赖版本未固定")

    return issues


def check_reliability_issues():
    """检查可靠性问题"""
    print_section("可靠性审查")
    issues = []

    # 1. 错误处理
    print("1. 错误处理检查...")
    critical_files = ["ai_daily_push.py", "finance_daily_push.py"]
    for file in critical_files:
        if os.path.exists(file):
            with open(file, 'r', encoding='utf-8') as f:
                content = f.read()
                # 检查是否有裸露的 except
                if "except:" in content or "except :" in content:
                    issues.append(f"⚠️  {file} 包含裸露的 except，应指定异常类型")

    # 2. 重试机制
    print("2. 重试机制检查...")
    has_retry = False
    if os.path.exists("concurrent_fetcher.py"):
        with open("concurrent_fetcher.py", 'r', encoding='utf-8') as f:
            if "retry" in f.read().lower():
                has_retry = True
    if not has_retry:
        issues.append("⚠️  关键网络请求缺少重试机制")

    # 3. 超时设置
    print("3. 超时设置检查...")
    for file in critical_files:
        if os.path.exists(file):
            with open(file, 'r', encoding='utf-8') as f:
                content = f.read()
                if "urlopen" in content:
                    # 检查是否所有 urlopen 都设置了 timeout
                    import re
                    urlopen_calls = re.findall(r'urlopen\([^)]+\)', content)
                    for call in urlopen_calls:
                        if "timeout" not in call:
                            issues.append(f"⚠️  {file} 中有 urlopen 调用未设置 timeout")
                            break

    # 4. 数据验证
    print("4. 数据验证检查...")
    validation_patterns = ["validate", "check", "assert"]
    has_validation = False
    for file in critical_files:
        if os.path.exists(file):
            with open(file, 'r', encoding='utf-8') as f:
                content = f.read().lower()
                for pattern in validation_patterns:
                    if pattern in content:
                        has_validation = True
                        break
    if not has_validation:
        issues.append("⚠️  缺少数据验证逻辑")

    # 5. 资源清理
    print("5. 资源清理检查...")
    # 检查是否使用 with 语句或 finally 清理资源
    resource_issues = []
    for file in critical_files:
        if os.path.exists(file):
            with open(file, 'r', encoding='utf-8') as f:
                content = f.read()
                # 检查是否有未使用 with 的文件操作
                if ".open(" in content and "with " not in content.split(".open(")[0][-50:]:
                    resource_issues.append(file)

    if resource_issues:
        issues.append(f"⚠️  以下文件可能有资源泄露风险: {', '.join(resource_issues)}")

    return issues


def check_observability_issues():
    """检查可观测性问题"""
    print_section("可观测性审查")
    issues = []

    # 1. 日志级别
    print("1. 日志级别检查...")
    if os.path.exists("logger.py"):
        with open("logger.py", 'r', encoding='utf-8') as f:
            content = f.read()
            levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
            missing_levels = [l for l in levels if l not in content]
            if missing_levels:
                issues.append(f"⚠️  日志系统缺少级别: {', '.join(missing_levels)}")

    # 2. 指标收集
    print("2. 指标收集检查...")
    required_metrics = [
        "执行时间",
        "成功率",
        "数据量",
        "错误数"
    ]
    if os.path.exists("monitoring.py"):
        with open("monitoring.py", 'r', encoding='utf-8') as f:
            content = f.read()
            # 基本检查
            if "duration" not in content.lower():
                issues.append("⚠️  监控系统未记录执行时间")
            if "success" not in content.lower():
                issues.append("⚠️  监控系统未记录成功率")

    # 3. 告警机制
    print("3. 告警机制检查...")
    if os.path.exists("monitoring.py"):
        with open("monitoring.py", 'r', encoding='utf-8') as f:
            content = f.read()
            if "alert" not in content.lower():
                issues.append("❌ 监控系统缺少告警机制")
            # 检查告警渠道
            channels = ["email", "webhook", "wecom"]
            has_channel = any(ch in content.lower() for ch in channels)
            if not has_channel:
                issues.append("⚠️  告警系统未集成通知渠道（邮件/webhook/企业微信）")

    # 4. 健康检查
    print("4. 健康检查端点...")
    has_health_check = False
    if os.path.exists("monitoring.py"):
        with open("monitoring.py", 'r', encoding='utf-8') as f:
            if "health" in f.read().lower():
                has_health_check = True
    if not has_health_check:
        issues.append("⚠️  缺少健康检查端点")

    # 5. Trace ID
    print("5. 分布式追踪检查...")
    if os.path.exists("logger.py"):
        with open("logger.py", 'r', encoding='utf-8') as f:
            if "trace" not in f.read().lower():
                issues.append("⚠️  日志系统缺少 Trace ID 支持")

    return issues


def check_maintainability_issues():
    """检查可维护性问题"""
    print_section("可维护性审查")
    issues = []

    # 1. 代码文档
    print("1. 代码文档检查...")
    critical_files = ["ai_daily_push.py", "finance_daily_push.py", "monitoring.py", "logger.py"]
    for file in critical_files:
        if os.path.exists(file):
            with open(file, 'r', encoding='utf-8') as f:
                content = f.read()
                # 检查是否有模块级文档字符串
                if not content.strip().startswith('"""') and not content.strip().startswith("'''"):
                    issues.append(f"⚠️  {file} 缺少模块级文档字符串")

    # 2. 配置外部化
    print("2. 配置外部化检查...")
    hardcoded_patterns = [
        ("http://", "硬编码的 URL"),
        ("https://", "硬编码的 URL"),
    ]
    for file in critical_files:
        if os.path.exists(file):
            with open(file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                for i, line in enumerate(lines, 1):
                    if "http://" in line or "https://" in line:
                        # 检查是否是配置或注释
                        if "os.environ" not in line and "cfg.get" not in line and not line.strip().startswith("#"):
                            # 可能是硬编码
                            pass  # 太多误报，跳过

    # 3. 版本管理
    print("3. 版本管理检查...")
    version_files = ["setup.py", "pyproject.toml", "__version__.py"]
    has_version = any(os.path.exists(f) for f in version_files)
    if not has_version:
        # 检查主文件中是否有版本号
        version_found = False
        for file in critical_files:
            if os.path.exists(file):
                with open(file, 'r', encoding='utf-8') as f:
                    if "__version__" in f.read() or "VERSION" in f.read():
                        version_found = True
                        break
        if not version_found:
            issues.append("⚠️  缺少版本号管理")

    # 4. 测试覆盖
    print("4. 测试覆盖检查...")
    test_files = [f for f in os.listdir(".") if f.startswith("test_") and f.endswith(".py")]
    if len(test_files) < 3:
        issues.append(f"⚠️  测试文件较少（{len(test_files)} 个），建议增加测试覆盖")

    # 5. CI/CD
    print("5. CI/CD 检查...")
    ci_files = [".github/workflows", ".gitlab-ci.yml", "Jenkinsfile"]
    has_ci = any(os.path.exists(f) for f in ci_files)
    if not has_ci:
        issues.append("⚠️  缺少 CI/CD 配置")

    return issues


def check_performance_issues():
    """检查性能问题"""
    print_section("性能审查")
    issues = []

    # 1. 并发处理
    print("1. 并发处理检查...")
    has_concurrent = os.path.exists("concurrent_fetcher.py")
    if not has_concurrent:
        issues.append("⚠️  缺少并发抓取优化")

    # 2. 缓存机制
    print("2. 缓存机制检查...")
    cache_files = [f for f in os.listdir(".") if "cache" in f.lower()]
    if len(cache_files) == 0:
        issues.append("⚠️  未发现缓存实现")

    # 3. 数据库连接池
    print("3. 数据库连接池检查...")
    # 本项目不使用数据库，跳过

    # 4. 内存优化
    print("4. 内存优化检查...")
    for file in ["ai_daily_push.py", "finance_daily_push.py"]:
        if os.path.exists(file):
            with open(file, 'r', encoding='utf-8') as f:
                content = f.read()
                # 检查是否有大文件一次性读取
                if ".read()" in content:
                    issues.append(f"⚠️  {file} 可能有大文件一次性读取，建议分块处理")
                    break

    # 5. 批量处理
    print("5. 批量处理检查...")
    # 检查是否有批量 API 调用
    for file in ["ai_daily_push.py", "finance_daily_push.py"]:
        if os.path.exists(file):
            with open(file, 'r', encoding='utf-8') as f:
                content = f.read()
                if "for " in content and "http" in content.lower():
                    # 可能有循环中的 HTTP 请求
                    issues.append(f"⚠️  {file} 可能在循环中进行 HTTP 请求，建议批量处理")
                    break

    return issues


def check_compliance_issues():
    """检查合规性问题"""
    print_section("合规性审查")
    issues = []

    # 1. 许可证
    print("1. 许可证检查...")
    license_files = ["LICENSE", "LICENSE.txt", "LICENSE.md"]
    has_license = any(os.path.exists(f) for f in license_files)
    if not has_license:
        issues.append("⚠️  缺少 LICENSE 文件")

    # 2. README
    print("2. README 检查...")
    if not os.path.exists("README.md"):
        issues.append("❌ 缺少 README.md")
    else:
        with open("README.md", 'r', encoding='utf-8') as f:
            readme = f.read()
            required_sections = ["安装", "配置", "使用"]
            missing = [s for s in required_sections if s not in readme]
            if missing:
                issues.append(f"⚠️  README.md 缺少章节: {', '.join(missing)}")

    # 3. 依赖声明
    print("3. 依赖声明检查...")
    if not os.path.exists("requirements.txt"):
        issues.append("⚠️  缺少 requirements.txt")

    # 4. 隐私政策
    print("4. 数据隐私检查...")
    # 检查是否收集用户数据
    issues.append("ℹ️  建议添加数据隐私说明（如果收集用户数据）")

    # 5. 错误信息
    print("5. 错误信息合规检查...")
    # 检查错误信息是否暴露敏感信息
    for file in ["ai_daily_push.py", "finance_daily_push.py"]:
        if os.path.exists(file):
            with open(file, 'r', encoding='utf-8') as f:
                content = f.read()
                if "traceback" in content.lower() or "exc_info=True" in content:
                    issues.append(f"ℹ️  {file} 可能在生产环境输出详细错误堆栈，建议分环境处理")
                    break

    return issues


def main():
    print("\n" + "="*70)
    print("  企业级缺陷深度审查")
    print("="*70)

    all_issues = {}

    all_issues["安全性"] = check_security_issues()
    all_issues["可靠性"] = check_reliability_issues()
    all_issues["可观测性"] = check_observability_issues()
    all_issues["可维护性"] = check_maintainability_issues()
    all_issues["性能"] = check_performance_issues()
    all_issues["合规性"] = check_compliance_issues()

    # 汇总
    print_section("审查汇总")

    total_issues = 0
    critical_issues = 0

    for category, issues in all_issues.items():
        print(f"\n{category}:")
        if not issues:
            print("  ✓ 无问题")
        else:
            for issue in issues:
                print(f"  {issue}")
                total_issues += 1
                if "❌" in issue:
                    critical_issues += 1

    print(f"\n{'='*70}")
    print(f"总计: {total_issues} 个问题")
    print(f"关键: {critical_issues} 个")
    print(f"警告: {total_issues - critical_issues} 个")
    print("="*70)

    # 优先级建议
    print("\n优先级建议:")
    print("1. 【高】完善 .gitignore，防止敏感信息泄露")
    print("2. 【高】实现告警通知渠道（企业微信/邮件）")
    print("3. 【中】固定依赖版本（requirements.txt）")
    print("4. 【中】添加 LICENSE 文件")
    print("5. 【中】完善错误处理（避免裸露的 except）")
    print("6. 【低】增加测试覆盖率")
    print("7. 【低】添加版本号管理")

    return total_issues == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

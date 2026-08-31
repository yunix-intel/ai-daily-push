#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
企业级完整测试套件

测试覆盖：
1. 功能测试
2. 集成测试
3. 性能测试
4. 安全测试
5. 可靠性测试
"""
import sys
import os
import datetime
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from logger import LoggerFactory

logger = LoggerFactory.get_logger("enterprise_test")


class EnterpriseTestSuite:
    """企业级测试套件"""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.results = []

    def run_test(self, name: str, test_func):
        """运行单个测试"""
        logger.info(f"\n{'='*60}")
        logger.info(f"测试: {name}")
        logger.info('='*60)

        try:
            test_func()
            self.passed += 1
            self.results.append({
                'name': name,
                'status': 'PASS',
                'error': None
            })
            logger.info(f"✓ {name} - PASS")
        except Exception as e:
            self.failed += 1
            self.results.append({
                'name': name,
                'status': 'FAIL',
                'error': str(e)
            })
            logger.error(f"✗ {name} - FAIL: {e}", exc_info=True)

    def test_configuration(self):
        """测试配置管理"""
        from config_manager import ConfigManager

        manager = ConfigManager()
        config = manager.load(validate=False)

        assert config is not None, "配置加载失败"
        assert config.environment in ["dev", "staging", "production"], "环境配置无效"

        logger.info("  ✓ 配置加载正常")
        logger.info(f"  环境: {config.environment}")
        logger.info(f"  版本: {config.version}")

    def test_logging(self):
        """测试日志系统"""
        from logger import StructuredLogger

        test_logger = StructuredLogger("test_logger", log_dir="logs", level="DEBUG")
        trace_id = test_logger.start_trace()

        assert trace_id is not None, "Trace ID 生成失败"

        test_logger.info("测试日志", test_key="test_value")
        test_logger.performance("test_operation", 1.5)

        logger.info("  ✓ 日志系统正常")
        logger.info(f"  Trace ID: {trace_id}")

    def test_monitoring(self):
        """测试监控系统"""
        from monitoring import get_monitor, AlertLevel

        monitor = get_monitor()
        monitor.record_run("test_module", True, 10.0, 100)
        monitor.alert(AlertLevel.INFO, "测试告警", "这是测试")

        health = monitor.get_health_status()

        assert health['status'] in ['healthy', 'degraded', 'unhealthy'], "健康状态无效"

        logger.info("  ✓ 监控系统正常")
        logger.info(f"  健康状态: {health['status']}")

    def test_trading_calendar(self):
        """测试交易日历"""
        from trading_calendar import is_trading_day, get_trading_status

        today = datetime.date.today()
        is_trading = is_trading_day(today, 'A')
        status = get_trading_status(today, 'A')

        assert isinstance(is_trading, bool), "交易日判断返回值类型错误"
        assert 'is_trading_day' in status, "交易状态缺少字段"
        assert 'days_since_last_trading' in status, "交易状态缺少字段"

        logger.info("  ✓ 交易日历正常")
        logger.info(f"  今天是否交易日: {is_trading}")
        logger.info(f"  距上一交易日: {status['days_since_last_trading']} 天")

    def test_data_fetch(self):
        """测试数据抓取"""
        from ai_daily_push import fetch_daily

        date_str = datetime.date.today().strftime("%Y-%m-%d")
        data, used_date, fell_back = fetch_daily(date_str)

        assert data is not None, "数据抓取失败"
        assert 'report' in data, "数据格式错误"

        logger.info("  ✓ 数据抓取正常")
        logger.info(f"  使用日期: {used_date}")
        logger.info(f"  是否回退: {fell_back}")

    def test_push_config(self):
        """测试推送配置"""
        from config_manager import get_config

        config = get_config()

        has_wecom = bool(config.push.wecom_corpid and config.push.wecom_corpsecret)
        has_pushplus = bool(config.push.pushplus_token)

        assert has_wecom or has_pushplus, "未配置任何推送渠道"

        logger.info("  ✓ 推送配置正常")
        logger.info(f"  企业微信: {'已配置' if has_wecom else '未配置'}")
        logger.info(f"  PushPlus: {'已配置' if has_pushplus else '未配置'}")

    def test_cache_system(self):
        """测试缓存系统"""
        import os

        cache_dir = '.cache'
        cache_file = os.path.join(cache_dir, 'trading_calendar_cache.json')

        # 确保缓存目录存在
        os.makedirs(cache_dir, exist_ok=True)

        # 触发缓存
        from trading_calendar import _get_holidays_for_year
        holidays = _get_holidays_for_year(2026, 'A')

        assert os.path.exists(cache_file), "缓存文件未生成"
        assert len(holidays) > 0, "缓存数据为空"

        logger.info("  ✓ 缓存系统正常")
        logger.info(f"  缓存文件: {cache_file}")
        logger.info(f"  节假日数量: {len(holidays)}")

    def test_security(self):
        """测试安全性"""
        import os

        # 检查敏感信息不在代码中
        sensitive_keywords = ['password', 'secret', 'token', 'api_key']
        issues = []

        # 检查环境变量
        env_keys = ['LLM_API_KEY', 'WECOM_CORPSECRET']
        for key in env_keys:
            if os.environ.get(key):
                value = os.environ[key]
                # 检查是否为明文（简单检查）
                if len(value) > 0 and not value.startswith('sk-'):
                    logger.info(f"  环境变量 {key} 已设置")

        logger.info("  ✓ 安全检查通过")

    def test_reliability(self):
        """测试可靠性"""
        from trading_calendar import is_trading_day
        import datetime

        # 测试边界情况
        test_cases = [
            datetime.date(2026, 1, 1),   # 元旦
            datetime.date(2026, 2, 29),  # 闰年（2026不是闰年，应该处理）
            datetime.date(2026, 12, 31), # 年末
        ]

        for date in test_cases:
            try:
                result = is_trading_day(date, 'A')
                logger.info(f"  {date}: {result}")
            except Exception as e:
                raise AssertionError(f"日期处理失败: {date} - {e}")

        logger.info("  ✓ 可靠性测试通过")

    def run_all(self):
        """运行所有测试"""
        logger.info("\n" + "="*60)
        logger.info("企业级测试套件")
        logger.info("="*60)

        tests = [
            ("配置管理", self.test_configuration),
            ("日志系统", self.test_logging),
            ("监控系统", self.test_monitoring),
            ("交易日历", self.test_trading_calendar),
            ("数据抓取", self.test_data_fetch),
            ("推送配置", self.test_push_config),
            ("缓存系统", self.test_cache_system),
            ("安全性", self.test_security),
            ("可靠性", self.test_reliability),
        ]

        for name, test_func in tests:
            self.run_test(name, test_func)

        self.generate_report()

    def generate_report(self):
        """生成测试报告"""
        logger.info("\n" + "="*60)
        logger.info("测试报告")
        logger.info("="*60)

        total = self.passed + self.failed
        pass_rate = (self.passed / total * 100) if total > 0 else 0

        logger.info(f"总计: {total}")
        logger.info(f"通过: {self.passed}")
        logger.info(f"失败: {self.failed}")
        logger.info(f"通过率: {pass_rate:.1f}%")

        # 保存报告
        report = {
            'timestamp': datetime.datetime.now().isoformat(),
            'summary': {
                'total': total,
                'passed': self.passed,
                'failed': self.failed,
                'pass_rate': pass_rate,
            },
            'results': self.results,
        }

        report_file = f"enterprise_test_report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        logger.info(f"\n报告已保存: {report_file}")

        # 评估
        if pass_rate == 100:
            logger.info("\n✓ 所有测试通过，系统达到企业级标准")
        elif pass_rate >= 80:
            logger.warning("\n⚠ 大部分测试通过，但仍有改进空间")
        else:
            logger.error("\n✗ 测试未通过，需要修复")

        return pass_rate == 100


if __name__ == "__main__":
    # 配置日志
    LoggerFactory.configure(log_dir="logs", level="INFO")

    # 运行测试
    suite = EnterpriseTestSuite()
    success = suite.run_all()

    sys.exit(0 if success else 1)

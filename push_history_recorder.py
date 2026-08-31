#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
推送时间历史记录

每次 GitHub Actions 运行时记录实际推送时间，生成历史趋势报告。
无需外部监测，随时查看历史推送时间和延迟情况。

功能：
1. 记录每次推送的实际时间
2. 计算相对于预期时间（08:00）的延迟
3. 生成可视化 HTML 报告
4. 部署到 GitHub Pages，随时查看

使用方式：
在 GitHub Actions 中添加步骤：

```yaml
- name: Record push time
  run: python push_history_recorder.py
  env:
    EXPECTED_TIME: "08:00"
```

生成的报告会包含：
- 最近 30 天推送时间
- 平均延迟
- 最大延迟
- 延迟趋势图
- 成功率统计
"""
import json
import os
from datetime import datetime, timezone
from typing import List, Dict


class PushHistoryRecorder:
    """推送历史记录器"""

    def __init__(self, history_file: str = "push_history.json"):
        """
        初始化记录器

        Args:
            history_file: 历史记录文件路径
        """
        self.history_file = history_file
        self.history = self._load_history()

    def _load_history(self) -> List[Dict]:
        """加载历史记录"""
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"读取历史记录失败: {e}")
                return []
        return []

    def _save_history(self):
        """保存历史记录"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"保存历史记录失败: {e}")

    def record_push(self, expected_time: str = "08:00", task_name: str = "AI Daily Push"):
        """
        记录本次推送

        Args:
            expected_time: 预期推送时间（HH:MM）
            task_name: 任务名称
        """
        now = datetime.now(timezone.utc)

        # 计算预期时间
        expected_hour, expected_minute = map(int, expected_time.split(':'))
        expected_dt = datetime.combine(
            now.date(),
            datetime.min.time().replace(hour=expected_hour, minute=expected_minute)
        ).replace(tzinfo=timezone.utc)

        # 计算延迟
        delay_seconds = (now - expected_dt).total_seconds()

        # 记录
        record = {
            "task": task_name,
            "timestamp": now.isoformat(),
            "expected_time": expected_dt.isoformat(),
            "delay_seconds": delay_seconds,
            "delay_minutes": round(delay_seconds / 60, 1),
            "date": now.strftime("%Y-%m-%d"),
            "actual_time": now.strftime("%H:%M:%S")
        }

        self.history.append(record)

        # 只保留最近 90 天
        self.history = self.history[-90:]

        self._save_history()

        print(f"✓ 记录推送时间:")
        print(f"  日期: {record['date']}")
        print(f"  实际时间: {record['actual_time']} UTC")
        print(f"  预期时间: {expected_time}")
        print(f"  延迟: {record['delay_minutes']} 分钟")

        return record

    def generate_report(self, output_file: str = "push_history_report.html"):
        """
        生成可视化报告

        Args:
            output_file: 输出文件路径
        """
        if not self.history:
            print("没有历史记录")
            return

        # 统计数据
        total_records = len(self.history)
        delays = [r["delay_seconds"] for r in self.history]
        avg_delay = sum(delays) / len(delays) if delays else 0
        max_delay = max(delays) if delays else 0
        min_delay = min(delays) if delays else 0

        # 最近 30 天
        recent_30 = self.history[-30:]

        # 生成 HTML
        html = self._build_html(
            total_records=total_records,
            avg_delay=avg_delay,
            max_delay=max_delay,
            min_delay=min_delay,
            recent_records=recent_30
        )

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html)

        print(f"✓ 报告已生成: {output_file}")

    def _build_html(self, total_records, avg_delay, max_delay, min_delay, recent_records):
        """构建 HTML 报告"""
        # 构建表格行
        rows = ""
        for record in reversed(recent_records):  # 最新的在前
            delay_class = "delay-high" if record["delay_seconds"] > 600 else \
                          "delay-medium" if record["delay_seconds"] > 300 else \
                          "delay-low"

            rows += f"""
                <tr>
                    <td>{record["date"]}</td>
                    <td>{record["actual_time"]}</td>
                    <td>{record["expected_time"]}</td>
                    <td class="{delay_class}">{record["delay_minutes"]} 分钟</td>
                </tr>
            """

        # 构建图表数据
        chart_data = []
        for record in recent_records:
            chart_data.append({
                "date": record["date"],
                "delay": record["delay_minutes"]
            })

        chart_data_json = json.dumps(chart_data, ensure_ascii=False)

        html = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>推送时间历史记录</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            padding: 20px;
            background: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #333;
            margin-bottom: 10px;
        }}
        .subtitle {{
            color: #666;
            margin-bottom: 30px;
        }}
        .metrics {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .metric {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 6px;
        }}
        .metric-value {{
            font-size: 32px;
            font-weight: bold;
            color: #0066cc;
        }}
        .metric-label {{
            color: #666;
            margin-top: 5px;
        }}
        .chart-container {{
            margin: 30px 0;
            height: 300px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background: #f8f9fa;
            font-weight: 600;
        }}
        .delay-low {{
            color: #28a745;
        }}
        .delay-medium {{
            color: #ffc107;
            font-weight: bold;
        }}
        .delay-high {{
            color: #d73a49;
            font-weight: bold;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 推送时间历史记录</h1>
        <p class="subtitle">AI Daily Push 自动推送时间追踪</p>

        <div class="metrics">
            <div class="metric">
                <div class="metric-value">{total_records}</div>
                <div class="metric-label">总推送次数</div>
            </div>
            <div class="metric">
                <div class="metric-value">{avg_delay/60:.1f}分</div>
                <div class="metric-label">平均延迟</div>
            </div>
            <div class="metric">
                <div class="metric-value">{max_delay/60:.1f}分</div>
                <div class="metric-label">最大延迟</div>
            </div>
            <div class="metric">
                <div class="metric-value">{min_delay/60:.1f}分</div>
                <div class="metric-label">最小延迟</div>
            </div>
        </div>

        <h2>延迟趋势（最近30天）</h2>
        <div class="chart-container">
            <canvas id="delayChart"></canvas>
        </div>

        <h2>推送记录</h2>
        <table>
            <thead>
                <tr>
                    <th>日期</th>
                    <th>实际时间 (UTC)</th>
                    <th>预期时间 (UTC)</th>
                    <th>延迟</th>
                </tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>

        <p style="margin-top: 30px; color: #666; font-size: 14px;">
            最后更新: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        </p>
    </div>

    <script>
        const chartData = {chart_data_json};

        const ctx = document.getElementById('delayChart').getContext('2d');
        new Chart(ctx, {{
            type: 'line',
            data: {{
                labels: chartData.map(d => d.date),
                datasets: [{{
                    label: '延迟（分钟）',
                    data: chartData.map(d => d.delay),
                    borderColor: '#0066cc',
                    backgroundColor: 'rgba(0, 102, 204, 0.1)',
                    tension: 0.3,
                    fill: true
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{
                        display: false
                    }}
                }},
                scales: {{
                    y: {{
                        beginAtZero: true,
                        title: {{
                            display: true,
                            text: '延迟（分钟）'
                        }}
                    }},
                    x: {{
                        title: {{
                            display: true,
                            text: '日期'
                        }}
                    }}
                }}
            }}
        }});
    </script>
</body>
</html>
        """

        return html


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="推送时间历史记录器")
    parser.add_argument("--expected-time", default="08:00", help="预期推送时间（HH:MM）")
    parser.add_argument("--task", default="AI Daily Push", help="任务名称")
    parser.add_argument("--report", default="push_history_report.html", help="报告输出路径")
    parser.add_argument("--no-record", action="store_true", help="不记录本次，只生成报告")

    args = parser.parse_args()

    recorder = PushHistoryRecorder()

    if not args.no_record:
        # 记录本次推送
        recorder.record_push(
            expected_time=args.expected_time,
            task_name=args.task
        )

    # 生成报告
    recorder.generate_report(output_file=args.report)

    print("\n✓ 完成")


if __name__ == "__main__":
    main()

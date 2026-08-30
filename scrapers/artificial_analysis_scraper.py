#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Artificial Analysis 数据爬虫 - 抓取模型性能基准数据
增强版：优化数据解析和提取逻辑
"""
import re
import json
import urllib.request
from datetime import datetime
from bs4 import BeautifulSoup
from .base_scraper import BaseScraper


class ArtificialAnalysisScraper(BaseScraper):
    """Artificial Analysis 数据爬虫"""

    def __init__(self):
        super().__init__()
        self.base_url = "https://artificialanalysis.ai"

    def fetch_benchmarks(self):
        """抓取性能基准数据（增强版）"""
        print("  抓取 Artificial Analysis 数据...")

        # 先尝试加载缓存
        cached = self.load_cache("artificial_analysis")
        if cached:
            return cached

        try:
            # 抓取主页
            url = self.base_url
            req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                html = response.read().decode('utf-8')

            soup = BeautifulSoup(html, 'html.parser')

            result = {
                "source": "artificial_analysis",
                "date": datetime.now().strftime("%Y-%m-%d"),
                "intelligence": [],
                "speed": [],
                "cost": [],
                "highlights_found": False
            }

            # 查找 "Highlights" 部分
            highlights_section = soup.find(string=re.compile(r"Highlights"))
            if highlights_section:
                result['highlights_found'] = True
                # 尝试解析三个指标
                result = self._parse_highlights(soup, result)

            # 如果找不到数据，尝试从脚本中提取
            if not any([result['intelligence'], result['speed'], result['cost']]):
                result = self._parse_from_scripts(soup, result)

            # 如果还是没有数据，尝试解析表格
            if not any([result['intelligence'], result['speed'], result['cost']]):
                result = self._parse_tables(soup, result)

            # 保存缓存
            self.save_cache("artificial_analysis", result)
            return result

        except Exception as e:
            print(f"     [WARN] Artificial Analysis 抓取失败：{e}")
            return self._load_fallback_cache()

    def _parse_highlights(self, soup, result):
        """解析 Highlights 区域的三个图表"""
        try:
            # 查找 Intelligence、Speed、Cost 相关的文本和数字
            page_text = soup.get_text()

            # 提取智能指数
            intel_matches = re.findall(r'(Claude|GPT|Gemini|Llama|Mistral|Qwen|DeepSeek)[^\d]*(\d{1,3})', page_text)
            for model, score in intel_matches[:10]:
                if int(score) > 0 and int(score) < 100:  # 合理的分数范围
                    result['intelligence'].append({
                        'model': model,
                        'score': int(score)
                    })

            # 提取速度数据（tokens per second）
            speed_matches = re.findall(r'(\w+(?:\s+\w+)?)[^\d]*(\d{2,4})\s*(?:tokens?|tok)\s*(?:per|/)\s*(?:second|sec|s)', page_text, re.IGNORECASE)
            for model, speed in speed_matches[:10]:
                if int(speed) > 10:  # 合理的速度范围
                    result['speed'].append({
                        'model': model.strip(),
                        'tokens_per_sec': int(speed)
                    })

            # 提取成本数据（$ per task）
            cost_matches = re.findall(r'(\w+(?:\s+\w+)?)[^\d]*\$?\s*(\d+\.?\d*)\s*(?:per|/)\s*task', page_text, re.IGNORECASE)
            for model, cost in cost_matches[:10]:
                try:
                    cost_val = float(cost)
                    if cost_val > 0 and cost_val < 10:  # 合理的成本范围
                        result['cost'].append({
                            'model': model.strip(),
                            'cost_per_task': cost_val
                        })
                except:
                    pass

        except Exception as e:
            print(f"     [WARN] Highlights 解析失败：{e}")

        return result

    def _parse_from_scripts(self, soup, result):
        """从页面脚本中提取数据"""

        try:
            # 查找所有 script 标签
            scripts = soup.find_all('script')
            for script in scripts:
                if script.string:
                    # 查找可能包含数据的 JSON
                    json_matches = re.findall(r'\{[^{}]*"(?:model|name|score|speed|cost)"[^{}]*\}', script.string)
                    for match in json_matches:
                        try:
                            data = json.loads(match)
                            # 提取有用的信息
                            if 'score' in data:
                                result['intelligence'].append(data)
                            elif 'speed' in data:
                                result['speed'].append(data)
                            elif 'cost' in data:
                                result['cost'].append(data)
                        except:
                            continue

        except Exception as e:
            print(f"     [WARN] 脚本解析失败：{e}")

        return result

    def _parse_tables(self, soup, result):
        """解析表格数据（降级方案）"""
        try:
            # 查找所有表格
            tables = soup.find_all('table')

            for table in tables:
                rows = table.find_all('tr')

                for row in rows[1:]:  # 跳过表头
                    cells = row.find_all(['td', 'th'])

                    if len(cells) >= 2:
                        model_name = cells[0].get_text(strip=True)
                        value_text = cells[1].get_text(strip=True)

                        # 尝试解析数值
                        try:
                            # 移除非数字字符
                            numeric_value = float(re.sub(r'[^\d.]', '', value_text))

                            # 根据值的范围推断类型
                            if numeric_value > 100:  # 可能是 tokens/sec
                                result["speed"].append({
                                    "model": model_name,
                                    "tokens_per_sec": int(numeric_value)
                                })
                            elif numeric_value < 1:  # 可能是成本
                                result["cost"].append({
                                    "model": model_name,
                                    "cost_per_task": numeric_value
                                })
                            else:  # 可能是分数
                                result["intelligence"].append({
                                    "model": model_name,
                                    "score": int(numeric_value)
                                })
                        except:
                            pass

        except Exception as e:
            print(f"     [WARN] 表格解析失败：{e}")

        return result

    def _load_fallback_cache(self):
        """加载历史缓存作为降级"""
        import glob
        from pathlib import Path

        cache_files = sorted(glob.glob(str(self.cache_dir / "artificial_analysis_*.json")), reverse=True)

        for cache_file in cache_files[:3]:
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                print(f"     [INFO] 使用历史缓存：{Path(cache_file).name}")
                data['is_fallback'] = True
                return data
            except:
                continue

        return {
            "source": "artificial_analysis",
            "error": "无法获取数据",
            "intelligence": [],
            "speed": [],
            "cost": []
        }


def fetch_aa_data():
    """对外接口：获取 Artificial Analysis 数据"""
    scraper = ArtificialAnalysisScraper()
    return scraper.fetch_benchmarks()


if __name__ == "__main__":
    # 测试
    data = fetch_aa_data()
    print(json.dumps(data, indent=2, ensure_ascii=False))

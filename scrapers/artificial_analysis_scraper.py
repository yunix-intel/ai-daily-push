#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Artificial Analysis 数据爬虫 - 抓取模型性能基准数据

解析路线（2026-09 修订）：AA 首页把各榜单以 schema.org Dataset 的
ld+json 结构化数据直埋在 HTML 里（Intelligence / Speed / Cost per Task），
直接解析这些 JSON，不再用"模型名附近抓数字"的正则——旧路线会把正文里
毫不相干的数字（如"Qwen … 3"）当成分数，是垃圾数的来源，已删除。

解析不出（页面改版）时返回空榜 + parsed=False，下游卡片直接隐藏，
绝不拿占位数字填充。
"""
import re
import json
import math
import urllib.request
from datetime import datetime
from .base_scraper import BaseScraper


# 榜单名 →（输出键，数值键别名，排序，取值上限）
_DATASETS = {
    "Intelligence": ("intelligence", ("artificialAnalysisIntelligenceIndex",), True),
    "Artificial Analysis Intelligence Index": ("intelligence", ("intelligenceIndex",), True),
    "Speed": ("speed", ("medianOutputSpeed",), True),
    "Output Speed": ("speed", ("outputSpeed",), True),
    "Cost per Task": ("cost", ("costPerIntelligenceIndexTask",), False),
}

# 输出键 →（结果字段，数值合理范围）
_FIELDS = {
    "intelligence": ("score", 0, 100),
    "speed": ("tokens_per_sec", 1, 20000),
    "cost": ("cost_per_task", 0, 1000),
}


class ArtificialAnalysisScraper(BaseScraper):
    """Artificial Analysis 数据爬虫"""

    def __init__(self):
        super().__init__()
        self.base_url = "https://artificialanalysis.ai"

    def fetch_benchmarks(self):
        """抓取性能基准数据"""
        print("  抓取 Artificial Analysis 数据...")

        cached = self.load_cache("artificial_analysis")
        if cached and self._is_usable_cache(cached):
            return cached
        if cached:
            print("     [WARN] 当日缓存是旧正则路线的垃圾数，忽略并重新直抓")

        try:
            req = urllib.request.Request(
                self.base_url, headers={"User-Agent": self.user_agent})
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                html = response.read().decode('utf-8')

            result = self.parse_homepage(html)
            if result["parsed"]:
                self.save_cache("artificial_analysis", result)
            else:
                print("     [WARN] AA 首页未找到榜单 Dataset，回退历史缓存")
                return self._load_fallback_cache()
            return result

        except Exception as e:
            print(f"     [WARN] Artificial Analysis 抓取失败：{e}")
            return self._load_fallback_cache()

    def parse_homepage(self, html):
        """从首页 HTML 的 ld+json Dataset 块解析三榜，可单测。"""
        result = {
            "source": "artificial_analysis",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "intelligence": [],
            "speed": [],
            "cost": [],
            "datasets_found": [],
            "parsed": False,
        }
        datasets = self._extract_datasets(html)
        for name, payload in datasets.items():
            spec = _DATASETS.get(name)
            if not spec:
                continue
            key, value_keys, descending = spec
            if result[key]:  # 同一榜单有多个 Dataset 块时取第一个（排序即排名）
                continue
            rows = self._clean_rows(payload, value_keys, key)
            if rows:
                rows.sort(key=lambda r: r["_v"], reverse=descending)
                field, _, _ = _FIELDS[key]
                result[key] = [
                    {"model": r["model"], field: r["out"]} for r in rows[:15]
                ]
                result["datasets_found"].append(name)
        result["parsed"] = bool(
            result["intelligence"] or result["speed"] or result["cost"])
        return result

    @staticmethod
    def _extract_datasets(html):
        """抽出所有 @type=Dataset 的 ld+json 块，按 name 去重（首个为准）。"""
        datasets = {}
        for match in re.findall(
                r'<script type="application/ld\+json">(.*?)</script>',
                html, re.S):
            try:
                data = json.loads(match)
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(data, dict) or data.get("@type") != "Dataset":
                continue
            name = data.get("name")
            if name and name not in datasets and isinstance(
                    data.get("data"), list):
                datasets[name] = data["data"]
        return datasets

    @staticmethod
    def _clean_rows(rows, value_keys, key):
        """垃圾数护栏：label 非空、数值有限且在合理范围内；同名去重（保首个）。"""
        field, lo, hi = _FIELDS[key]
        cleaned, seen = [], set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            label = str(row.get("label") or "").strip()
            if not label or not re.search(r"[A-Za-z0-9一-鿿]", label):
                continue
            norm = re.sub(r"\s+", " ", label).lower()
            if norm in seen:
                continue
            value = next((row.get(k) for k in value_keys
                          if isinstance(row.get(k), (int, float))
                          and math.isfinite(row.get(k))), None)
            if value is None or not (lo <= value <= hi):
                continue
            out = round(value, 1) if key in ("intelligence", "speed") \
                else round(value, 4)
            seen.add(norm)
            cleaned.append({"model": label, "out": out, "_v": value})
        return cleaned

    @staticmethod
    def _sane_rows(rows, kind):
        """旧缓存清洗：只要看起来像真实榜单的行。

        旧正则路线产出的典型垃圾：model 是光秃秃的厂商名（Qwen/GPT），
        score 是正文里顺手抓的个位数。真实 Intelligence Index 在 30~60 区间，
        label 带具体型号；速度低于 10 tok/s 的不可能是上榜模型。
        """
        sane = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            model = str(row.get("model") or "").strip()
            if not model:
                continue
            if kind == "intelligence":
                score = row.get("score")
                if isinstance(score, (int, float)) and math.isfinite(score) \
                        and 10 <= score <= 100:
                    sane.append({"model": model, "score": score})
            elif kind == "speed":
                tps = row.get("tokens_per_sec")
                if isinstance(tps, (int, float)) and math.isfinite(tps) \
                        and tps >= 10:
                    sane.append({"model": model, "tokens_per_sec": tps})
            elif kind == "cost":
                cost = row.get("cost_per_task")
                if isinstance(cost, (int, float)) and math.isfinite(cost) \
                        and 0 <= cost <= 1000:
                    sane.append({"model": model, "cost_per_task": cost})
        return sane

    @classmethod
    def _is_usable_cache(cls, cached):
        """新格式（parsed=True）直接可用；旧格式逐行过筛，全灭则不可用。"""
        if not isinstance(cached, dict):
            return False
        if cached.get("parsed") is True:
            return True
        return bool(cls._sane_rows(cached.get("intelligence"), "intelligence")
                    or cls._sane_rows(cached.get("speed"), "speed")
                    or cls._sane_rows(cached.get("cost"), "cost"))

    def _load_fallback_cache(self):
        """加载历史缓存作为降级"""
        import glob
        from pathlib import Path

        cache_files = sorted(glob.glob(str(self.cache_dir / "artificial_analysis_*.json")), reverse=True)

        for cache_file in cache_files[:3]:
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # 历史缓存可能是旧路线的垃圾数，先过筛；全灭就试下一个文件。
                data["intelligence"] = self._sane_rows(
                    data.get("intelligence"), "intelligence")
                data["speed"] = self._sane_rows(data.get("speed"), "speed")
                data["cost"] = self._sane_rows(data.get("cost"), "cost")
                if not (data["intelligence"] or data["speed"] or data["cost"]):
                    continue
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
            "cost": [],
            "parsed": False,
        }


def fetch_aa_data():
    """对外接口：获取 Artificial Analysis 数据"""
    scraper = ArtificialAnalysisScraper()
    return scraper.fetch_benchmarks()


if __name__ == "__main__":
    # 测试
    data = fetch_aa_data()
    print(json.dumps(data, indent=2, ensure_ascii=False))

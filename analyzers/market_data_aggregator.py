#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
市场数据聚合器 - 整合多个数据源
"""
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import glob
import json
from scrapers import fetch_openrouter_data, fetch_aa_data
from .news_metrics_extractor import NewsMetricsExtractor

SNAPSHOT_DIR = Path(__file__).resolve().parent.parent / "data" / "market_data"


def build_token_history(data_dir=None, days=7):
    """从逐日快照拼 Token 总量/份额序列，供趋势呈现。

    只有 total_weekly_tokens > 0 的快照才算有效点（旧快照解析器是死的，
    全是空总量，混进去会把曲线拉成断崖）。文件损坏一律跳过，不抛异常。
    """
    data_dir = Path(data_dir) if data_dir else SNAPSHOT_DIR
    points = []
    try:
        files = sorted(glob.glob(str(data_dir / "openrouter_*.json")))[-days:]
    except OSError:
        return []
    for path in files:
        try:
            with open(path, encoding="utf-8") as f:
                snap = json.load(f)
        except (OSError, ValueError):
            continue
        total = snap.get("total_weekly_tokens") or 0
        if not isinstance(total, (int, float)) or total <= 0:
            continue
        rows = snap.get("token_usage") or []
        points.append({
            "date": snap.get("date") or Path(path).stem.rsplit("_", 1)[-1],
            "total_weekly_tokens": total,
            "top": [{"model": r.get("model", ""),
                     "market_share": r.get("market_share", 0)}
                    for r in rows[:3]
                    if isinstance(r, dict) and r.get("model")],
        })
    return points


def build_token_trend(history):
    """Token 趋势指标：周环比、ARR（年化运行率）及其斜率。

    ARR = 最新周总量 × 52（把单周网关吞吐外推成年化口径，便于跨期比较量级）；
    ARR 斜率 = ARR 相对上一有效点的变化率（×52 在除法中约掉，数值上等于
    相邻两点的周环比，这里如实标注，不包装成新概念）；
    3 点以上再给最小二乘日斜率的年化增速，反映窗口内趋势陡峭程度。
    点不足 2 个时返回空字典，调用方隐藏趋势行，绝不编造斜率。
    """
    pts = [p for p in (history or [])
           if isinstance(p, dict)
           and isinstance(p.get("total_weekly_tokens"), (int, float))
           and p["total_weekly_tokens"] > 0
           and not isinstance(p.get("total_weekly_tokens"), bool)]
    if len(pts) < 2:
        return {}
    first, last = pts[0], pts[-1]
    wow_pct = round((last["total_weekly_tokens"] / first["total_weekly_tokens"] - 1) * 100, 2)
    arr = last["total_weekly_tokens"] * 52
    prev_arr = pts[-2]["total_weekly_tokens"] * 52
    trend = {"wow_pct": wow_pct, "arr": arr,
             "arr_change_pct": (round((arr / prev_arr - 1) * 100, 2)
                                if prev_arr else None),
             "window_days": len(pts),
             "start_date": first.get("date", ""),
             "end_date": last.get("date", "")}
    if len(pts) >= 3:
        n = len(pts)
        mean_x = (n - 1) / 2
        mean_y = sum(p["total_weekly_tokens"] for p in pts) / n
        denom = sum((x - mean_x) ** 2 for x in range(n))
        if denom and mean_y:
            slope = sum((x - mean_x) * (p["total_weekly_tokens"] - mean_y)
                        for x, p in zip(range(n), pts)) / denom
            trend["slope_annualized_pct"] = round(slope * 365 / mean_y * 100, 2)
    return trend


class MarketDataAggregator:
    """市场数据聚合器"""

    def __init__(self):
        self.metrics_extractor = NewsMetricsExtractor()

    def aggregate(self, news_items=None):
        """
        聚合所有数据源

        Args:
            news_items: 新闻列表（可选）

        Returns:
            dict: 聚合后的市场数据
        """
        print("\n=== 市场数据聚合 ===")

        def fetch_source(fetcher, empty):
            try:
                return fetcher()
            except Exception as e:
                self._log_error("市场数据获取", e)
                return empty

        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="market-source") as executor:
            openrouter_future = executor.submit(
                fetch_source, fetch_openrouter_data,
                {"total_models": 0, "rankings": [], "pricing": []}
            )
            aa_future = executor.submit(
                fetch_source, fetch_aa_data,
                {"intelligence": [], "speed": [], "cost": []}
            )
            openrouter_data = openrouter_future.result()
            aa_data = aa_future.result()

        # 3. 提取新闻指标（如果提供了新闻）
        news_metrics = {}
        if news_items:
            print("3. 从新闻中提取指标...")
            try:
                news_metrics = self.metrics_extractor.extract_metrics(news_items)
            except Exception as e:
                self._log_error("新闻指标提取", e)
                news_metrics = self.metrics_extractor._empty_metrics()
        else:
            print("3. 跳过新闻指标提取（无新闻数据）")
            news_metrics = self.metrics_extractor._empty_metrics()

        # 4. 整合数据
        print("4. 整合数据...")
        try:
            aggregated = self._merge_data(openrouter_data, aa_data, news_metrics)
        except Exception as e:
            self._log_error("数据整合", e)
            return self._empty_aggregated()

        # 5. 交叉验证
        print("5. 交叉验证...")
        try:
            aggregated['cross_validation'] = self._cross_validate(
                openrouter_data, news_metrics
            )
        except Exception as e:
            self._log_error("交叉验证", e)
            aggregated['cross_validation'] = {"confirmed": [], "unconfirmed": []}

        print("=== 聚合完成 ===\n")
        return aggregated

    def _log_error(self, context, error):
        """统一的错误日志格式"""
        error_type = type(error).__name__
        print(f"     [ERROR] {context}失败 - {error_type}: {error}")

    def _empty_aggregated(self):
        """返回空的聚合数据结构"""
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "timestamp": datetime.now().isoformat(),
            "market_trends": {
                "total_models": 0,
                "top_models_by_price": [],
                "pricing_summary": {}
            },
            "intelligence_rankings": [],
            "speed_rankings": [],
            "cost_rankings": [],
            "news_metrics": self.metrics_extractor._empty_metrics(),
            "cross_validation": {"confirmed": [], "unconfirmed": []},
            "sources": {
                "openrouter": None,
                "artificial_analysis": None,
                "news_count": 0
            }
        }

    def _merge_data(self, openrouter, aa, news_metrics):
        """合并数据"""
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "timestamp": datetime.now().isoformat(),

            # OpenRouter 数据
            "market_trends": {
                "total_models": openrouter.get("total_models", 0),
                "top_models_by_price": self._extract_top_models(openrouter),
                "pricing_summary": self._summarize_pricing(openrouter),
                # 直抓的周 token 用量（网关口径）：总量 + 各模型份额 + 环比，不走新闻抽取
                "token_usage": openrouter.get("token_usage", []),
                "total_weekly_tokens": openrouter.get("total_weekly_tokens", 0),
                "token_usage_note": openrouter.get("token_usage_note", ""),
                # 多日序列：逐日快照累积的曲线，空快照已在 builder 里滤掉
                "token_history": build_token_history(),
            },

            # Artificial Analysis 数据（去重）
            "intelligence_rankings": self._deduplicate_rankings(aa.get("intelligence", []))[:10],
            "speed_rankings": self._deduplicate_rankings(aa.get("speed", []))[:10],
            "cost_rankings": self._deduplicate_rankings(aa.get("cost", []))[:10],

            # 新闻指标
            "news_metrics": news_metrics,

            # 元数据
            "sources": {
                "openrouter": openrouter.get("date"),
                "artificial_analysis": aa.get("date"),
                "news_count": len(news_metrics.get("revenue", [])) +
                             len(news_metrics.get("funding", [])) +
                             len(news_metrics.get("users", [])) +
                             len(news_metrics.get("token_usage", [])) +
                             len(news_metrics.get("price_changes", []))
            }
        }

    def _deduplicate_rankings(self, rankings):
        """去重排名数据（基于模型名称和分数）"""
        if not rankings:
            return []

        seen = set()
        unique = []

        for rank in rankings:
            model = rank.get("model", "")
            score = rank.get("score", 0)

            # 创建唯一键（标准化模型名称 + 分数）
            normalized_model = self._normalize_model_name(model)
            key = (normalized_model, score)

            if key not in seen and model:  # 确保模型名称不为空
                seen.add(key)
                unique.append(rank)

        return unique

    def _extract_top_models(self, openrouter):
        """提取 Top 模型"""
        rankings = openrouter.get("rankings", [])
        return [
            {
                "model": r.get("model"),
                "price_per_1m_tokens": r.get("price_per_1m_tokens")
            }
            for r in rankings[:10]
        ]

    def _summarize_pricing(self, openrouter):
        """价格摘要统计"""
        pricing = openrouter.get("pricing", [])
        if not pricing:
            return {}

        prices = [p.get("price_per_1m_tokens", 0) for p in pricing if p.get("price_per_1m_tokens", 0) > 0]

        if not prices:
            return {}

        return {
            "min_price": round(min(prices), 4),
            "max_price": round(max(prices), 4),
            "avg_price": round(sum(prices) / len(prices), 4),
            "count": len(prices)
        }

    def _cross_validate(self, openrouter, news_metrics):
        """交叉验证 - 多源印证"""
        validated = {
            "confirmed": [],
            "unconfirmed": []
        }

        # 检查价格变化是否在两个数据源中都有
        price_changes = news_metrics.get("price_changes", [])
        openrouter_models = {
            r.get("model"): r.get("price_per_1m_tokens")
            for r in openrouter.get("rankings", [])
        }

        for change in price_changes:
            model_name = change.get("model", "")
            # 使用模糊匹配
            found_in_or = False
            matched_model = None

            for or_model in openrouter_models.keys():
                if self._fuzzy_match_model(model_name, or_model):
                    found_in_or = True
                    matched_model = or_model
                    break

            if found_in_or:
                validated["confirmed"].append({
                    "type": "price_change",
                    "model": model_name,
                    "matched_with": matched_model,
                    "sources": ["news", "openrouter"]
                })
            else:
                validated["unconfirmed"].append({
                    "type": "price_change",
                    "model": model_name,
                    "sources": ["news"]
                })

        return validated

    def _normalize_model_name(self, name):
        """标准化模型名称用于匹配"""
        import re
        if not name:
            return ""

        # 移除常见前缀
        name = re.sub(r'^(OpenAI|Anthropic|Google|Meta|DeepSeek|Qwen|Alibaba|Tencent|Z\.ai):\s*', '', name, flags=re.I)
        # 统一大小写
        name = name.lower()
        # 移除特殊字符和空格
        name = re.sub(r'[-_\s\.]+', '', name)
        return name

    def _fuzzy_match_model(self, name1, name2, threshold=0.75):
        """模糊匹配两个模型名称"""
        from difflib import SequenceMatcher

        n1 = self._normalize_model_name(name1)
        n2 = self._normalize_model_name(name2)

        if not n1 or not n2:
            return False

        # 检查是否有一个是另一个的子串
        if n1 in n2 or n2 in n1:
            return True

        # 使用序列匹配器计算相似度
        ratio = SequenceMatcher(None, n1, n2).ratio()
        return ratio >= threshold


# 测试函数
def test_aggregator():
    """测试市场数据聚合"""
    aggregator = MarketDataAggregator()

    # 不使用新闻数据测试
    result = aggregator.aggregate()

    print("聚合结果：")
    import json
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    test_aggregator()

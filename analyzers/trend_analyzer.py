#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
趋势分析器 - 对比历史数据
"""
import glob
import json
from pathlib import Path
from datetime import datetime, timedelta


class TrendAnalyzer:
    """趋势分析器"""

    def __init__(self, data_dir="data/market_data"):
        self.data_dir = Path(data_dir)

    def analyze_trends(self, current_data, days_back=7):
        """
        分析趋势（对比历史数据）

        Args:
            current_data: 当前数据
            days_back: 回溯天数

        Returns:
            dict: 趋势分析结果
        """
        # 加载历史数据
        historical = self._load_historical_data(days_back)

        if not historical:
            return {"trends": [], "note": "无足够历史数据"}

        # 分析价格趋势
        price_trends = self._analyze_price_trends(current_data, historical)

        # 分析排名变化
        ranking_trends = self._analyze_ranking_trends(current_data, historical)

        return {
            "period": f"past_{days_back}_days",
            "price_trends": price_trends,
            "ranking_trends": ranking_trends
        }

    def _load_historical_data(self, days_back):
        """加载历史数据"""
        historical = []

        # 查找过去 N 天的缓存文件
        for i in range(1, days_back + 1):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            cache_file = self.data_dir / f"openrouter_{date}.json"

            if cache_file.exists():
                try:
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        historical.append({"date": date, "data": data})
                except:
                    continue

        return historical

    def _analyze_price_trends(self, current, historical):
        """分析价格趋势：与最近一份历史快照对比。

        不跟每一天都比：同一次调价会在 7 天里生成 7 条内容相同的记录，
        调用方还得再去重。要「相比上次有没有变」，最近那份就够了。
        """
        trends = []
        if not historical:
            return trends

        current_prices = {
            r.get("model"): r.get("price_per_1m_tokens", 0)
            for r in current.get("market_trends", {}).get("top_models_by_price", [])
        }

        latest = historical[0]
        hist_prices = {
            r.get("model"): r.get("price_per_1m_tokens", 0)
            for r in (latest.get("data", {}).get("rankings") or [])
        }

        for model, current_price in current_prices.items():
            hist_price = hist_prices.get(model)
            if hist_price and current_price != hist_price:
                change_pct = ((current_price - hist_price) / hist_price) * 100
                trends.append({
                    "model": model,
                    "from_date": latest.get("date"),
                    "old_price": hist_price,
                    "new_price": current_price,
                    "change_percent": round(change_pct, 2)
                })

        return trends

    def _analyze_ranking_trends(self, current, historical):
        """分析模型分布变化：新进榜 / 掉出榜 / 名次移动。

        对比的是最近一份历史快照，不是全部历史——「相比昨天有什么变化」
        才是有信息量的，跟 7 天前逐日对比会产生一堆重复条目。
        原实现只是把当前排名原样返回，那是「当前状态」不是「变化」，
        页面上的「模型分布变化」因此一直没有内容。

        只跟同一数据源比：历史缓存 openrouter_*.json 里的 rankings 存的是
        OpenRouter 口径的模型名（"Tencent: Hy4 preview"），而
        intelligence_rankings 来自 Artificial Analysis，是厂商级名字
        （"Qwen"、"DeepSeek"）。两者交叉比对时没有一个名字能对上，
        会天天报出「全部新进榜 + 全部掉出榜」的假变化。
        """
        empty = {"entered": [], "exited": [], "moved": [], "compared_with": ""}
        if not historical:
            return empty

        # historical 按回溯天数升序追加，第一个就是离今天最近的一天
        latest = historical[0]
        hist_models = [r.get("model") for r in (latest.get("data", {}).get("rankings") or [])
                       if r.get("model")]
        # 当前侧必须用 OpenRouter 口径（价格榜同样出自 openrouter rankings）
        cur_models = [r.get("model") for r in
                      (current.get("market_trends", {}).get("top_models_by_price") or [])
                      if r.get("model")]
        if not hist_models or not cur_models:
            return {**empty, "compared_with": latest.get("date", "")}

        # 名字口径对不上就别报变化：交集为空说明两侧根本不是同一份榜单，
        # 此时算出的 entered/exited 全是噪音。
        if not (set(hist_models) & set(cur_models)):
            return {**empty, "compared_with": latest.get("date", ""),
                    "note": "历史快照与当前榜单口径不一致，跳过分布对比"}

        # 价格榜是历史 rankings 的一个截断子集（只取前 N 名），
        # 直接跟完整历史榜比会把「没进前 N」误报成「掉出榜单」。
        # 把历史侧截到同样长度，比较的才是同一个窗口。
        hist_window = hist_models[:len(cur_models)]

        hist_pos = {m: i for i, m in enumerate(hist_window)}
        cur_pos = {m: i for i, m in enumerate(cur_models)}

        entered = [m for m in cur_models if m not in hist_pos]
        exited = [m for m in hist_window if m not in cur_pos]
        moved = [
            {"model": m, "from_rank": hist_pos[m] + 1, "to_rank": cur_pos[m] + 1,
             "delta": hist_pos[m] - cur_pos[m]}
            for m in cur_models if m in hist_pos and hist_pos[m] != cur_pos[m]
        ]
        moved.sort(key=lambda x: abs(x["delta"]), reverse=True)

        return {
            "entered": entered,
            "exited": exited,
            "moved": moved,
            "compared_with": latest.get("date", ""),
        }


# 测试函数
def test_trend_analyzer():
    """测试趋势分析"""
    analyzer = TrendAnalyzer()

    # 需要先有聚合数据
    from .market_data_aggregator import MarketDataAggregator
    aggregator = MarketDataAggregator()
    current_data = aggregator.aggregate()

    trends = analyzer.analyze_trends(current_data)

    print("趋势分析：")
    import json
    print(json.dumps(trends, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    test_trend_analyzer()

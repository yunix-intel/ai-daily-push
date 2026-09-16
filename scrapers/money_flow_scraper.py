#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
资金流向数据爬虫 - 东方财富数据源
"""
import requests
import json
import re
from datetime import datetime, date
import math
import os
from pathlib import Path


class MoneyFlowScraper:
    """资金流向爬虫"""

    # 东财主站对 http:// 直接回 502，且单个 host 经常抽风，按序做故障转移。
    API_HOSTS = [
        "https://push2delay.eastmoney.com",
        "https://push2.eastmoney.com",
        "https://82.push2.eastmoney.com",
    ]
    UT = 'b2884a393a59ad64002292a3e90d46a5'

    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://data.eastmoney.com/'
        }
        self.timeout = 15
        self.cache_path = Path(os.environ.get(
            "MONEY_FLOW_CACHE", "data/market_data/money_flow_north.json"
        ))

    def _load_cached_north(self, target_date):
        """Return the newest valid cached session not later than target_date."""
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            return None
        records = payload if isinstance(payload, list) else [payload]
        valid = []
        for record in records:
            if not isinstance(record, dict) or not record.get("available"):
                continue
            trade_date = str(record.get("trade_date") or record.get("date") or "")
            if not self._valid_cache_date(trade_date, target_date):
                continue
            item = dict(record)
            item["stale"] = True
            item["collection_mode"] = "cached_post_close"
            item["reason"] = f"实时数据不可用，显示最近有效交易日 {trade_date} 的缓存"
            valid.append(item)
        return max(valid, key=lambda item: item.get("trade_date") or item.get("date")) if valid else None

    @staticmethod
    def _valid_cache_date(trade_date, target_date):
        """只认请求当日（target）的缓存。

        2026-09-16 线上实证：放宽到 <= target 会把 13 天前的旧快照
        当成北向展示。从此宁缺毋滥：日期对不上就当没缓存。
        """
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", trade_date):
            return False
        try:
            date.fromisoformat(trade_date)
            date.fromisoformat(str(target_date))
        except ValueError:
            return False
        return trade_date == str(target_date)

    def _save_cached_north(self, record):
        """Persist only a successful, non-sensitive northbound observation."""
        if not isinstance(record, dict) or not record.get("available"):
            return
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            existing = json.loads(self.cache_path.read_text(encoding="utf-8"))
            records = existing if isinstance(existing, list) else [existing]
        except (OSError, json.JSONDecodeError, TypeError):
            records = []
        trade_date = str(record.get("trade_date") or record.get("date") or "")
        records = [r for r in records if isinstance(r, dict) and
                   str(r.get("trade_date") or r.get("date") or "") != trade_date]
        records.append({k: record.get(k) for k in (
            "date", "trade_date", "prev_trade_date",
            "sh_flow", "sz_flow", "total_flow",
            "sh_turnover", "sz_turnover", "total_turnover",
            "sh_change_pct", "sz_change_pct", "total_change_pct",
            "metric", "available", "collection_mode", "source",
            "reason", "stale"
        )})
        try:
            self.cache_path.write_text(
                json.dumps(records[-30:], ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            # Cache persistence is best effort; a live observation must still
            # be returned when the runner filesystem is read-only.
            return

    def get_turnover_history(self, days=30):
        """北向成交总额历史序列（页面曲线用）：读本地缓存，只收有效总额点。

        缓存按交易日去重保留近 30 条，每日跑批自然累积成序列；不足 2 点
        时调用方隐藏曲线，只展示单日数字+环比。
        """
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            return []
        records = payload if isinstance(payload, list) else [payload]
        points = []
        for record in records:
            if not isinstance(record, dict) or not record.get("available"):
                continue
            day = str(record.get("trade_date") or record.get("date") or "")
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
                continue
            try:
                total = float(record.get("total_turnover"))
            except (TypeError, ValueError):
                continue
            if not math.isfinite(total) or total <= 0:
                continue
            points.append({"date": day, "total": round(total, 2)})
        points.sort(key=lambda point: point["date"])
        return points[-days:]

    def _get_json(self, path, params):
        """按 host 列表依次尝试，第一个成功返回 JSON 的即用。全挂则抛最后一个异常。"""
        last_exc = None
        for host in self.API_HOSTS:
            try:
                response = requests.get(f"{host}{path}", params=params,
                                        headers=self.headers, timeout=self.timeout)
                response.raise_for_status()
                return response.json()
            except Exception as exc:
                last_exc = exc
                continue
        raise last_exc

    def _clist(self, fs, page_size, ascending=False):
        """拉取资金流排行。ascending=True 取净流出榜。

        必须单独请求一次升序：接口本身按 fid 降序返回，
        在降序结果的尾部取「流出」拿到的其实还是净流入的条目。
        """
        params = {
            'pn': '1',
            'pz': str(page_size),
            'po': '0' if ascending else '1',
            'np': '1',
            'ut': self.UT,
            'fltt': '2',
            'invt': '2',
            'fid': 'f62',
            'fs': fs,
            'fields': 'f12,f14,f2,f3,f62,f184',
        }
        data = self._get_json("/api/qt/clist/get", params)
        if not data or not data.get('data') or not data['data'].get('diff'):
            return []
        return data['data']['diff']

    def fetch_north_flow(self, target_date=None):
        """北向资金盘后成交总额（东财 datacenter 为主链路）。

        披露口径（2024 年新规后）：盘中实时净流入停披；盘后只披露成交总额
        （+十大活跃股），净流入连盘后都不再披露。因此本方法只返回成交总额，
        字段为 sh_turnover/sz_turnover/total_turnover（亿元），绝不编造净流入。
        链路：datacenter → eastmoney kamt → 10jqka → 当日缓存 → 空。
        """
        target = self._resolve_target_date(target_date)
        errors = []
        for source, fetcher in (("datacenter", self._fetch_datacenter_post_close),
                                ("eastmoney", self._fetch_eastmoney_post_close),
                                ("10jqka", self._fetch_10jqka_post_close)):
            try:
                result = fetcher(target)
                if result and result.get("available"):
                    result["attempted_sources"] = [source]
                    self._save_cached_north(result)
                    return result
                errors.append(f"{source}:未返回有效盘后数据")
            except Exception as exc:
                errors.append(f"{source}:{type(exc).__name__}")
        cached = self._load_cached_north(target)
        if cached:
            cached["attempted_sources"] = ["datacenter", "eastmoney", "10jqka", "cache"]
            return cached
        return self._empty_north_flow(
            "；".join(errors) or "东方财富和同花顺均未返回有效盘后数据"
        )

    def _resolve_target_date(self, target_date=None):
        if target_date:
            return target_date.isoformat() if hasattr(target_date, "isoformat") else str(target_date)
        current = datetime.now().date()
        try:
            from trading_calendar import get_last_trading_day
            # 日报在北京时间 07:00 运行，当日市场尚未收盘；该函数会从
            # 基准日的前一天开始回溯，因此直接传入今天即可得到最近已收盘交易日。
            return get_last_trading_day(current).isoformat()
        except Exception:
            return current.isoformat()

    def _fetch_datacenter_post_close(self, target_date):
        """东财 datacenter 陆股通成交历史（RPT_MUTUAL_DEAL_HISTORY）。

        通道：001=沪股通，003=深股通，005=北向合计。北向三通道只有 DEAL_AMT
        （成交总额）有数，BUY/SELL/NET 全空——符合交易所新规，不是故障。
        金额单位：均笔成交交叉验证为百万元（DEAL_AMT/DEAL_NUM≈0.042 即
        4.2万元/笔；若为万元则仅 422 元/笔，不合理），转亿元除以 100。
        取不晚于 target 的最新有数交易日，trade_date 如实标注。
        """
        url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
        params = {"sortColumns": "TRADE_DATE,MUTUAL_TYPE", "sortTypes": "-1,-1",
                  "pageSize": "60", "pageNumber": "1",
                  "reportName": "RPT_MUTUAL_DEAL_HISTORY",
                  "columns": "TRADE_DATE,MUTUAL_TYPE,DEAL_AMT,DEAL_NUM",
                  "source": "WEB", "client": "WEB"}
        response = requests.get(url, params=params, headers=self.headers,
                                timeout=self.timeout)
        response.raise_for_status()
        rows = (response.json().get("result") or {}).get("data") or []
        by_date = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            day = str(row.get("TRADE_DATE") or "")[:10]
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
                continue
            if day > str(target_date):
                continue
            by_date.setdefault(day, {})[str(row.get("MUTUAL_TYPE"))] = row
        if not by_date:
            raise ValueError("盘后成交记录为空")
        trade_dates = sorted(by_date, reverse=True)
        trade_date = trade_dates[0]
        day_rows = by_date[trade_date]

        def _turnover(rows, code):
            value = (rows.get(code) or {}).get("DEAL_AMT")
            if not isinstance(value, (int, float)) \
                    or not math.isfinite(value) or value < 0:
                return None
            return round(value / 100, 2)

        sh_turnover = _turnover(day_rows, "001")
        sz_turnover = _turnover(day_rows, "003")
        if sh_turnover is None or sz_turnover is None:
            raise ValueError("当日沪/深通道无有效成交总额")
        total_raw = _turnover(day_rows, "005")
        if total_raw is not None:
            total_turnover = total_raw
        else:
            total_turnover = round(sh_turnover + sz_turnover, 2)

        # 资金流看变动不看绝对值：往前找上一个双通道有数的交易日，算日环比。
        prev_date, sh_prev, sz_prev, total_prev = None, None, None, None
        for day in trade_dates[1:]:
            rows = by_date[day]
            sh_prev, sz_prev = _turnover(rows, "001"), _turnover(rows, "003")
            if sh_prev is None or sz_prev is None:
                continue
            tp = _turnover(rows, "005")
            total_prev = tp if tp is not None else round(sh_prev + sz_prev, 2)
            prev_date = day
            break

        def _pct(now, before):
            if before is None or before == 0:
                return None
            return round((now - before) / before * 100, 2)

        return {"date": trade_date, "trade_date": trade_date,
                "prev_trade_date": prev_date,
                "sh_turnover": sh_turnover, "sz_turnover": sz_turnover,
                "total_turnover": total_turnover,
                "sh_change_pct": _pct(sh_turnover, sh_prev),
                "sz_change_pct": _pct(sz_turnover, sz_prev),
                "total_change_pct": _pct(total_turnover, total_prev),
                "available": True,
                "collection_mode": "post_close",
                "source": "eastmoney_datacenter",
                "metric": "turnover", "reason": "", "stale": False}

    def _fetch_eastmoney_post_close(self, target_date):
        params = {'fields1': 'f1,f2,f3,f4', 'fields2': 'f51,f52,f53,f54,f55,f56',
                  'klt': '101', 'lmt': '30', 'ut': self.UT}
        data = self._get_json("/api/qt/kamt.kline/get", params)
        return self._parse_post_close_kline(data, target_date, "eastmoney")

    def _fetch_10jqka_post_close(self, target_date):
        """读取同花顺公开的北向资金日线接口。"""
        url = "https://data.10jqka.com.cn/hsgt/history/type/north/date/day/"
        response = requests.get(url, headers={**self.headers, "Referer": "https://data.10jqka.com.cn/hsgt/"},
                                timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        daily = ((payload.get("data") or {}).get("zhuri") or {})
        dates = daily.get("date") or []
        index = next((i for i, value in enumerate(dates) if str(value) == target_date), None)
        if index is None:
            raise ValueError("同花顺盘后记录日期不匹配")
        sh = self._optional_num((daily.get("h") or [])[index])
        total = self._optional_num((daily.get("total") or [])[index])
        if sh is None or total is None:
            raise ValueError("同花顺盘后数据不是有限数值")
        sh /= 100000000
        total /= 100000000
        sz = total - sh
        if not all(math.isfinite(value) for value in (sh, sz, total)):
            raise ValueError("同花顺盘后数据不是有限数值")
        return {"date": target_date, "trade_date": target_date,
                "sh_flow": round(sh, 2), "sz_flow": round(sz, 2),
                "total_flow": round(total, 2), "available": True,
                "collection_mode": "post_close", "source": "10jqka",
                "reason": "", "stale": False}

    def _parse_post_close_kline(self, data, target_date, source):
        rows = (data or {}).get("data", {}).get("hk2sh", [])
        sz_rows = (data or {}).get("data", {}).get("hk2sz", [])
        if isinstance(rows, dict):
            rows = [f"{target_date},{rows.get('dayNetAmtIn', 0)},0,0"]
        if isinstance(sz_rows, dict):
            sz_rows = [f"{target_date},{sz_rows.get('dayNetAmtIn', 0)},0,0"]
        sh = next((row for row in rows if str(row).split(",", 1)[0] == target_date), None)
        sz = next((row for row in sz_rows if str(row).split(",", 1)[0] == target_date), None)
        if not sh or not sz:
            raise ValueError("盘后数据日期不匹配")
        sh_value = self._num(str(sh).split(",")[1]) / 100000000
        sz_value = self._num(str(sz).split(",")[1]) / 100000000
        if sh_value == 0 and sz_value == 0:
            raise ValueError("东方财富仅返回北向占位零值")
        return {"date": target_date, "trade_date": target_date,
                "sh_flow": round(sh_value, 2), "sz_flow": round(sz_value, 2),
                "total_flow": round(sh_value + sz_value, 2), "available": True,
                "collection_mode": "post_close", "source": source,
                "reason": "", "stale": False}

    def fetch_sector_flow(self, top_n=5):
        """
        获取行业资金流向

        Args:
            top_n: 返回前 N 个行业

        Returns:
            dict: 行业资金流向数据
        """
        today = datetime.now().strftime("%Y-%m-%d")
        inflow = []
        outflow = []
        errors = []
        try:
            inflow = self._clist('m:90+t:2', top_n)
        except Exception as e:
            errors.append(f"inflow: {e}")
        try:
            outflow = self._clist('m:90+t:2', top_n, ascending=True)
        except Exception as e:
            errors.append(f"outflow: {e}")
        if errors:
            print(f"     [WARN] 行业资金流向部分失败: {'; '.join(errors)}")
        valid_inflow = self._valid_rank_rows(inflow[:top_n])
        valid_outflow = self._valid_rank_rows(outflow[:top_n])
        available = bool(valid_inflow or valid_outflow)
        reason = ""
        if (inflow or outflow) and not available:
            reason = "东方财富返回盘前占位或无效行业资金数据"
        elif not available:
            reason = "; ".join(errors) or "行业资金数据暂不可用"
        return {
            "date": today,
            "top_inflow": [self._shape_flow(x) for x in valid_inflow],
            "top_outflow": [self._shape_flow(x) for x in valid_outflow],
            "available": available,
            "error": "; ".join(errors),
            "reason": reason,
        }

    def fetch_stock_flow(self, top_n=10):
        """
        获取个股资金流向

        Args:
            top_n: 返回前 N 个个股

        Returns:
            dict: 个股资金流向数据
        """
        fs = 'm:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23'
        try:
            inflow = self._clist(fs, top_n)
            outflow = self._clist(fs, top_n, ascending=True)
            valid_inflow = self._valid_rank_rows(inflow[:top_n])
            valid_outflow = self._valid_rank_rows(outflow[:top_n])
            available = bool(valid_inflow or valid_outflow)
            return {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "top_inflow": [self._shape_flow(x, with_code=True) for x in valid_inflow],
                "top_outflow": [self._shape_flow(x, with_code=True) for x in valid_outflow],
                "available": available,
                "reason": "" if available else "东方财富返回盘前占位或无效个股资金数据",
            }
        except Exception as e:
            print(f"     [WARN] 个股资金流向获取失败: {e}")
            return self._empty_stock_flow()

    @staticmethod
    def _optional_num(value):
        """Parse a required Eastmoney numeric field without inventing zero."""
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if math.isfinite(parsed) else None

    @classmethod
    def _valid_rank_rows(cls, rows):
        """Drop pre-open placeholders and malformed ranking rows."""
        valid = []
        for item in rows:
            if not isinstance(item, dict) or not str(item.get('f14') or '').strip():
                continue
            values = [cls._optional_num(item.get(field)) for field in ('f62', 'f3', 'f184')]
            if any(value is None for value in values):
                continue
            valid.append(item)
        # A whole ranking whose market fields are all zero is Eastmoney's
        # pre-open placeholder response, not an observed zero-flow market.
        if valid and not any(
            cls._optional_num(item.get(field)) != 0
            for item in valid for field in ('f62', 'f3', 'f184')
        ):
            return []
        return valid

    @staticmethod
    def _num(value):
        """Parse optional numeric values used by legacy response shapes."""
        try:
            parsed = float(value)
            return parsed if math.isfinite(parsed) else 0.0
        except (TypeError, ValueError):
            return 0.0

    def _shape_flow(self, item, with_code=False):
        """整形单条资金流记录。

        f62 主力净流入（元）→ 亿元；f184 主力净占比（%）；
        f3 涨跌幅在 fltt=2 下已经是百分数，再除 100 会把 +4.4% 变成 +0.04%。
        """
        shaped = {
            "name": item.get('f14', ''),
            "net_inflow": round(self._num(item.get('f62')) / 100000000, 2),
            "change_pct": round(self._num(item.get('f3')), 2),
            "net_ratio": round(self._num(item.get('f184')), 2),
        }
        if with_code:
            shaped["code"] = item.get('f12', '')
        return shaped

    def _parse_north_flow(self, data):
        """解析北向资金数据"""
        try:
            flow_data = (data or {}).get('data') or {}

            # 新版接口按通道拆开：hk2sh / hk2sz 才是「北向」（外资买入 A 股）。
            # dayNetAmtIn 单位为元。
            sh_flow = self._num((flow_data.get('hk2sh') or {}).get('dayNetAmtIn')) / 100000000
            sz_flow = self._num((flow_data.get('hk2sz') or {}).get('dayNetAmtIn')) / 100000000
            total_flow = sh_flow + sz_flow

            # 两个通道都是 0 基本可以断定是停止披露后的占位值，不是「刚好零流入」
            available = bool(sh_flow or sz_flow)
            return {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "sh_flow": round(sh_flow, 2),
                "sz_flow": round(sz_flow, 2),
                "total_flow": round(total_flow, 2),
                "available": available,
                # 带上原因，展示层才能说明「为什么没有」，而不是整块静默消失
                "reason": "" if available else "沪深交易所已停止披露北向资金盘中净流入",
            }

        except Exception as e:
            print(f"     [WARN] 北向资金数据解析失败: {e}")
            return self._empty_north_flow()

    def _empty_north_flow(self, reason="北向资金数据暂不可用"):
        """返回空的北向资金数据"""
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "trade_date": None,
            "sh_flow": 0,
            "sz_flow": 0,
            "total_flow": 0,
            "available": False,
            "collection_mode": "post_close",
            "source": "none",
            "stale": False,
            "reason": reason,
        }

    def _empty_sector_flow(self):
        """返回空的行业资金流向数据"""
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "top_inflow": [],
            "top_outflow": []
        }

    def _empty_stock_flow(self):
        """返回空的个股资金流向数据"""
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "top_inflow": [],
            "top_outflow": []
        }


# 测试函数
def test_scraper():
    """测试爬虫功能"""
    print("=== 资金流向数据测试 ===\n")

    scraper = MoneyFlowScraper()

    print("1. 测试北向资金...")
    north = scraper.fetch_north_flow()
    print(f"   日期: {north['date']}")
    print(f"   沪股通: {north['sh_flow']} 亿元")
    print(f"   深股通: {north['sz_flow']} 亿元")
    print(f"   合计: {north['total_flow']} 亿元\n")

    print("2. 测试行业资金流向（Top 5）...")
    sector = scraper.fetch_sector_flow(top_n=5)
    print(f"   日期: {sector['date']}")
    print(f"   Top 流入: {len(sector['top_inflow'])} 个行业")
    print(f"   Top 流出: {len(sector['top_outflow'])} 个行业")
    if sector['top_inflow']:
        print(f"   最大流入: {sector['top_inflow'][0]['name']} ({sector['top_inflow'][0]['net_inflow']} 亿)\n")

    print("3. 测试个股资金流向（Top 10）...")
    stock = scraper.fetch_stock_flow(top_n=10)
    print(f"   日期: {stock['date']}")
    print(f"   Top 流入: {len(stock['top_inflow'])} 只个股")
    print(f"   Top 流出: {len(stock['top_outflow'])} 只个股")
    if stock['top_inflow']:
        print(f"   最大流入: {stock['top_inflow'][0]['name']} ({stock['top_inflow'][0]['net_inflow']} 亿)")

    print("\n=== 测试完成 ===")


if __name__ == "__main__":
    test_scraper()

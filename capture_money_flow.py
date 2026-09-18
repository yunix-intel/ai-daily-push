#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""盘后资金榜抓拍：收盘后 _clist 返回冻结终值，落盘为次日盘前回退种子。

设计说明（见 CHANGELOG [Unreleased]）：
- 早 07:00 任务在盘前，自身永远抓不到实时榜，只能消费快照；
  本任务在工作日收盘后抓一次，当天终值即次日（及节后首日）的展示数据。
- 只抓榜、只写 data/market_data 缓存：不推送、不发页、不碰其他文件。
- 节假日全天无盘时 _clist 返回占位，fetch_* 内部判定 available=False
  即不落盘，旧快照靠严格同日期 gate 自然失效，前端显示 reason，不造数。
"""
import datetime
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "scrapers"))

from money_flow_scraper import MoneyFlowScraper
from trading_calendar import get_trading_status


def main():
    today = datetime.date.today()
    status = get_trading_status(today, market='A')
    if not status.get('is_trading_day'):
        # 假日/周末：cron 只能排除周末，落在工作日的节假日靠这里拦截。
        # 返回 2 与占位日同语义：workflow 记 warning，不标红、不更新缓存。
        print(f"CAPTURE_SKIP: non-trading day {today} "
              f"({status.get('market_status')}), cache untouched")
        return 2
    scraper = MoneyFlowScraper()
    sector = scraper.fetch_sector_flow(top_n=5)
    stock = scraper.fetch_stock_flow(top_n=10)

    s_top = (sector.get("top_inflow") or [{}])[0]
    k_top = (stock.get("top_inflow") or [{}])[0]
    print(f"sector available={sector.get('available')} "
          f"trade_date={sector.get('trade_date')} "
          f"Top1={s_top.get('name')} {s_top.get('net_inflow')}亿")
    print(f"stock  available={stock.get('available')} "
          f"trade_date={stock.get('trade_date')} "
          f"Top1={k_top.get('name')} {k_top.get('net_inflow')}亿")

    ok = bool(sector.get("available") and stock.get("available"))
    # 占位日（节假日）返回非零退出码，让 workflow 以 warning 留痕而非静默成功。
    print("CAPTURE_OK" if ok else "CAPTURE_EMPTY: placeholder day, cache untouched")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3

from __future__ import annotations

import sys
from datetime import datetime, timedelta

from diagnostic_support import init_mt5_from_env


def _fmt_ts(ts):
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ts)


def _summarize(mt5, items, label, time_attr="time"):
    if items is None:
        print(f"{label}: None last_error={mt5.last_error()}")
        return

    items = list(items)
    print(f"{label}: {len(items)} last_error={mt5.last_error()}")
    if not items:
        return

    tvals = [getattr(item, time_attr, None) for item in items]
    tvals = [value for value in tvals if isinstance(value, (int, float))]
    if tvals:
        print(f"  {label} time_range: {_fmt_ts(min(tvals))} -> {_fmt_ts(max(tvals))}")

    sample = items[-1]
    fields = ["ticket", "order", "position_id", "entry", "type", "symbol", "volume", "price", "time"]
    print("  last_item:", ", ".join(f"{field}={getattr(sample, field)}" for field in fields if hasattr(sample, field)))


def main() -> int:
    mt5 = init_mt5_from_env()
    if not mt5:
        return 1

    try:
        print("initialize", True, "last_error", mt5.last_error())
        account_info = mt5.account_info()
        print("account_info_available", account_info is not None)
        print("now_local", datetime.now())
        print("now_utc  ", datetime.utcnow())

        end_local = datetime.now()
        start_local = end_local - timedelta(days=2)

        _summarize(mt5, mt5.history_deals_get(start_local, end_local), "deals_local")
        _summarize(mt5, mt5.history_orders_get(start_local, end_local), "orders_local")

        today = datetime.now().date()
        noon_start = datetime(today.year, today.month, today.day, 12, 0, 0)
        noon_end = datetime(today.year, today.month, today.day, 13, 0, 0)
        _summarize(mt5, mt5.history_deals_get(noon_start, noon_end), "deals_12_13")
        _summarize(mt5, mt5.history_orders_get(noon_start, noon_end), "orders_12_13")
        return 0
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    sys.exit(main())

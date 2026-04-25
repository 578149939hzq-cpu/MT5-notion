#!/usr/bin/env python3

from __future__ import annotations

import sys
from datetime import datetime, timedelta

from diagnostic_support import init_mt5_from_env


def main() -> int:
    mt5 = init_mt5_from_env()
    if not mt5:
        return 1

    try:
        print("initialize", True, "last_error", mt5.last_error())
        print("now_local", datetime.now())
        print("now_utc  ", datetime.utcnow())

        now_utc = datetime.utcnow()
        for days in [1, 2, 7, 30, 365]:
            start_utc = now_utc - timedelta(days=days)
            deals = mt5.history_deals_get(start_utc, now_utc)
            count = 0 if deals is None else len(deals)
            print("range_utc_days", days, "count", count, "none?", deals is None)
            if deals:
                first = min(deals, key=lambda item: item.time)
                last = max(deals, key=lambda item: item.time)
                print(
                    "  first_time",
                    datetime.fromtimestamp(first.time),
                    "ticket",
                    first.ticket,
                    "entry",
                    first.entry,
                )
                print(
                    "  last_time ",
                    datetime.fromtimestamp(last.time),
                    "ticket",
                    last.ticket,
                    "entry",
                    last.entry,
                )
        return 0
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    sys.exit(main())

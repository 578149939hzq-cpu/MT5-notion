#!/usr/bin/env python3
"""
Inspect MT5 trade data without echoing sensitive account identifiers.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta

from diagnostic_support import init_mt5_from_env, sanitize_output


def main() -> int:
    print("Connecting to MT5...")
    mt5 = init_mt5_from_env()
    if not mt5:
        return 1

    try:
        print("[OK] MT5 connection succeeded")
        print(f"MT5 version: {mt5.version()}")

        account_info = mt5.account_info()
        if account_info:
            print("\nAccount info:")
            print("  [OK] account information is available")
            print(f"  Leverage: {account_info.leverage}")
        else:
            print("[ERROR] account information is unavailable")

        print("\nFetching the last 30 days of trade data...")
        end_time = datetime.now()
        start_time = end_time - timedelta(days=30)
        deals = mt5.history_deals_get(start_time, end_time)
        deals = [] if deals is None else list(deals)
        print(f"Trade records: {len(deals)}")

        if deals:
            entry_in = sum(1 for deal in deals if getattr(deal, "entry", None) == 0)
            entry_out = sum(1 for deal in deals if getattr(deal, "entry", None) == 1)
            other = len(deals) - entry_in - entry_out

            print(f"Entry records: {entry_in}")
            print(f"Exit records: {entry_out}")
            print(f"Other records: {other}")

            print("\nFirst 3 sample records:")
            for index, deal in enumerate(deals[:3], start=1):
                print(f"  Record {index}:")
                print(f"    Ticket: {deal.ticket}")
                print(f"    Symbol: {deal.symbol}")
                print(f"    Side: {'BUY' if deal.type == 0 else 'SELL'}")
                print(f"    Price: {deal.price}")
                print(f"    Volume: {deal.volume}")
                print(f"    Time: {datetime.fromtimestamp(deal.time)}")
                print(f"    Entry flag: {deal.entry}")
        else:
            print("[INFO] No trade records in the last 30 days")

        positions = mt5.positions_get()
        print(f"\nOpen positions: {0 if not positions else len(positions)}")

        orders = mt5.orders_get()
        print(f"Pending orders: {0 if not orders else len(orders)}")

        print("\n[OK] Debug check complete")
        return 0
    except Exception as exc:
        print(f"[ERROR] MT5 debug failed: {sanitize_output(exc)}")
        return 1
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Deeper MT5 data inspection without echoing sensitive account details.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

from diagnostic_support import init_mt5_from_env, sanitize_output


def main() -> int:
    print("Deep MT5 inspection")
    print("=" * 60)

    mt5 = init_mt5_from_env()
    if not mt5:
        return 1

    try:
        account_info = mt5.account_info()
        if account_info:
            print("\nAccount info:")
            print("  [OK] account information is available")
            print(f"  Leverage: {account_info.leverage}")
        else:
            print("[ERROR] account information is unavailable")

        print("\n2. Checking multiple history retrieval methods...")
        total_deals = mt5.history_deals_total()
        print(f"\nMethod 1: history_deals_total() -> {total_deals}")

        try:
            all_deals = mt5.history_deals_get()
            if all_deals:
                entry_in = sum(1 for item in all_deals if item.entry == 0)
                entry_out = sum(1 for item in all_deals if item.entry == 1)
                print(f"Method 2: full history -> {len(all_deals)} records")
                print(f"  ENTRY_IN: {entry_in}")
                print(f"  ENTRY_OUT: {entry_out}")
            else:
                print("Method 2: full history -> empty result")
        except Exception as exc:
            print(f"Method 2 failed: {sanitize_output(exc)}")

        for label, days in (("last 30 days", 30), ("last 365 days", 365)):
            print(f"\nMethod 3: querying {label}...")
            end_time = datetime.now()
            start_time = end_time - timedelta(days=days)
            print(f"  Window: {start_time} -> {end_time}")
            try:
                deals = mt5.history_deals_get(start_time, end_time)
                orders = mt5.history_orders_get(start_time, end_time)
                print(f"  Orders: {0 if orders is None else len(orders)}")
                print(f"  Deals: {0 if deals is None else len(deals)}")
                if deals:
                    for index, deal in enumerate(deals[:5], start=1):
                        print(
                            f"    {index}. ticket={deal.ticket}, time={datetime.fromtimestamp(deal.time)}, "
                            f"symbol={deal.symbol}, side={'BUY' if deal.type == 0 else 'SELL'}"
                        )
            except Exception as exc:
                print(f"  Error: {sanitize_output(exc)}")

        print("\n4. Checking MT5 terminal state...")
        terminal_info = mt5.terminal_info()
        if terminal_info:
            data_path = getattr(terminal_info, "data_path", None)
            print(f"  Trading allowed: {bool(getattr(terminal_info, 'trade_allowed', False))}")

            if data_path:
                history_dir = os.path.join(data_path, "History")
                if os.path.exists(history_dir):
                    print("  [OK] History directory exists")
                    try:
                        subdirs = [
                            item
                            for item in os.listdir(history_dir)
                            if os.path.isdir(os.path.join(history_dir, item))
                        ]
                        print(f"  History subdirectory count: {len(subdirs)}")
                    except Exception as exc:
                        print(f"  Unable to inspect history directory: {sanitize_output(exc)}")
                else:
                    print("  History directory is missing")

        positions = mt5.positions_get()
        orders = mt5.orders_get()
        history = mt5.history_deals_get()
        print("\n5. Current activity summary...")
        print(f"  Open positions: {0 if positions is None else len(positions)}")
        print(f"  Pending orders: {0 if orders is None else len(orders)}")
        print(f"  Historical deals: {0 if history is None else len(history)}")

        print("\n[OK] Deep inspection complete")
        return 0
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    sys.exit(main())

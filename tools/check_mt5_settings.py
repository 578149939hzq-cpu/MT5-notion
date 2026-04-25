#!/usr/bin/env python3
"""
Check local MT5 connectivity and recent data availability.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta

from diagnostic_support import init_mt5_from_env, sanitize_output


def _print_processes() -> None:
    print("1. Checking MT5 processes...")
    try:
        import psutil

        mt5_processes = [
            process
            for process in psutil.process_iter(["name"])
            if process.info["name"] == "terminal64.exe"
        ]
        if mt5_processes:
            print("   [OK] terminal64.exe is running")
            for process in mt5_processes:
                print(f"   Process ID: {process.pid}")
        else:
            print("   [WARNING] terminal64.exe was not found")
    except Exception as exc:
        print(f"   [WARNING] Process check failed: {sanitize_output(exc)}")


def main() -> int:
    print("MT5 settings check")
    print("=" * 50)
    _print_processes()

    print("\n2. Connecting to MT5...")
    mt5 = init_mt5_from_env()
    if not mt5:
        return 1

    try:
        print("   [OK] MT5 connection succeeded")

        account_info = mt5.account_info()
        if account_info:
            print("\n   Account info:")
            print("   [OK] account information is available")
            print(f"   Leverage: {account_info.leverage}")
        else:
            print("   [ERROR] account information is unavailable")

        print("\n3. Checking data sources...")
        end_time = datetime.now()
        start_time = end_time - timedelta(days=7)
        print(f"   Window: {start_time} -> {end_time}")

        orders = mt5.history_orders_get(start_time, end_time)
        deals = mt5.history_deals_get(start_time, end_time)
        print(f"   History orders: {0 if orders is None else len(orders)}")
        print(f"   History deals: {0 if deals is None else len(deals)}")

        positions = mt5.positions_get()
        current_orders = mt5.orders_get()
        print(f"   Open positions: {0 if positions is None else len(positions)}")
        print(f"   Pending orders: {0 if current_orders is None else len(current_orders)}")

        total_orders = mt5.history_orders_total()
        total_deals = mt5.history_deals_total()
        print(f"   Total history orders: {total_orders}")
        print(f"   Total history deals: {total_deals}")

        if deals:
            entry_in = sum(1 for item in deals if getattr(item, "entry", None) == 0)
            entry_out = sum(1 for item in deals if getattr(item, "entry", None) == 1)
            print(f"   Recent entry records: {entry_in}")
            print(f"   Recent exit records: {entry_out}")

        print("\n[OK] Check complete")
        return 0
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    sys.exit(main())

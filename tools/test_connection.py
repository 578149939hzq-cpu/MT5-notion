#!/usr/bin/env python3
"""
MT5 and Notion connection smoke tests.
"""

from __future__ import annotations

import datetime
import os
import sys

from diagnostic_support import ENV_FILE, config_status, init_mt5_from_env, load_project_env, sanitize_output


def test_dependencies() -> bool:
    print("=== Dependency Check ===")

    libraries = {
        "MetaTrader5": "MetaTrader5",
        "notion-client": "notion_client",
        "python-dotenv": "dotenv",
        "pytz": "pytz",
        "requests": "requests",
    }

    missing = []
    for display_name, import_name in libraries.items():
        try:
            __import__(import_name)
            print(f"[OK] {display_name} installed")
        except ImportError:
            print(f"[ERROR] {display_name} missing")
            missing.append(display_name)

    if missing:
        print(f"\nMissing dependencies: {', '.join(missing)}")
        return False

    print("\nAll required dependencies are installed")
    return True


def test_notion_connection() -> bool:
    print("\n=== Notion Connection ===")

    notion_token = os.getenv("NOTION_TOKEN")
    database_id = os.getenv("DATABASE_ID")

    if not notion_token:
        print(f"[ERROR] NOTION_TOKEN not found in {ENV_FILE}")
        return False
    if not database_id:
        print(f"[ERROR] DATABASE_ID not found in {ENV_FILE}")
        return False

    print(config_status("NOTION_TOKEN"))
    print(config_status("DATABASE_ID"))

    try:
        from notion_client import Client

        client = Client(auth=notion_token)
        print("[OK] Notion client initialized")

        try:
            databases = client.search({"filter": {"value": "database", "property": "object"}})["results"]
            print(f"[OK] Search completed, databases visible: {len(databases)}")
        except Exception as exc:
            print(f"[WARNING] Database search failed: {sanitize_output(exc)}")

        return True
    except Exception as exc:
        print(f"[ERROR] Notion connection failed: {sanitize_output(exc)}")
        return False


def test_mt5_connection() -> bool:
    print("\n=== MT5 Connection ===")

    mt5 = init_mt5_from_env()
    if not mt5:
        return False

    try:
        print(f"[OK] MT5 version: {mt5.version()}")
        account_info = mt5.account_info()
        print(f"[OK] Account info available: {account_info is not None}")
        return True
    except Exception as exc:
        print(f"[ERROR] MT5 connection failed: {sanitize_output(exc)}")
        return False
    finally:
        mt5.shutdown()


def test_timezone() -> bool:
    print("\n=== Timezone Handling ===")

    try:
        import pytz

        utc8 = pytz.timezone("Asia/Shanghai")
        print(f"[OK] Timezone loaded: {utc8}")

        now_utc = datetime.datetime.now(datetime.UTC)
        now_utc8 = now_utc.astimezone(utc8)
        print(f"UTC now: {now_utc}")
        print(f"Asia/Shanghai now: {now_utc8}")
        return True
    except Exception as exc:
        print(f"[ERROR] Timezone handling failed: {sanitize_output(exc)}")
        return False


def test_mt5_data() -> bool:
    print("\n=== MT5 Data Access ===")

    mt5 = init_mt5_from_env()
    if not mt5:
        return False

    try:
        end_time = datetime.datetime.now()
        start_time = end_time - datetime.timedelta(hours=24)
        deals = mt5.history_deals_get(start_time, end_time)
        deals = [] if deals is None else list(deals)

        print(f"[OK] Deals in last 24 hours: {len(deals)}")
        closed_deals = [deal for deal in deals if getattr(deal, 'entry', None) in (1, 2, 3)]
        print(f"[OK] Closed-deal-related records in last 24 hours: {len(closed_deals)}")
        return True
    except Exception as exc:
        print(f"[ERROR] MT5 data access failed: {sanitize_output(exc)}")
        return False
    finally:
        mt5.shutdown()


def main() -> int:
    load_project_env()

    print("MT5 to Notion smoke tests")
    print("=" * 50)

    tests = [
        ("Dependencies", test_dependencies()),
        ("Notion", test_notion_connection()),
        ("MT5", test_mt5_connection()),
        ("Timezone", test_timezone()),
        ("MT5 Data", test_mt5_data()),
    ]

    print("\n" + "=" * 50)
    print("Summary:")

    all_passed = True
    for name, passed in tests:
        status = "passed" if passed else "failed"
        print(f"{name}: {status}")
        if not passed:
            all_passed = False

    print("\n" + "=" * 50)
    if all_passed:
        print("SUCCESS: all checks passed.")
        return 0

    print("FAILED: some checks did not pass.")
    print("Install dependencies with: python -m pip install -r requirements.txt")
    return 1


if __name__ == "__main__":
    sys.exit(main())

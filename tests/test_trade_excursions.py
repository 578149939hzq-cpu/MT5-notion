from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from mt5_notion_sync import (
    DEFAULT_FIELD_MAPPING,
    NotionSync,
    SYNC_STATUS_CREATED,
    SYNC_STATUS_DUPLICATE,
    calculate_order_excursion,
)


class StubMT5Client:
    TIMEFRAME_M1 = "M1"
    COPY_TICKS_ALL = 0

    def __init__(self, rates_return=None, ticks_return=None, point: float = 0.1):
        self.rates_return = rates_return
        self.ticks_return = ticks_return
        self.point = point
        self.rates_calls = []
        self.tick_calls = []

    def symbol_info(self, symbol: str):
        return SimpleNamespace(point=self.point)

    def copy_rates_range(self, symbol, timeframe, start, end):
        self.rates_calls.append((symbol, timeframe, start, end))
        return self.rates_return

    def copy_ticks_range(self, symbol, start, end, flags):
        self.tick_calls.append((symbol, start, end, flags))
        return self.ticks_return


class CalculateOrderExcursionTests(unittest.TestCase):
    def test_calculate_order_excursion_uses_m1_range_for_buy_orders(self):
        mt5 = StubMT5Client(rates_return=[{"high": 101.2, "low": 99.7}], point=0.1)
        entry_time = datetime(2026, 1, 1, 10, 15, 30, tzinfo=timezone(timedelta(hours=8)))
        exit_time = datetime(2026, 1, 1, 10, 17, 10, tzinfo=timezone(timedelta(hours=8)))

        excursion = calculate_order_excursion(
            mt5,
            symbol="XAUUSD",
            direction=0,
            entry_price=100.0,
            entry_time=entry_time,
            exit_time=exit_time,
        )

        self.assertEqual(excursion["mfe"], 12.0)
        self.assertEqual(excursion["mae"], 3.0)
        self.assertEqual(len(mt5.rates_calls), 1)
        self.assertEqual(mt5.rates_calls[0][2], datetime(2026, 1, 1, 2, 15, tzinfo=timezone.utc))
        self.assertEqual(mt5.rates_calls[0][3], datetime(2026, 1, 1, 2, 17, tzinfo=timezone.utc))

    def test_calculate_order_excursion_falls_back_to_ticks_for_sell_orders(self):
        mt5 = StubMT5Client(
            rates_return=[],
            ticks_return=[
                {"bid": 97.5, "ask": 98.0},
                {"bid": 101.0, "ask": 101.5},
            ],
            point=0.5,
        )
        entry_time = datetime(2026, 1, 1, 2, 15, tzinfo=timezone.utc)
        exit_time = entry_time + timedelta(seconds=30)

        excursion = calculate_order_excursion(
            mt5,
            symbol="XAUUSD",
            direction=1,
            entry_price=100.0,
            entry_time=entry_time,
            exit_time=exit_time,
        )

        self.assertEqual(excursion["mfe"], 5.0)
        self.assertEqual(excursion["mae"], 3.0)
        self.assertEqual(len(mt5.tick_calls), 1)


class NotionExcursionMappingTests(unittest.TestCase):
    def test_format_update_properties_includes_excursion_fields_when_present(self):
        notion_sync = NotionSync(DEFAULT_FIELD_MAPPING)
        duration_property = DEFAULT_FIELD_MAPPING["duration_hours"]["property"]
        session_property = DEFAULT_FIELD_MAPPING["session"]["property"]
        realized_pnl_property = DEFAULT_FIELD_MAPPING["realized_pnl"]["property"]
        account_property = DEFAULT_FIELD_MAPPING["account_name"]["property"]
        notion_sync.properties = {
            duration_property: {"type": "number"},
            session_property: {"type": "select"},
            realized_pnl_property: {"type": "number"},
            account_property: {"type": "select"},
            "MAE": {"type": "number"},
            "MFE": {"type": "number"},
        }

        props = notion_sync.format_update_properties(
            {
                "duration_hours": 1.236,
                "session": "\u4e9a\u6d32\u76d8",
                "realized_pnl": 23.456,
                "mae": 12.345,
                "mfe": 67.891,
                "account_name": "Primary",
            }
        )

        self.assertEqual(props[duration_property]["number"], 1.24)
        self.assertEqual(props[session_property]["select"]["name"], "\u4e9a\u6d32\u76d8")
        self.assertEqual(props[realized_pnl_property]["number"], 23.46)
        self.assertEqual(props[account_property]["select"]["name"], "Primary")
        self.assertEqual(props["MAE"]["number"], 12.35)
        self.assertEqual(props["MFE"]["number"], 67.89)

    def test_resolve_existing_page_id_caches_duplicate_lookup(self):
        class StubNotionSync(NotionSync):
            def __init__(self):
                super().__init__(DEFAULT_FIELD_MAPPING)
                self.lookup_calls = 0

            def find_existing_page(self, ticket, account_name=None):
                self.lookup_calls += 1
                return {"id": "page-1", "properties": {}}

        notion_sync = StubNotionSync()
        trade = {"ticket": 1, "account_name": "Primary"}

        self.assertEqual(notion_sync.resolve_existing_page_id(trade), "page-1")
        self.assertEqual(notion_sync.resolve_existing_page_id(trade), "page-1")
        self.assertEqual(notion_sync.lookup_calls, 1)

    def test_sync_trades_only_prepares_new_tickets_when_update_is_disabled(self):
        class StubNotionSync(NotionSync):
            def __init__(self):
                super().__init__(DEFAULT_FIELD_MAPPING)
                self.parent = {"type": "database_id", "database_id": "db"}
                self.headers = {"Authorization": "Bearer test"}
                self.sync_delay_seconds = 0

            def find_existing_page(self, ticket, account_name=None):
                if ticket == 1:
                    return {"id": "page-1", "properties": {}}
                return None

            def sync_trade(self, trade):
                if trade["ticket"] == 1:
                    return SYNC_STATUS_DUPLICATE
                return SYNC_STATUS_CREATED

        notion_sync = StubNotionSync()
        prepared_tickets = []

        def before_create(trade):
            prepared_tickets.append(trade["ticket"])
            trade["mae"] = 1.0
            trade["mfe"] = 2.0

        summary = notion_sync.sync_trades(
            [
                {"ticket": 1, "account_name": "Primary"},
                {"ticket": 2, "account_name": "Primary"},
            ],
            before_create=before_create,
        )

        self.assertEqual(prepared_tickets, [2])
        self.assertEqual(summary["duplicate"], 1)
        self.assertEqual(summary["created"], 1)

    def test_sync_trades_prepares_existing_ticket_when_excursion_is_missing_and_updates_enabled(self):
        class StubNotionSync(NotionSync):
            def __init__(self):
                super().__init__(DEFAULT_FIELD_MAPPING)
                self.parent = {"type": "database_id", "database_id": "db"}
                self.headers = {"Authorization": "Bearer test"}
                self.sync_delay_seconds = 0
                self.update_existing = True
                self.properties = {
                    "MAE": {"type": "number"},
                    "MFE": {"type": "number"},
                }

            def find_existing_page(self, ticket, account_name=None):
                return {
                    "id": "page-1",
                    "properties": {
                        "MAE": {"type": "number", "number": None},
                        "MFE": {"type": "number", "number": None},
                    },
                }

            def sync_trade(self, trade):
                return SYNC_STATUS_CREATED

        notion_sync = StubNotionSync()
        prepared_tickets = []

        def before_create(trade):
            prepared_tickets.append(trade["ticket"])
            trade["mae"] = 1.0
            trade["mfe"] = 2.0

        notion_sync.sync_trades(
            [{"ticket": 1, "account_name": "Primary"}],
            before_create=before_create,
        )

        self.assertEqual(prepared_tickets, [1])


if __name__ == "__main__":
    unittest.main()

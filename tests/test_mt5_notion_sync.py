from __future__ import annotations

import json
import os
import shutil
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import mkdtemp
from types import SimpleNamespace
from unittest.mock import patch

import requests

from mt5_notion_sync import (
    AccountConfig,
    DEFAULT_FIELD_MAPPING,
    NotionSync,
    SyncRunResult,
    SyncRuntimeOptions,
    SYNC_STATUS_CREATED,
    SYNC_STATUS_DUPLICATE,
    SYNC_STATUS_FAILED,
    SYNC_STATUS_UPDATED,
    build_sync_summary,
    calculate_realized_pnl,
    calculate_incremental_start_time,
    get_sync_profile_runtime_options,
    get_account_switch_delay_seconds,
    get_incremental_lookback_minutes,
    get_sync_hours,
    load_accounts,
    normalize_sync_status,
    resolve_accounts_file_path,
    resolve_mapping_file_path,
    resolve_project_path,
    run_sync,
    sanitize_diagnostic_text,
    sync_all_accounts,
    tag_session,
)


class PathResolutionTests(unittest.TestCase):
    def make_temp_dir(self) -> Path:
        return Path(mkdtemp(dir=Path(__file__).resolve().parent))

    def test_resolve_project_path_uses_base_dir_for_relative_path(self):
        base_dir = Path("D:/tmp/project")
        self.assertEqual(resolve_project_path("logs/output.log", base_dir), base_dir / "logs" / "output.log")

    def test_resolve_mapping_file_path_uses_explicit_relative_path(self):
        base_dir = Path("D:/tmp/project")
        self.assertEqual(
            resolve_mapping_file_path("config/mapping.md", base_dir),
            base_dir / "config" / "mapping.md",
        )

    def test_resolve_accounts_file_path_defaults_to_project_root(self):
        base_dir = Path("D:/tmp/project")
        self.assertEqual(resolve_accounts_file_path(base_dir=base_dir), base_dir / "accounts.json")

    def test_resolve_mapping_file_path_prefers_existing_default_file(self):
        base_dir = self.make_temp_dir()
        try:
            fallback = base_dir / "claude.md"
            fallback.write_text("demo", encoding="utf-8")
            self.assertEqual(resolve_mapping_file_path(base_dir=base_dir), fallback)
        finally:
            shutil.rmtree(base_dir, ignore_errors=True)

    def test_resolve_mapping_file_path_returns_primary_default_when_missing(self):
        base_dir = self.make_temp_dir()
        try:
            self.assertEqual(resolve_mapping_file_path(base_dir=base_dir), base_dir / "Claude.md")
        finally:
            shutil.rmtree(base_dir, ignore_errors=True)


class AccountLoadingTests(unittest.TestCase):
    def make_temp_dir(self) -> Path:
        return Path(mkdtemp(dir=Path(__file__).resolve().parent))

    def test_load_accounts_reads_multiple_accounts(self):
        base_dir = self.make_temp_dir()
        try:
            accounts_file = base_dir / "accounts.json"
            accounts_file.write_text(
                json.dumps(
                    [
                        {
                            "account_name": "Primary",
                            "login": 123456,
                            "password": "secret-a",
                            "server": "Server-A",
                        },
                        {
                            "account_name": "Secondary",
                            "login": "789012",
                            "password": "secret-b",
                            "server": "Server-B",
                        },
                    ]
                ),
                encoding="utf-8",
            )

            accounts = load_accounts(accounts_file)

            self.assertEqual(
                accounts,
                [
                    AccountConfig("Primary", 123456, "secret-a", "Server-A"),
                    AccountConfig("Secondary", 789012, "secret-b", "Server-B"),
                ],
            )
        finally:
            shutil.rmtree(base_dir, ignore_errors=True)

    def test_accounts_example_file_uses_safe_placeholders(self):
        accounts_example = Path(__file__).resolve().parents[1] / "accounts.example.json"
        payload = json.loads(accounts_example.read_text(encoding="utf-8"))

        self.assertTrue(payload)
        for account in payload:
            self.assertTrue(str(account["account_name"]).startswith("Example-"))
            self.assertTrue(str(account["password"]).startswith("replace-with-your-"))
            self.assertTrue(str(account["server"]).startswith("Your-"))

    def test_load_accounts_rejects_duplicate_account_names(self):
        base_dir = self.make_temp_dir()
        try:
            accounts_file = base_dir / "accounts.json"
            accounts_file.write_text(
                json.dumps(
                    [
                        {
                            "account_name": "Primary",
                            "login": 1,
                            "password": "a",
                            "server": "Server-A",
                        },
                        {
                            "account_name": "Primary",
                            "login": 2,
                            "password": "b",
                            "server": "Server-B",
                        },
                    ]
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                load_accounts(accounts_file)
        finally:
            shutil.rmtree(base_dir, ignore_errors=True)


class SyncSummaryTests(unittest.TestCase):
    def test_build_sync_summary_initializes_all_known_statuses(self):
        self.assertEqual(
            build_sync_summary(),
            {
                SYNC_STATUS_CREATED: 0,
                SYNC_STATUS_UPDATED: 0,
                SYNC_STATUS_DUPLICATE: 0,
                SYNC_STATUS_FAILED: 0,
            },
        )

    def test_normalize_sync_status_falls_back_to_failed(self):
        self.assertEqual(normalize_sync_status("unexpected"), SYNC_STATUS_FAILED)
        self.assertEqual(normalize_sync_status(None), SYNC_STATUS_FAILED)

    def test_sync_trades_counts_each_status_and_unknown_values(self):
        class StubNotionSync(NotionSync):
            def __init__(self, statuses):
                super().__init__(DEFAULT_FIELD_MAPPING)
                self.parent = {"type": "database_id", "database_id": "db"}
                self.headers = {"Authorization": "Bearer test"}
                self.sync_delay_seconds = 0
                self._statuses = iter(statuses)

            def sync_trade(self, trade):
                return next(self._statuses)

        notion_sync = StubNotionSync(
            [
                SYNC_STATUS_CREATED,
                SYNC_STATUS_UPDATED,
                SYNC_STATUS_DUPLICATE,
                SYNC_STATUS_FAILED,
                "unknown-status",
            ]
        )
        summary = notion_sync.sync_trades([{}, {}, {}, {}, {}])

        self.assertEqual(summary[SYNC_STATUS_CREATED], 1)
        self.assertEqual(summary[SYNC_STATUS_UPDATED], 1)
        self.assertEqual(summary[SYNC_STATUS_DUPLICATE], 1)
        self.assertEqual(summary[SYNC_STATUS_FAILED], 2)

    def test_sync_trade_returns_failed_when_duplicate_lookup_errors(self):
        class StubNotionSync(NotionSync):
            def __init__(self):
                super().__init__(DEFAULT_FIELD_MAPPING)
                self.parent = {"type": "database_id", "database_id": "db"}
                self.headers = {"Authorization": "Bearer test"}

            def find_existing_page_id(self, ticket, account_name=None):
                raise RuntimeError(f"query failed for {ticket}/{account_name}")

        notion_sync = StubNotionSync()
        status = notion_sync.sync_trade({"ticket": 42, "account_name": "Primary"})

        self.assertEqual(status, SYNC_STATUS_FAILED)

    def test_sync_trades_skips_in_batch_duplicates_before_second_sync_attempt(self):
        class StubNotionSync(NotionSync):
            def __init__(self):
                super().__init__(DEFAULT_FIELD_MAPPING)
                self.parent = {"type": "database_id", "database_id": "db"}
                self.headers = {"Authorization": "Bearer test"}
                self.sync_delay_seconds = 0
                self.synced_tickets = []

            def sync_trade(self, trade):
                self.synced_tickets.append((trade["account_name"], trade["ticket"]))
                return SYNC_STATUS_CREATED

        notion_sync = StubNotionSync()
        summary = notion_sync.sync_trades(
            [
                {"ticket": 42, "account_name": "Primary"},
                {"ticket": "42", "account_name": "Primary"},
                {"ticket": 42, "account_name": "Secondary"},
            ]
        )

        self.assertEqual(
            notion_sync.synced_tickets,
            [("Primary", 42), ("Secondary", 42)],
        )
        self.assertEqual(summary[SYNC_STATUS_CREATED], 2)
        self.assertEqual(summary[SYNC_STATUS_DUPLICATE], 1)


class SyncWindowTests(unittest.TestCase):
    def test_get_sync_hours_defaults_to_recent_week(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(get_sync_hours(), 7 * 24)

    def test_get_sync_hours_still_allows_explicit_override(self):
        with patch.dict(os.environ, {"SYNC_DAYS": "3", "SYNC_HOURS": "24"}, clear=True):
            self.assertEqual(get_sync_hours(), 3 * 24)

    def test_get_incremental_lookback_minutes_defaults_and_override(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(get_incremental_lookback_minutes(), 5.0)
        with patch.dict(os.environ, {"SYNC_LOOKBACK_MINUTES": "12.5"}, clear=True):
            self.assertEqual(get_incremental_lookback_minutes(), 12.5)

    def test_get_account_switch_delay_seconds_defaults_and_override(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(get_account_switch_delay_seconds(), 2.5)
        with patch.dict(os.environ, {"ACCOUNT_SWITCH_DELAY_SECONDS": "3"}, clear=True):
            self.assertEqual(get_account_switch_delay_seconds(), 3.0)

    def test_calculate_incremental_start_time_uses_latest_synced_with_overlap(self):
        latest_synced = datetime(2026, 4, 20, 12, 0, tzinfo=timezone.utc)
        now_utc = datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc)

        start_time = calculate_incremental_start_time(
            latest_synced_time=latest_synced,
            fallback_hours=24,
            overlap_minutes=7.5,
            now_utc=now_utc,
        )

        self.assertEqual(start_time, latest_synced - timedelta(minutes=7.5))

    def test_calculate_incremental_start_time_falls_back_when_no_history(self):
        now_utc = datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc)
        start_time = calculate_incremental_start_time(
            latest_synced_time=None,
            fallback_hours=6,
            overlap_minutes=5,
            now_utc=now_utc,
        )

        self.assertEqual(start_time, now_utc - timedelta(hours=6))


class RuntimeOptionTests(unittest.TestCase):
    def test_get_sync_profile_runtime_options_returns_incremental_defaults(self):
        options = get_sync_profile_runtime_options("incremental")

        self.assertEqual(options, SyncRuntimeOptions(profile_name="incremental", skip_mae_mfe=True))

    def test_get_sync_profile_runtime_options_returns_reconcile_defaults(self):
        options = get_sync_profile_runtime_options("reconcile")

        self.assertEqual(
            options,
            SyncRuntimeOptions(profile_name="reconcile", skip_mae_mfe=False, update_existing=True),
        )

    def test_run_sync_returns_structured_failure_when_required_env_is_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            result = run_sync()

        self.assertIsInstance(result, SyncRunResult)
        self.assertEqual(result.exit_code, 1)
        self.assertIn("NOTION_TOKEN", result.error_message or "")
        self.assertEqual(result.summary, build_sync_summary())


class NotionQueryTests(unittest.TestCase):
    def test_request_retries_transient_status_before_succeeding_without_sleep_when_backoff_is_zero(self):
        class StubResponse:
            def __init__(self, status_code, payload=None, text=""):
                self.status_code = status_code
                self._payload = payload or {}
                self.text = text or json.dumps(self._payload)

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise requests.HTTPError(f"status={self.status_code}", response=self)

            def json(self):
                return self._payload

        with patch.dict(
            os.environ,
            {
                "NOTION_HTTP_MAX_RETRIES": "2",
                "NOTION_HTTP_RETRY_BACKOFF_SECONDS": "0",
            },
            clear=False,
        ):
            notion_sync = NotionSync(DEFAULT_FIELD_MAPPING)

        notion_sync.headers = {"Authorization": "Bearer test"}
        with patch("requests.request", side_effect=[StubResponse(429), StubResponse(200, {"ok": True})]) as request_mock:
            with patch("time.sleep") as sleep_mock:
                response = notion_sync._request("GET", "https://api.notion.com/v1/databases/test")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(request_mock.call_count, 2)
        sleep_mock.assert_not_called()

    def test_request_retries_transient_status_before_succeeding_with_positive_backoff(self):
        class StubResponse:
            def __init__(self, status_code, payload=None, text=""):
                self.status_code = status_code
                self._payload = payload or {}
                self.text = text or json.dumps(self._payload)

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise requests.HTTPError(f"status={self.status_code}", response=self)

            def json(self):
                return self._payload

        with patch.dict(
            os.environ,
            {
                "NOTION_HTTP_MAX_RETRIES": "2",
                "NOTION_HTTP_RETRY_BACKOFF_SECONDS": "0.25",
            },
            clear=False,
        ):
            notion_sync = NotionSync(DEFAULT_FIELD_MAPPING)

        notion_sync.headers = {"Authorization": "Bearer test"}
        with patch("requests.request", side_effect=[StubResponse(429), StubResponse(200, {"ok": True})]) as request_mock:
            with patch("time.sleep") as sleep_mock:
                response = notion_sync._request("GET", "https://api.notion.com/v1/databases/test")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(request_mock.call_count, 2)
        sleep_mock.assert_called_once_with(0.25)

    def test_request_does_not_retry_permanent_auth_errors(self):
        class StubResponse:
            def __init__(self, status_code):
                self.status_code = status_code
                self.text = "{}"

            def raise_for_status(self):
                raise requests.HTTPError(f"status={self.status_code}", response=self)

        notion_sync = NotionSync(DEFAULT_FIELD_MAPPING)
        notion_sync.headers = {"Authorization": "Bearer test"}

        with patch("requests.request", return_value=StubResponse(401)) as request_mock:
            with self.assertRaises(requests.HTTPError):
                notion_sync._request("GET", "https://api.notion.com/v1/databases/test")

        self.assertEqual(request_mock.call_count, 1)

    def test_find_existing_page_filters_by_ticket_and_account_name(self):
        class StubNotionSync(NotionSync):
            def __init__(self):
                super().__init__(DEFAULT_FIELD_MAPPING)
                self.parent = {"type": "database_id", "database_id": "db"}
                self.headers = {"Authorization": "Bearer test"}
                self.captured_filter = None

            def _query(self, filter_obj=None, page_size=1, sorts=None):
                self.captured_filter = filter_obj
                return {"results": []}

        notion_sync = StubNotionSync()
        notion_sync.find_existing_page(123, account_name="Primary")

        self.assertEqual(
            notion_sync.captured_filter,
            {
                "and": [
                    {
                        "property": DEFAULT_FIELD_MAPPING["ticket"]["property"],
                        "number": {"equals": 123},
                    },
                    {
                        "property": DEFAULT_FIELD_MAPPING["account_name"]["property"],
                        "select": {"equals": "Primary"},
                    },
                ]
            },
        )

    def test_find_latest_account_sync_time_parses_latest_date(self):
        class StubNotionSync(NotionSync):
            def __init__(self):
                super().__init__(DEFAULT_FIELD_MAPPING)
                self.parent = {"type": "database_id", "database_id": "db"}
                self.headers = {"Authorization": "Bearer test"}

            def _query(self, filter_obj=None, page_size=1, sorts=None):
                return {
                    "results": [
                        {
                            "properties": {
                                DEFAULT_FIELD_MAPPING["time_utc8"]["property"]: {
                                    "type": "date",
                                    "date": {"start": "2026-04-20T15:00:00+08:00"},
                                }
                            }
                        }
                    ]
                }

        notion_sync = StubNotionSync()
        latest = notion_sync.find_latest_account_sync_time("Primary")

        self.assertEqual(latest, datetime(2026, 4, 20, 7, 0, tzinfo=timezone.utc))

    def test_sync_trade_caches_created_page_for_later_duplicate_checks(self):
        class StubResponse:
            status_code = 200
            text = "{}"

            def raise_for_status(self):
                return None

            def json(self):
                return {"id": "page-created", "properties": {}}

        notion_sync = NotionSync(DEFAULT_FIELD_MAPPING)
        notion_sync.parent = {"type": "database_id", "database_id": "db"}
        notion_sync.headers = {"Authorization": "Bearer test"}
        notion_sync.properties = {
            DEFAULT_FIELD_MAPPING["account_name"]["property"]: {"type": "select", "select": {"options": []}},
        }

        trade = {
            "ticket": 42,
            "symbol": "XAUUSD",
            "direction": "多",
            "time_utc8": datetime(2026, 1, 1, 9, 30),
            "entry_price": 3300.5,
            "exit_price": 3310.5,
            "sl": 3290.0,
            "tp": 3320.0,
            "volume": 0.2,
            "account_name": "Primary",
        }

        with patch("requests.request", return_value=StubResponse()):
            status = notion_sync.sync_trade(trade)

        self.assertEqual(status, SYNC_STATUS_CREATED)
        self.assertEqual(notion_sync.find_existing_page_id(42, account_name="Primary"), "page-created")


class FormattingTests(unittest.TestCase):
    def test_calculate_realized_pnl_sums_net_components(self):
        deal = SimpleNamespace(profit=125.5, commission=-3.2, swap=1.1, fee=-0.4)

        self.assertEqual(calculate_realized_pnl(deal), 123.0)

    def test_sanitize_diagnostic_text_redacts_known_identifiers_and_paths(self):
        with patch.dict(
            os.environ,
            {
                "DATABASE_ID": "00000000-0000-0000-0000-000000000000",
                "NOTION_TOKEN": "secret_token_value",
            },
            clear=False,
        ):
            raw = (
                "400 Client Error for url: "
                "https://api.notion.com/v1/databases/00000000-0000-0000-0000-000000000000/query "
                "token=secret_token_value "
                "path=C:\\Users\\demo\\AppData\\Roaming\\MetaQuotes\\Terminal\\ABC123"
            )

            sanitized = sanitize_diagnostic_text(raw)

        self.assertNotIn("00000000-0000-0000-0000-000000000000", sanitized)
        self.assertNotIn("secret_token_value", sanitized)
        self.assertNotIn("C:\\Users\\demo\\AppData\\Roaming\\MetaQuotes\\Terminal\\ABC123", sanitized)
        self.assertIn("https://api.notion.com/v1/databases/<database-id>/query", sanitized)
        self.assertIn("<notion-token>", sanitized)
        self.assertIn("<mt5-data-path>", sanitized)

    def test_tag_session_maps_expected_windows(self):
        self.assertEqual(tag_session(datetime(2026, 1, 1, 8, 0)), "\u4e9a\u6d32\u76d8")
        self.assertEqual(tag_session(datetime(2026, 1, 1, 16, 0)), "\u4f26\u6566\u76d8")
        self.assertEqual(tag_session(datetime(2026, 1, 1, 21, 0)), "\u7ebd\u7ea6\u76d8")
        self.assertEqual(tag_session(datetime(2026, 1, 1, 5, 0)), "\u5176\u4ed6")
        self.assertIsNone(tag_session(None))

    def test_format_trade_to_notion_includes_optional_fields_when_schema_supports_them(self):
        notion_sync = NotionSync(DEFAULT_FIELD_MAPPING)
        notion_sync.properties = {
            DEFAULT_FIELD_MAPPING["duration_hours"]["property"]: {"type": "number"},
            DEFAULT_FIELD_MAPPING["session"]["property"]: {"type": "select"},
            DEFAULT_FIELD_MAPPING["realized_pnl"]["property"]: {"type": "number"},
            DEFAULT_FIELD_MAPPING["account_name"]["property"]: {"type": "select"},
        }
        trade = {
            "ticket": 123456,
            "symbol": "XAUUSD",
            "direction": "\u591a",
            "time_utc8": datetime(2026, 1, 1, 9, 30),
            "entry_price": 3300.5,
            "exit_price": 3310.5,
            "sl": 3290.0,
            "tp": 3320.0,
            "volume": 0.2,
            "duration_hours": 2.75,
            "session": "\u4e9a\u6d32\u76d8",
            "realized_pnl": 45.678,
            "account_name": "Primary",
        }

        payload = notion_sync.format_trade_to_notion(trade)
        properties = payload["properties"]

        self.assertEqual(properties[DEFAULT_FIELD_MAPPING["symbol"]["property"]]["title"][0]["text"]["content"], "XAUUSD")
        self.assertEqual(properties[DEFAULT_FIELD_MAPPING["direction"]["property"]]["select"]["name"], "\u591a")
        self.assertEqual(properties[DEFAULT_FIELD_MAPPING["ticket"]["property"]]["number"], 123456)
        self.assertEqual(
            properties[DEFAULT_FIELD_MAPPING["duration_hours"]["property"]]["number"],
            2.75,
        )
        self.assertEqual(
            properties[DEFAULT_FIELD_MAPPING["session"]["property"]]["select"]["name"],
            "\u4e9a\u6d32\u76d8",
        )
        self.assertEqual(
            properties[DEFAULT_FIELD_MAPPING["realized_pnl"]["property"]]["number"],
            45.68,
        )
        self.assertEqual(
            properties[DEFAULT_FIELD_MAPPING["account_name"]["property"]]["select"]["name"],
            "Primary",
        )

    def test_format_trade_to_notion_requires_account_name(self):
        notion_sync = NotionSync(DEFAULT_FIELD_MAPPING)
        notion_sync.properties = {}
        trade = {
            "ticket": 1,
            "symbol": "XAUUSD",
            "direction": "\u591a",
            "time_utc8": datetime(2026, 1, 1, 9, 30),
            "entry_price": 1.0,
            "exit_price": 2.0,
            "sl": None,
            "tp": None,
            "volume": 0.1,
            "account_name": None,
        }

        with self.assertRaises(ValueError):
            notion_sync.format_trade_to_notion(trade)


class MultiAccountSyncTests(unittest.TestCase):
    def test_sync_all_accounts_continues_after_login_failure(self):
        class StubMT5Connector:
            def __init__(self):
                self.login_attempts = []

            def is_terminal_connected(self):
                return True

            def login_account(self, account):
                self.login_attempts.append(account.account_name)
                return account.account_name != "Bad"

            def get_recent_closed_trades(self, **kwargs):
                account_name = kwargs["account_name"]
                return [{"ticket": 1001, "account_name": account_name}]

            def populate_trade_excursion(self, trade):
                trade["mae"] = 1.0
                trade["mfe"] = 2.0
                return trade

        class StubNotionSync:
            def __init__(self):
                self.synced_accounts = []

            def find_latest_account_sync_time(self, account_name):
                return None

            def sync_trades(self, trades, before_create=None):
                for trade in trades:
                    if before_create:
                        before_create(trade)
                self.synced_accounts.append(trades[0]["account_name"])
                return {
                    SYNC_STATUS_CREATED: len(trades),
                    SYNC_STATUS_UPDATED: 0,
                    SYNC_STATUS_DUPLICATE: 0,
                    SYNC_STATUS_FAILED: 0,
                }

        accounts = [
            AccountConfig("Bad", 1, "secret-a", "Server-A"),
            AccountConfig("Good", 2, "secret-b", "Server-B"),
        ]

        summary, account_failures = sync_all_accounts(
            accounts=accounts,
            mt5_connector=StubMT5Connector(),
            notion_sync=StubNotionSync(),
            fallback_hours=24,
            overlap_minutes=5.0,
            switch_delay_seconds=0,
        )

        self.assertEqual(summary[SYNC_STATUS_CREATED], 1)
        self.assertEqual(account_failures, 1)


if __name__ == "__main__":
    unittest.main()

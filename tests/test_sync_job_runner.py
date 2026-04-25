from __future__ import annotations

import json
import os
import shutil
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import mkdtemp
from unittest.mock import patch


TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import sync_job_runner
from mt5_notion_sync import SyncRunResult, build_sync_summary


class SyncJobRunnerTests(unittest.TestCase):
    def make_temp_dir(self) -> Path:
        return Path(mkdtemp(dir=Path(__file__).resolve().parent))

    @staticmethod
    def write_accounts_file(path: Path) -> None:
        path.write_text(
            json.dumps(
                [
                    {
                        "account_name": "Primary",
                        "login": 123456,
                        "password": "secret",
                        "server": "Server-A",
                    }
                ]
            ),
            encoding="utf-8",
        )

    def test_run_profile_records_preflight_failure_before_worker_start(self):
        temp_dir = self.make_temp_dir()
        try:
            accounts_file = temp_dir / "accounts.json"
            self.write_accounts_file(accounts_file)
            paths = sync_job_runner.build_automation_paths(temp_dir, accounts_value="accounts.json")

            with patch.object(sync_job_runner, "run_sync") as run_sync_mock:
                exit_code = sync_job_runner.run_profile("incremental", paths=paths)

            self.assertEqual(exit_code, 1)
            run_sync_mock.assert_not_called()

            state = sync_job_runner.read_status_file(paths.status_file)
            profile_state = state["profiles"]["incremental"]
            self.assertEqual(profile_state["last_run_status"], sync_job_runner.RUN_STATUS_PREFLIGHT_FAILED)
            self.assertIn(".env", profile_state["last_error_message"])
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_run_profile_skips_when_active_lock_exists(self):
        temp_dir = self.make_temp_dir()
        try:
            (temp_dir / ".env").write_text("", encoding="utf-8")
            accounts_file = temp_dir / "accounts.json"
            self.write_accounts_file(accounts_file)
            paths = sync_job_runner.build_automation_paths(temp_dir, accounts_value="accounts.json")
            sync_job_runner.ensure_state_dir(paths)
            paths.lock_file.write_text(
                json.dumps({"pid": 999, "hostname": "demo", "profile": "incremental"}, ensure_ascii=False),
                encoding="utf-8",
            )

            with patch.object(sync_job_runner, "run_sync") as run_sync_mock:
                exit_code = sync_job_runner.run_profile(
                    "incremental",
                    paths=paths,
                    process_alive_checker=lambda pid: True,
                )

            self.assertEqual(exit_code, 0)
            run_sync_mock.assert_not_called()

            state = sync_job_runner.read_status_file(paths.status_file)
            profile_state = state["profiles"]["incremental"]
            self.assertEqual(profile_state["last_run_status"], sync_job_runner.RUN_STATUS_SKIPPED_BY_LOCK)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_run_profile_reclaims_stale_lock_and_persists_success(self):
        temp_dir = self.make_temp_dir()
        try:
            (temp_dir / ".env").write_text("", encoding="utf-8")
            accounts_file = temp_dir / "accounts.json"
            self.write_accounts_file(accounts_file)
            paths = sync_job_runner.build_automation_paths(temp_dir, accounts_value="accounts.json")
            sync_job_runner.ensure_state_dir(paths)
            paths.lock_file.write_text(
                json.dumps({"pid": 999, "hostname": "demo", "profile": "incremental"}, ensure_ascii=False),
                encoding="utf-8",
            )

            started_at = datetime(2026, 4, 23, 10, 0, tzinfo=timezone.utc)
            finished_at = started_at + timedelta(minutes=1)
            result = SyncRunResult(
                exit_code=0,
                summary={
                    "created": 1,
                    "updated": 0,
                    "duplicate": 0,
                    "failed": 0,
                },
                account_failures=0,
                error_message=None,
                started_at=started_at,
                finished_at=finished_at,
                profile_name="incremental",
            )

            with patch.object(sync_job_runner, "run_sync", return_value=result) as run_sync_mock:
                exit_code = sync_job_runner.run_profile(
                    "incremental",
                    paths=paths,
                    process_alive_checker=lambda pid: False,
                )

            self.assertEqual(exit_code, 0)
            run_sync_mock.assert_called_once()
            self.assertFalse(paths.lock_file.exists())

            state = sync_job_runner.read_status_file(paths.status_file)
            profile_state = state["profiles"]["incremental"]
            self.assertEqual(profile_state["last_run_status"], sync_job_runner.RUN_STATUS_SUCCESS)
            self.assertEqual(profile_state["last_summary"]["created"], 1)
            self.assertEqual(profile_state["last_success_at"], finished_at.isoformat())
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_run_health_check_fails_for_stale_profile_and_sends_alert(self):
        temp_dir = self.make_temp_dir()
        try:
            paths = sync_job_runner.build_automation_paths(temp_dir, accounts_value="accounts.json")
            sync_job_runner.write_json_file(
                paths.status_file,
                {
                    "version": 1,
                    "profiles": {
                        "incremental": {
                            "last_success_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
                        }
                    },
                },
            )

            with patch.dict(os.environ, {"SYNC_ALERT_WEBHOOK_URL": "https://example.invalid"}, clear=False):
                with patch.object(sync_job_runner, "send_alert_event") as send_alert_mock:
                    exit_code = sync_job_runner.run_health_check("incremental", paths=paths)

            self.assertEqual(exit_code, 1)
            send_alert_mock.assert_called_once()
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_run_health_check_passes_when_recent_success_exists(self):
        temp_dir = self.make_temp_dir()
        try:
            paths = sync_job_runner.build_automation_paths(temp_dir, accounts_value="accounts.json")
            sync_job_runner.write_json_file(
                paths.status_file,
                {
                    "version": 1,
                    "profiles": {
                        "incremental": {
                            "last_success_at": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
                        }
                    },
                },
            )

            with patch.object(sync_job_runner, "send_alert_event") as send_alert_mock:
                exit_code = sync_job_runner.run_health_check("incremental", paths=paths)

            self.assertEqual(exit_code, 0)
            send_alert_mock.assert_not_called()
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

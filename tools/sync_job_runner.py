#!/usr/bin/env python3
"""
Automation runner for scheduled MT5 -> Notion sync jobs.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mt5_notion_sync import (
    ENV_FILE,
    build_sync_summary,
    get_sync_profile_runtime_options,
    load_accounts,
    resolve_accounts_file_path,
    run_sync,
    sanitize_diagnostic_text,
)


logger = logging.getLogger(__name__)
STATE_DIR = PROJECT_ROOT / "state"
LOCK_FILE = STATE_DIR / "mt5_sync.lock"
STATUS_FILE = STATE_DIR / "mt5_sync_status.json"
RUN_STATUS_SUCCESS = "success"
RUN_STATUS_FAILED = "failed"
RUN_STATUS_PREFLIGHT_FAILED = "preflight_failed"
RUN_STATUS_SKIPPED_BY_LOCK = "skipped_by_lock"
DEFAULT_PROFILE_STALE_MINUTES = {
    "incremental": 20,
    "reconcile": 36 * 60,
}


@dataclass(frozen=True)
class AutomationPaths:
    project_root: Path
    env_file: Path
    accounts_file: Path
    state_dir: Path
    lock_file: Path
    status_file: Path


@dataclass(frozen=True)
class LockAcquisition:
    acquired: bool
    payload: Dict[str, object]
    stale_reclaimed: bool = False


@dataclass(frozen=True)
class HealthCheckEvaluation:
    healthy: bool
    exit_code: int
    message: str
    last_success_at: Optional[datetime]
    stale_after_seconds: int


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def isoformat_or_none(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


def parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def build_automation_paths(
    project_root: Path = PROJECT_ROOT,
    *,
    accounts_value: Optional[str] = None,
) -> AutomationPaths:
    resolved_project_root = Path(project_root).resolve()
    accounts_file = resolve_accounts_file_path(
        accounts_value if accounts_value is not None else os.getenv("ACCOUNTS_FILE"),
        base_dir=resolved_project_root,
    )
    state_dir = resolved_project_root / "state"
    return AutomationPaths(
        project_root=resolved_project_root,
        env_file=resolved_project_root / ENV_FILE.name,
        accounts_file=accounts_file,
        state_dir=state_dir,
        lock_file=state_dir / LOCK_FILE.name,
        status_file=state_dir / STATUS_FILE.name,
    )


def ensure_state_dir(paths: AutomationPaths) -> None:
    paths.state_dir.mkdir(parents=True, exist_ok=True)


def read_json_file(path: Path, *, default: Optional[Dict[str, object]] = None) -> Dict[str, object]:
    if not path.exists():
        return dict(default or {})
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_file(path: Path, payload: Dict[str, object]) -> None:
    ensure_parent = path.parent
    ensure_parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    temp_path.replace(path)


def read_status_file(status_file: Path) -> Dict[str, object]:
    state = read_json_file(status_file, default={"profiles": {}, "version": 1})
    state.setdefault("profiles", {})
    state.setdefault("version", 1)
    return state


def get_profile_stale_after_seconds(profile_name: str) -> int:
    default_minutes = DEFAULT_PROFILE_STALE_MINUTES[profile_name]
    env_name = f"SYNC_HEALTH_STALE_MINUTES_{profile_name.upper()}"
    value = os.getenv(env_name)
    if not value:
        return default_minutes * 60
    return max(1, int(float(value) * 60))


def is_process_alive(pid: int) -> bool:
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def build_lock_payload(profile_name: str) -> Dict[str, object]:
    return {
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "profile": profile_name,
        "acquired_at": utc_now().isoformat(),
    }


def read_lock_payload(lock_file: Path) -> Dict[str, object]:
    try:
        payload = read_json_file(lock_file)
    except Exception as exc:
        logger.warning("Failed to parse lock file %s: %s", lock_file, sanitize_diagnostic_text(exc))
        return {}
    return payload


def acquire_singleton_lock(
    paths: AutomationPaths,
    profile_name: str,
    *,
    process_alive_checker: Callable[[int], bool] = is_process_alive,
) -> LockAcquisition:
    ensure_state_dir(paths)

    for reclaim_attempt in range(2):
        payload = build_lock_payload(profile_name)
        try:
            fd = os.open(paths.lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            existing_payload = read_lock_payload(paths.lock_file)
            existing_pid = existing_payload.get("pid")
            if existing_pid is not None:
                try:
                    pid_int = int(existing_pid)
                except (TypeError, ValueError):
                    pid_int = None
                if pid_int is not None and process_alive_checker(pid_int):
                    return LockAcquisition(acquired=False, payload=existing_payload, stale_reclaimed=False)

            logger.warning("Reclaiming stale lock file: %s", paths.lock_file)
            try:
                paths.lock_file.unlink()
            except FileNotFoundError:
                pass
            continue
        else:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            return LockAcquisition(acquired=True, payload=payload, stale_reclaimed=bool(reclaim_attempt))

    existing_payload = read_lock_payload(paths.lock_file)
    return LockAcquisition(acquired=False, payload=existing_payload, stale_reclaimed=False)


def release_singleton_lock(paths: AutomationPaths, acquisition: LockAcquisition) -> None:
    if not acquisition.acquired:
        return
    if not paths.lock_file.exists():
        return

    current_payload = read_lock_payload(paths.lock_file)
    if current_payload and current_payload != acquisition.payload:
        logger.warning("Skipping lock release because lock ownership changed: %s", paths.lock_file)
        return

    try:
        paths.lock_file.unlink()
    except FileNotFoundError:
        pass


def persist_profile_state(
    paths: AutomationPaths,
    profile_name: str,
    *,
    run_status: str,
    exit_code: int,
    error_message: Optional[str],
    summary: Optional[Dict[str, int]],
    account_failures: int,
    started_at: datetime,
    finished_at: datetime,
) -> None:
    state = read_status_file(paths.status_file)
    profiles = state.setdefault("profiles", {})
    profile_state = dict(profiles.get(profile_name) or {})
    last_success_at = profile_state.get("last_success_at")

    if run_status == RUN_STATUS_SUCCESS:
        last_success_at = isoformat_or_none(finished_at)

    profile_state.update(
        {
            "profile_name": profile_name,
            "last_run_status": run_status,
            "last_run_started_at": isoformat_or_none(started_at),
            "last_run_finished_at": isoformat_or_none(finished_at),
            "last_exit_code": exit_code,
            "last_error_message": error_message,
            "last_summary": dict(summary or build_sync_summary()),
            "last_account_failures": account_failures,
            "last_success_at": last_success_at,
            "updated_at": isoformat_or_none(utc_now()),
        }
    )
    profiles[profile_name] = profile_state
    write_json_file(paths.status_file, state)


def send_alert_event(event: Dict[str, object]) -> bool:
    webhook_url = os.getenv("SYNC_ALERT_WEBHOOK_URL")
    if not webhook_url:
        return False

    request = urllib.request.Request(
        webhook_url,
        data=json.dumps(event, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30):
        return True


def maybe_send_alert(event: Dict[str, object]) -> None:
    if not os.getenv("SYNC_ALERT_WEBHOOK_URL"):
        return

    try:
        send_alert_event(event)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        logger.warning("Failed to send sync alert: %s", sanitize_diagnostic_text(exc))


def build_alert_event(
    event_type: str,
    profile_name: str,
    *,
    message: str,
    exit_code: Optional[int] = None,
    last_success_at: Optional[datetime] = None,
    threshold_seconds: Optional[int] = None,
) -> Dict[str, object]:
    return {
        "event_type": event_type,
        "profile": profile_name,
        "message": message,
        "exit_code": exit_code,
        "last_success_at": isoformat_or_none(last_success_at),
        "threshold_seconds": threshold_seconds,
        "hostname": socket.gethostname(),
        "emitted_at": utc_now().isoformat(),
    }


def preflight_error(paths: AutomationPaths) -> Optional[str]:
    if not paths.env_file.exists():
        return f"Local env file not found: {paths.env_file}"
    if not paths.accounts_file.exists():
        return f"Accounts file not found: {paths.accounts_file}"

    try:
        load_accounts(paths.accounts_file)
    except Exception as exc:
        return f"Accounts file is invalid: {sanitize_diagnostic_text(exc)}"

    return None


def evaluate_profile_health(
    profile_name: str,
    paths: AutomationPaths,
    *,
    now_utc: Optional[datetime] = None,
) -> HealthCheckEvaluation:
    current_time = now_utc or utc_now()
    stale_after_seconds = get_profile_stale_after_seconds(profile_name)

    if not paths.status_file.exists():
        return HealthCheckEvaluation(
            healthy=False,
            exit_code=1,
            message=f"Status file not found: {paths.status_file}",
            last_success_at=None,
            stale_after_seconds=stale_after_seconds,
        )

    try:
        state = read_status_file(paths.status_file)
    except Exception as exc:
        return HealthCheckEvaluation(
            healthy=False,
            exit_code=1,
            message=f"Failed to read status file: {sanitize_diagnostic_text(exc)}",
            last_success_at=None,
            stale_after_seconds=stale_after_seconds,
        )

    profile_state = (state.get("profiles") or {}).get(profile_name) or {}
    last_success_at = parse_iso_datetime(profile_state.get("last_success_at"))
    if last_success_at is None:
        return HealthCheckEvaluation(
            healthy=False,
            exit_code=1,
            message=f"No successful sync recorded yet for profile {profile_name}",
            last_success_at=None,
            stale_after_seconds=stale_after_seconds,
        )

    age_seconds = (current_time - last_success_at).total_seconds()
    if age_seconds > stale_after_seconds:
        return HealthCheckEvaluation(
            healthy=False,
            exit_code=1,
            message=(
                f"Latest successful sync for profile {profile_name} is stale: "
                f"{int(age_seconds)}s old > {stale_after_seconds}s threshold"
            ),
            last_success_at=last_success_at,
            stale_after_seconds=stale_after_seconds,
        )

    return HealthCheckEvaluation(
        healthy=True,
        exit_code=0,
        message=f"Profile {profile_name} is healthy",
        last_success_at=last_success_at,
        stale_after_seconds=stale_after_seconds,
    )


def run_profile(
    profile_name: str,
    *,
    paths: Optional[AutomationPaths] = None,
    process_alive_checker: Callable[[int], bool] = is_process_alive,
) -> int:
    get_sync_profile_runtime_options(profile_name)
    paths = paths or build_automation_paths()
    started_at = utc_now()

    error_message = preflight_error(paths)
    if error_message:
        logger.error("[ERROR] Preflight failed for %s: %s", profile_name, error_message)
        finished_at = utc_now()
        try:
            persist_profile_state(
                paths,
                profile_name,
                run_status=RUN_STATUS_PREFLIGHT_FAILED,
                exit_code=1,
                error_message=error_message,
                summary=build_sync_summary(),
                account_failures=0,
                started_at=started_at,
                finished_at=finished_at,
            )
        except Exception as exc:
            logger.error("[ERROR] Failed to write run state after preflight error: %s", sanitize_diagnostic_text(exc))
            maybe_send_alert(
                build_alert_event(
                    "state_write_failed",
                    profile_name,
                    message=f"Failed to persist run state: {sanitize_diagnostic_text(exc)}",
                    exit_code=1,
                )
            )
            return 1

        maybe_send_alert(
            build_alert_event("preflight_failed", profile_name, message=error_message, exit_code=1)
        )
        return 1

    acquisition = acquire_singleton_lock(paths, profile_name, process_alive_checker=process_alive_checker)
    if not acquisition.acquired:
        message = f"Skipped profile {profile_name} because another sync run is active"
        logger.info(message)
        finished_at = utc_now()
        try:
            persist_profile_state(
                paths,
                profile_name,
                run_status=RUN_STATUS_SKIPPED_BY_LOCK,
                exit_code=0,
                error_message=message,
                summary=build_sync_summary(),
                account_failures=0,
                started_at=started_at,
                finished_at=finished_at,
            )
        except Exception as exc:
            logger.error("[ERROR] Failed to write run state after lock skip: %s", sanitize_diagnostic_text(exc))
            maybe_send_alert(
                build_alert_event(
                    "state_write_failed",
                    profile_name,
                    message=f"Failed to persist lock-skip state: {sanitize_diagnostic_text(exc)}",
                    exit_code=1,
                )
            )
            return 1
        return 0

    try:
        runtime_options = get_sync_profile_runtime_options(profile_name)
        result = run_sync(runtime_options=runtime_options)
        run_status = RUN_STATUS_SUCCESS if result.exit_code == 0 else RUN_STATUS_FAILED

        try:
            persist_profile_state(
                paths,
                profile_name,
                run_status=run_status,
                exit_code=result.exit_code,
                error_message=result.error_message,
                summary=result.summary,
                account_failures=result.account_failures,
                started_at=result.started_at,
                finished_at=result.finished_at,
            )
        except Exception as exc:
            logger.error("[ERROR] Failed to write run state: %s", sanitize_diagnostic_text(exc))
            maybe_send_alert(
                build_alert_event(
                    "state_write_failed",
                    profile_name,
                    message=f"Failed to persist run state: {sanitize_diagnostic_text(exc)}",
                    exit_code=1,
                )
            )
            return 1

        if result.exit_code != 0:
            maybe_send_alert(
                build_alert_event(
                    "sync_failed",
                    profile_name,
                    message=result.error_message or "Sync failed",
                    exit_code=result.exit_code,
                    last_success_at=evaluate_profile_health(profile_name, paths).last_success_at,
                )
            )
        return result.exit_code
    finally:
        release_singleton_lock(paths, acquisition)


def run_health_check(profile_name: str, *, paths: Optional[AutomationPaths] = None) -> int:
    get_sync_profile_runtime_options(profile_name)
    paths = paths or build_automation_paths()
    evaluation = evaluate_profile_health(profile_name, paths)
    if evaluation.healthy:
        logger.info(evaluation.message)
        return 0

    logger.error("[ERROR] %s", evaluation.message)
    maybe_send_alert(
        build_alert_event(
            "stale_sync",
            profile_name,
            message=evaluation.message,
            exit_code=evaluation.exit_code,
            last_success_at=evaluation.last_success_at,
            threshold_seconds=evaluation.stale_after_seconds,
        )
    )
    return evaluation.exit_code


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run or check scheduled MT5 sync jobs.")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run a sync profile")
    run_parser.add_argument("--profile", default="incremental", choices=sorted(DEFAULT_PROFILE_STALE_MINUTES))

    health_parser = subparsers.add_parser("health-check", help="Evaluate sync freshness from state only")
    health_parser.add_argument("--profile", default="incremental", choices=sorted(DEFAULT_PROFILE_STALE_MINUTES))

    parser.set_defaults(command="run", profile="incremental")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)

    if args.command == "health-check":
        return run_health_check(args.profile)
    return run_profile(args.profile)


if __name__ == "__main__":
    sys.exit(main())

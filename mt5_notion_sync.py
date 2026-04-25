#!/usr/bin/env python3
"""
Sync closed MT5 trades into a Notion database.
"""

from __future__ import annotations

import logging
import os
import sys
import time
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, Optional

import pytz
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent
LOG_DIR = PROJECT_ROOT / "logs"
ENV_FILE = PROJECT_ROOT / ".env"
ACCOUNTS_FILE = PROJECT_ROOT / "accounts.json"
DEFAULT_MAPPING_FILES = ("Claude.md", "claude.md")

TIMEZONE = "Asia/Shanghai"
DEAL_ENTRY_IN = 0
DEAL_ENTRY_OUT = 1
DEAL_ENTRY_INOUT = 2
DEAL_ENTRY_OUT_BY = 3
ENTRY_LOOKBACK_DAYS = 30
DEFAULT_SYNC_DAYS = 7
DEFAULT_SYNC_HOURS = DEFAULT_SYNC_DAYS * 24
DEFAULT_INCREMENTAL_LOOKBACK_MINUTES = 5.0
DEFAULT_ACCOUNT_SWITCH_DELAY_SECONDS = 2.5
DEFAULT_MT5_RECOVERY_DELAY_SECONDS = 3.0
BUY_DIRECTION_LABEL = "\u591a"
SELL_DIRECTION_LABEL = "\u7a7a"
NOTION_RESOURCE_URL_RE = re.compile(r"https://api\.notion\.com/v1/(databases|data_sources|pages)/[A-Za-z0-9-]+")
MT5_DATA_PATH_RE = re.compile(r"[A-Za-z]:\\Users\\[^\\\s]+\\AppData\\Roaming\\MetaQuotes\\Terminal\\[^\\\s]+")

SYNC_STATUS_CREATED = "created"
SYNC_STATUS_UPDATED = "updated"
SYNC_STATUS_DUPLICATE = "duplicate"
SYNC_STATUS_FAILED = "failed"
SYNC_STATUS_ORDER = (
    SYNC_STATUS_CREATED,
    SYNC_STATUS_UPDATED,
    SYNC_STATUS_DUPLICATE,
    SYNC_STATUS_FAILED,
)
DEFAULT_NOTION_HTTP_TIMEOUT_SECONDS = 30.0
DEFAULT_NOTION_HTTP_MAX_RETRIES = 3
DEFAULT_NOTION_HTTP_RETRY_BACKOFF_SECONDS = 1.0
RETRIABLE_NOTION_HTTP_STATUS_CODES = {429, 500, 502, 503, 504}

DEFAULT_FIELD_MAPPING = {
    "symbol": {"property": "交易标的", "type": "title", "required": True},
    "direction": {"property": "方向", "type": "select", "required": True},
    "time_utc8": {"property": "交易日期", "type": "date", "required": True},
    "entry_price": {"property": "入场价格", "type": "number", "required": True},
    "exit_price": {"property": "实际出场", "type": "number", "required": True},
    "sl": {"property": "止损", "type": "number", "required": True},
    "tp": {"property": "止盈", "type": "number", "required": True},
    "volume": {"property": "仓位", "type": "number", "required": True},
    "ticket": {"property": "订单ID", "type": "number", "required": True},
    "duration_hours": {"property": "持仓时长(小时)", "type": "number", "required": False},
    "session": {"property": "交易时段", "type": "select", "required": False},
    "realized_pnl": {"property": "实现盈亏", "type": "number", "required": False},
    "mae": {"property": "MAE", "type": "number", "required": False},
    "mfe": {"property": "MFE", "type": "number", "required": False},
    "account_name": {"property": "\u6240\u5c5e\u8d26\u6237", "type": "select", "required": True},
}


@dataclass(frozen=True)
class AccountConfig:
    account_name: str
    login: int
    password: str
    server: str


@dataclass(frozen=True)
class SyncRuntimeOptions:
    profile_name: Optional[str] = None
    skip_mae_mfe: Optional[bool] = None
    update_existing: Optional[bool] = None


@dataclass(frozen=True)
class SyncRunResult:
    exit_code: int
    summary: Dict[str, int]
    account_failures: int
    error_message: Optional[str]
    started_at: datetime
    finished_at: datetime
    profile_name: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "profile_name": self.profile_name,
            "exit_code": self.exit_code,
            "summary": dict(self.summary),
            "account_failures": self.account_failures,
            "error_message": self.error_message,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
        }


SYNC_PROFILE_OPTIONS = {
    "incremental": SyncRuntimeOptions(profile_name="incremental", skip_mae_mfe=True),
    "reconcile": SyncRuntimeOptions(profile_name="reconcile", skip_mae_mfe=False, update_existing=True),
}


def sanitize_diagnostic_text(value: object) -> str:
    text = str(value)

    for env_name, replacement in (
        ("DATABASE_ID", "<database-id>"),
        ("NOTION_TOKEN", "<notion-token>"),
    ):
        env_value = os.getenv(env_name)
        if env_value:
            text = text.replace(env_value, replacement)

    text = NOTION_RESOURCE_URL_RE.sub(
        lambda match: f"https://api.notion.com/v1/{match.group(1)}/<redacted>",
        text,
    )
    text = MT5_DATA_PATH_RE.sub("<mt5-data-path>", text)
    return text


def format_exception_message(exc: BaseException) -> str:
    return sanitize_diagnostic_text(exc)


def is_truthy_value(value: object) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def load_project_env(env_file: Path = ENV_FILE) -> None:
    load_dotenv(dotenv_path=env_file)


def resolve_project_path(path_value: os.PathLike | str, base_dir: Path = PROJECT_ROOT) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return base_dir / path


def resolve_mapping_file_path(
    mapping_value: Optional[str] = None, base_dir: Path = PROJECT_ROOT
) -> Path:
    if mapping_value:
        return resolve_project_path(mapping_value, base_dir)

    for candidate_name in DEFAULT_MAPPING_FILES:
        candidate = base_dir / candidate_name
        if candidate.exists():
            return candidate

    return base_dir / DEFAULT_MAPPING_FILES[0]


def resolve_accounts_file_path(
    accounts_value: Optional[str] = None, base_dir: Path = PROJECT_ROOT
) -> Path:
    if accounts_value:
        return resolve_project_path(accounts_value, base_dir)
    return base_dir / ACCOUNTS_FILE.name


def load_accounts(file_path: Path) -> list[AccountConfig]:
    if not file_path.exists():
        raise FileNotFoundError(f"Accounts file not found: {file_path}")

    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Failed to parse accounts file {file_path}: {exc}") from exc

    if not isinstance(payload, list) or not payload:
        raise ValueError("Accounts file must contain a non-empty JSON array")

    accounts = []
    seen_names = set()
    required_fields = ("account_name", "login", "password", "server")
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Account entry #{index} must be an object")

        missing_fields = [field for field in required_fields if item.get(field) in (None, "")]
        if missing_fields:
            raise ValueError(f"Account entry #{index} is missing required fields: {', '.join(missing_fields)}")

        account_name = str(item["account_name"]).strip()
        if not account_name:
            raise ValueError(f"Account entry #{index} has an empty account_name")
        if account_name in seen_names:
            raise ValueError(f"Duplicate account_name found in accounts file: {account_name}")
        seen_names.add(account_name)

        try:
            login = int(item["login"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Account {account_name} has an invalid login value: {item['login']!r}") from exc

        accounts.append(
            AccountConfig(
                account_name=account_name,
                login=login,
                password=str(item["password"]),
                server=str(item["server"]),
            )
        )

    return accounts


def configure_logging(log_dir: Path = LOG_DIR) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "mt5_notion_sync.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(),
        ],
        force=True,
    )
    return logging.getLogger(__name__)


load_project_env()
logger = configure_logging()
MAPPING_FILE = resolve_mapping_file_path(os.getenv("MAPPING_FILE"))


def build_sync_summary() -> Dict[str, int]:
    return {status: 0 for status in SYNC_STATUS_ORDER}


def resolve_update_existing(override: Optional[bool] = None) -> bool:
    if override is not None:
        return bool(override)
    return is_truthy_value(os.getenv("UPDATE_EXISTING", ""))


def get_sync_profile_runtime_options(profile_name: str) -> SyncRuntimeOptions:
    normalized_name = str(profile_name or "").strip().lower()
    if normalized_name not in SYNC_PROFILE_OPTIONS:
        raise ValueError(
            f"Unknown sync profile: {profile_name!r}. Available profiles: {', '.join(sorted(SYNC_PROFILE_OPTIONS))}"
        )
    return SYNC_PROFILE_OPTIONS[normalized_name]


def normalize_sync_status(status: Optional[str]) -> str:
    if status in SYNC_STATUS_ORDER:
        return status
    return SYNC_STATUS_FAILED


def get_sync_hours() -> int:
    this_week = os.getenv("SYNC_THIS_WEEK")
    if is_truthy_value(this_week):
        tz = pytz.timezone(TIMEZONE)
        now_cn = datetime.now(tz)
        week_start_cn = now_cn.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
            days=now_cn.weekday()
        )
        now_utc = datetime.now(timezone.utc)
        week_start_utc = week_start_cn.astimezone(pytz.utc)
        seconds = (now_utc - week_start_utc).total_seconds()
        hours = int(seconds // 3600)
        return max(1, hours + 1)

    months = os.getenv("SYNC_MONTHS")
    if months:
        return int(float(months) * 30 * 24)

    days = os.getenv("SYNC_DAYS")
    if days:
        return int(float(days) * 24)

    hours = os.getenv("SYNC_HOURS")
    if hours:
        return int(float(hours))

    return DEFAULT_SYNC_HOURS


def get_incremental_lookback_minutes() -> float:
    value = os.getenv("SYNC_LOOKBACK_MINUTES")
    if not value:
        return DEFAULT_INCREMENTAL_LOOKBACK_MINUTES
    return max(0.0, float(value))


def get_account_switch_delay_seconds() -> float:
    value = os.getenv("ACCOUNT_SWITCH_DELAY_SECONDS")
    if not value:
        return DEFAULT_ACCOUNT_SWITCH_DELAY_SECONDS
    return max(0.0, float(value))


def should_skip_mae_mfe(override: Optional[bool] = None) -> bool:
    if override is not None:
        return bool(override)
    return is_truthy_value(os.getenv("SKIP_MAE_MFE", ""))


def get_notion_http_timeout_seconds() -> float:
    value = os.getenv("NOTION_HTTP_TIMEOUT_SECONDS")
    if not value:
        return DEFAULT_NOTION_HTTP_TIMEOUT_SECONDS
    return max(1.0, float(value))


def get_notion_http_max_retries() -> int:
    value = os.getenv("NOTION_HTTP_MAX_RETRIES")
    if not value:
        return DEFAULT_NOTION_HTTP_MAX_RETRIES
    return max(0, int(float(value)))


def get_notion_http_retry_backoff_seconds() -> float:
    value = os.getenv("NOTION_HTTP_RETRY_BACKOFF_SECONDS")
    if not value:
        return DEFAULT_NOTION_HTTP_RETRY_BACKOFF_SECONDS
    return max(0.0, float(value))


def ensure_utc_datetime(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def to_naive_utc(value: datetime) -> datetime:
    normalized = ensure_utc_datetime(value)
    if normalized is None:
        raise ValueError("Expected datetime value")
    return normalized.replace(tzinfo=None)


def calculate_incremental_start_time(
    latest_synced_time: Optional[datetime],
    fallback_hours: int,
    overlap_minutes: float,
    now_utc: Optional[datetime] = None,
) -> datetime:
    effective_now = ensure_utc_datetime(now_utc) or datetime.now(timezone.utc)
    latest = ensure_utc_datetime(latest_synced_time)
    if latest is None:
        return effective_now - timedelta(hours=max(0.0, float(fallback_hours)))

    latest = min(latest, effective_now)
    return latest - timedelta(minutes=max(0.0, overlap_minutes))


def merge_sync_summaries(target: Dict[str, int], source: Dict[str, int]) -> Dict[str, int]:
    for status in SYNC_STATUS_ORDER:
        target[status] = int(target.get(status, 0)) + int(source.get(status, 0))
    return target


def floor_to_minute(value: datetime) -> datetime:
    return value.replace(second=0, microsecond=0)


def _get_item_field(item, field_name: str):
    if isinstance(item, dict):
        return item.get(field_name)
    try:
        return item[field_name]
    except Exception:
        return getattr(item, field_name, None)


def _coerce_positive_float(value: object) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    return number


def _extract_rate_bounds(rates) -> Optional[tuple[float, float]]:
    if rates is None or len(rates) == 0:
        return None

    highs = []
    lows = []
    for rate in rates:
        high = _coerce_positive_float(_get_item_field(rate, "high"))
        low = _coerce_positive_float(_get_item_field(rate, "low"))
        if high is not None:
            highs.append(high)
        if low is not None:
            lows.append(low)

    if not highs or not lows:
        return None
    return max(highs), min(lows)


def _extract_tick_bounds(ticks) -> Optional[tuple[float, float]]:
    if ticks is None or len(ticks) == 0:
        return None

    highs = []
    lows = []
    for tick in ticks:
        prices = []
        for field_name in ("last", "bid", "ask"):
            price = _coerce_positive_float(_get_item_field(tick, field_name))
            if price is not None:
                prices.append(price)
        if not prices:
            continue
        highs.append(max(prices))
        lows.append(min(prices))

    if not highs or not lows:
        return None
    return max(highs), min(lows)


def _copy_rates_range(mt5_client, symbol: str, start_dt_utc: datetime, end_dt_utc: datetime):
    timeframe_m1 = getattr(mt5_client, "TIMEFRAME_M1", None)
    if timeframe_m1 is None:
        return None

    for start_value, end_value in (
        (start_dt_utc, end_dt_utc),
        (int(start_dt_utc.timestamp()), int(end_dt_utc.timestamp())),
    ):
        try:
            rates = mt5_client.copy_rates_range(symbol, timeframe_m1, start_value, end_value)
            if rates is not None:
                return rates
        except Exception:
            continue

    return None


def _copy_ticks_range(mt5_client, symbol: str, start_dt_utc: datetime, end_dt_utc: datetime):
    tick_flags = getattr(mt5_client, "COPY_TICKS_ALL", None)
    if tick_flags is None:
        return None

    tick_end_dt_utc = end_dt_utc if end_dt_utc > start_dt_utc else start_dt_utc + timedelta(seconds=1)
    for start_value, end_value in (
        (start_dt_utc, tick_end_dt_utc),
        (int(start_dt_utc.timestamp()), int(tick_end_dt_utc.timestamp())),
    ):
        try:
            ticks = mt5_client.copy_ticks_range(symbol, start_value, end_value, tick_flags)
            if ticks is not None:
                return ticks
        except Exception:
            continue

    return None


def calculate_order_excursion(
    mt5_client,
    symbol: str,
    direction,
    entry_price: Optional[float],
    entry_time: Optional[datetime],
    exit_time: Optional[datetime],
) -> Dict[str, float]:
    excursion = {"mae": 0.0, "mfe": 0.0}
    if not mt5_client or not symbol or entry_price in (None, 0, 0.0) or not entry_time or not exit_time:
        return excursion

    symbol_info = mt5_client.symbol_info(symbol)
    point = float(getattr(symbol_info, "point", 0.0) or 0.0) if symbol_info else 0.0
    if point <= 0:
        logger.warning("Missing symbol point for %s. Defaulting MAE/MFE to 0.", symbol)
        return excursion

    entry_dt_utc = ensure_utc_datetime(entry_time)
    exit_dt_utc = ensure_utc_datetime(exit_time)
    if not entry_dt_utc or not exit_dt_utc or exit_dt_utc < entry_dt_utc:
        logger.warning("Invalid excursion window for %s. Defaulting MAE/MFE to 0.", symbol)
        return excursion

    bar_start_dt_utc = floor_to_minute(entry_dt_utc)
    bar_end_dt_utc = floor_to_minute(exit_dt_utc)

    bounds = _extract_rate_bounds(_copy_rates_range(mt5_client, symbol, bar_start_dt_utc, bar_end_dt_utc))
    if bounds is None:
        bounds = _extract_tick_bounds(_copy_ticks_range(mt5_client, symbol, entry_dt_utc, exit_dt_utc))
    if bounds is None:
        return excursion

    high_price, low_price = bounds
    entry_price_value = float(entry_price)

    if direction in (BUY_DIRECTION_LABEL, "BUY", "buy", 0, "0"):
        mfe_points = (high_price - entry_price_value) / point
        mae_points = (entry_price_value - low_price) / point
    elif direction in (SELL_DIRECTION_LABEL, "SELL", "sell", 1, "1"):
        mfe_points = (entry_price_value - low_price) / point
        mae_points = (high_price - entry_price_value) / point
    else:
        logger.warning("Unknown trade direction for %s. Defaulting MAE/MFE to 0.", symbol)
        return excursion

    excursion["mfe"] = round(max(0.0, mfe_points), 2)
    excursion["mae"] = round(max(0.0, mae_points), 2)
    return excursion


def tag_session(entry_time_utc8: Optional[datetime]) -> Optional[str]:
    if not entry_time_utc8:
        return None

    hour = entry_time_utc8.hour + (entry_time_utc8.minute / 60.0)
    if 7.0 <= hour < 15.0:
        return "亚洲盘"
    if 15.0 <= hour < 20.0:
        return "伦敦盘"
    if hour >= 20.0 or hour < 4.0:
        return "纽约盘"
    return "其他"


def calculate_realized_pnl(deal) -> Optional[float]:
    components = []
    for field_name in ("profit", "commission", "swap", "fee"):
        value = getattr(deal, field_name, None)
        if value in (None, ""):
            continue
        try:
            components.append(float(value))
        except (TypeError, ValueError):
            continue

    if not components:
        return None
    return round(sum(components), 2)


def load_field_mapping(file_path: Path) -> Dict[str, Dict[str, object]]:
    mapping = {key: dict(value) for key, value in DEFAULT_FIELD_MAPPING.items()}
    if not file_path.exists():
        logger.warning("Mapping file not found: %s. Falling back to defaults.", file_path)
        return mapping

    try:
        lines = [line.strip() for line in file_path.read_text(encoding="utf-8").splitlines()]
        table_lines = [line for line in lines if line.startswith("|") and line.count("|") >= 2]
        if len(table_lines) < 3:
            logger.warning("Mapping file %s does not contain a valid table. Using defaults.", file_path)
            return mapping

        for line in table_lines[2:]:
            parts = [part.strip() for part in line.strip("|").split("|")]
            if len(parts) < 2:
                continue
            key, property_name = parts[0], parts[1]
            if key in mapping and property_name:
                mapping[key]["property"] = property_name
    except Exception as exc:
        logger.warning("Failed to parse mapping file %s: %s. Using defaults.", file_path, exc)

    return mapping


def check_dependencies() -> None:
    required_libs = {
        "MetaTrader5": "MetaTrader5",
        "python-dotenv": "dotenv",
        "pytz": "pytz",
        "requests": "requests",
    }

    missing_libs = []
    for display_name, import_name in required_libs.items():
        try:
            __import__(import_name)
            logger.info("[OK] Dependency available: %s", display_name)
        except ImportError:
            logger.error("[ERROR] Missing dependency: %s", display_name)
            missing_libs.append(display_name)

    if missing_libs:
        raise ImportError(f"Missing required dependencies: {', '.join(missing_libs)}")


class MT5Connector:
    def __init__(self) -> None:
        self.connected = False
        self.mt5 = None

    def initialize_terminal(self) -> bool:
        try:
            import MetaTrader5 as mt5
        except Exception as exc:
            logger.error("[ERROR] Failed to import MetaTrader5: %s", exc)
            return False

        logger.info("Initializing MT5 terminal...")

        try:
            ok = mt5.initialize()
            if not ok:
                logger.error("[ERROR] MT5 initialize failed: %s", mt5.last_error())
                return False

            self.mt5 = mt5
            self.connected = True
            logger.info("[OK] MT5 terminal initialized")

            terminal_info = mt5.terminal_info()
            if terminal_info:
                connected = getattr(terminal_info, "connected", None)
                if connected is not None:
                    logger.info("MT5 internet connected=%s", connected)

            return True
        except Exception as exc:
            logger.error("[ERROR] MT5 initialize error: %s", format_exception_message(exc))
            return False

    def connect(self) -> bool:
        return self.initialize_terminal()

    def reinitialize_terminal(self, reason: Optional[str] = None) -> bool:
        if reason:
            logger.warning("Reinitializing MT5 terminal: %s", reason)

        self.shutdown_terminal()
        time.sleep(DEFAULT_MT5_RECOVERY_DELAY_SECONDS)
        return self.initialize_terminal()

    def is_terminal_connected(self) -> bool:
        if not self.connected or not self.mt5:
            logger.error("[ERROR] MT5 terminal is not initialized")
            return False

        try:
            terminal_info = self.mt5.terminal_info()
        except Exception as exc:
            logger.error("[ERROR] Failed to inspect MT5 terminal status: %s", format_exception_message(exc))
            return False

        if not terminal_info:
            logger.error("[ERROR] MT5 terminal_info is unavailable")
            return False

        connected = getattr(terminal_info, "connected", None)
        if connected is None:
            logger.warning("MT5 terminal does not expose a connectivity flag. Proceeding with login attempt.")
            return True
        return bool(connected)

    def login_account(self, account: AccountConfig) -> bool:
        if not self.connected or not self.mt5:
            logger.error("[ERROR] MT5 terminal is not initialized")
            return False

        logger.info(
            "Logging into MT5 account '%s'",
            account.account_name,
        )

        try:
            ok = self.mt5.login(account.login, password=account.password, server=account.server)
        except Exception as exc:
            logger.error(
                "[ERROR] MT5 login error for account %s: %s",
                account.account_name,
                format_exception_message(exc),
            )
            return False

        if not ok:
            logger.error(
                "[ERROR] MT5 login failed for account %s: %s",
                account.account_name,
                self.mt5.last_error(),
            )
            return False

        info = self.mt5.account_info()
        if not info:
            logger.error("[ERROR] MT5 account_info unavailable after login for %s", account.account_name)
            return False

        active_login = getattr(info, "login", None)
        if active_login is not None and int(active_login) != int(account.login):
            logger.error(
                "[ERROR] MT5 switched to an unexpected account while processing %s",
                account.account_name,
            )
            return False

        logger.info("[OK] MT5 account ready for %s", account.account_name)
        return True

    def shutdown_terminal(self) -> None:
        if not self.connected:
            return

        try:
            if self.mt5:
                self.mt5.shutdown()
        finally:
            self.connected = False
            self.mt5 = None
            logger.info("[OK] MT5 terminal shut down")

    def disconnect(self) -> None:
        self.shutdown_terminal()

    def _history_deals_get(self, start_dt: datetime, end_dt: datetime):
        if not self.mt5:
            return None

        for start_value, end_value in (
            (start_dt, end_dt),
            (int(start_dt.timestamp()), int(end_dt.timestamp())),
        ):
            try:
                deals = self.mt5.history_deals_get(start_value, end_value)
                if deals is not None:
                    return deals
            except Exception:
                continue

        logger.warning("history_deals_get failed: %s", self.mt5.last_error())
        return None

    def _history_orders_get(self, start_dt: datetime, end_dt: datetime):
        if not self.mt5:
            return None

        for start_value, end_value in (
            (start_dt, end_dt),
            (int(start_dt.timestamp()), int(end_dt.timestamp())),
        ):
            try:
                orders = self.mt5.history_orders_get(start_value, end_value)
                if orders is not None:
                    return orders
            except Exception:
                continue

        logger.warning("history_orders_get failed: %s", self.mt5.last_error())
        return None

    def populate_trade_excursion(self, trade: Dict[str, object]) -> Dict[str, object]:
        if not self.connected or not self.mt5:
            trade["mae"] = 0.0
            trade["mfe"] = 0.0
            return trade

        excursion = calculate_order_excursion(
            self.mt5,
            symbol=str(trade.get("symbol") or ""),
            direction=trade.get("direction"),
            entry_price=trade.get("entry_price"),
            entry_time=trade.get("entry_time_utc"),
            exit_time=trade.get("exit_time_utc"),
        )
        trade.update(excursion)
        return trade

    def get_recent_closed_trades(
        self,
        hours: Optional[int] = 24,
        start_dt: Optional[datetime] = None,
        end_dt: Optional[datetime] = None,
        account_name: Optional[str] = None,
    ):
        if not self.connected or not self.mt5:
            logger.error("[ERROR] MT5 is not connected")
            return []

        effective_end_dt = ensure_utc_datetime(end_dt) or datetime.now(timezone.utc)
        if start_dt is None:
            effective_hours = hours if hours is not None else 24
            effective_start_dt = effective_end_dt - timedelta(hours=effective_hours)
        else:
            effective_start_dt = ensure_utc_datetime(start_dt)

        if effective_start_dt is None or effective_start_dt > effective_end_dt:
            logger.warning("Invalid MT5 history window: start=%s end=%s", effective_start_dt, effective_end_dt)
            return []

        mt5_end_dt = to_naive_utc(effective_end_dt)
        mt5_start_dt = to_naive_utc(effective_start_dt)

        deals = self._history_deals_get(mt5_start_dt, mt5_end_dt)
        if deals is None:
            logger.warning("Failed to fetch MT5 deals for the requested window")
            return []

        if len(deals) == 0:
            probe_start = mt5_end_dt - timedelta(days=30)
            probe = self._history_deals_get(probe_start, mt5_end_dt) or []
            if probe:
                last_deal = max(probe, key=lambda item: getattr(item, "time", 0))
                last_deal_time = datetime.fromtimestamp(getattr(last_deal, "time", 0))
                logger.info(
                    "No deals found between %s and %s. Last deal in the previous 30 days: %s "
                    "(ticket=%s entry=%s)",
                    effective_start_dt.isoformat(),
                    effective_end_dt.isoformat(),
                    last_deal_time,
                    getattr(last_deal, "ticket", None),
                    getattr(last_deal, "entry", None),
                )

        out_deals = [
            deal
            for deal in deals
            if getattr(deal, "entry", None) in (DEAL_ENTRY_OUT, DEAL_ENTRY_OUT_BY, DEAL_ENTRY_INOUT)
        ]
        logger.info(
            "Fetched %s deals between %s and %s, including %s closed deals",
            len(deals),
            effective_start_dt.isoformat(),
            effective_end_dt.isoformat(),
            len(out_deals),
        )
        if not out_deals:
            return []

        entry_start_dt = mt5_start_dt - timedelta(days=ENTRY_LOOKBACK_DAYS)
        all_deals_for_entry = self._history_deals_get(entry_start_dt, mt5_end_dt) or []
        deals_by_position = {}
        for deal in all_deals_for_entry:
            position_id = getattr(deal, "position_id", None)
            if position_id is None:
                continue
            deals_by_position.setdefault(position_id, []).append(deal)

        orders = self._history_orders_get(entry_start_dt, mt5_end_dt) or []
        orders_by_ticket = {
            getattr(order, "ticket", None): order
            for order in orders
            if getattr(order, "ticket", None) is not None
        }

        tz_utc8 = pytz.timezone(TIMEZONE)
        trades = []

        for out_deal in out_deals:
            position_id = getattr(out_deal, "position_id", None)
            related_deals = deals_by_position.get(position_id, []) if position_id is not None else []
            in_deals = [
                deal
                for deal in related_deals
                if getattr(deal, "entry", None) in (DEAL_ENTRY_IN, DEAL_ENTRY_INOUT)
            ]

            entry_price = None
            entry_type = None
            entry_order_id = None
            entry_dt_utc = None
            entry_dt_utc8 = None
            if in_deals:
                total_volume = 0.0
                total_cost = 0.0
                in_deals_sorted = sorted(in_deals, key=lambda item: getattr(item, "time", 0))
                entry_type = getattr(in_deals_sorted[0], "type", None)
                entry_order_id = getattr(in_deals_sorted[0], "order", None)
                entry_dt_utc = datetime.fromtimestamp(getattr(in_deals_sorted[0], "time", 0), tz=timezone.utc)
                entry_dt_utc8 = entry_dt_utc.astimezone(tz_utc8)

                for deal in in_deals_sorted:
                    volume = float(getattr(deal, "volume", 0.0) or 0.0)
                    price = float(getattr(deal, "price", 0.0) or 0.0)
                    if volume <= 0 or price <= 0:
                        continue
                    total_volume += volume
                    total_cost += volume * price

                if total_volume > 0:
                    entry_price = total_cost / total_volume

            if entry_type is None:
                out_type = getattr(out_deal, "type", None)
                if out_type == 0:
                    entry_type = 1
                elif out_type == 1:
                    entry_type = 0

            direction = None
            if entry_type == 0:
                direction = BUY_DIRECTION_LABEL
            elif entry_type == 1:
                direction = SELL_DIRECTION_LABEL

            sl = None
            tp = None
            if entry_order_id is not None:
                order = orders_by_ticket.get(entry_order_id)
                if order is not None:
                    sl_value = getattr(order, "sl", None)
                    tp_value = getattr(order, "tp", None)
                    sl = float(sl_value) if sl_value not in (None, 0, 0.0) else None
                    tp = float(tp_value) if tp_value not in (None, 0, 0.0) else None

            close_dt_utc = datetime.fromtimestamp(getattr(out_deal, "time", 0), tz=timezone.utc)
            close_dt_utc8 = close_dt_utc.astimezone(tz_utc8)
            duration_hours = None
            if entry_dt_utc8:
                duration_hours = round(
                    max(0.0, (close_dt_utc8 - entry_dt_utc8).total_seconds() / 3600.0),
                    2,
                )

            trades.append(
                {
                    "ticket": int(getattr(out_deal, "ticket", 0)),
                    "symbol": getattr(out_deal, "symbol", ""),
                    "direction": direction,
                    "entry_time_utc": entry_dt_utc,
                    "time_utc8": close_dt_utc8,
                    "entry_time_utc8": entry_dt_utc8,
                    "exit_time_utc": close_dt_utc,
                    "entry_price": entry_price,
                    "exit_price": float(getattr(out_deal, "price", 0.0) or 0.0),
                    "sl": sl,
                    "tp": tp,
                    "volume": float(getattr(out_deal, "volume", 0.0) or 0.0),
                    "duration_hours": duration_hours,
                    "session": tag_session(entry_dt_utc8),
                    "realized_pnl": calculate_realized_pnl(out_deal),
                    "mae": None,
                    "mfe": None,
                    "account_name": account_name,
                }
            )

        return trades


class NotionSync:
    def __init__(
        self,
        field_mapping: Dict[str, Dict[str, object]],
        *,
        update_existing: Optional[bool] = None,
    ) -> None:
        self.token = os.getenv("NOTION_TOKEN")
        self.database_id = os.getenv("DATABASE_ID")
        self.parent = None
        self.headers = None
        self.notion_version = os.getenv("NOTION_VERSION", "2022-06-28")
        self.field_mapping = field_mapping
        self.properties = None
        self._missing_account_options_logged: set[str] = set()
        self.update_existing = resolve_update_existing(update_existing)
        self.sync_delay_seconds = float(os.getenv("NOTION_SYNC_DELAY_SECONDS", "0.5"))
        self.request_timeout_seconds = get_notion_http_timeout_seconds()
        self.request_max_retries = get_notion_http_max_retries()
        self.request_retry_backoff_seconds = get_notion_http_retry_backoff_seconds()
        self._existing_pages_by_trade_key: Dict[tuple[str, int], Dict[str, object]] = {}

    @staticmethod
    def _should_retry_response_status(status_code: int) -> bool:
        return status_code in RETRIABLE_NOTION_HTTP_STATUS_CODES

    def _retry_delay_seconds(self, attempt_number: int) -> float:
        return self.request_retry_backoff_seconds * (2 ** max(0, attempt_number - 1))

    def _request(self, method: str, url: str, *, json_payload: Optional[Dict[str, object]] = None):
        import requests

        if not self.headers:
            raise RuntimeError("Notion is not connected")

        total_attempts = self.request_max_retries + 1
        request_label = f"{method.upper()} {sanitize_diagnostic_text(url)}"

        for attempt in range(1, total_attempts + 1):
            try:
                response = requests.request(
                    method,
                    url,
                    headers=self.headers,
                    json=json_payload,
                    timeout=self.request_timeout_seconds,
                )
            except (requests.Timeout, requests.ConnectionError) as exc:
                if attempt < total_attempts:
                    delay = self._retry_delay_seconds(attempt)
                    logger.warning(
                        "Retrying Notion request after %s (%s/%s): %s",
                        type(exc).__name__,
                        attempt,
                        total_attempts - 1,
                        request_label,
                    )
                    if delay > 0:
                        time.sleep(delay)
                    continue
                raise

            if self._should_retry_response_status(response.status_code) and attempt < total_attempts:
                delay = self._retry_delay_seconds(attempt)
                logger.warning(
                    "Retrying Notion request after status=%s (%s/%s): %s",
                    response.status_code,
                    attempt,
                    total_attempts - 1,
                    request_label,
                )
                if delay > 0:
                    time.sleep(delay)
                continue

            response.raise_for_status()
            return response

    def connect(self) -> bool:
        if not self.token:
            logger.error("[ERROR] NOTION_TOKEN is not set")
            return False
        if not self.database_id:
            logger.error("[ERROR] DATABASE_ID is not set")
            return False

        try:
            self.headers = {
                "Authorization": f"Bearer {self.token}",
                "Notion-Version": self.notion_version,
                "Content-Type": "application/json",
            }

            response = self._request(
                "GET",
                f"https://api.notion.com/v1/databases/{self.database_id}",
            )
            database_info = response.json()

            data_sources = database_info.get("data_sources") or []
            if data_sources:
                data_source_id = data_sources[0].get("id")
                if not data_source_id:
                    raise ValueError("Notion database returned data_sources without an id")
                self.parent = {"type": "data_source_id", "data_source_id": data_source_id}
                schema_response = self._request(
                    "GET",
                    f"https://api.notion.com/v1/data_sources/{data_source_id}",
                )
                properties = schema_response.json().get("properties") or {}
            else:
                self.parent = {"type": "database_id", "database_id": self.database_id}
                properties = database_info.get("properties") or {}

            self.properties = properties
            self._validate_schema(properties)
            logger.info("[OK] Notion connected")
            return True
        except Exception as exc:
            logger.error("[ERROR] Notion connection failed: %s", format_exception_message(exc))
            return False

    def _validate_schema(self, properties: Dict[str, Dict[str, object]]) -> None:
        missing = []
        type_mismatches = []
        for key, config in self.field_mapping.items():
            property_name = config["property"]
            required = bool(config.get("required", True))
            if property_name not in properties:
                if required:
                    missing.append(property_name)
                continue

            actual_type = properties[property_name].get("type")
            expected_type = config.get("type")
            if expected_type and actual_type != expected_type:
                type_mismatches.append(f"{property_name}: expected {expected_type}, got {actual_type}")

        if missing:
            raise ValueError(
                "Notion database is missing required properties: "
                + ", ".join(missing)
                + f". Available properties: {', '.join(sorted(properties.keys()))}"
            )
        if type_mismatches:
            raise ValueError("Notion property type mismatches: " + "; ".join(type_mismatches))

    @staticmethod
    def _combine_filters(filters: list[Dict[str, object]]) -> Optional[Dict[str, object]]:
        effective_filters = [item for item in filters if item]
        if not effective_filters:
            return None
        if len(effective_filters) == 1:
            return effective_filters[0]
        return {"and": effective_filters}

    @staticmethod
    def _normalize_account_name(account_name: Optional[str]) -> str:
        return str(account_name or "").strip()

    def _trade_key(self, ticket: int, account_name: Optional[str]) -> tuple[str, int]:
        return (self._normalize_account_name(account_name), int(ticket))

    def _trade_key_from_trade(self, trade: Dict[str, object]) -> Optional[tuple[str, int]]:
        ticket = trade.get("ticket")
        if ticket in (None, ""):
            return None

        try:
            return self._trade_key(int(ticket), trade.get("account_name"))
        except (TypeError, ValueError):
            return None

    def _cache_existing_page(
        self,
        ticket: int,
        account_name: Optional[str],
        page: Optional[Dict[str, object]],
    ) -> None:
        if not page or not page.get("id"):
            return

        self._existing_pages_by_trade_key[self._trade_key(ticket, account_name)] = page

    def _build_ticket_filter(self, ticket: int) -> Dict[str, object]:
        ticket_prop = self.field_mapping["ticket"]["property"]
        return {"property": ticket_prop, "number": {"equals": int(ticket)}}

    def _build_account_filter(self, account_name: Optional[str]) -> Optional[Dict[str, object]]:
        if not account_name:
            return None

        account_property = self.field_mapping["account_name"]["property"]
        return {"property": account_property, "select": {"equals": account_name}}

    def _account_option_exists(self, account_name: Optional[str]) -> bool:
        if not account_name:
            return True

        account_property = self.field_mapping["account_name"]["property"]
        properties = self.properties or {}
        property_config = properties.get(account_property) or {}
        if property_config.get("type") != "select":
            return True

        options = ((property_config.get("select") or {}).get("options") or [])
        option_names = {str(option.get("name", "")).strip() for option in options if option.get("name")}
        if account_name in option_names:
            return True

        if account_name not in self._missing_account_options_logged:
            logger.info(
                "Notion select option '%s' is not present in '%s' yet; treating this as a first sync with no existing records.",
                account_name,
                account_property,
            )
            self._missing_account_options_logged.add(account_name)
        return False

    def _query(self, filter_obj=None, page_size: int = 1, sorts: Optional[list[Dict[str, object]]] = None):
        import json
        import requests

        if not self.parent or not self.headers:
            raise RuntimeError("Notion is not connected")

        if self.parent["type"] == "data_source_id":
            url = f"https://api.notion.com/v1/data_sources/{self.parent['data_source_id']}/query"
        else:
            url = f"https://api.notion.com/v1/databases/{self.parent['database_id']}/query"

        payload = {"page_size": page_size}
        if filter_obj:
            payload["filter"] = filter_obj
        if sorts:
            payload["sorts"] = sorts

        try:
            response = self._request("POST", url, json_payload=payload)
        except requests.HTTPError as exc:
            response = getattr(exc, "response", None)
            logger.error(
                "[ERROR] Notion query failed: status=%s body=%s payload=%s",
                getattr(response, "status_code", "unknown"),
                sanitize_diagnostic_text(getattr(response, "text", "<unavailable>")),
                sanitize_diagnostic_text(json.dumps(payload, ensure_ascii=False)),
            )
            raise
        return response.json()

    def find_existing_page(self, ticket: int, account_name: Optional[str] = None) -> Optional[Dict[str, object]]:
        cached_page = self._existing_pages_by_trade_key.get(self._trade_key(ticket, account_name))
        if cached_page is not None:
            return cached_page

        if account_name and not self._account_option_exists(account_name):
            return None

        filter_obj = self._combine_filters(
            [
                self._build_ticket_filter(ticket),
                self._build_account_filter(account_name),
            ]
        )
        data = self._query(filter_obj, page_size=1)
        results = data.get("results", []) or []
        if not results:
            return None
        page = results[0]
        self._cache_existing_page(ticket, account_name, page)
        return page

    def find_existing_page_id(self, ticket: int, account_name: Optional[str] = None) -> Optional[str]:
        page = self.find_existing_page(ticket, account_name=account_name)
        if not page:
            return None
        return page.get("id")

    @staticmethod
    def _page_date_property_start(page: Optional[Dict[str, object]], property_name: str) -> Optional[datetime]:
        if not page:
            return None

        properties = page.get("properties") or {}
        property_value = properties.get(property_name)
        if not property_value or property_value.get("type") != "date":
            return None

        date_value = (property_value.get("date") or {}).get("start")
        if not date_value:
            return None

        try:
            return ensure_utc_datetime(datetime.fromisoformat(date_value.replace("Z", "+00:00")))
        except ValueError:
            return None

    def find_latest_account_sync_time(self, account_name: str) -> Optional[datetime]:
        if not self._account_option_exists(account_name):
            return None

        date_property = self.field_mapping["time_utc8"]["property"]
        data = self._query(
            self._build_account_filter(account_name),
            page_size=1,
            sorts=[{"property": date_property, "direction": "descending"}],
        )
        results = data.get("results", []) or []
        if not results:
            return None
        return self._page_date_property_start(results[0], date_property)

    def resolve_existing_page(self, trade: Dict[str, object]) -> Optional[Dict[str, object]]:
        if trade.get("_existing_page_loaded"):
            return trade.get("_existing_page")

        page = self.find_existing_page(int(trade["ticket"]), account_name=trade.get("account_name"))
        trade["_existing_page_loaded"] = True
        trade["_existing_page"] = page
        trade["_existing_page_id_loaded"] = True
        trade["_existing_page_id"] = page.get("id") if page else None
        return page

    def resolve_existing_page_id(self, trade: Dict[str, object]) -> Optional[str]:
        if trade.get("_existing_page_id_loaded"):
            return trade.get("_existing_page_id")

        page = self.resolve_existing_page(trade)
        return page.get("id") if page else None

    @staticmethod
    def _page_number_property_has_value(page: Optional[Dict[str, object]], property_name: str) -> bool:
        if not page:
            return False

        properties = page.get("properties") or {}
        property_value = properties.get(property_name)
        if not property_value or property_value.get("type") != "number":
            return False
        return property_value.get("number") is not None

    def should_calculate_excursion_for_trade(self, trade: Dict[str, object]) -> bool:
        page = self.resolve_existing_page(trade)
        if not page:
            return True
        if not self.update_existing:
            return False
        if not self.properties:
            return False

        for key in ("mae", "mfe"):
            property_name = self.field_mapping[key]["property"]
            if property_name not in self.properties:
                continue
            if not self._page_number_property_has_value(page, property_name):
                return True

        return False

    def format_update_properties(self, trade: Dict[str, object]):
        if not self.properties:
            return {}

        props = {}
        mapping = self.field_mapping

        account_property = mapping["account_name"]["property"]
        if account_property in self.properties and trade.get("account_name"):
            props[account_property] = {"select": {"name": str(trade["account_name"])}}

        duration_property = mapping["duration_hours"]["property"]
        if duration_property in self.properties and trade.get("duration_hours") is not None:
            props[duration_property] = {"number": round(float(trade["duration_hours"]), 2)}

        session_property = mapping["session"]["property"]
        if session_property in self.properties and trade.get("session"):
            props[session_property] = {"select": {"name": trade["session"]}}

        realized_pnl_property = mapping["realized_pnl"]["property"]
        if realized_pnl_property in self.properties and trade.get("realized_pnl") is not None:
            props[realized_pnl_property] = {"number": round(float(trade["realized_pnl"]), 2)}

        mae_property = mapping["mae"]["property"]
        if mae_property in self.properties and trade.get("mae") is not None:
            props[mae_property] = {"number": round(float(trade["mae"]), 2)}

        mfe_property = mapping["mfe"]["property"]
        if mfe_property in self.properties and trade.get("mfe") is not None:
            props[mfe_property] = {"number": round(float(trade["mfe"]), 2)}

        return props

    def update_existing_page(self, page_id: str, trade: Dict[str, object]) -> bool:
        props = self.format_update_properties(trade)
        if not props:
            return False

        self._request(
            "PATCH",
            f"https://api.notion.com/v1/pages/{page_id}",
            json_payload={"properties": props},
        )
        return True

    def format_trade_to_notion(self, trade: Dict[str, object]):
        account_name = trade.get("account_name")
        if not account_name:
            raise ValueError(f"Trade {trade.get('ticket')} is missing account_name")

        direction = trade.get("direction")
        if not direction:
            raise ValueError(f"Trade {trade.get('ticket')} is missing a resolved direction")

        time_utc8 = trade["time_utc8"]
        date_iso = time_utc8.isoformat(timespec="seconds")
        mapping = self.field_mapping

        props = {
            mapping["symbol"]["property"]: {"title": [{"text": {"content": trade["symbol"]}}]},
            mapping["direction"]["property"]: {"select": {"name": direction}},
            mapping["time_utc8"]["property"]: {"date": {"start": date_iso, "end": None}},
            mapping["entry_price"]["property"]: {"number": trade["entry_price"]},
            mapping["exit_price"]["property"]: {"number": trade["exit_price"]},
            mapping["sl"]["property"]: {"number": trade["sl"]},
            mapping["tp"]["property"]: {"number": trade["tp"]},
            mapping["volume"]["property"]: {"number": trade["volume"]},
            mapping["ticket"]["property"]: {"number": trade["ticket"]},
            mapping["account_name"]["property"]: {"select": {"name": str(account_name)}},
        }

        optional_updates = self.format_update_properties(trade)
        props.update(optional_updates)
        return {"properties": props}

    def sync_trade(self, trade: Dict[str, object]) -> str:
        page_id = None
        try:
            page_id = self.resolve_existing_page_id(trade)
        except Exception as exc:
            logger.error(
                "[ERROR] Failed to query duplicate for ticket %s: %s",
                trade["ticket"],
                format_exception_message(exc),
            )
            return SYNC_STATUS_FAILED

        if page_id:
            if self.update_existing:
                try:
                    if self.update_existing_page(page_id, trade):
                        logger.info("[OK] Updated ticket %s", trade["ticket"])
                        return SYNC_STATUS_UPDATED
                except Exception as exc:
                    logger.error(
                        "[ERROR] Failed to update ticket %s: %s",
                        trade["ticket"],
                        format_exception_message(exc),
                    )
                    return SYNC_STATUS_FAILED

            logger.info("Skipped duplicate ticket %s", trade["ticket"])
            return SYNC_STATUS_DUPLICATE

        try:
            if not self.parent or not self.headers:
                raise RuntimeError("Notion is not connected")

            notion_data = self.format_trade_to_notion(trade)
            payload = {"parent": self.parent, "properties": notion_data["properties"]}
            response = self._request(
                "POST",
                "https://api.notion.com/v1/pages",
                json_payload=payload,
            )
            self._cache_existing_page(
                int(trade["ticket"]),
                trade.get("account_name"),
                response.json(),
            )

            logger.info("[OK] Created ticket %s", trade["ticket"])
            return SYNC_STATUS_CREATED
        except Exception as exc:
            logger.error(
                "[ERROR] Failed to sync ticket %s: %s",
                trade["ticket"],
                format_exception_message(exc),
            )
            return SYNC_STATUS_FAILED

    def sync_trades(
        self,
        trades: Iterable[Dict[str, object]],
        before_create: Optional[Callable[[Dict[str, object]], Dict[str, object] | None]] = None,
    ):
        if not self.parent or not self.headers:
            logger.error("[ERROR] Notion is not connected")
            return build_sync_summary()

        trades = list(trades)
        summary = build_sync_summary()
        processed_trade_keys: set[tuple[str, int]] = set()
        logger.info("Starting sync for %s trades...", len(trades))

        for index, trade in enumerate(trades, start=1):
            logger.info("Processing trade %s/%s...", index, len(trades))

            trade_key = self._trade_key_from_trade(trade)
            if trade_key and trade_key in processed_trade_keys:
                logger.info(
                    "Skipped in-batch duplicate ticket %s for account %s",
                    trade.get("ticket"),
                    trade.get("account_name"),
                )
                summary[SYNC_STATUS_DUPLICATE] += 1
                if index < len(trades) and self.sync_delay_seconds > 0:
                    time.sleep(self.sync_delay_seconds)
                continue

            if before_create:
                try:
                    should_prepare = self.should_calculate_excursion_for_trade(trade)
                except Exception as exc:
                    logger.error(
                        "[ERROR] Failed to query duplicate for ticket %s: %s",
                        trade["ticket"],
                        format_exception_message(exc),
                    )
                    summary[SYNC_STATUS_FAILED] += 1
                    if index < len(trades) and self.sync_delay_seconds > 0:
                        time.sleep(self.sync_delay_seconds)
                    continue

                if should_prepare:
                    try:
                        before_create(trade)
                    except Exception as exc:
                        logger.error(
                            "[ERROR] Failed to prepare ticket %s before sync: %s",
                            trade["ticket"],
                            format_exception_message(exc),
                        )
                        summary[SYNC_STATUS_FAILED] += 1
                        if index < len(trades) and self.sync_delay_seconds > 0:
                            time.sleep(self.sync_delay_seconds)
                        continue

            status = normalize_sync_status(self.sync_trade(trade))
            summary[status] += 1
            if trade_key and status in (
                SYNC_STATUS_CREATED,
                SYNC_STATUS_UPDATED,
                SYNC_STATUS_DUPLICATE,
            ):
                processed_trade_keys.add(trade_key)

            if index < len(trades) and self.sync_delay_seconds > 0:
                time.sleep(self.sync_delay_seconds)

        logger.info("=" * 50)
        logger.info("Sync complete")
        logger.info("Created: %s", summary[SYNC_STATUS_CREATED])
        logger.info("Updated: %s", summary[SYNC_STATUS_UPDATED])
        logger.info("Duplicates: %s", summary[SYNC_STATUS_DUPLICATE])
        logger.info("Failed: %s", summary[SYNC_STATUS_FAILED])
        logger.info("=" * 50)
        return summary


def sync_all_accounts(
    accounts: Iterable[AccountConfig],
    mt5_connector: MT5Connector,
    notion_sync: NotionSync,
    fallback_hours: int,
    overlap_minutes: float,
    switch_delay_seconds: float,
    skip_mae_mfe: bool = False,
) -> tuple[Dict[str, int], int]:
    overall_summary = build_sync_summary()
    account_failures = 0
    accounts = list(accounts)
    before_create = None if skip_mae_mfe else mt5_connector.populate_trade_excursion

    for index, account in enumerate(accounts, start=1):
        logger.info("=" * 50)
        logger.info("Processing account %s/%s: %s", index, len(accounts), account.account_name)

        try:
            if not mt5_connector.is_terminal_connected():
                logger.warning(
                    "MT5 terminal is offline before processing account %s. Attempting recovery.",
                    account.account_name,
                )
                if (
                    not mt5_connector.reinitialize_terminal(f"offline before account {account.account_name}")
                    or not mt5_connector.is_terminal_connected()
                ):
                    logger.error(
                        "[ERROR] MT5 terminal recovery failed before processing account %s",
                        account.account_name,
                    )
                    account_failures += 1
                    continue

            if not mt5_connector.login_account(account):
                logger.warning(
                    "Initial login failed for account %s. Attempting MT5 terminal recovery and one retry.",
                    account.account_name,
                )
                if (
                    not mt5_connector.reinitialize_terminal(f"login retry for account {account.account_name}")
                    or not mt5_connector.login_account(account)
                ):
                    account_failures += 1
                    continue

            latest_synced_time = notion_sync.find_latest_account_sync_time(account.account_name)
            window_end = datetime.now(timezone.utc)
            window_start = calculate_incremental_start_time(
                latest_synced_time=latest_synced_time,
                fallback_hours=fallback_hours,
                overlap_minutes=overlap_minutes,
                now_utc=window_end,
            )
            logger.info(
                "Account %s sync window: %s -> %s (latest_synced=%s)",
                account.account_name,
                window_start.isoformat(),
                window_end.isoformat(),
                latest_synced_time.isoformat() if latest_synced_time else "None",
            )

            trades = mt5_connector.get_recent_closed_trades(
                start_dt=window_start,
                end_dt=window_end,
                account_name=account.account_name,
            )
            if not trades:
                logger.info("No trades need syncing for account %s", account.account_name)
                continue

            summary = notion_sync.sync_trades(trades, before_create=before_create)
            merge_sync_summaries(overall_summary, summary)
            logger.info(
                "Account %s summary: created=%s updated=%s duplicate=%s failed=%s",
                account.account_name,
                summary[SYNC_STATUS_CREATED],
                summary[SYNC_STATUS_UPDATED],
                summary[SYNC_STATUS_DUPLICATE],
                summary[SYNC_STATUS_FAILED],
            )
        except Exception as exc:
            logger.error(
                "[ERROR] Unexpected account error for %s: %s",
                account.account_name,
                format_exception_message(exc),
            )
            account_failures += 1
        finally:
            if index < len(accounts) and switch_delay_seconds > 0:
                logger.info("Waiting %.1f seconds before the next account...", switch_delay_seconds)
                time.sleep(switch_delay_seconds)

    return overall_summary, account_failures


def run_sync(runtime_options: Optional[SyncRuntimeOptions] = None) -> SyncRunResult:
    runtime_options = runtime_options or SyncRuntimeOptions()
    started_at = datetime.now(timezone.utc)
    summary = build_sync_summary()
    account_failures = 0
    error_message = None
    exit_code = 1

    def failure_result(message: str, *, exit_status: int = 1) -> SyncRunResult:
        return SyncRunResult(
            exit_code=exit_status,
            summary=summary,
            account_failures=account_failures,
            error_message=message,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            profile_name=runtime_options.profile_name,
        )

    logger.info("MT5 to Notion sync started")
    logger.info("Project root: %s", PROJECT_ROOT)
    if runtime_options.profile_name:
        logger.info("Runtime profile: %s", runtime_options.profile_name)

    mt5_connector = MT5Connector()

    try:
        check_dependencies()
    except ImportError as exc:
        error_message = str(exc)
        logger.error(error_message)
        return failure_result(error_message)

    if not os.getenv("NOTION_TOKEN"):
        error_message = f"Please set NOTION_TOKEN in {ENV_FILE}"
        logger.error("[ERROR] %s", error_message)
        return failure_result(error_message)
    if not os.getenv("DATABASE_ID"):
        error_message = f"Please set DATABASE_ID in {ENV_FILE}"
        logger.error("[ERROR] %s", error_message)
        return failure_result(error_message)

    accounts_file = resolve_accounts_file_path(os.getenv("ACCOUNTS_FILE"))
    try:
        accounts = load_accounts(accounts_file)
    except Exception as exc:
        error_message = f"Failed to load accounts from {accounts_file}: {exc}"
        logger.error("[ERROR] %s", error_message)
        return failure_result(error_message)

    try:
        field_mapping = load_field_mapping(MAPPING_FILE)
        notion_sync = NotionSync(field_mapping, update_existing=runtime_options.update_existing)
        fallback_hours = get_sync_hours()
        overlap_minutes = get_incremental_lookback_minutes()
        switch_delay_seconds = get_account_switch_delay_seconds()
        skip_mae_mfe = should_skip_mae_mfe(runtime_options.skip_mae_mfe)

        if skip_mae_mfe:
            logger.info("SKIP_MAE_MFE is enabled; MAE/MFE backfill will be skipped for this run.")

        if not notion_sync.connect():
            error_message = "Notion connection failed"
            exit_code = 1
            return failure_result(error_message, exit_status=exit_code)
        if not mt5_connector.initialize_terminal():
            error_message = "MT5 terminal initialization failed"
            exit_code = 1
            return failure_result(error_message, exit_status=exit_code)

        summary, account_failures = sync_all_accounts(
            accounts=accounts,
            mt5_connector=mt5_connector,
            notion_sync=notion_sync,
            fallback_hours=fallback_hours,
            overlap_minutes=overlap_minutes,
            switch_delay_seconds=switch_delay_seconds,
            skip_mae_mfe=skip_mae_mfe,
        )
        logger.info(
            "Run summary: created=%s updated=%s duplicate=%s failed=%s account_failures=%s",
            summary[SYNC_STATUS_CREATED],
            summary[SYNC_STATUS_UPDATED],
            summary[SYNC_STATUS_DUPLICATE],
            summary[SYNC_STATUS_FAILED],
            account_failures,
        )
        exit_code = 1 if summary[SYNC_STATUS_FAILED] or account_failures else 0
        if exit_code:
            error_message = "One or more accounts or trades failed during sync"
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        exit_code = 130
        error_message = "Interrupted by user"
    except Exception as exc:
        error_message = format_exception_message(exc)
        logger.error("[ERROR] Unexpected program error: %s", error_message)
        exit_code = 1
    finally:
        mt5_connector.shutdown_terminal()
        logger.info("Program finished")

    finished_at = datetime.now(timezone.utc)
    return SyncRunResult(
        exit_code=exit_code,
        summary=summary,
        account_failures=account_failures,
        error_message=error_message,
        started_at=started_at,
        finished_at=finished_at,
        profile_name=runtime_options.profile_name,
    )


def main() -> int:
    return run_sync().exit_code


if __name__ == "__main__":
    sys.exit(main())

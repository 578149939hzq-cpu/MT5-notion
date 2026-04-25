#!/usr/bin/env python3
"""
Shared helpers for repository-local diagnostic scripts.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_ROOT / ".env"
ENV_EXAMPLE_FILE = PROJECT_ROOT / ".env.example"
NOTION_RESOURCE_URL_RE = re.compile(r"https://api\.notion\.com/v1/(databases|data_sources|pages)/[A-Za-z0-9-]+")
MT5_DATA_PATH_RE = re.compile(r"[A-Za-z]:\\Users\\[^\\\s]+\\AppData\\Roaming\\MetaQuotes\\Terminal\\[^\\\s]+")


def load_project_env() -> None:
    load_dotenv(dotenv_path=ENV_FILE)


def sanitize_output(value: object) -> str:
    text = str(value)

    for env_name, replacement in (
        ("DATABASE_ID", "<database-id>"),
        ("NOTION_TOKEN", "<notion-token>"),
        ("MT5_ACCOUNT", "<mt5-account>"),
        ("MT5_SERVER", "<mt5-server>"),
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


def config_status(name: str) -> str:
    return f"[OK] {name} configured" if os.getenv(name) else f"[WARNING] {name} missing"


def require_env(*names: str) -> bool:
    missing = [name for name in names if not os.getenv(name)]
    if not missing:
        return True

    print(f"[ERROR] Missing environment variables: {', '.join(missing)}")
    print(f"Update {ENV_FILE} before running this tool.")
    if ENV_EXAMPLE_FILE.exists():
        print(f"See example config: {ENV_EXAMPLE_FILE}")
    return False


def init_mt5_from_env():
    load_project_env()
    if not require_env("MT5_ACCOUNT", "MT5_PASSWORD", "MT5_SERVER"):
        return None

    try:
        import MetaTrader5 as mt5
    except Exception as exc:
        print(f"[ERROR] Unable to import MetaTrader5: {sanitize_output(exc)}")
        return None

    account_raw = os.getenv("MT5_ACCOUNT", "").strip()
    password = os.getenv("MT5_PASSWORD", "")
    server = os.getenv("MT5_SERVER", "")

    try:
        account = int(account_raw)
    except ValueError:
        print(f"[ERROR] MT5_ACCOUNT must be numeric. Current value: {sanitize_output(account_raw)!r}")
        return None

    if not mt5.initialize(login=account, password=password, server=server):
        print(f"[ERROR] MT5 initialization failed: {sanitize_output(mt5.last_error())}")
        return None

    return mt5

#!/usr/bin/env python3
"""
Test Notion connectivity and list accessible databases.
"""

from __future__ import annotations

import os
import sys

from diagnostic_support import ENV_FILE, config_status, load_project_env, require_env, sanitize_output


def main() -> int:
    load_project_env()
    if not require_env("NOTION_TOKEN"):
        return 1

    token = os.getenv("NOTION_TOKEN")
    database_id = os.getenv("DATABASE_ID")

    try:
        from notion_client import Client

        print("Connecting to Notion...")
        client = Client(auth=token)
        print("[OK] Notion connection succeeded")
        print(config_status("NOTION_TOKEN"))

        if database_id:
            try:
                database = client.databases.retrieve(database_id=database_id)
                title = database.get("title", [{"text": {"content": "Untitled"}}])[0]["text"]["content"]
                print(config_status("DATABASE_ID"))
                print(f"Configured database title: {title}")
            except Exception as exc:
                print(f"[WARNING] Configured DATABASE_ID could not be verified: {sanitize_output(exc)}")
        else:
            print(f"[WARNING] DATABASE_ID not set. Check {ENV_FILE}")

        print("\nFetching accessible databases...")
        search_results = client.search({"filter": {"value": "database", "property": "object"}})
        databases = search_results.get("results", [])

        if not databases:
            print("[INFO] No accessible databases found")
            return 0

        print(f"Found {len(databases)} accessible databases:")
        for index, database in enumerate(databases, start=1):
            title = database.get("title", [{"text": {"content": "Untitled"}}])[0]["text"]["content"]
            print(f"{index}. {title}")

            try:
                client.databases.query(database_id=database["id"], page_size=1)
                print("   [OK] Query access confirmed")
            except Exception as exc:
                print(f"   [WARNING] Query check failed: {sanitize_output(str(exc)[:100])}...")

        return 0
    except Exception as exc:
        print(f"[ERROR] Notion connection failed: {sanitize_output(exc)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

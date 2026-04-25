#!/usr/bin/env python3
"""
Inspect the property schema of the configured Notion database.
"""

from __future__ import annotations

import os
import sys

from diagnostic_support import config_status, load_project_env, require_env, sanitize_output


def main() -> int:
    load_project_env()
    if not require_env("NOTION_TOKEN", "DATABASE_ID"):
        return 1

    token = os.getenv("NOTION_TOKEN")
    database_id = os.getenv("DATABASE_ID")

    try:
        from notion_client import Client

        print("Connecting to Notion...")
        print(config_status("NOTION_TOKEN"))
        print(config_status("DATABASE_ID"))
        client = Client(auth=token)

        database_info = client.databases.retrieve(database_id=database_id)

        title = database_info.get("title", [{"text": {"content": "Untitled"}}])[0]["text"]["content"]
        print(f"\nDatabase title: {title}")

        properties = database_info.get("properties", {})
        print(f"Property count: {len(properties)}")
        print(f"Created time: {database_info.get('created_time', 'N/A')}")
        print(f"Last edited time: {database_info.get('last_edited_time', 'N/A')}")

        if not properties:
            print("\n[WARNING] No properties were returned by the Notion API.")

        for name, config in properties.items():
            prop_type = config.get("type", "unknown")
            print(f"\nProperty: {name}")
            print(f"  Type: {prop_type}")
            if prop_type == "select":
                options = config.get("select", {}).get("options", [])
                if options:
                    print(f"  Options: {[option.get('name', 'unknown') for option in options]}")

        return 0
    except Exception as exc:
        print(f"[ERROR] {sanitize_output(exc)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

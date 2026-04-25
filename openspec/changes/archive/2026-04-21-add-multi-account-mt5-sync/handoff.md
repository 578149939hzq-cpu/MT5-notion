## Current Status

- Date: 2026-04-22
- Change: `add-multi-account-mt5-sync`
- OpenSpec status: `proposal/design/specs/tasks` are complete and the change has already been archived
- Code status: multi-account polling refactor has been implemented and the first real sync validation has been completed
- Live sync status: a fast real sync run with temporary `SKIP_MAE_MFE=1` completed successfully with `created=1 updated=7 duplicate=0 failed=0 account_failures=0`
- Notion status: field `所属账户` exists as a `select` property; missing account options are now treated as first-sync/no-history instead of causing a query failure
- MT5 status: terminal recovery has been hardened so the script can reinitialize MT5 and retry once after terminal offline/login IPC failures

## Implemented And Validated Scope

- Added external account loading from `accounts.json`
- Split MT5 terminal initialization from per-account login
- Added account-scoped incremental sync based on the latest Notion record per account
- Added Notion property mapping for `account_name -> 所属账户`
- Changed duplicate detection from `ticket` to `account_name + ticket`
- Added account-level error isolation and switch delay handling
- Completed the first real multi-account sync validation
- Added temporary `SKIP_MAE_MFE` support for fast first-run / recovery syncs
- Added MT5 terminal reinitialize-and-retry behavior for runtime recovery
- Updated docs, example config, and runtime notes to match the live-sync workflow

## Important Files

- Main script: `/D:/ClaudeCode/mt5_notion_sync.py`
- Example accounts file: `/D:/ClaudeCode/accounts.example.json`
- Environment example: `/D:/ClaudeCode/.env.example`
- Project guide: `/D:/ClaudeCode/README.md`
- Archived OpenSpec handoff: `/D:/ClaudeCode/openspec/changes/archive/2026-04-21-add-multi-account-mt5-sync/handoff.md`

## Operational Notes

1. Default one-click run still expects `/D:/ClaudeCode/accounts.json`. If a different filled account file is used, set `ACCOUNTS_FILE` explicitly.
2. Standard sync command:
   `python /D:/ClaudeCode/mt5_notion_sync.py`
3. Fast sync without `MAE/MFE` backfill:
   PowerShell:
   `$env:SKIP_MAE_MFE='1'; python /D:/ClaudeCode/mt5_notion_sync.py`
4. To backfill `MAE/MFE` later, run the script again without `SKIP_MAE_MFE` and keep `UPDATE_EXISTING=1`.
5. Duplicate detection is scoped to `account_name + ticket`. With `UPDATE_EXISTING=1`, duplicates update the existing page; with `UPDATE_EXISTING=0`, duplicates are skipped.

## Next Session Checklist

1. Ensure the real account file is stored as `/D:/ClaudeCode/accounts.json` for standard one-click runs
2. Decide when to backfill `MAE/MFE` by rerunning without `SKIP_MAE_MFE`
3. Watch `/D:/ClaudeCode/logs/mt5_notion_sync.log` if MT5 shows repeated IPC instability

## Resume Prompt

Use this next time:

`继续同步 MT5 多账户交易；如果要补 MAE/MFE，就不要带 SKIP_MAE_MFE`

# AGENTS.md

## Repo layout
- `src/` stores the main application code.
- `tests/` stores automated tests.
- `tools/` stores operational scripts.
- `openspec/` stores spec, design, and task artifacts. Do not change archived material unless the task explicitly requires it.

## Commands
- Install: `python -m pip install -r requirements.txt`
- Run tests: `pytest`
- Lint: `ruff check .`
- Format: `ruff format .`

## Working rules
- Prefer minimal, targeted changes.
- Do not add dependencies unless clearly necessary.
- Ask before changing schema, external interfaces, or long-lived file layouts.
- Do not modify local secret files such as `.env` unless explicitly asked.
- If behavior changes, update or add focused tests when the repo has a test path for that area.

## Done when
- Relevant tests or checks have run.
- The changed behavior matches the request.
- The final summary includes changed files, verification, and remaining risks.

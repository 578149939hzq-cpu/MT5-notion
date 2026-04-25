# AGENTS.override.md

## Local rules
- This directory has stricter scope than the repo root instructions.
- Touch only files in this subtree unless the task explicitly requires a cross-cutting change.
- Prefer small, reversible edits.

## Local commands
- Run local tests for this area first: `pytest tests/<subdir>`

## Local constraints
- Do not change public interfaces from this subtree without explicit confirmation.
- Preserve existing naming and file organization patterns in this module.

## Done when
- Local tests for this subtree pass.
- The summary calls out any impacts outside this subtree.

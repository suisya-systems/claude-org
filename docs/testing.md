# Automated Tests

Execution guide for Python-based regression tests for the parser/converter and Bash-based regression tests for hooks.

## Scope

| Function | Description |
|------|------|
| `_parse_org_state` | Parse status, objective, and work items from `org-state.md` |
| `_parse_journal` | Parse the event log in `journal.jsonl` |
| `_parse_projects` | Parse the Markdown table in `projects.md` |
| `_parse_workers` | Parse the `worker-*.md` files |
| `_parse_knowledge` | Count H2 sections in `curated/*.md` |
| `org_state_converter.py` | Convert `org-state` Markdown to JSON and load dashboard JSON |
| `.hooks/*.sh` | Regression checks for worker boundary / claude-org structure / git push blocking |

## How to Run

```bash
# Python tests
# Windows (use `python` if `py -3` is not available)
python -m unittest discover -s tests -v

# Mac / Linux
python3 -m unittest discover -s tests -v

# Shell hook tests
bash tests/run-all.sh
```

Run these from the project root. No external libraries are required, but the shell hook tests require `bash` and `jq`.

In day-to-day use, do not treat Python tests alone as sufficient. Require `bash tests/run-all.sh` to pass as well.

## Test Layout

```
tests/
  __init__.py              # Package initialization (empty)
  test_parsers.py          # Parser tests for dashboard/server.py
  test_org_state_converter.py
  run-all.sh               # Shell hook test runner
  test-block-git-push.sh
  test-block-org-structure.sh
  test-check-worker-boundary.sh
  fixtures/
    org-state-sample.md    # Sample for the org-state parser
    journal-sample.jsonl   # Sample for the journal parser
    projects-sample.md     # Sample for the projects parser
    workers/
      worker-abc12345.md   # Sample for the workers parser
    curated/
      .gitkeep             # Used to verify skip behavior
      sample-topic.md      # Sample for the knowledge parser
```

## Storing Test Results

If you need to record test results, save them under `docs/test-results/`.

## CI

GitHub Actions runs the same two test suites. Run both locally before opening a PR to reduce failures that do not reproduce locally.
---
